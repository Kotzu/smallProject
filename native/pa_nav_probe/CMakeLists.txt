cmake_minimum_required(VERSION 3.20)
project(pa_nav_probe LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(PA_NAV_BUILD_SPATIAL_TESTS "Build isolated observation tests" OFF)
if(PA_NAV_BUILD_SPATIAL_TESTS)
    enable_testing()
    add_executable(pa_height_scan_test tests/height_scan_test.cpp)
    add_test(NAME spatial_height_scan COMMAND pa_height_scan_test)
endif()

if(NOT DEFINED NAMIGATOR_ROOT OR NOT DEFINED NAMIGATOR_BUILD_ROOT)
    message(FATAL_ERROR "NAMIGATOR_ROOT and NAMIGATOR_BUILD_ROOT are required")
endif()

add_executable(pa_nav_probe main.cpp)
target_compile_definitions(pa_nav_probe PRIVATE DT_POLYREF64)
target_include_directories(pa_nav_probe PRIVATE "${NAMIGATOR_ROOT}")
target_link_libraries(pa_nav_probe PRIVATE
    "${NAMIGATOR_BUILD_ROOT}/pathfind/Debug/libpathfind.lib"
    "${NAMIGATOR_BUILD_ROOT}/utility/Debug/utility.lib"
    "${NAMIGATOR_BUILD_ROOT}/recastnavigation/Detour/Debug/Detour-d.lib"
    "${NAMIGATOR_BUILD_ROOT}/recastnavigation/Recast/Debug/Recast-d.lib"
)

# Offline geometry regression only; never installed over the active worker.
option(PA_NAV_BUILD_GEOMETRY_TESTS "Build isolated portal/capsule regression" OFF)
if(PA_NAV_BUILD_GEOMETRY_TESTS)
    enable_testing()
    add_executable(pa_portal_clearance_test tests/portal_clearance_test.cpp)
    target_compile_definitions(pa_portal_clearance_test PRIVATE DT_POLYREF64)
    target_include_directories(pa_portal_clearance_test PRIVATE "${NAMIGATOR_ROOT}")
    target_link_libraries(pa_portal_clearance_test PRIVATE
        "${NAMIGATOR_BUILD_ROOT}/pathfind/Debug/libpathfind.lib"
        "${NAMIGATOR_BUILD_ROOT}/utility/Debug/utility.lib"
        "${NAMIGATOR_BUILD_ROOT}/recastnavigation/Detour/Debug/Detour-d.lib"
        "${NAMIGATOR_BUILD_ROOT}/recastnavigation/Recast/Debug/Recast-d.lib"
    )
    add_test(NAME portal_capsule_clearance COMMAND pa_portal_clearance_test)
    add_executable(pa_recast_erosion_test tests/recast_erosion_test.cpp)
    target_include_directories(pa_recast_erosion_test PRIVATE "${NAMIGATOR_ROOT}")
    target_link_libraries(pa_recast_erosion_test PRIVATE
        "${NAMIGATOR_BUILD_ROOT}/recastnavigation/Recast/Debug/Recast-d.lib")
    add_test(NAME recast_erosion_semantics COMMAND pa_recast_erosion_test)
endif()
