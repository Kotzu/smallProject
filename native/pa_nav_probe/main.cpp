#include "pathfind/pathfind_c_bindings.hpp"
#include "Common.hpp"
#include "height_scan.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr int kMaxPathHops = 4096;
constexpr float kPi = 3.14159265358979323846f;
constexpr float kObstacleProbeHeight = 1.20f;
// Small props can have a wide solid pedestal below the normal shoulder-height
// ray.  The low ray is preference-only: it may choose a wider outdoor detour,
// but can never invalidate a proven capsule-clear WMO corridor.
constexpr float kPreferredLowObstacleProbeHeight = 0.35f;
constexpr unsigned char kRoadGroundArea = 1;
constexpr unsigned char kSteepGroundArea = 10;
constexpr unsigned char kDoodadTraversalArea = 11;
constexpr float kDoodadTraversalCost = 8.0f;
// Every traversability decision below probes the full steering tunnel: the
// actor capsule plus the controller's bounded cross-track tolerance.  Keep the
// same effective planning budget as the former 256 centre-ray checks while
// accounting for five bounded LOS calls across that width.
constexpr int kMaxDoodadLineProbes = 1280;
constexpr int kMaxDoodadBlockerDiscoveryProbes = 512;
constexpr int kMaxMovementPathSimplificationProbes = 2560;
constexpr std::size_t kMaxReportedDoodadBlockers = 8;
constexpr float kDirectTopologyRepairStep = 0.75f;
constexpr float kMaxDirectTopologyRepairDistance = 35.0f;
constexpr float kTopologyGapInflationRatio = 2.0f;
constexpr float kTopologyGapInflationAllowance = 12.0f;
// A physical topology-gap proof must use the same slope envelope that baked
// the standalone WorldPack.  A second, stricter magic angle rejected terrain
// that the client-derived mesh itself classifies as walkable and turned a
// 12-yard road continuation into a map-scale Detour loop.  Ground, low-ray
// and full capsule-tunnel probes below remain mandatory, so this does not
// authorize a chord through a cliff, wall or prop.
const float kMaximumWalkableSlopeRatio =
    std::tan(MeshSettings::WalkableSlope * kPi / 180.0f);
// TBC exposes the standard player/world-object bounding radius as 0.389 yd.
// Keep a separate bounded steering margin instead of treating cross-track
// look-ahead as physical body width; the former 1.67 yd tunnel made normal
// road props look several times larger than the actor.
constexpr float kPlayerCapsuleProbeRadius = 0.389f;
constexpr float kControllerCrossTrackTolerance = 0.30f;
constexpr float kMovementTunnelRadius =
    kPlayerCapsuleProbeRadius + kControllerCrossTrackTolerance;
constexpr float kPreferredStaticClearanceMargin = 0.30f;
constexpr int kMaxPreferredClearanceProbes = 512;
// The extracted navmesh is valid for a point.  WoW's player capsule has a
// shoulder radius, so Detour's shortest funnel can legally touch a portal
// endpoint while the visible actor collides with the wall (and the camera is
// forced into it).  Inset only actual funnel corners along their shared portal;
// this retains Detour topology without reverting to every-portal midpoints.
constexpr float kPlayerPortalInset = 0.90f;
constexpr float kPortalEndpointMatch = 0.18f;
constexpr float kMinimumInsetPortalWidth = 2.0f;
constexpr float kWideGroundPortalClearance = 6.0f;
constexpr float kSearchVantageRadius = 8.0f;
constexpr float kSearchVantageOverheadHeight = 12.0f;
constexpr int kSearchVantageRadialProbeCount = 16;
constexpr float kLocalAwarenessRadius = 12.0f;
constexpr int kLocalAwarenessRadialProbeCount = 16;
constexpr int kLocalAwarenessBinarySearchIterations = 7;
constexpr float kLocalTopologyRadius = 60.0f;
constexpr std::size_t kMaxLocalTopologyPolygons = 2048;
constexpr std::size_t kMaxLocalWallSegments = 128;
constexpr std::size_t kMaxLocalSurfaceTransitionPortals = 64;
constexpr std::size_t kMaxLocalEgressPortals = 32;
constexpr std::size_t kMaxLocalOverheadSamples = 512;
constexpr int kMaxLocalEgressPathPolygons = 2048;
constexpr std::size_t kMaxLocalOpenContinuationPolygons = 128;
constexpr float kLocalEgressOpenDepth = 4.0f;
constexpr float kLocalEgressOpenSearchRadius = 12.0f;

struct SearchVantageMetrics {
    int radial_clear_count = 0;
    bool overhead_clear = false;
};

struct LocalRadialProbe {
    float bearing_rad = 0.0f;
    float clearance_yards = 0.0f;
    bool navmesh_reachable = false;
};

struct LocalAwarenessMetrics {
    std::array<LocalRadialProbe, kLocalAwarenessRadialProbeCount> radial_probes {};
    bool overhead_clear = false;
};

struct LocalWallSegment {
    std::array<float, 3> left {};
    std::array<float, 3> right {};
    float distance_yards = 0.0f;
};

struct LocalSurfaceTransitionPortal {
    std::array<float, 3> left {};
    std::array<float, 3> right {};
    float width_yards = 0.0f;
    float distance_yards = 0.0f;
    unsigned short from_flags = 0;
    unsigned short to_flags = 0;
};

struct LocalTopologicalEgressPortal {
    std::array<float, 3> left {};
    std::array<float, 3> right {};
    float width_yards = 0.0f;
    float distance_yards = 0.0f;
    float route_distance_yards = 0.0f;
    unsigned short from_flags = 0;
    unsigned short to_flags = 0;
};

struct PolygonOverheadSample {
    dtPolyRef polygon_ref = 0;
    bool overhead_clear = false;
};

struct LocalTopologyMetrics {
    std::vector<LocalWallSegment> wall_segments;
    std::vector<LocalSurfaceTransitionPortal> surface_transition_portals;
    std::vector<LocalTopologicalEgressPortal> egress_portals;
    int component_polygon_count = 0;
    bool component_truncated = false;
    bool wall_segments_truncated = false;
    bool surface_transition_portals_truncated = false;
    bool egress_inference_complete = true;
    bool egress_portals_truncated = false;
};

float parse_float(const char* value, const char* name) {
    char* end = nullptr;
    const float result = std::strtof(value, &end);
    if (end == value || *end != '\0')
        throw std::invalid_argument(std::string("invalid ") + name);
    return result;
}

void require_success(PathfindResultType result, const char* operation) {
    if (result != 0)
        throw std::runtime_error(
            std::string(operation) + " failed with result " + std::to_string(result));
}

void require_detour(dtStatus status, const char* operation) {
    if (dtStatusFailed(status))
        throw std::runtime_error(std::string(operation) + " failed");
}

std::array<float, 3> to_recast(float x, float y, float z) {
    return {-y, z, -x};
}

std::array<float, 3> to_wow(const float* point) {
    return {-point[2], -point[0], point[1]};
}

void print_point(const std::array<float, 3>& point) {
    std::cout << '[' << point[0] << ',' << point[1] << ',' << point[2] << ']';
}

void print_physical_surfaces(unsigned short flags) {
    std::cout << '[';
    bool wrote_surface = false;
    const auto write_surface = [&wrote_surface](const char* name) {
        if (wrote_surface)
            std::cout << ',';
        std::cout << '\"' << name << '\"';
        wrote_surface = true;
    };
    if (flags & PolyFlags::Ground)
        write_surface("ground");
    if (flags & PolyFlags::Wmo)
        write_surface("wmo");
    if (flags & PolyFlags::Doodad)
        write_surface("doodad");
    std::cout << ']';
}

bool single_doodad_line_clear_at_height(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    float height,
    int& line_probes_remaining) {
    if (line_probes_remaining <= 0)
        return false;
    --line_probes_remaining;
    std::uint8_t clear = 0;
    require_success(
        pathfind_line_of_sight(
            map,
            start[0], start[1], start[2] + height,
            stop[0], stop[1], stop[2] + height,
            &clear, 1),
        "doodad_line_of_sight");
    return clear != 0;
}

bool doodad_capsule_clear_at_height(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    float height,
    int& line_probes_remaining) {
    const float dx = stop[0] - start[0];
    const float dy = stop[1] - start[1];
    const float length = std::sqrt(dx * dx + dy * dy);
    if (length < 0.01f)
        return true;

    const float perpendicular_x = -dy / length;
    const float perpendicular_y = dx / length;
    constexpr float offsets[] = {
        0.0f,
        kMovementTunnelRadius * 0.5f,
        -kMovementTunnelRadius * 0.5f,
        kMovementTunnelRadius,
        -kMovementTunnelRadius,
    };
    for (const float offset : offsets) {
        const std::array<float, 3> ray_start {
            start[0] + perpendicular_x * offset,
            start[1] + perpendicular_y * offset,
            start[2],
        };
        const std::array<float, 3> ray_stop {
            stop[0] + perpendicular_x * offset,
            stop[1] + perpendicular_y * offset,
            stop[2],
        };
        if (!single_doodad_line_clear_at_height(
                map, ray_start, ray_stop, height,
                line_probes_remaining))
            return false;
    }
    return true;
}

bool doodad_capsule_clear(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    int& line_probes_remaining) {
    return doodad_capsule_clear_at_height(
        map, start, stop, kObstacleProbeHeight, line_probes_remaining);
}

bool doodad_outer_clear(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    int& line_probes_remaining) {
    const float dx = stop[0] - start[0];
    const float dy = stop[1] - start[1];
    const float length = std::sqrt(dx * dx + dy * dy);
    if (length < 0.01f)
        return true;
    const float perpendicular_x = -dy / length;
    const float perpendicular_y = dx / length;
    constexpr float preferred_radius =
        kMovementTunnelRadius + kPreferredStaticClearanceMargin;
    for (const float offset : {preferred_radius, -preferred_radius}) {
        const std::array<float, 3> ray_start {
            start[0] + perpendicular_x * offset,
            start[1] + perpendicular_y * offset,
            start[2],
        };
        const std::array<float, 3> ray_stop {
            stop[0] + perpendicular_x * offset,
            stop[1] + perpendicular_y * offset,
            stop[2],
        };
        if (!single_doodad_line_clear_at_height(
                map, ray_start, ray_stop, kObstacleProbeHeight,
                line_probes_remaining))
            return false;
    }
    return true;
}

bool doodad_path_has_preferred_clearance(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& candidate,
    const std::vector<std::array<float, 3>>& continuation,
    int& line_probes_remaining) {
    if (!doodad_outer_clear(map, start, candidate, line_probes_remaining)
        || !doodad_capsule_clear_at_height(
            map, start, candidate, kPreferredLowObstacleProbeHeight,
            line_probes_remaining))
        return false;
    auto previous = candidate;
    for (const auto& point : continuation) {
        if (!doodad_outer_clear(map, previous, point, line_probes_remaining)
            || !doodad_capsule_clear_at_height(
                map, previous, point, kPreferredLowObstacleProbeHeight,
                line_probes_remaining))
            return false;
        previous = point;
    }
    return true;
}

SearchVantageMetrics measure_search_vantage(
    pathfind::Map* map,
    const std::array<float, 3>& stop) {
    SearchVantageMetrics result;
    int radial_probes_remaining = kSearchVantageRadialProbeCount;
    for (int index = 0; index < kSearchVantageRadialProbeCount; ++index) {
        const float angle = 2.0f * kPi * static_cast<float>(index)
            / static_cast<float>(kSearchVantageRadialProbeCount);
        const std::array<float, 3> radial_stop {
            stop[0] + std::cos(angle) * kSearchVantageRadius,
            stop[1] + std::sin(angle) * kSearchVantageRadius,
            stop[2],
        };
        if (single_doodad_line_clear_at_height(
                map, stop, radial_stop, kObstacleProbeHeight,
                radial_probes_remaining))
            ++result.radial_clear_count;
    }

    std::uint8_t overhead_clear = 0;
    require_success(
        pathfind_line_of_sight(
            map,
            stop[0], stop[1], stop[2] + kObstacleProbeHeight,
            stop[0], stop[1], stop[2] + kSearchVantageOverheadHeight,
            &overhead_clear, 1),
        "search_vantage_overhead_line_of_sight");
    result.overhead_clear = overhead_clear != 0;
    return result;
}

LocalAwarenessMetrics measure_local_awareness(
    pathfind::Map* map,
    const dtNavMeshQuery& query,
    const dtQueryFilter& filter,
    dtPolyRef start_ref,
    const std::array<float, 3>& recast_start,
    const std::array<float, 3>& origin) {
    LocalAwarenessMetrics result;
    int line_probes_remaining = kLocalAwarenessRadialProbeCount
        * (1 + kLocalAwarenessBinarySearchIterations);
    for (int index = 0; index < kLocalAwarenessRadialProbeCount; ++index) {
        const float bearing = 2.0f * kPi * static_cast<float>(index)
            / static_cast<float>(kLocalAwarenessRadialProbeCount);
        const auto point_at = [&origin, bearing](float distance) {
            return std::array<float, 3> {
                origin[0] + std::cos(bearing) * distance,
                origin[1] + std::sin(bearing) * distance,
                origin[2],
            };
        };
        float lower = 0.0f;
        float upper = kLocalAwarenessRadius;
        const auto radial_stop = point_at(kLocalAwarenessRadius);
        if (single_doodad_line_clear_at_height(
                map, origin, radial_stop, kObstacleProbeHeight,
                line_probes_remaining)) {
            lower = kLocalAwarenessRadius;
        } else {
            for (int iteration = 0;
                 iteration < kLocalAwarenessBinarySearchIterations;
                 ++iteration) {
                const float midpoint = (lower + upper) * 0.5f;
                const auto midpoint_stop = point_at(midpoint);
                if (single_doodad_line_clear_at_height(
                        map, origin, midpoint_stop, kObstacleProbeHeight,
                        line_probes_remaining))
                    lower = midpoint;
                else
                    upper = midpoint;
            }
        }
        bool navmesh_reachable = false;
        if (lower >= kLocalAwarenessRadius * 0.95f) {
            const auto recast_stop = to_recast(
                radial_stop[0], radial_stop[1], radial_stop[2]);
            float hit_fraction = 0.0f;
            std::array<float, 3> hit_normal {};
            std::array<dtPolyRef, 64> visited {};
            int visited_count = 0;
            require_detour(
                query.raycast(
                    start_ref, recast_start.data(), recast_stop.data(), &filter,
                    &hit_fraction, hit_normal.data(), visited.data(),
                    &visited_count, static_cast<int>(visited.size())),
                "local_awareness_navmesh_raycast");
            navmesh_reachable = hit_fraction >= 1.0f;
        }
        result.radial_probes[index] = {
            bearing, lower, navmesh_reachable,
        };
    }

    std::uint8_t overhead_clear = 0;
    require_success(
        pathfind_line_of_sight(
            map,
            origin[0], origin[1], origin[2] + kObstacleProbeHeight,
            origin[0], origin[1], origin[2] + kSearchVantageOverheadHeight,
            &overhead_clear, 1),
        "local_awareness_overhead_line_of_sight");
    result.overhead_clear = overhead_clear != 0;
    return result;
}

bool ground_candidate(
    pathfind::Map* map,
    const std::array<float, 3>& origin,
    float x,
    float y,
    std::array<float, 3>& candidate) {
    // FindHeight asks for a path from origin to candidate.  That is circular
    // here: the whole purpose of this point is to route around the obstacle
    // that makes the direct path fail.  Slice the already loaded client map at
    // the candidate instead and stay on the vertical layer nearest the actor.
    std::array<float, 64> heights {};
    unsigned int height_count = 0;
    const auto result = pathfind_find_heights(
        map, x, y, heights.data(), static_cast<unsigned int>(heights.size()),
        &height_count);
    if (result != 0 || height_count == 0) {
        if (std::getenv("PA_NAV_DEBUG") != nullptr)
            std::cerr << "ground rejected=query result=" << result
                      << " origin=" << origin[0] << ',' << origin[1] << ',' << origin[2]
                      << " xy=" << x << ',' << y << " count=" << height_count << '\n';
        return false;
    }
    float z = heights[0];
    float best_delta = std::abs(z - origin[2]);
    for (unsigned int index = 1; index < height_count; ++index) {
        const float delta = std::abs(heights[index] - origin[2]);
        if (delta < best_delta) {
            z = heights[index];
            best_delta = delta;
        }
    }
    if (!std::isfinite(z))
        return false;
    candidate = {x, y, z};
    const float horizontal = std::sqrt(
        (candidate[0] - origin[0]) * (candidate[0] - origin[0]) +
        (candidate[1] - origin[1]) * (candidate[1] - origin[1]));
    // A nearest-height query can select another terrain layer on steep hills.
    // Reject any local detour that a ground character could not traverse.
    if (
        horizontal < 0.25f
        || std::abs(candidate[2] - origin[2])
            > horizontal * kMaximumWalkableSlopeRatio
    ) {
        if (std::getenv("PA_NAV_DEBUG") != nullptr)
            std::cerr << "ground rejected=slope origin=" << origin[0] << ',' << origin[1]
                      << ',' << origin[2] << " candidate=" << candidate[0] << ','
                      << candidate[1] << ',' << candidate[2] << " horizontal="
                      << horizontal << " dz=" << std::abs(candidate[2] - origin[2]) << '\n';
        return false;
    }
    return true;
}

float polyline_length_2d(
    const std::vector<std::array<float, 3>>& points) {
    float result = 0.0f;
    for (std::size_t index = 0; index + 1 < points.size(); ++index)
        result += std::hypot(
            points[index][0] - points[index + 1][0],
            points[index][1] - points[index + 1][1]);
    return result;
}

bool prove_direct_ground_shortcut(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    std::vector<std::array<float, 3>>& proven_points,
    int& line_probes_remaining) {
    const float direct_distance = std::hypot(
        start[0] - stop[0], start[1] - stop[1]);
    if (
        direct_distance < 1.0f
        || direct_distance > kMaxDirectTopologyRepairDistance
    )
        return false;
    const int sample_count = std::max(
        1, static_cast<int>(std::ceil(
            direct_distance / kDirectTopologyRepairStep)));
    std::vector<std::array<float, 3>> samples;
    samples.reserve(static_cast<std::size_t>(sample_count) + 1);
    samples.push_back(start);
    auto previous = start;
    for (int index = 1; index <= sample_count; ++index) {
        const float fraction = static_cast<float>(index)
            / static_cast<float>(sample_count);
        std::array<float, 3> candidate {};
        if (!ground_candidate(
                map, previous,
                start[0] + (stop[0] - start[0]) * fraction,
                start[1] + (stop[1] - start[1]) * fraction,
                candidate))
            return false;
        if (
            index == sample_count
            && std::abs(candidate[2] - stop[2]) > 0.75f
        )
            return false;
        if (
            !doodad_capsule_clear(
                map, previous, candidate, line_probes_remaining)
            || !doodad_capsule_clear_at_height(
                map, previous, candidate, kPreferredLowObstacleProbeHeight,
                line_probes_remaining)
        )
            return false;
        samples.push_back(candidate);
        previous = candidate;
    }
    samples.back() = stop;
    proven_points = std::move(samples);
    return true;
}

int simplify_proven_movement_path(
    pathfind::Map* map,
    std::vector<std::array<float, 3>>& points,
    int& line_probes_remaining) {
    // Per-segment avoidance can otherwise alternate around a prop and create
    // a valid but visibly drunken loop.  Remove reversals only when the whole
    // replacement chord is independently proven on the same client-derived
    // surface, slope envelope, low obstacle ray and full movement tunnel.
    // No map coordinates or object identities participate in this decision.
    if (points.size() < 3 || line_probes_remaining <= 0)
        return 0;

    std::vector<std::array<float, 3>> simplified;
    simplified.reserve(points.size());
    simplified.push_back(points.front());
    std::size_t source_index = 0;
    int removed_points = 0;
    while (source_index + 1 < points.size()) {
        std::size_t chosen_index = source_index + 1;
        std::vector<std::array<float, 3>> chosen_proof;
        for (std::size_t candidate_index = points.size() - 1;
             candidate_index > source_index + 1;
             --candidate_index) {
            std::vector<std::array<float, 3>> proof;
            if (!prove_direct_ground_shortcut(
                    map, points[source_index], points[candidate_index], proof,
                    line_probes_remaining))
                continue;
            chosen_index = candidate_index;
            chosen_proof = std::move(proof);
            break;
        }
        if (chosen_index > source_index + 1) {
            simplified.insert(
                simplified.end(), chosen_proof.begin() + 1,
                chosen_proof.end());
            removed_points += static_cast<int>(
                chosen_index - source_index - 1);
        } else {
            simplified.push_back(points[chosen_index]);
        }
        source_index = chosen_index;
    }
    points = std::move(simplified);
    return removed_points;
}

bool append_doodad_aware_segment(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    std::vector<std::array<float, 3>>& output,
    int depth,
    int& detour_count,
    int& line_probes_remaining) {
    if (line_probes_remaining <= 0)
        return false;
    if (doodad_capsule_clear(map, start, stop, line_probes_remaining)) {
        output.push_back(stop);
        return true;
    }
    if (depth >= 10)
        return false;
    const float dx = stop[0] - start[0];
    const float dy = stop[1] - start[1];
    const float length = std::sqrt(dx * dx + dy * dy);
    if (length < 0.5f)
        return false;

    float low = 0.0f;
    float high = 1.0f;
    for (int iteration = 0; iteration < 10; ++iteration) {
        const float fraction = (low + high) * 0.5f;
        const std::array<float, 3> probe {
            start[0] + dx * fraction,
            start[1] + dy * fraction,
            start[2] + (stop[2] - start[2]) * fraction,
        };
        if (doodad_capsule_clear(map, start, probe, line_probes_remaining))
            low = fraction;
        else
            high = fraction;
    }

    const float forward_fraction = std::min(0.92f, high + 3.0f / length);
    const float base_x = start[0] + dx * forward_fraction;
    const float base_y = start[1] + dy * forward_fraction;
    const float perpendicular_x = -dy / length;
    const float perpendicular_y = dx / length;
    constexpr float offsets[] = {2.5f, -2.5f, 4.5f, -4.5f, 7.0f, -7.0f, 10.0f, -10.0f};
    bool preferred_available = false;
    float preferred_cost = std::numeric_limits<float>::infinity();
    std::array<float, 3> preferred_candidate {};
    std::vector<std::array<float, 3>> preferred_continuation;
    int preferred_nested_detours = 0;
    bool fallback_available = false;
    float fallback_cost = std::numeric_limits<float>::infinity();
    std::array<float, 3> fallback_candidate {};
    std::vector<std::array<float, 3>> fallback_continuation;
    int fallback_nested_detours = 0;
    int preferred_clearance_probes_remaining = kMaxPreferredClearanceProbes;
    for (const float offset : offsets) {
        std::array<float, 3> candidate {};
        if (!ground_candidate(
                map, start,
                base_x + perpendicular_x * offset,
                base_y + perpendicular_y * offset,
                candidate)) {
            if (std::getenv("PA_NAV_DEBUG") != nullptr)
                std::cerr << "detour depth=" << depth << " offset=" << offset
                          << " rejected=ground_candidate\n";
            continue;
        }
        if (line_probes_remaining <= 0)
            return false;
        if (!doodad_capsule_clear(map, start, candidate, line_probes_remaining)) {
            if (std::getenv("PA_NAV_DEBUG") != nullptr)
                std::cerr << "detour depth=" << depth << " offset=" << offset
                          << " rejected=approach_los candidate=" << candidate[0]
                          << ',' << candidate[1] << ',' << candidate[2] << '\n';
            continue;
        }
        std::vector<std::array<float, 3>> continuation;
        int nested_detours = 0;
        if (!append_doodad_aware_segment(
                map, candidate, stop, continuation, depth + 1, nested_detours,
                line_probes_remaining)) {
            if (std::getenv("PA_NAV_DEBUG") != nullptr)
                std::cerr << "detour depth=" << depth << " offset=" << offset
                          << " rejected=continuation candidate=" << candidate[0]
                          << ',' << candidate[1] << ',' << candidate[2] << '\n';
            continue;
        }
        // Recursive legs are already bounded by the caller's candidate.  Keep
        // them first-fit so top-level left/right comparison cannot expand into
        // a combinatorial search or exhaust the deterministic probe budget.
        if (depth > 0) {
            output.push_back(candidate);
            output.insert(
                output.end(), continuation.begin(), continuation.end());
            detour_count += 1 + nested_detours;
            return true;
        }
        float candidate_cost = std::hypot(
            start[0] - candidate[0], start[1] - candidate[1]);
        auto previous_candidate = candidate;
        for (const auto& continuation_point : continuation) {
            candidate_cost += std::hypot(
                previous_candidate[0] - continuation_point[0],
                previous_candidate[1] - continuation_point[1]);
            previous_candidate = continuation_point;
        }
        if (
            depth == 0
            && !doodad_path_has_preferred_clearance(
                map, start, candidate, continuation,
                preferred_clearance_probes_remaining)
        ) {
            if (!fallback_available || candidate_cost < fallback_cost) {
                fallback_available = true;
                fallback_cost = candidate_cost;
                fallback_candidate = candidate;
                fallback_continuation = continuation;
                fallback_nested_detours = nested_detours;
            }
            if (std::getenv("PA_NAV_DEBUG") != nullptr)
                std::cerr << "detour depth=" << depth << " offset=" << offset
                          << " retained=capsule_clear_fallback"
                          << " candidate=" << candidate[0] << ',' << candidate[1]
                          << ',' << candidate[2] << '\n';
            continue;
        }
        if (!preferred_available || candidate_cost < preferred_cost) {
            preferred_available = true;
            preferred_cost = candidate_cost;
            preferred_candidate = candidate;
            preferred_continuation = continuation;
            preferred_nested_detours = nested_detours;
        }
    }
    if (preferred_available) {
        output.push_back(preferred_candidate);
        output.insert(
            output.end(), preferred_continuation.begin(),
            preferred_continuation.end());
        detour_count += 1 + preferred_nested_detours;
        return true;
    }
    if (fallback_available) {
        output.push_back(fallback_candidate);
        output.insert(
            output.end(), fallback_continuation.begin(),
            fallback_continuation.end());
        detour_count += 1 + fallback_nested_detours;
        return true;
    }
    return false;
}

bool locate_first_doodad_blocker(
    pathfind::Map* map,
    const std::array<float, 3>& start,
    const std::array<float, 3>& stop,
    std::array<float, 4>& blocker,
    int& line_probes_remaining) {
    const float dx = stop[0] - start[0];
    const float dy = stop[1] - start[1];
    if (std::hypot(dx, dy) < 0.05f)
        return false;
    if (doodad_capsule_clear(map, start, stop, line_probes_remaining))
        return false;
    float low = 0.0f;
    float high = 1.0f;
    for (int iteration = 0; iteration < 10; ++iteration) {
        const float fraction = (low + high) * 0.5f;
        const std::array<float, 3> probe {
            start[0] + dx * fraction,
            start[1] + dy * fraction,
            start[2] + (stop[2] - start[2]) * fraction,
        };
        if (doodad_capsule_clear(map, start, probe, line_probes_remaining))
            low = fraction;
        else
            high = fraction;
    }
    blocker = {
        start[0] + dx * high,
        start[1] + dy * high,
        start[2] + (stop[2] - start[2]) * high,
        1.5f,
    };
    return true;
}

float polygon_slope_degrees(const dtMeshTile* tile, const dtPoly* poly) {
    if (poly->vertCount < 3)
        return 0.0f;
    const float* a = &tile->verts[poly->verts[0] * 3];
    float largest_triangle_squared_area = 0.0f;
    float slope_degrees = 0.0f;
    for (int index = 1; index + 1 < poly->vertCount; ++index) {
        const float* b = &tile->verts[poly->verts[index] * 3];
        const float* c = &tile->verts[poly->verts[index + 1] * 3];
        const float ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
        const float vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
        const float nx = uy * vz - uz * vy;
        const float ny = uz * vx - ux * vz;
        const float nz = ux * vy - uy * vx;
        const float squared_area = nx * nx + ny * ny + nz * nz;
        if (squared_area > largest_triangle_squared_area) {
            largest_triangle_squared_area = squared_area;
            slope_degrees =
                std::atan2(std::sqrt(nx * nx + nz * nz), std::abs(ny)) *
                180.0f / kPi;
        }
    }
    return slope_degrees;
}

std::array<float, 3> polygon_centroid_wow(const dtMeshTile* tile, const dtPoly* poly) {
    std::array<float, 3> centroid {};
    for (int index = 0; index < poly->vertCount; ++index) {
        const auto point = to_wow(&tile->verts[poly->verts[index] * 3]);
        centroid[0] += point[0];
        centroid[1] += point[1];
        centroid[2] += point[2];
    }
    for (float& value : centroid)
        value /= poly->vertCount;
    return centroid;
}

bool try_polygon_overhead_clear(
    pathfind::Map* map,
    const dtNavMesh& navmesh,
    dtPolyRef polygon_ref,
    std::vector<PolygonOverheadSample>& samples,
    bool& overhead_clear) {
    const auto existing = std::find_if(
        samples.begin(), samples.end(),
        [polygon_ref](const PolygonOverheadSample& sample) {
            return sample.polygon_ref == polygon_ref;
        });
    if (existing != samples.end()) {
        overhead_clear = existing->overhead_clear;
        return true;
    }
    if (samples.size() >= kMaxLocalOverheadSamples)
        return false;

    const dtMeshTile* tile = nullptr;
    const dtPoly* poly = nullptr;
    require_detour(
        navmesh.getTileAndPolyByRef(polygon_ref, &tile, &poly),
        "get_local_overhead_polygon");
    const auto centroid = polygon_centroid_wow(tile, poly);
    std::uint8_t clear = 0;
    require_success(
        pathfind_line_of_sight(
            map,
            centroid[0], centroid[1], centroid[2] + kObstacleProbeHeight,
            centroid[0], centroid[1],
            centroid[2] + kSearchVantageOverheadHeight,
            &clear, 1),
        "local_topology_overhead_line_of_sight");
    overhead_clear = clear != 0;
    samples.push_back({polygon_ref, overhead_clear});
    return true;
}

bool try_route_distance_to_polygon(
    const dtNavMeshQuery& query,
    const dtQueryFilter& filter,
    dtPolyRef start_ref,
    const std::array<float, 3>& recast_start,
    dtPolyRef stop_ref,
    const std::array<float, 3>& recast_stop,
    float& route_distance_yards) {
    std::array<dtPolyRef, kMaxLocalEgressPathPolygons> path_refs {};
    int path_count = 0;
    const dtStatus path_status = query.findPath(
        start_ref, stop_ref, recast_start.data(), recast_stop.data(), &filter,
        path_refs.data(), &path_count,
        static_cast<int>(path_refs.size()));
    if (
        dtStatusFailed(path_status) || path_count <= 0
        || path_refs[path_count - 1] != stop_ref)
        return false;

    std::array<float, kMaxLocalEgressPathPolygons * 3> straight_points {};
    std::array<unsigned char, kMaxLocalEgressPathPolygons> straight_flags {};
    std::array<dtPolyRef, kMaxLocalEgressPathPolygons> straight_refs {};
    int straight_count = 0;
    const dtStatus straight_status = query.findStraightPath(
        recast_start.data(), recast_stop.data(), path_refs.data(), path_count,
        straight_points.data(), straight_flags.data(), straight_refs.data(),
        &straight_count, static_cast<int>(straight_refs.size()));
    if (dtStatusFailed(straight_status) || straight_count <= 0)
        return false;

    route_distance_yards = 0.0f;
    for (int index = 1; index < straight_count; ++index) {
        const float* previous = &straight_points[(index - 1) * 3];
        const float* current = &straight_points[index * 3];
        const float dx = current[0] - previous[0];
        const float dy = current[1] - previous[1];
        const float dz = current[2] - previous[2];
        route_distance_yards += std::sqrt(dx * dx + dy * dy + dz * dz);
    }
    return true;
}

bool has_sustained_open_continuation(
    pathfind::Map* map,
    const dtNavMesh& navmesh,
    const dtNavMeshQuery& query,
    const dtQueryFilter& filter,
    dtPolyRef open_ref,
    const std::array<float, 3>& portal_midpoint,
    std::vector<PolygonOverheadSample>& overhead_samples,
    bool& inference_complete) {
    std::vector<dtPolyRef> frontier {open_ref};
    std::size_t cursor = 0;
    while (cursor < frontier.size()) {
        const dtPolyRef current_ref = frontier[cursor++];
        const dtMeshTile* tile = nullptr;
        const dtPoly* poly = nullptr;
        require_detour(
            navmesh.getTileAndPolyByRef(current_ref, &tile, &poly),
            "get_local_open_continuation_polygon");
        bool overhead_clear = false;
        if (!try_polygon_overhead_clear(
                map, navmesh, current_ref, overhead_samples,
                overhead_clear)) {
            inference_complete = false;
            return false;
        }
        if (!overhead_clear)
            continue;
        const auto centroid = polygon_centroid_wow(tile, poly);
        const float distance = std::hypot(
            centroid[0] - portal_midpoint[0],
            centroid[1] - portal_midpoint[1]);
        if (distance >= kLocalEgressOpenDepth)
            return true;
        if (distance > kLocalEgressOpenSearchRadius)
            continue;

        std::array<float, 32 * 6> segments {};
        std::array<dtPolyRef, 32> segment_refs {};
        int segment_count = 0;
        require_detour(
            query.getPolyWallSegments(
                current_ref, &filter, segments.data(), segment_refs.data(),
                &segment_count, static_cast<int>(segment_refs.size())),
            "get_local_open_continuation_segments");
        for (int index = 0; index < segment_count; ++index) {
            const dtPolyRef neighbor_ref = segment_refs[index];
            if (
                !neighbor_ref
                || std::find(frontier.begin(), frontier.end(), neighbor_ref)
                    != frontier.end())
                continue;
            bool neighbor_overhead_clear = false;
            if (!try_polygon_overhead_clear(
                    map, navmesh, neighbor_ref, overhead_samples,
                    neighbor_overhead_clear)) {
                inference_complete = false;
                return false;
            }
            if (!neighbor_overhead_clear)
                continue;
            if (frontier.size() >= kMaxLocalOpenContinuationPolygons) {
                inference_complete = false;
                return false;
            }
            frontier.push_back(neighbor_ref);
        }
    }
    return false;
}

LocalTopologyMetrics measure_local_topology(
    pathfind::Map* map,
    const dtNavMesh& navmesh,
    const dtNavMeshQuery& query,
    const dtQueryFilter& filter,
    dtPolyRef start_ref,
    const std::array<float, 3>& recast_start,
    bool start_overhead_clear,
    const std::array<float, 3>& origin) {
    LocalTopologyMetrics result;
    const dtMeshTile* start_tile = nullptr;
    const dtPoly* start_poly = nullptr;
    require_detour(
        navmesh.getTileAndPolyByRef(start_ref, &start_tile, &start_poly),
        "get_local_topology_start_polygon");
    if (!(start_poly->flags & PolyFlags::Wmo))
        return result;

    std::vector<dtPolyRef> frontier {start_ref};
    std::vector<PolygonOverheadSample> overhead_samples;
    overhead_samples.reserve(std::min(
        kMaxLocalOverheadSamples, kMaxLocalTopologyPolygons));
    std::size_t cursor = 0;
    while (cursor < frontier.size()) {
        const dtPolyRef current_ref = frontier[cursor++];
        const dtMeshTile* tile = nullptr;
        const dtPoly* poly = nullptr;
        require_detour(
            navmesh.getTileAndPolyByRef(current_ref, &tile, &poly),
            "get_local_topology_polygon");
        const auto centroid = polygon_centroid_wow(tile, poly);
        if (
            current_ref != start_ref
            && std::hypot(centroid[0] - origin[0], centroid[1] - origin[1])
                > kLocalTopologyRadius)
            continue;
        ++result.component_polygon_count;
        bool current_overhead_clear = start_overhead_clear;
        bool current_overhead_known = true;
        if (!start_overhead_clear) {
            current_overhead_known = try_polygon_overhead_clear(
                map, navmesh, current_ref, overhead_samples,
                current_overhead_clear);
            if (!current_overhead_known)
                result.egress_inference_complete = false;
        }

        std::array<float, 32 * 6> segments {};
        std::array<dtPolyRef, 32> segment_refs {};
        int segment_count = 0;
        require_detour(
            query.getPolyWallSegments(
                current_ref, &filter, segments.data(), segment_refs.data(),
                &segment_count, static_cast<int>(segment_refs.size())),
            "get_local_topology_segments");
        for (int segment_index = 0;
             segment_index < segment_count; ++segment_index) {
            const auto left = to_wow(&segments[segment_index * 6]);
            const auto right = to_wow(&segments[segment_index * 6 + 3]);
            const float midpoint_x = (left[0] + right[0]) * 0.5f;
            const float midpoint_y = (left[1] + right[1]) * 0.5f;
            const float distance = std::hypot(
                midpoint_x - origin[0], midpoint_y - origin[1]);
            if (distance > kLocalTopologyRadius)
                continue;

            const dtPolyRef neighbor_ref = segment_refs[segment_index];
            if (!neighbor_ref) {
                if (result.wall_segments.size() < kMaxLocalWallSegments)
                    result.wall_segments.push_back({left, right, distance});
                else
                    result.wall_segments_truncated = true;
                continue;
            }

            const dtMeshTile* neighbor_tile = nullptr;
            const dtPoly* neighbor_poly = nullptr;
            require_detour(
                navmesh.getTileAndPolyByRef(
                    neighbor_ref, &neighbor_tile, &neighbor_poly),
                "get_local_topology_neighbor");
            const float dx = right[0] - left[0];
            const float dy = right[1] - left[1];
            const float dz = right[2] - left[2];
            const float width = std::sqrt(dx * dx + dy * dy + dz * dz);

            if (
                !start_overhead_clear && current_overhead_known
                && !current_overhead_clear) {
                bool neighbor_overhead_clear = false;
                if (!try_polygon_overhead_clear(
                        map, navmesh, neighbor_ref, overhead_samples,
                        neighbor_overhead_clear)) {
                    result.egress_inference_complete = false;
                } else if (neighbor_overhead_clear) {
                    const std::array<float, 3> portal_midpoint {
                        midpoint_x, midpoint_y,
                        (left[2] + right[2]) * 0.5f,
                    };
                    bool continuation_inference_complete = true;
                    const bool sustained_open_continuation =
                        has_sustained_open_continuation(
                            map, navmesh, query, filter, neighbor_ref,
                            portal_midpoint, overhead_samples,
                            continuation_inference_complete);
                    if (!continuation_inference_complete)
                        result.egress_inference_complete = false;
                    const bool duplicate_egress = std::any_of(
                        result.egress_portals.begin(),
                        result.egress_portals.end(),
                        [midpoint_x, midpoint_y](
                            const LocalTopologicalEgressPortal& existing) {
                            const float existing_x =
                                (existing.left[0] + existing.right[0]) * 0.5f;
                            const float existing_y =
                                (existing.left[1] + existing.right[1]) * 0.5f;
                            return std::hypot(
                                existing_x - midpoint_x,
                                existing_y - midpoint_y) < 0.10f;
                        });
                    if (sustained_open_continuation && !duplicate_egress) {
                        const auto neighbor_centroid =
                            polygon_centroid_wow(neighbor_tile, neighbor_poly);
                        const auto recast_neighbor = to_recast(
                            neighbor_centroid[0], neighbor_centroid[1],
                            neighbor_centroid[2]);
                        float route_distance = 0.0f;
                        if (!try_route_distance_to_polygon(
                                query, filter, start_ref, recast_start,
                                neighbor_ref, recast_neighbor,
                                route_distance)) {
                            result.egress_inference_complete = false;
                        } else if (
                            result.egress_portals.size()
                            < kMaxLocalEgressPortals) {
                            result.egress_portals.push_back({
                                left, right, width, distance, route_distance,
                                poly->flags, neighbor_poly->flags,
                            });
                        } else {
                            result.egress_portals_truncated = true;
                        }
                    }
                }
            }

            if (neighbor_poly->flags & PolyFlags::Wmo) {
                if (
                    std::find(frontier.begin(), frontier.end(), neighbor_ref)
                        == frontier.end()) {
                    if (frontier.size() < kMaxLocalTopologyPolygons)
                        frontier.push_back(neighbor_ref);
                    else {
                        result.component_truncated = true;
                        if (!start_overhead_clear)
                            result.egress_inference_complete = false;
                    }
                }
                continue;
            }

            const bool duplicate = std::any_of(
                result.surface_transition_portals.begin(),
                result.surface_transition_portals.end(),
                [midpoint_x, midpoint_y](
                    const LocalSurfaceTransitionPortal& existing) {
                    const float existing_x =
                        (existing.left[0] + existing.right[0]) * 0.5f;
                    const float existing_y =
                        (existing.left[1] + existing.right[1]) * 0.5f;
                    return std::hypot(
                        existing_x - midpoint_x,
                        existing_y - midpoint_y) < 0.10f;
                });
            if (!duplicate) {
                if (result.surface_transition_portals.size()
                    < kMaxLocalSurfaceTransitionPortals)
                    result.surface_transition_portals.push_back({
                        left, right, width, distance,
                        poly->flags, neighbor_poly->flags,
                    });
                else
                    result.surface_transition_portals_truncated = true;
            }
        }
    }
    std::sort(
        result.wall_segments.begin(), result.wall_segments.end(),
        [](const LocalWallSegment& left, const LocalWallSegment& right) {
            return left.distance_yards < right.distance_yards;
        });
    std::sort(
        result.surface_transition_portals.begin(),
        result.surface_transition_portals.end(),
        [](const LocalSurfaceTransitionPortal& left,
           const LocalSurfaceTransitionPortal& right) {
            return left.distance_yards < right.distance_yards;
        });
    std::sort(
        result.egress_portals.begin(), result.egress_portals.end(),
        [](const LocalTopologicalEgressPortal& left,
           const LocalTopologicalEgressPortal& right) {
            return left.route_distance_yards < right.route_distance_yards;
        });
    return result;
}

float point_segment_distance_squared(
    float px, float py, float ax, float ay, float bx, float by) {
    const float dx = bx - ax;
    const float dy = by - ay;
    const float length_squared = dx * dx + dy * dy;
    const float t = length_squared <= 1.0e-6f
        ? 0.0f
        : std::max(0.0f, std::min(
            1.0f, ((px - ax) * dx + (py - ay) * dy) / length_squared));
    const float nearest_x = ax + dx * t;
    const float nearest_y = ay + dy * t;
    const float offset_x = px - nearest_x;
    const float offset_y = py - nearest_y;
    return offset_x * offset_x + offset_y * offset_y;
}

bool polygon_overlaps_observed_blocker(
    const dtMeshTile* tile,
    const dtPoly* poly,
    const std::array<float, 4>& blocker) {
    std::array<std::array<float, 3>, DT_VERTS_PER_POLYGON> vertices {};
    float minimum_z = std::numeric_limits<float>::max();
    float maximum_z = std::numeric_limits<float>::lowest();
    for (int index = 0; index < poly->vertCount; ++index) {
        vertices[index] = to_wow(&tile->verts[poly->verts[index] * 3]);
        minimum_z = std::min(minimum_z, vertices[index][2]);
        maximum_z = std::max(maximum_z, vertices[index][2]);
    }
    const float vertical_tolerance = std::max(1.5f, blocker[3] * 0.75f);
    if (blocker[2] < minimum_z - vertical_tolerance
        || blocker[2] > maximum_z + vertical_tolerance)
        return false;

    bool inside = false;
    for (int current = 0, previous = poly->vertCount - 1;
         current < poly->vertCount; previous = current++) {
        const auto& a = vertices[current];
        const auto& b = vertices[previous];
        if (((a[1] > blocker[1]) != (b[1] > blocker[1]))
            && blocker[0] < (b[0] - a[0]) * (blocker[1] - a[1])
                / (b[1] - a[1]) + a[0])
            inside = !inside;
    }
    if (inside)
        return true;

    const float radius_squared = blocker[3] * blocker[3];
    for (int index = 0; index < poly->vertCount; ++index) {
        const auto& a = vertices[index];
        const auto& b = vertices[(index + 1) % poly->vertCount];
        if (point_segment_distance_squared(
                blocker[0], blocker[1], a[0], a[1], b[0], b[1])
            <= radius_squared)
            return true;
    }
    return false;
}

struct Portal {
    int from_index;
    int to_index;
    std::array<float, 3> left;
    std::array<float, 3> right;
    float width;
};

float distance_2d(
    const std::array<float, 3>& left,
    const std::array<float, 3>& right) {
    return std::hypot(left[0] - right[0], left[1] - right[1]);
}

int inset_funnel_corners(
    std::vector<std::array<float, 3>>& points,
    const std::vector<Portal>& portals) {
    if (points.size() < 3 || portals.empty())
        return 0;
    int adjusted = 0;
    for (std::size_t point_index = 1; point_index + 1 < points.size(); ++point_index) {
        const auto original = points[point_index];
        std::array<float, 3> accumulated {};
        int candidate_count = 0;
        bool exact_shared_corner = true;
        bool horizontal_portals = true;
        for (const auto& portal : portals) {
            if (portal.width < kMinimumInsetPortalWidth)
                continue;
            const bool at_left = distance_2d(original, portal.left) <= kPortalEndpointMatch;
            const bool at_right = distance_2d(original, portal.right) <= kPortalEndpointMatch;
            if (!at_left && !at_right)
                continue;
            const auto& endpoint = at_left ? portal.left : portal.right;
            const auto& opposite = at_left ? portal.right : portal.left;
            const float horizontal_width = distance_2d(endpoint, opposite);
            if (horizontal_width <= kPlayerPortalInset * 2.0f)
                continue;
            exact_shared_corner = exact_shared_corner
                && distance_2d(original, endpoint) <= 0.0001f
                && std::abs(original[2] - endpoint[2]) <= 0.0001f;
            horizontal_portals = horizontal_portals
                && std::abs(opposite[2] - endpoint[2]) <= 0.0001f;
            const float fraction = std::min(
                0.45f, kPlayerPortalInset / horizontal_width);
            for (int axis = 0; axis < 3; ++axis)
                accumulated[axis] += endpoint[axis]
                    + (opposite[axis] - endpoint[axis]) * fraction;
            ++candidate_count;
        }
        if (candidate_count == 0)
            continue;
        for (int axis = 0; axis < 3; ++axis)
            points[point_index][axis] = accumulated[axis] / candidate_count;
        // Averaging two portal offsets at the same corner shortens their
        // horizontal clearance (0.9 / sqrt(2) at a right angle). Preserve the
        // existing inset radius along the mean direction, not the contracted
        // mean length. Near-but-distinct corners and ambiguous opposing
        // directions retain the old behavior. Sloped portals also retain it:
        // extending XY alone would leave Z off their plane. Z stays unchanged;
        // this does not certify physical clearance or replace path validation.
        const float dx = points[point_index][0] - original[0];
        const float dy = points[point_index][1] - original[1];
        const float mean_radius = std::hypot(dx, dy);
        if (candidate_count > 1 && exact_shared_corner && horizontal_portals
            && mean_radius > 0.0001f && mean_radius < kPlayerPortalInset) {
            const float scale = kPlayerPortalInset / mean_radius;
            points[point_index][0] = original[0] + dx * scale;
            points[point_index][1] = original[1] + dy * scale;
        }
        ++adjusted;
    }
    return adjusted;
}

bool blocker_is_inset_wmo_portal_artifact(
    const std::array<float, 4>& blocker,
    const std::vector<Portal>& portals,
    const std::vector<dtPolyRef>& polygon_refs,
    const dtNavMesh& navmesh) {
    const std::array<float, 3> blocker_point {
        blocker[0], blocker[1], blocker[2],
    };
    for (const auto& portal : portals) {
        if (
            portal.width < kPlayerCapsuleProbeRadius * 2.0f
            || portal.from_index < 0
            || portal.to_index < 0
            || static_cast<std::size_t>(portal.to_index) >= polygon_refs.size()
        )
            continue;
        const auto endpoint_matches = [&blocker_point](
            const std::array<float, 3>& endpoint) {
            return distance_2d(blocker_point, endpoint) <= 1.75f
                && std::abs(blocker_point[2] - endpoint[2]) <= 2.75f;
        };
        if (!endpoint_matches(portal.left) && !endpoint_matches(portal.right))
            continue;
        const dtMeshTile* from_tile = nullptr;
        const dtPoly* from_poly = nullptr;
        const dtMeshTile* to_tile = nullptr;
        const dtPoly* to_poly = nullptr;
        if (
            dtStatusFailed(navmesh.getTileAndPolyByRef(
                polygon_refs[portal.from_index], &from_tile, &from_poly))
            || dtStatusFailed(navmesh.getTileAndPolyByRef(
                polygon_refs[portal.to_index], &to_tile, &to_poly))
        )
            continue;
        if (
            (from_poly->flags & PolyFlags::Wmo)
            && (to_poly->flags & PolyFlags::Wmo)
        )
            return true;
        if (
            portal.width >= kWideGroundPortalClearance
            && (from_poly->flags & PolyFlags::Ground)
            && (to_poly->flags & PolyFlags::Ground)
        )
            return true;
        if (std::getenv("PA_NAV_DEBUG") != nullptr)
            std::cerr << "portal_blocker_not_ignored blocker=" << blocker[0]
                      << ',' << blocker[1] << ',' << blocker[2]
                      << " portal=" << portal.from_index << "->"
                      << portal.to_index << " width=" << portal.width
                      << " flags=" << from_poly->flags << ','
                      << to_poly->flags << '\n';
    }
    return false;
}

Portal find_portal(
    const dtNavMeshQuery& query,
    const dtQueryFilter& filter,
    dtPolyRef from_ref,
    dtPolyRef to_ref,
    int from_index) {
    std::array<float, 16 * 6> segments {};
    std::array<dtPolyRef, 16> segment_refs {};
    int segment_count = 0;
    require_detour(
        query.getPolyWallSegments(
            from_ref, &filter, segments.data(), segment_refs.data(), &segment_count,
            static_cast<int>(segment_refs.size())),
        "get_poly_wall_segments");
    for (int index = 0; index < segment_count; ++index) {
        if (segment_refs[index] != to_ref)
            continue;
        const auto left = to_wow(&segments[index * 6]);
        const auto right = to_wow(&segments[index * 6 + 3]);
        const float dx = right[0] - left[0];
        const float dy = right[1] - left[1];
        const float dz = right[2] - left[2];
        return {from_index, from_index + 1, left, right,
                std::sqrt(dx * dx + dy * dy + dz * dz)};
    }
    throw std::runtime_error("corridor polygons have no traversable portal");
}

void print_server_segment(
    const std::array<float, 3>& left,
    const std::array<float, 3>& right) {
    std::cout << '[';
    print_point(left);
    std::cout << ',';
    print_point(right);
    std::cout << ']';
}

void print_local_awareness_json(
    unsigned short polygon_flags,
    const LocalAwarenessMetrics& awareness,
    const LocalTopologyMetrics& topology) {
    std::cout << "{\"physical_surfaces\":";
    print_physical_surfaces(polygon_flags);
    std::cout << ",\"probe_radius_yards\":" << kLocalAwarenessRadius
              << ",\"overhead_clear\":"
              << (awareness.overhead_clear ? "true" : "false")
              << ",\"radial_probes\":[";
    for (std::size_t index = 0; index < awareness.radial_probes.size(); ++index) {
        if (index != 0)
            std::cout << ',';
        const auto& probe = awareness.radial_probes[index];
        std::cout << "{\"bearing_rad\":" << probe.bearing_rad
                  << ",\"clearance_yards\":" << probe.clearance_yards
                  << ",\"navmesh_reachable\":"
                  << (probe.navmesh_reachable ? "true" : "false") << '}';
    }
    std::cout << "],\"topology_radius_yards\":" << kLocalTopologyRadius
              << ",\"component_polygon_count\":"
              << topology.component_polygon_count
              << ",\"component_truncated\":"
              << (topology.component_truncated ? "true" : "false")
              << ",\"wall_segments_truncated\":"
              << (topology.wall_segments_truncated ? "true" : "false")
              << ",\"surface_transition_portals_truncated\":"
              << (topology.surface_transition_portals_truncated ? "true" : "false")
              << ",\"egress_inference_complete\":"
              << (topology.egress_inference_complete ? "true" : "false")
              << ",\"egress_portals_truncated\":"
              << (topology.egress_portals_truncated ? "true" : "false")
              << ",\"wall_segments\":[";
    for (std::size_t index = 0; index < topology.wall_segments.size(); ++index) {
        if (index != 0)
            std::cout << ',';
        const auto& wall = topology.wall_segments[index];
        std::cout << "{\"left\":";
        print_point(wall.left);
        std::cout << ",\"right\":";
        print_point(wall.right);
        std::cout << ",\"distance_yards\":" << wall.distance_yards << '}';
    }
    std::cout << "],\"surface_transition_portals\":[";
    for (std::size_t index = 0;
         index < topology.surface_transition_portals.size(); ++index) {
        if (index != 0)
            std::cout << ',';
        const auto& portal = topology.surface_transition_portals[index];
        std::cout << "{\"left\":";
        print_point(portal.left);
        std::cout << ",\"right\":";
        print_point(portal.right);
        std::cout << ",\"width_yards\":" << portal.width_yards
                  << ",\"distance_yards\":" << portal.distance_yards
                  << ",\"from_surfaces\":";
        print_physical_surfaces(portal.from_flags);
        std::cout << ",\"to_surfaces\":";
        print_physical_surfaces(portal.to_flags);
        std::cout << '}';
    }
    std::cout << "],\"egress_portals\":[";
    for (std::size_t index = 0; index < topology.egress_portals.size(); ++index) {
        if (index != 0)
            std::cout << ',';
        const auto& portal = topology.egress_portals[index];
        std::cout << "{\"left\":";
        print_point(portal.left);
        std::cout << ",\"right\":";
        print_point(portal.right);
        std::cout << ",\"width_yards\":" << portal.width_yards
                  << ",\"distance_yards\":" << portal.distance_yards
                  << ",\"route_distance_yards\":" << portal.route_distance_yards
                  << ",\"from_overhead_clear\":false"
                  << ",\"to_overhead_clear\":true"
                  << ",\"from_surfaces\":";
        print_physical_surfaces(portal.from_flags);
        std::cout << ",\"to_surfaces\":";
        print_physical_surfaces(portal.to_flags);
        std::cout << '}';
    }
    std::cout << "]}";
}

#include "vertical_continuity.hpp"

int run_awareness_server(const char* nav_root, const char* map_name, bool spatial_scan = false) {
    PathfindResultType create_result = 255;
    pathfind::Map* map = pathfind_new_map(nav_root, map_name, &create_result);
    require_success(create_result, "create_awareness_server");
    if (map == nullptr)
        throw std::runtime_error("awareness server create returned a null map");
    struct MapGuard {
        pathfind::Map* value;
        ~MapGuard() { pathfind_free_map(value); }
    } guard {map};

    std::cout << "{\"status\":\"READY\",\"protocol\":1}\n" << std::flush;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line == "QUIT")
            break;
        unsigned long long sequence = 0;
        float start_x = 0.0f;
        float start_y = 0.0f;
        float requested_start_z = 0.0f;
        std::string extra;
        std::istringstream input(line);
        if (
            !(input >> sequence >> start_x >> start_y >> requested_start_z)
            || (input >> extra)
            || !std::isfinite(start_x)
            || !std::isfinite(start_y)
            || !std::isfinite(requested_start_z)
        ) {
            std::cout << "{\"status\":\"ERROR\",\"sequence\":"
                      << sequence
                      << ",\"detail\":\"invalid awareness request\"}\n"
                      << std::flush;
            continue;
        }
        try {
            float adt_x = -1.0f;
            float adt_y = -1.0f;
            require_success(
                pathfind_load_adt_at(map, start_x, start_y, &adt_x, &adt_y),
                "awareness_load_adt_at");
            std::array<float, 64> heights {};
            unsigned int height_count = 0;
            require_success(
                pathfind_find_heights(
                    map, start_x, start_y, heights.data(),
                    static_cast<unsigned int>(heights.size()), &height_count),
                "awareness_find_heights");
            if (height_count == 0)
                throw std::runtime_error(
                    "awareness find_heights returned no walkable surface");
            float start_z = heights[0];
            float best_delta = std::abs(start_z - requested_start_z);
            for (unsigned int index = 1; index < height_count; ++index) {
                const float delta = std::abs(heights[index] - requested_start_z);
                if (delta < best_delta) {
                    start_z = heights[index];
                    best_delta = delta;
                }
            }
            const auto recast_hint = to_recast(start_x, start_y, start_z);
            std::array<float, 3> recast_start {};
            constexpr float extents[] = {5.0f, 5.0f, 5.0f};
            const dtNavMeshQuery& query = map->GetNavMeshQuery();
            const dtNavMesh& navmesh = map->GetNavMesh();
            dtQueryFilter filter;
            filter.setAreaCost(kRoadGroundArea, 1.0f);
            filter.setAreaCost(kSteepGroundArea, 1000.0f);
            dtPolyRef start_ref = 0;
            require_detour(
                query.findNearestPoly(
                    recast_hint.data(), extents, &filter,
                    &start_ref, recast_start.data()),
                "awareness_find_start_poly");
            if (!start_ref)
                throw std::runtime_error(
                    "awareness endpoint has no polygon");
            const dtMeshTile* tile = nullptr;
            const dtPoly* poly = nullptr;
            require_detour(
                navmesh.getTileAndPolyByRef(start_ref, &tile, &poly),
                "awareness_get_start_polygon");
            const auto resolved = to_wow(recast_start.data());
            const auto awareness = measure_local_awareness(
                map, query, filter, start_ref, recast_start, resolved);
            const auto topology = measure_local_topology(
                map, navmesh, query, filter, start_ref, recast_start,
                awareness.overhead_clear, resolved);

            std::optional<pa_spatial::Scan> height_scan;
            if (spatial_scan) {
                height_scan = pa_spatial::scan([&](float bearing, float height, float distance) {
                    std::uint8_t clear = 0;
                    require_success(pathfind_line_of_sight(
                        map, resolved[0], resolved[1], resolved[2] + height,
                        resolved[0] + std::cos(bearing) * distance,
                        resolved[1] + std::sin(bearing) * distance,
                        resolved[2] + height, &clear, 1), "spatial_height_scan");
                    return clear != 0;
                });
            }

            std::cout << std::fixed << std::setprecision(6)
                      << "{\"status\":\"OK\",\"sequence\":" << sequence
                      << ",\"source\":[" << start_x << ',' << start_y << ','
                      << requested_start_z << "],\"resolved\":";
            print_point(resolved);
            if (height_scan) {
                std::cout << ",\"height_scan\":{\"schema_version\":1,"
                          << "\"source\":\"CLIENT_ASSET_LINE_OF_SIGHT\","
                          << "\"exhaustive\":false,\"origin_xyz\":";
                print_point(resolved);
                std::cout << ",\"radius_yards\":" << pa_spatial::radius
                          << ",\"binary_search_iterations\":" << pa_spatial::iterations
                          << ",\"rays\":[";
                bool first = true;
                for (const auto& ray : *height_scan) {
                    if (!first) std::cout << ',';
                    first = false;
                    std::cout << "{\"bearing_rad\":" << ray.bearing
                              << ",\"height_offset_yards\":" << ray.height
                              << ",\"clear_prefix_yards\":" << ray.clear_prefix
                              << ",\"blocked_by_yards\":";
                    if (ray.blocked) std::cout << ray.blocked_by;
                    else std::cout << "null";
                    std::cout << '}';
                }
                std::cout << "]}";
            }
            // Optional observation metadata; does not change layer selection.
            // Asset surfaces are hypotheses, not measured actor elevation.
            std::cout << ",\"vertical_candidates\":{\"schema_version\":1,"
                      << "\"source\":\"CLIENT_ASSET_HEIGHT_QUERY\","
                      << "\"exhaustive\":false,\"selected_surface_z\":"
                      << start_z << ",\"heights\":[";
            for (unsigned int index = 0; index < height_count; ++index) {
                if (index != 0) std::cout << ',';
                std::cout << heights[index];
            }
            std::cout << "]}";
            std::cout << ",\"physical_surfaces\":";
            print_physical_surfaces(poly->flags);
            std::cout << ",\"overhead_clear\":"
                      << (awareness.overhead_clear ? "true" : "false")
                      << ",\"awareness\":";
            print_local_awareness_json(poly->flags, awareness, topology);
            std::cout << ",\"walls\":[";
            for (std::size_t index = 0;
                 index < topology.wall_segments.size(); ++index) {
                if (index != 0)
                    std::cout << ',';
                print_server_segment(
                    topology.wall_segments[index].left,
                    topology.wall_segments[index].right);
            }
            std::cout << "],\"transitions\":[";
            for (std::size_t index = 0;
                 index < topology.surface_transition_portals.size(); ++index) {
                if (index != 0)
                    std::cout << ',';
                print_server_segment(
                    topology.surface_transition_portals[index].left,
                    topology.surface_transition_portals[index].right);
            }
            std::cout << "],\"egresses\":[";
            for (std::size_t index = 0;
                 index < topology.egress_portals.size(); ++index) {
                if (index != 0)
                    std::cout << ',';
                print_server_segment(
                    topology.egress_portals[index].left,
                    topology.egress_portals[index].right);
            }
            std::cout << "]}\n" << std::flush;
        } catch (const std::exception& error) {
            std::cout << "{\"status\":\"ERROR\",\"sequence\":"
                      << sequence << ",\"detail\":\"awareness query failed\"}\n"
                      << std::flush;
            if (std::getenv("PA_NAV_DEBUG") != nullptr)
                std::cerr << error.what() << '\n';
        }
    }
    return 0;
}
}

int main(int argc, char** argv) {
    if (argc == 4 && std::string(argv[1]) == "--vertical-continuity-server") {
        try { return run_vertical_continuity_server(argv[2], argv[3]); }
        catch (const std::exception&) { return 1; }
    }
    if (argc == 4 && (std::string(argv[1]) == "--awareness-server"
                     || std::string(argv[1]) == "--spatial-awareness-server")) {
        try {
            return run_awareness_server(argv[2], argv[3],
                std::string(argv[1]) == "--spatial-awareness-server");
        } catch (const std::exception& error) {
            std::cerr << "{\"status\":\"ERROR\",\"detail\":\""
                      << error.what() << "\"}\n";
            return 1;
        }
    }
    if (argc < 8) {
        std::cerr << "usage: pa_nav_probe NAV_ROOT MAP START_X START_Y START_Z STOP_X STOP_Y"
                     " [--stop-z STOP_Z]"
                     " [BLOCKED_X BLOCKED_Y BLOCKED_Z BLOCKED_RADIUS]\n"
                     "   or: pa_nav_probe --awareness-server NAV_ROOT MAP\n";
        return 2;
    }

    try {
        const float start_x = parse_float(argv[3], "START_X");
        const float start_y = parse_float(argv[4], "START_Y");
        const float requested_start_z = parse_float(argv[5], "START_Z");
        const float stop_x = parse_float(argv[6], "STOP_X");
        const float stop_y = parse_float(argv[7], "STOP_Y");
        int blocker_start = 8;
        std::optional<float> requested_stop_z;
        if (argc >= 10 && std::string(argv[8]) == "--stop-z") {
            requested_stop_z = parse_float(argv[9], "STOP_Z");
            blocker_start = 10;
        }
        if (
            (argc - blocker_start) % 4 != 0
            || argc > blocker_start + 32
        ) {
            throw std::invalid_argument(
                "optional stop Z or blocker arguments are malformed"
            );
        }
        std::vector<std::array<float, 4>> observed_blockers;
        for (int index = blocker_start; index < argc; index += 4) {
            const float radius = parse_float(argv[index + 3], "BLOCKED_RADIUS");
            if (radius < 1.0f || radius > 30.0f)
                throw std::invalid_argument("blocked radius is outside [1, 30]");
            observed_blockers.push_back({
                parse_float(argv[index], "BLOCKED_X"),
                parse_float(argv[index + 1], "BLOCKED_Y"),
                parse_float(argv[index + 2], "BLOCKED_Z"),
                radius,
            });
        }

        PathfindResultType create_result = 255;
        pathfind::Map* map = pathfind_new_map(argv[1], argv[2], &create_result);
        require_success(create_result, "create");
        if (map == nullptr)
            throw std::runtime_error("create returned a null map");

        struct MapGuard {
            pathfind::Map* value;
            ~MapGuard() { pathfind_free_map(value); }
        } guard {map};

        float adt_x = -1.0f;
        float adt_y = -1.0f;
        require_success(pathfind_load_adt_at(map, start_x, start_y, &adt_x, &adt_y),
                        "load_adt_at");
        float stop_adt_x = -1.0f;
        float stop_adt_y = -1.0f;
        require_success(pathfind_load_adt_at(map, stop_x, stop_y, &stop_adt_x, &stop_adt_y),
                        "load_stop_adt_at");

        const int min_adt_x = static_cast<int>(std::min(adt_x, stop_adt_x));
        const int max_adt_x = static_cast<int>(std::max(adt_x, stop_adt_x));
        const int min_adt_y = static_cast<int>(std::min(adt_y, stop_adt_y));
        const int max_adt_y = static_cast<int>(std::max(adt_y, stop_adt_y));
        for (int load_y = min_adt_y; load_y <= max_adt_y; ++load_y)
            for (int load_x = min_adt_x; load_x <= max_adt_x; ++load_x) {
                float loaded_x = -1.0f;
                float loaded_y = -1.0f;
                require_success(pathfind_load_adt(map, load_x, load_y, &loaded_x, &loaded_y),
                                "load_corridor_adt");
            }

        std::array<float, 64> heights {};
        unsigned int height_count = 0;
        require_success(pathfind_find_heights(map, start_x, start_y, heights.data(),
                                              static_cast<unsigned int>(heights.size()),
                                              &height_count),
                        "find_heights");
        if (height_count == 0)
            throw std::runtime_error("find_heights returned no walkable surface");

        float start_z = heights[0];
        float best_delta = std::abs(start_z - requested_start_z);
        for (unsigned int index = 1; index < height_count; ++index) {
            const float delta = std::abs(heights[index] - requested_start_z);
            if (delta < best_delta) {
                start_z = heights[index];
                best_delta = delta;
            }
        }

        std::array<float, 64> stop_heights {};
        unsigned int stop_height_count = 0;
        require_success(pathfind_find_heights(map, stop_x, stop_y, stop_heights.data(),
                                              static_cast<unsigned int>(stop_heights.size()),
                                              &stop_height_count),
                        "find_stop_heights");
        if (stop_height_count == 0)
            throw std::runtime_error("find_stop_heights returned no walkable surface");
        float stop_z = stop_heights[0];
        const float stop_height_reference = requested_stop_z.value_or(start_z);
        float stop_best_delta = std::abs(stop_z - stop_height_reference);
        for (unsigned int index = 1; index < stop_height_count; ++index) {
            const float delta = std::abs(stop_heights[index] - stop_height_reference);
            if (delta < stop_best_delta) {
                stop_z = stop_heights[index];
                stop_best_delta = delta;
            }
        }

        const auto recast_start_hint = to_recast(start_x, start_y, start_z);
        const auto recast_stop_hint = to_recast(stop_x, stop_y, stop_z);
        std::array<float, 3> recast_start {};
        std::array<float, 3> recast_stop {};
        constexpr float extents[] = {5.0f, 5.0f, 5.0f};
        const dtNavMeshQuery& query = map->GetNavMeshQuery();
        const dtNavMesh& navmesh = map->GetNavMesh();
        dtQueryFilter filter;
        // The atlas-derived semantic planner already chooses the global road
        // corridor.  Discounting road polygons again at 0.25 made a local
        // Detour leg prefer a route up to four times longer, often walking
        // behind the actor to rejoin a cheap polygon and forcing a 180-degree
        // camera pivot at every semantic hand-off.  Locally, road and ordinary
        // walkable ground must have equal cost; semantic rolling goals retain
        // the global road intent while Detour selects the shortest valid leg.
        filter.setAreaCost(kRoadGroundArea, 1.0f);
        filter.setAreaCost(kSteepGroundArea, 1000.0f);
        filter.setAreaCost(kDoodadTraversalArea, kDoodadTraversalCost);
        dtPolyRef start_ref = 0;
        dtPolyRef stop_ref = 0;
        const auto find_preferred_endpoint = [&query, &filter, &extents](
            const std::array<float, 3>& hint,
            float requested_x,
            float requested_y,
            dtPolyRef& result_ref,
            std::array<float, 3>& result_point,
            const char* label) {
            dtQueryFilter stable_surface_filter = filter;
            stable_surface_filter.setExcludeFlags(
                static_cast<unsigned short>(PolyFlags::Doodad));
            dtPolyRef preferred_ref = 0;
            std::array<float, 3> preferred_point {};
            require_detour(
                query.findNearestPoly(
                    hint.data(), extents, &stable_surface_filter,
                    &preferred_ref, preferred_point.data()),
                label);
            if (preferred_ref) {
                const auto preferred_world = to_wow(preferred_point.data());
                if (std::hypot(
                        preferred_world[0] - requested_x,
                        preferred_world[1] - requested_y) <= 1.5f) {
                    result_ref = preferred_ref;
                    result_point = preferred_point;
                    return;
                }
            }
            require_detour(
                query.findNearestPoly(
                    hint.data(), extents, &filter,
                    &result_ref, result_point.data()),
                label);
        };
        find_preferred_endpoint(
            recast_start_hint, start_x, start_y, start_ref, recast_start,
            "find_start_poly");
        find_preferred_endpoint(
            recast_stop_hint, stop_x, stop_y, stop_ref, recast_stop,
            "find_stop_poly");
        if (!start_ref || !stop_ref)
            throw std::runtime_error("corridor endpoint has no polygon");
        const dtMeshTile* start_awareness_tile = nullptr;
        const dtPoly* start_awareness_poly = nullptr;
        require_detour(
            navmesh.getTileAndPolyByRef(
                start_ref, &start_awareness_tile, &start_awareness_poly),
            "get_start_awareness_polygon");
        const auto start_awareness = measure_local_awareness(
            map, query, filter, start_ref, recast_start,
            to_wow(recast_start.data()));
        const auto start_topology = measure_local_topology(
            map, navmesh, query, filter, start_ref, recast_start,
            start_awareness.overhead_clear, to_wow(recast_start.data()));
        int road_polygons_preferred = 0;
        float road_min_x = std::numeric_limits<float>::max();
        float road_min_y = std::numeric_limits<float>::max();
        float road_max_x = std::numeric_limits<float>::lowest();
        float road_max_y = std::numeric_limits<float>::lowest();
        float nearest_road_to_start = std::numeric_limits<float>::max();
        int steep_polygons_penalized = 0;
        int doodad_polygons_penalized = 0;
        int impassable_uphill_polygons_excluded = 0;
        int observed_blocker_polygons_excluded = 0;
        for (int tile_index = 0; tile_index < navmesh.getMaxTiles(); ++tile_index) {
            const dtMeshTile* tile = navmesh.getTile(tile_index);
            if (tile == nullptr || tile->header == nullptr)
                continue;
            for (int poly_index = 0; poly_index < tile->header->polyCount; ++poly_index) {
                const dtPoly& poly = tile->polys[poly_index];
                if (poly.getType() != DT_POLYTYPE_GROUND)
                    continue;
                const dtPolyRef poly_ref =
                    navmesh.getPolyRefBase(tile) | static_cast<dtPolyRef>(poly_index);
                const bool observed_blocked = std::any_of(
                    observed_blockers.begin(), observed_blockers.end(),
                    [tile, &poly](const std::array<float, 4>& blocker) {
                        return polygon_overlaps_observed_blocker(
                            tile, &poly, blocker);
                    });
                if (observed_blocked && poly_ref != start_ref && poly_ref != stop_ref) {
                    // Detour's default query filter excludes zero-flag
                    // polygons.  The worker process owns this loaded navmesh,
                    // so this bounded mutation cannot leak into another query.
                    const_cast<dtPoly&>(poly).flags = 0;
                    ++observed_blocker_polygons_excluded;
                    continue;
                }
                if (poly.flags & PolyFlags::Doodad) {
                    const_cast<dtPoly&>(poly).setArea(kDoodadTraversalArea);
                    ++doodad_polygons_penalized;
                }
                if (poly.getArea() == kRoadGroundArea) {
                    ++road_polygons_preferred;
                    const auto center = polygon_centroid_wow(tile, &poly);
                    road_min_x = std::min(road_min_x, center[0]);
                    road_min_y = std::min(road_min_y, center[1]);
                    road_max_x = std::max(road_max_x, center[0]);
                    road_max_y = std::max(road_max_y, center[1]);
                    const float dx = center[0] - start_x;
                    const float dy = center[1] - start_y;
                    nearest_road_to_start = std::min(
                        nearest_road_to_start, std::sqrt(dx * dx + dy * dy));
                } else if (poly.getArea() == kSteepGroundArea)
                    ++steep_polygons_penalized;
            }
        }
        std::vector<dtPolyRef> polygon_refs(kMaxPathHops);
        int polygon_count = 0;
        require_detour(query.findPath(
                           start_ref, stop_ref, recast_start.data(), recast_stop.data(),
                           &filter, polygon_refs.data(), &polygon_count, kMaxPathHops),
                       "find_polygon_corridor");
        if (polygon_count <= 0)
            throw std::runtime_error("polygon corridor is empty");
        const float projected_stop_dx = recast_stop[0] - recast_stop_hint[0];
        const float projected_stop_dz = recast_stop[2] - recast_stop_hint[2];
        const bool corridor_complete =
            polygon_refs[polygon_count - 1] == stop_ref
            && std::sqrt(
                projected_stop_dx * projected_stop_dx
                + projected_stop_dz * projected_stop_dz) <= 0.05f;
        polygon_refs.resize(polygon_count);

        std::array<float, 3> corridor_stop = recast_stop;
        if (!corridor_complete) {
            bool over_polygon = false;
            require_detour(
                query.closestPointOnPoly(
                    polygon_refs.back(), recast_stop.data(), corridor_stop.data(), &over_polygon),
                "closest_partial_corridor_stop");
        }
        const auto requested_stop_wow = to_wow(recast_stop.data());
        const SearchVantageMetrics search_vantage =
            measure_search_vantage(map, requested_stop_wow);
        const dtMeshTile* search_vantage_tile = nullptr;
        const dtPoly* search_vantage_poly = nullptr;
        require_detour(
            navmesh.getTileAndPolyByRef(
                stop_ref, &search_vantage_tile, &search_vantage_poly),
            "get_search_vantage_polygon");

        std::vector<float> straight_points(kMaxPathHops * 3);
        std::vector<unsigned char> straight_flags(kMaxPathHops);
        std::vector<dtPolyRef> straight_refs(kMaxPathHops);
        int straight_count = 0;
        require_detour(query.findStraightPath(
                           recast_start.data(), corridor_stop.data(), polygon_refs.data(), polygon_count,
                           straight_points.data(), straight_flags.data(), straight_refs.data(),
                           &straight_count, kMaxPathHops),
                       "find_straight_path");
        if (straight_count <= 0)
            throw std::runtime_error("straight path is empty");

        std::vector<Portal> portals;
        portals.reserve(std::max(0, polygon_count - 1));
        for (int index = 0; index + 1 < polygon_count; ++index)
            portals.push_back(find_portal(query, filter, polygon_refs[index],
                                          polygon_refs[index + 1], index));

        // Keep Detour's funnel/string-pulled path as the traversable base.  A
        // midpoint for every portal is safe but creates artificial zig-zags:
        // adjacent wide polygons can alternate portal centres and demand
        // 90-125 degree camera pivots on otherwise open ground.  Project every
        // sparse straight-path point back onto its exact corridor polygon so
        // the XY remains funnel-smoothed while Z cannot leak to another floor.
        std::vector<std::array<float, 3>> base_points;
        base_points.reserve(straight_count);
        for (int index = 0; index < straight_count; ++index) {
            const float* straight_point = &straight_points[index * 3];
            dtPolyRef surface_ref = straight_refs[index];
            if (!surface_ref)
                surface_ref = index == 0 ? polygon_refs.front() : polygon_refs.back();
            std::array<float, 3> surface_point_recast {};
            bool over_polygon = false;
            require_detour(
                query.closestPointOnPoly(
                    surface_ref, straight_point, surface_point_recast.data(), &over_polygon),
                "project_straight_point_to_corridor_surface");
            const auto surface_point_wow = to_wow(surface_point_recast.data());
            if (base_points.empty()
                || std::hypot(
                    surface_point_wow[0] - base_points.back()[0],
                    surface_point_wow[1] - base_points.back()[1]) > 0.01f
                || std::abs(surface_point_wow[2] - base_points.back()[2]) > 0.01f)
                base_points.push_back(surface_point_wow);
        }
        if (base_points.empty())
            throw std::runtime_error("projected straight path is empty");
        if (std::getenv("PA_NAV_DEBUG") != nullptr) {
            std::cerr << "base_path_points=" << base_points.size() << '\n';
            for (const auto& point : base_points)
                std::cerr << "base=" << point[0] << ',' << point[1] << ','
                          << point[2] << '\n';
            int ground_flags = 0, wmo_flags = 0, doodad_flags = 0;
            for (const auto polygon_ref : polygon_refs) {
                const dtMeshTile* debug_tile = nullptr;
                const dtPoly* debug_poly = nullptr;
                if (dtStatusSucceed(navmesh.getTileAndPolyByRef(
                        polygon_ref, &debug_tile, &debug_poly))) {
                    if (debug_poly->flags & PolyFlags::Ground)
                        ++ground_flags;
                    if (debug_poly->flags & PolyFlags::Wmo)
                        ++wmo_flags;
                    if (debug_poly->flags & PolyFlags::Doodad)
                        ++doodad_flags;
                }
            }
            std::cerr << "physical_flags ground=" << ground_flags
                      << " wmo=" << wmo_flags
                      << " doodad=" << doodad_flags << '\n';
        }

        std::vector<std::array<float, 3>> movement_points;
        int doodad_detour_count = 0;
        int doodad_initial_unresolved_segment_count = 0;
        int doodad_line_probes_remaining = kMaxDoodadLineProbes;
        const float direct_distance = distance_2d(
            base_points.front(), base_points.back());
        const float detour_distance = polyline_length_2d(base_points);
        const bool inflated_topology_route =
            direct_distance <= kMaxDirectTopologyRepairDistance
            && detour_distance > std::max(
                direct_distance * kTopologyGapInflationRatio,
                direct_distance + kTopologyGapInflationAllowance);
        const bool topology_gap_direct_shortcut_applied =
            inflated_topology_route
            && prove_direct_ground_shortcut(
                map, base_points.front(), base_points.back(), movement_points,
                doodad_line_probes_remaining);
        if (!topology_gap_direct_shortcut_applied) {
            movement_points.push_back(base_points.front());
            for (std::size_t index = 0; index + 1 < base_points.size(); ++index) {
                if (!append_doodad_aware_segment(
                        map, base_points[index], base_points[index + 1],
                        movement_points, 0, doodad_detour_count,
                        doodad_line_probes_remaining)) {
                    // Terrain/WMO surfaces also participate in this conservative
                    // ray query. Preserve the proven Detour portal step when a
                    // doodad-only local detour cannot be established.
                    movement_points.push_back(base_points[index + 1]);
                    ++doodad_initial_unresolved_segment_count;
                }
            }
        }
        // Apply capsule clearance after conservative doodad detours are known.
        // Insetting the sparse funnel first changes LOS recursion endpoints and
        // can discard an otherwise proven local M2 detour.
        const int clearance_inset_count = topology_gap_direct_shortcut_applied
            ? 0 : inset_funnel_corners(movement_points, portals);
        int movement_path_simplification_probes_remaining =
            kMaxMovementPathSimplificationProbes;
        const int movement_path_shortcut_count = simplify_proven_movement_path(
            map, movement_points,
            movement_path_simplification_probes_remaining);

        // Portal insetting can resolve a pre-inset endpoint collision.  Only
        // the final path receives execution authority, so discover blockers
        // again after every inset and local detour has been applied.
        int doodad_unresolved_segment_count = 0;
        int final_validation_probes_remaining = kMaxDoodadLineProbes;
        int doodad_blocker_discovery_probes_remaining =
            kMaxDoodadBlockerDiscoveryProbes;
        std::vector<std::array<float, 4>> doodad_unresolved_blockers;
        for (std::size_t index = 0;
             index + 1 < movement_points.size(); ++index) {
            if (doodad_capsule_clear(
                    map, movement_points[index], movement_points[index + 1],
                    final_validation_probes_remaining))
                continue;
            std::array<float, 4> blocker {};
            const bool blocker_located = locate_first_doodad_blocker(
                    map, movement_points[index], movement_points[index + 1],
                    blocker, doodad_blocker_discovery_probes_remaining);
            if (
                blocker_located
                && blocker_is_inset_wmo_portal_artifact(
                    blocker, portals, polygon_refs, navmesh)
            )
                continue;
            ++doodad_unresolved_segment_count;
            if (
                !blocker_located
                || doodad_unresolved_blockers.size()
                    >= kMaxReportedDoodadBlockers
            )
                continue;
            const bool duplicate = std::any_of(
                doodad_unresolved_blockers.begin(),
                doodad_unresolved_blockers.end(),
                [&blocker](const std::array<float, 4>& existing) {
                    return std::hypot(
                        blocker[0] - existing[0],
                        blocker[1] - existing[1]) < 1.0f
                        && std::abs(blocker[2] - existing[2]) < 2.5f;
                });
            if (!duplicate)
                doodad_unresolved_blockers.push_back(blocker);
        }
        if (std::getenv("PA_NAV_DEBUG") != nullptr)
            std::cerr << "doodad_initial_unresolved="
                      << doodad_initial_unresolved_segment_count
                      << " final_unresolved="
                      << doodad_unresolved_segment_count << '\n';
        if (std::getenv("PA_NAV_DEBUG") != nullptr) {
            int low_validation_probes_remaining = kMaxDoodadLineProbes;
            for (std::size_t index = 0;
                 index + 1 < movement_points.size(); ++index) {
                if (!doodad_capsule_clear_at_height(
                        map, movement_points[index], movement_points[index + 1],
                        kPreferredLowObstacleProbeHeight,
                        low_validation_probes_remaining))
                    std::cerr << "final_low_clearance_failed segment="
                              << index << " start="
                              << movement_points[index][0] << ','
                              << movement_points[index][1] << ','
                              << movement_points[index][2] << " stop="
                              << movement_points[index + 1][0] << ','
                              << movement_points[index + 1][1] << ','
                              << movement_points[index + 1][2] << '\n';
            }
        }

        std::cout << std::fixed << std::setprecision(6);
        std::cout << "{\"status\":\"OK\",\"adt_x\":" << adt_x
                  << ",\"adt_y\":" << adt_y
                  << ",\"start\":";
        print_point(to_wow(recast_start.data()));
        std::cout
                  << ",\"stop\":";
        print_point(to_wow(corridor_stop.data()));
        std::cout << ",\"requested_stop\":[" << stop_x << ',' << stop_y << ',' << stop_z << ']'
                  << ",\"requested_stop_z_hint\":";
        if (requested_stop_z.has_value())
            std::cout << requested_stop_z.value();
        else
            std::cout << "null";
        std::cout << ",\"complete\":" << (corridor_complete ? "true" : "false")
                  << ",\"topology_gap_direct_shortcut_applied\":"
                  << (topology_gap_direct_shortcut_applied ? "true" : "false")
                  << ",\"doodad_avoidance_applied\":"
                  << (doodad_detour_count > 0 ? "true" : "false")
                  << ",\"doodad_detour_count\":" << doodad_detour_count
                  << ",\"doodad_unresolved_segment_count\":"
                  << doodad_unresolved_segment_count
                  << ",\"doodad_unresolved_blockers\":[";
        for (std::size_t index = 0;
             index < doodad_unresolved_blockers.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            std::cout << '[' << doodad_unresolved_blockers[index][0] << ','
                      << doodad_unresolved_blockers[index][1] << ','
                      << doodad_unresolved_blockers[index][2] << ','
                      << doodad_unresolved_blockers[index][3] << ']';
        }
        std::cout
                  << ']'
                  << ",\"clearance_inset_count\":" << clearance_inset_count
                  << ",\"movement_path_shortcut_count\":"
                  << movement_path_shortcut_count
                  << ",\"steep_polygons_penalized\":" << steep_polygons_penalized
                  << ",\"doodad_polygons_penalized\":"
                  << doodad_polygons_penalized
                  << ",\"road_polygons_preferred\":" << road_polygons_preferred
                  << ",\"nearest_road_polygon_to_start\":"
                  << (std::isfinite(nearest_road_to_start) ? nearest_road_to_start : -1.0f)
                  << ",\"road_polygon_bounds\":["
                  << (road_polygons_preferred ? road_min_x : 0.0f) << ','
                  << (road_polygons_preferred ? road_min_y : 0.0f) << ','
                  << (road_polygons_preferred ? road_max_x : 0.0f) << ','
                  << (road_polygons_preferred ? road_max_y : 0.0f) << ']'
                  << ",\"impassable_uphill_polygons_excluded\":"
                  << impassable_uphill_polygons_excluded
                  << ",\"observed_blocker_polygons_excluded\":"
                  << observed_blocker_polygons_excluded
                  << ",\"height_candidates\":" << height_count
                  << ",\"stop_height_candidates\":" << stop_height_count
                  << ",\"search_vantage_radial_clear_count\":"
                  << search_vantage.radial_clear_count
                  << ",\"search_vantage_radial_probe_count\":"
                  << kSearchVantageRadialProbeCount
                  << ",\"search_vantage_radial_probe_radius\":"
                  << kSearchVantageRadius
                  << ",\"search_vantage_overhead_clear\":"
                  << (search_vantage.overhead_clear ? "true" : "false")
                  << ",\"search_vantage_physical_surfaces\":";
        print_physical_surfaces(search_vantage_poly->flags);
        std::cout << ",\"start_awareness\":{\"physical_surfaces\":";
        print_physical_surfaces(start_awareness_poly->flags);
        std::cout << ",\"probe_radius_yards\":" << kLocalAwarenessRadius
                  << ",\"overhead_clear\":"
                  << (start_awareness.overhead_clear ? "true" : "false")
                  << ",\"radial_probes\":[";
        for (std::size_t index = 0;
             index < start_awareness.radial_probes.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            const auto& probe = start_awareness.radial_probes[index];
            std::cout << "{\"bearing_rad\":" << probe.bearing_rad
                      << ",\"clearance_yards\":" << probe.clearance_yards
                      << ",\"navmesh_reachable\":"
                      << (probe.navmesh_reachable ? "true" : "false")
                      << '}';
        }
        std::cout << "],\"topology_radius_yards\":" << kLocalTopologyRadius
                  << ",\"component_polygon_count\":"
                  << start_topology.component_polygon_count
                  << ",\"component_truncated\":"
                  << (start_topology.component_truncated ? "true" : "false")
                  << ",\"wall_segments_truncated\":"
                  << (start_topology.wall_segments_truncated ? "true" : "false")
                  << ",\"surface_transition_portals_truncated\":"
                  << (start_topology.surface_transition_portals_truncated
                      ? "true" : "false")
                  << ",\"egress_inference_complete\":"
                  << (start_topology.egress_inference_complete
                      ? "true" : "false")
                  << ",\"egress_portals_truncated\":"
                  << (start_topology.egress_portals_truncated
                      ? "true" : "false")
                  << ",\"wall_segments\":[";
        for (std::size_t index = 0;
             index < start_topology.wall_segments.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            const auto& wall = start_topology.wall_segments[index];
            std::cout << "{\"left\":";
            print_point(wall.left);
            std::cout << ",\"right\":";
            print_point(wall.right);
            std::cout << ",\"distance_yards\":" << wall.distance_yards << '}';
        }
        std::cout << "],\"surface_transition_portals\":[";
        for (std::size_t index = 0;
             index < start_topology.surface_transition_portals.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            const auto& portal = start_topology.surface_transition_portals[index];
            std::cout << "{\"left\":";
            print_point(portal.left);
            std::cout << ",\"right\":";
            print_point(portal.right);
            std::cout << ",\"width_yards\":" << portal.width_yards
                      << ",\"distance_yards\":" << portal.distance_yards
                      << ",\"from_surfaces\":";
            print_physical_surfaces(portal.from_flags);
            std::cout << ",\"to_surfaces\":";
            print_physical_surfaces(portal.to_flags);
            std::cout << '}';
        }
        std::cout << "],\"egress_portals\":[";
        for (std::size_t index = 0;
             index < start_topology.egress_portals.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            const auto& portal = start_topology.egress_portals[index];
            std::cout << "{\"left\":";
            print_point(portal.left);
            std::cout << ",\"right\":";
            print_point(portal.right);
            std::cout << ",\"width_yards\":" << portal.width_yards
                      << ",\"distance_yards\":" << portal.distance_yards
                      << ",\"route_distance_yards\":"
                      << portal.route_distance_yards
                      << ",\"from_overhead_clear\":false"
                      << ",\"to_overhead_clear\":true"
                      << ",\"from_surfaces\":";
            print_physical_surfaces(portal.from_flags);
            std::cout << ",\"to_surfaces\":";
            print_physical_surfaces(portal.to_flags);
            std::cout << '}';
        }
        std::cout << "]},\"path\":[";
        for (std::size_t index = 0; index < movement_points.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            print_point(movement_points[index]);
        }
        std::cout << "],\"polygons\":[";
        for (int index = 0; index < polygon_count; ++index) {
            if (index != 0)
                std::cout << ',';
            const dtMeshTile* tile = nullptr;
            const dtPoly* poly = nullptr;
            require_detour(navmesh.getTileAndPolyByRef(polygon_refs[index], &tile, &poly),
                           "get_corridor_polygon");
            std::array<float, 3> centroid {};
            std::cout << "{\"index\":" << index << ",\"area\":"
                      << static_cast<int>(poly->getArea()) << ",\"type\":"
                      << static_cast<int>(poly->getType()) << ",\"slope_degrees\":"
                      << polygon_slope_degrees(tile, poly)
                      << ",\"physical_surfaces\":";
            print_physical_surfaces(poly->flags);
            std::cout << ",\"vertices\":[";
            for (int vertex_index = 0; vertex_index < poly->vertCount; ++vertex_index) {
                if (vertex_index != 0)
                    std::cout << ',';
                const auto vertex = to_wow(&tile->verts[poly->verts[vertex_index] * 3]);
                centroid[0] += vertex[0];
                centroid[1] += vertex[1];
                centroid[2] += vertex[2];
                print_point(vertex);
            }
            for (float& value : centroid)
                value /= poly->vertCount;
            std::cout << "],\"centroid\":";
            print_point(centroid);
            std::cout << '}';
        }
        std::cout << "],\"portals\":[";
        for (std::size_t index = 0; index < portals.size(); ++index) {
            if (index != 0)
                std::cout << ',';
            const Portal& portal = portals[index];
            std::cout << "{\"from_index\":" << portal.from_index
                      << ",\"to_index\":" << portal.to_index << ",\"left\":";
            print_point(portal.left);
            std::cout << ",\"right\":";
            print_point(portal.right);
            std::cout << ",\"width\":" << portal.width << '}';
        }
        std::cout << "]}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "{\"status\":\"ERROR\",\"detail\":\"" << error.what() << "\"}\n";
        return 1;
    }
}
