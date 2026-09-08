#include "../height_scan.hpp"
#include <stdexcept>
#include <iostream>

void require(bool value) { if (!value) throw std::runtime_error("height scan regression"); }

int main() {
    int calls = 0;
    auto open = pa_spatial::scan([&](float, float, float) { ++calls; return true; });
    require(calls == 64);
    for (const auto& ray : open) require(!ray.blocked && ray.clear_prefix == 12);

    // A low plinth is missed by the old 1.20 yd ray, but seen at lower offsets.
    auto plinth = pa_spatial::scan([](float, float height, float distance) {
        return height > 0.75f || distance < 3.4f;
    });
    for (const auto& ray : plinth) {
        require(ray.blocked == (ray.height <= 0.75f));
        if (ray.blocked) {
            require(ray.clear_prefix < 3.4f && ray.blocked_by >= 3.4f);
            require(ray.blocked_by - ray.clear_prefix <= 12.0f / 128);
        }
    }
    auto overhang = pa_spatial::scan([](float, float height, float distance) {
        return height < 1.6f || distance < 2.1f;
    });
    for (const auto& ray : overhang) require(ray.blocked == (ray.height > 1.6f));
    calls = 0;
    auto inside = pa_spatial::scan([&](float, float, float) { ++calls; return false; });
    require(calls == pa_spatial::maximum_queries);
    for (const auto& ray : inside) require(ray.clear_prefix == 0 && ray.blocked_by > 0);
    bool propagated = false;
    try { pa_spatial::scan([](float, float, float) -> bool { throw std::runtime_error("source failed"); }); }
    catch (const std::runtime_error&) { propagated = true; }
    require(propagated);
    std::cout << "height_scan: open, low plinth, overhang, bounded queries, error propagation PASS\n";
}
