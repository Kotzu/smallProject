// Offline Recast experiment, not a bake or a test of the active WorldPack.
// Synthetic voxel floors use the local builder's dimensions and connectivity.
#include "Common.hpp"
#include "recastnavigation/Recast/Include/Recast.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>

using Field = std::unique_ptr<rcHeightfield, decltype(&rcFreeHeightField)>;
using Compact = std::unique_ptr<rcCompactHeightfield, decltype(&rcFreeCompactHeightfield)>;

Compact corridor(rcContext& ctx, int width, bool stairs, bool erode) {
    constexpr int length = 40;
    const float lower[] {0, 0, 0};
    const float upper[] {width * MeshSettings::CellSize, 30,
                         length * MeshSettings::CellSize};
    Field solid(rcAllocHeightfield(), rcFreeHeightField);
    if (!solid || !rcCreateHeightfield(&ctx, *solid, width, length, lower, upper,
                                      MeshSettings::CellSize, MeshSettings::CellHeight))
        throw std::runtime_error("heightfield allocation failed");
    for (int z = 0; z < length; ++z) {
        // 0.25 yd risers every two cells: below the existing 0.6 yd limit.
        const unsigned short height = stairs ? 1 + z / 2 : 1;
        for (int x = 0; x < width; ++x)
            if (!rcAddSpan(&ctx, *solid, x, z, height - 1, height,
                           RC_WALKABLE_AREA, 0))
                throw std::runtime_error("span allocation failed");
    }
    Compact compact(rcAllocCompactHeightfield(), rcFreeCompactHeightfield);
    // SerializeMeshTile currently uses this same unlimited connection climb.
    if (!compact || !rcBuildCompactHeightfield(&ctx, MeshSettings::VoxelWalkableHeight,
                    (std::numeric_limits<int>::max)(), *solid, *compact))
        throw std::runtime_error("compact build failed");
    if (erode && !rcErodeWalkableArea(&ctx, MeshSettings::VoxelWalkableRadius, *compact))
        throw std::runtime_error("erosion failed");
    return compact;
}

int traversable_width(const rcCompactHeightfield& field, int z) {
    int count = 0;
    for (int x = 0; x < field.width; ++x) {
        const auto& cell = field.cells[x + z * field.width];
        for (unsigned int i = cell.index; i < cell.index + cell.count; ++i)
            count += field.areas[i] != RC_NULL_AREA;
    }
    return count;
}

bool connected_middle(const rcCompactHeightfield& field) {
    const int x = field.width / 2;
    // Exclude intentional erosion at the finite fixture's two end caps.
    for (int z = 5; z < field.height - 6; ++z) {
        const auto& cell = field.cells[x + z * field.width];
        if (cell.count != 1 || field.areas[cell.index] == RC_NULL_AREA)
            return false;
        const auto& next = field.cells[x + (z + 1) * field.width];
        if (next.count != 1 || field.areas[next.index] == RC_NULL_AREA)
            return false;
        // Recast direction 1 is +z; verify the step's actual span connection.
        if (rcGetCon(field.spans[cell.index], 1) == RC_NOT_CONNECTED)
            return false;
    }
    return true;
}

int main() {
    rcContext ctx;
    int failures = 0;
    for (int width : {6, 8, 12}) {
        for (bool stairs : {false, true}) {
            auto raw = corridor(ctx, width, stairs, false);
            auto eroded = corridor(ctx, width, stairs, true);
            const int before = traversable_width(*raw, 20);
            const int after = traversable_width(*eroded, 20);
            const int expected = std::max(0, width - 2 * MeshSettings::VoxelWalkableRadius);
            const bool pass = before == width && after == expected
                && connected_middle(*raw)
                && connected_middle(*eroded) == (expected > 0);
            std::cout << "width_yards=" << width * MeshSettings::CellSize
                      << " stairs=" << stairs << " before_cells=" << before
                      << " after_cells=" << after
                      << " retained_connection=" << connected_middle(*eroded)
                      << " pass=" << pass << '\n';
            failures += !pass;
        }
    }
    std::cout << "declared_radius=" << MeshSettings::WalkableRadius
              << " erosion_cells=" << MeshSettings::VoxelWalkableRadius
              << " cell_size=" << MeshSettings::CellSize
              << " active_worldpack_tested=false\n";
    return failures ? 1 : 0;
}
