#pragma once
#include <array>
#include <cmath>

namespace pa_spatial {
constexpr float radius = 12.0f;
constexpr int directions = 16;
constexpr int iterations = 7;
constexpr std::array<float, 4> offsets {0.25f, 0.60f, 1.20f, 1.80f};
constexpr int maximum_queries = directions * offsets.size() * (iterations + 1);

struct Ray {
    float bearing;
    float height;
    float clear_prefix;
    float blocked_by;
    bool blocked;
};
using Scan = std::array<Ray, directions * offsets.size()>;

// Clear prefixes are tested line segments, never a volume or an exact hit.
// Callback errors must propagate; failure is not silently changed to a hit.
template<class LineClear>
Scan scan(LineClear&& line_clear) {
    Scan result {};
    int index = 0;
    for (const float height : offsets) {
        for (int direction = 0; direction < directions; ++direction) {
            const float bearing = 6.2831853071795864769f * direction / directions;
            float lower = 0.0f;
            float upper = radius;
            const bool blocked = !line_clear(bearing, height, radius);
            if (!blocked) {
                lower = radius;
            } else {
                for (int step = 0; step < iterations; ++step) {
                    const float midpoint = (lower + upper) * 0.5f;
                    if (line_clear(bearing, height, midpoint)) lower = midpoint;
                    else upper = midpoint;
                }
            }
            result[index++] = {bearing, height, lower, upper, blocked};
        }
    }
    return result;
}
}  // namespace pa_spatial
