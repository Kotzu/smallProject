cmake_minimum_required(VERSION 3.20)
project(pa_client_asset_extract LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED NAMIGATOR_ROOT OR NOT DEFINED NAMIGATOR_BUILD_ROOT)
    message(FATAL_ERROR "NAMIGATOR_ROOT and NAMIGATOR_BUILD_ROOT are required")
endif()

add_executable(pa_client_asset_extract main.cpp)
target_compile_definitions(pa_client_asset_extract PRIVATE STORMLIB_NO_AUTO_LINK)
target_include_directories(pa_client_asset_extract PRIVATE
    "${NAMIGATOR_ROOT}/stormlib/src"
)
target_link_libraries(pa_client_asset_extract PRIVATE
    "${NAMIGATOR_BUILD_ROOT}/stormlib/Debug/StormLib.lib"
    wininet
)
