// Offline branch reproduction; no game, input, live map or dependency mutation.
// The function body between markers is source-parity checked against NAMIGATOR.
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

struct Point { float Z; };
struct Bounds {
    Point getMaximum() const { return {20.f}; }
    Point getMinimum() const { return {0.f}; }
};
struct Tile { Bounds m_bounds; };
struct AuditMap {
    Tile tile;
    bool repeat_hit = true;
    mutable unsigned calls = 0;
    const Tile* GetTile(float, float) const { return &tile; }
    bool FindNextZ(const Tile*, float, float, float current, bool, float& next) const {
        if (++calls > 16) throw std::runtime_error("unbounded query");
        for (float height : {12.f, 4.f}) {
            if (height < current || (repeat_hit && height == current)) {
                next = height;
                return true;
            }
        }
        return false;
    }
    bool GetADTHeight(const Tile*, float, float, float& height) const {
        height = 18.f;
        return true;
    }
    bool FindHeights(float x, float y, std::vector<float>& output) const;
};

// BEGIN_UPSTREAM_BODY
bool AuditMap::FindHeights(float x, float y, std::vector<float>& output) const
{
    auto const tile = GetTile(x, y);

    if (!tile)
        return false;


    // FIXME: not sure what the use case for this search is.  should it be
    // always precise, never, or user-defined?

    float current = tile->m_bounds.getMaximum().Z;
    do
    {
        float next;
        if (!FindNextZ(tile, x, y, current, false, next))
            break;

        // if we just found the same z, nudge down slightly
        if (next == current)
        {
            current = std::nextafter(next, next - 1.f);

            // if this nudge put us below the tile boundary, don't try another ray cast
            // as this will cause the ray to go upward instead of downward.
            if (current < tile->m_bounds.getMaximum().Z)
                break;
        }
        else
        {
            output.push_back(next);
            current = next;
        }
    } while (true);

    float adtHeight;
    if (GetADTHeight(tile, x, y, adtHeight))
        output.push_back(adtHeight);

    return !output.empty();
}
// END_UPSTREAM_BODY

int main() {
    AuditMap repeated, distinct;
    distinct.repeat_hit = false;
    std::vector<float> a, b;
    repeated.FindHeights(0, 0, a);
    distinct.FindHeights(0, 0, b);
    if (a != std::vector<float>{12.f, 18.f} || b != std::vector<float>{12.f, 4.f, 18.f})
        return 1;
    std::cout << "{\"status\":\"CONDITIONAL_OMISSION_REPRODUCED\","
              << "\"repeat_hit_heights\":[12,18],\"distinct_hit_heights\":[12,4,18],"
              << "\"omitted_height\":4,\"live_reproduction\":false,"
              << "\"fixture_next_hit_provider\":true,\"execution_authority\":false}\n";
}
