// Compile the actual production function, not a second mathematical imitation.
// The renamed worker entry point is never invoked. No assets/client are needed.
#define main unused_nav_worker_entry_point
#include "../main.cpp"
#undef main

float origin_segment_distance(const std::array<float, 3>& a,
                              const std::array<float, 3>& b) {
    const float dx = b[0] - a[0], dy = b[1] - a[1];
    const float length2 = dx * dx + dy * dy;
    const float t = length2 > 0 ? std::clamp(
        -(a[0] * dx + a[1] * dy) / length2, 0.0f, 1.0f) : 0.0f;
    return std::hypot(a[0] + t * dx, a[1] + t * dy);
}

int main() {
    // L-shaped free space around a convex obstacle corner at the origin.
    // Both portals share the same physical corner. Their independent 0.9 yd
    // insets must not be averaged into a smaller body/tracking envelope.
    int failures = 0;
    for (const float rotation : {0.0f, 0.7f, 1.9f}) {
        auto rotate = [rotation](std::array<float, 3> p) {
            const float x = p[0], y = p[1];
            p[0] = x * std::cos(rotation) - y * std::sin(rotation);
            p[1] = x * std::sin(rotation) + y * std::cos(rotation);
            return p;
        };
        std::vector<std::array<float, 3>> points {
            rotate({-5, 0, 0}), {0, 0, 0}, rotate({0, 5, 0})};
        const std::vector<Portal> portals {
            {0, 1, {0, 0, 0}, rotate({-4, 0, 0}), 4},
            {1, 2, {0, 0, 0}, rotate({0, 4, 0}), 4}};
        const int count = inset_funnel_corners(points, portals);
        const float center_distance = std::hypot(points[1][0], points[1][1]);
        const float swept_center_distance = std::min(
            origin_segment_distance(points[0], points[1]),
            origin_segment_distance(points[1], points[2]));
        const float worst_body_clearance = swept_center_distance
            - kPlayerCapsuleProbeRadius - kControllerCrossTrackTolerance;
        const bool pass = count == 1 && worst_body_clearance >= -1e-6f
            && std::abs(center_distance - kPlayerPortalInset) < 1e-6f;
        std::cout << "rotation=" << rotation << " inset_count=" << count
                  << " corner_center_distance=" << center_distance
                  << " swept_center_distance=" << swept_center_distance
                  << " radius_plus_tracking=" << kMovementTunnelRadius
                  << " worst_body_clearance=" << worst_body_clearance
                  << " pass=" << pass << '\n';
        failures += !pass;
    }
    // Baseline behavior must remain unchanged away from an exact shared
    // corner. These are invariance tests, not a claim that every old path has
    // capsule clearance (in particular an opposing pair is ambiguous).
    const auto check = [&failures](const char* name,
            std::vector<std::array<float, 3>> points,
            const std::vector<Portal>& portals,
            const std::array<float, 3>& expected, int expected_count) {
        const auto first = points.front(), last = points.back();
        const int count = inset_funnel_corners(points, portals);
        bool pass = count == expected_count && points.front() == first && points.back() == last;
        for (int axis = 0; axis < 3; ++axis)
            pass = pass && std::abs(points[1][axis] - expected[axis]) < 0.0001f;
        std::cout << name << " pass=" << pass << '\n';
        failures += !pass;
    };
    const std::vector<std::array<float, 3>> base {{-5, 0, 0}, {0, 0, 0}, {0, 5, 0}};
    check("empty_portals", base, {}, {0, 0, 0}, 0);
    check("single_portal", base, {{0, 1, {0, 0, 0}, {-4, 0, 0}, 4}}, {-.9f, 0, 0}, 1);
    check("narrow_portals", base, {{0, 1, {0, 0, 0}, {-1.8f, 0, 0}, 1.8f},
          {1, 2, {0, 0, 0}, {0, 1.8f, 0}, 1.8f}}, {0, 0, 0}, 0);
    check("opposing_portals", base, {{0, 1, {0, 0, 0}, {-4, 0, 0}, 4},
          {1, 2, {0, 0, 0}, {4, 0, 0}, 4}}, {0, 0, 0}, 1);
    check("near_distinct_corner", base, {{0, 1, {0, 0, 0}, {-4, 0, 0}, 4},
          {1, 2, {.1f, 0, 0}, {.1f, 4, 0}, 4}}, {-.4f, .45f, 0}, 1);
    check("different_floor_height", base, {{0, 1, {0, 0, 0}, {-4, 0, 0}, 4},
          {1, 2, {0, 0, 1}, {0, 4, 1}, 4}}, {-.45f, .45f, .5f}, 1);
    check("sloped_plane_unchanged", base, {{0, 1, {0, 0, 0}, {-4, 0, 2}, 4.472136f},
          {1, 2, {0, 0, 0}, {0, 4, 2}, 4.472136f}}, {-.45f, .45f, .45f}, 1);
    check("duplicate_direction", base, {{0, 1, {0, 0, 0}, {-4, 0, 0}, 4},
          {1, 2, {0, 0, 0}, {-8, 0, 0}, 8}}, {-.9f, 0, 0}, 1);
    auto translated = base;
    for (auto& p : translated) { p[0] += 100; p[1] -= 200; p[2] += 30; }
    check("translated_shared_corner", translated,
          {{0, 1, {100, -200, 30}, {96, -200, 30}, 4},
           {1, 2, {100, -200, 30}, {100, -196, 30}, 4}},
          {100 - .9f / std::sqrt(2.f), -200 + .9f / std::sqrt(2.f), 30}, 1);
    return failures ? 1 : 0;
}
