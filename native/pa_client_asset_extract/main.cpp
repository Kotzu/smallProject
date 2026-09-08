#include <StormLib.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace {

struct ClientMapRecord {
    std::uint32_t map_id = 0;
    std::string internal_name;
};

struct MapAssetInventory {
    ClientMapRecord map;
    bool wdt_present = false;
    std::vector<std::pair<int, int>> adt_tiles;
};

std::vector<unsigned char> read_file(HANDLE archive, const std::string& asset) {
    HANDLE file = nullptr;
    if (!SFileOpenFileEx(archive, asset.c_str(), SFILE_OPEN_FROM_MPQ, &file)) {
        return {};
    }
    const DWORD size = SFileGetFileSize(file, nullptr);
    if (size == SFILE_INVALID_SIZE) {
        SFileCloseFile(file);
        throw std::runtime_error("cannot read asset size: " + asset);
    }
    std::vector<unsigned char> bytes(size);
    DWORD read = 0;
    const bool ok = SFileReadFile(file, bytes.data(), size, &read, nullptr) != FALSE;
    SFileCloseFile(file);
    if (!ok || read != size) {
        throw std::runtime_error("cannot read complete asset: " + asset);
    }
    return bytes;
}

std::vector<unsigned char> read_first_file(
    const std::vector<HANDLE>& archives,
    const std::string& asset) {
    for (HANDLE archive : archives) {
        auto bytes = read_file(archive, asset);
        if (!bytes.empty()) {
            return bytes;
        }
    }
    return {};
}

bool asset_exists(const std::vector<HANDLE>& archives, const std::string& asset) {
    return std::any_of(
        archives.begin(), archives.end(),
        [&](HANDLE archive) { return SFileHasFile(archive, asset.c_str()) != FALSE; }
    );
}

std::uint32_t read_u32(const std::vector<unsigned char>& bytes, std::size_t offset) {
    if (offset > bytes.size() || bytes.size() - offset < sizeof(std::uint32_t)) {
        throw std::runtime_error("Map.dbc integer is outside the asset");
    }
    std::uint32_t value = 0;
    std::memcpy(&value, bytes.data() + offset, sizeof(value));
    return value;
}

std::vector<ClientMapRecord> parse_map_dbc(
    const std::vector<unsigned char>& bytes) {
    if (bytes.size() < 20 || std::memcmp(bytes.data(), "WDBC", 4) != 0) {
        throw std::runtime_error("client Map.dbc is not a WDBC table");
    }
    const std::uint32_t record_count = read_u32(bytes, 4);
    const std::uint32_t field_count = read_u32(bytes, 8);
    const std::uint32_t record_size = read_u32(bytes, 12);
    const std::uint32_t string_size = read_u32(bytes, 16);
    if (field_count < 2 || record_size < 8) {
        throw std::runtime_error("client Map.dbc record layout is invalid");
    }
    const std::size_t records_start = 20;
    const std::size_t records_size =
        static_cast<std::size_t>(record_count) * record_size;
    if (
        record_count != 0
        && records_size / record_count != record_size
    ) {
        throw std::runtime_error("client Map.dbc record length overflows");
    }
    const std::size_t strings_start = records_start + records_size;
    const std::size_t strings_stop = strings_start + string_size;
    if (
        strings_start < records_start
        || strings_stop < strings_start
        || strings_stop != bytes.size()
    ) {
        throw std::runtime_error("client Map.dbc byte length is invalid");
    }

    std::vector<ClientMapRecord> maps;
    maps.reserve(record_count);
    for (std::uint32_t index = 0; index < record_count; ++index) {
        const std::size_t record_offset = records_start
            + static_cast<std::size_t>(index) * record_size;
        const std::uint32_t map_id = read_u32(bytes, record_offset);
        const std::uint32_t name_offset = read_u32(bytes, record_offset + 4);
        if (name_offset >= string_size) {
            throw std::runtime_error("client Map.dbc map name offset is invalid");
        }
        const std::size_t name_start = strings_start + name_offset;
        const auto terminator = std::find(
            bytes.begin() + static_cast<std::ptrdiff_t>(name_start),
            bytes.begin() + static_cast<std::ptrdiff_t>(strings_stop),
            static_cast<unsigned char>(0)
        );
        if (terminator == bytes.begin() + static_cast<std::ptrdiff_t>(strings_stop)) {
            throw std::runtime_error("client Map.dbc map name is unterminated");
        }
        const std::string internal_name(
            bytes.begin() + static_cast<std::ptrdiff_t>(name_start),
            terminator
        );
        if (internal_name.empty()) {
            throw std::runtime_error("client Map.dbc map name is empty");
        }
        maps.push_back({map_id, internal_name});
    }
    std::sort(maps.begin(), maps.end(), [](const auto& left, const auto& right) {
        return std::tie(left.map_id, left.internal_name)
            < std::tie(right.map_id, right.internal_name);
    });
    const auto duplicate = std::adjacent_find(
        maps.begin(), maps.end(), [](const auto& left, const auto& right) {
            return left.map_id == right.map_id;
        }
    );
    if (duplicate != maps.end()) {
        throw std::runtime_error("client Map.dbc contains duplicate map IDs");
    }
    return maps;
}

std::string json_escape(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size());
    constexpr char hex[] = "0123456789abcdef";
    for (const unsigned char character : value) {
        switch (character) {
            case '\"': escaped += "\\\""; break;
            case '\\': escaped += "\\\\"; break;
            case '\b': escaped += "\\b"; break;
            case '\f': escaped += "\\f"; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default:
                if (character < 0x20) {
                    escaped += "\\u00";
                    escaped += hex[(character >> 4) & 0x0f];
                    escaped += hex[character & 0x0f];
                } else {
                    escaped += static_cast<char>(character);
                }
        }
    }
    return escaped;
}

MapAssetInventory inventory_map_assets(
    const std::vector<HANDLE>& archives,
    const ClientMapRecord& map) {
    const std::string prefix = "World\\Maps\\" + map.internal_name + "\\";
    MapAssetInventory inventory;
    inventory.map = map;
    inventory.wdt_present = asset_exists(
        archives,
        prefix + map.internal_name + ".wdt"
    );
    for (int grid_x = 0; grid_x < 64; ++grid_x) {
        for (int grid_y = 0; grid_y < 64; ++grid_y) {
            const std::string asset = prefix + map.internal_name + "_"
                + std::to_string(grid_x) + "_" + std::to_string(grid_y) + ".adt";
            if (asset_exists(archives, asset)) {
                inventory.adt_tiles.emplace_back(grid_x, grid_y);
            }
        }
    }
    return inventory;
}

void print_world_inventory(const std::vector<HANDLE>& archives) {
    const auto map_dbc = read_first_file(archives, "DBFilesClient\\Map.dbc");
    if (map_dbc.empty()) {
        throw std::runtime_error("client Map.dbc is absent from the MPQ set");
    }
    const auto maps = parse_map_dbc(map_dbc);
    std::cout << "{\"record_type\":\"client_world_asset_inventory\","
              << "\"schema_version\":\"1.0\","
              << "\"asset_container\":\"mpq\","
              << "\"map_count\":" << maps.size() << ",\"maps\":[";
    bool first_map = true;
    for (const auto& map : maps) {
        const auto inventory = inventory_map_assets(archives, map);
        if (!first_map) {
            std::cout << ',';
        }
        first_map = false;
        std::cout << "{\"map_id\":" << inventory.map.map_id
                  << ",\"internal_name\":\""
                  << json_escape(inventory.map.internal_name) << "\""
                  << ",\"wdt_present\":"
                  << (inventory.wdt_present ? "true" : "false")
                  << ",\"adt_count\":" << inventory.adt_tiles.size()
                  << ",\"adt_bounds\":";
        if (inventory.adt_tiles.empty()) {
            std::cout << "null";
        } else {
            int min_x = std::numeric_limits<int>::max();
            int min_y = std::numeric_limits<int>::max();
            int max_x = std::numeric_limits<int>::min();
            int max_y = std::numeric_limits<int>::min();
            for (const auto& [grid_x, grid_y] : inventory.adt_tiles) {
                min_x = std::min(min_x, grid_x);
                min_y = std::min(min_y, grid_y);
                max_x = std::max(max_x, grid_x);
                max_y = std::max(max_y, grid_y);
            }
            std::cout << '[' << min_x << ',' << min_y << ',' << max_x << ',' << max_y << ']';
        }
        std::cout << ",\"tiles\":[";
        bool first_tile = true;
        for (const auto& [grid_x, grid_y] : inventory.adt_tiles) {
            if (!first_tile) {
                std::cout << ',';
            }
            first_tile = false;
            std::cout << "{\"grid_x\":" << grid_x
                      << ",\"grid_y\":" << grid_y << '}';
        }
        std::cout << "]}";
    }
    std::cout << "],\"execution_authority\":false}\n";
}

void write_asset(const fs::path& destination, const std::vector<unsigned char>& bytes) {
    std::ofstream output(destination, std::ios::binary | std::ios::trunc);
    output.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size())
    );
    if (!output) {
        throw std::runtime_error("cannot write asset: " + destination.string());
    }
}

void extract_map_assets(
    const std::vector<HANDLE>& archives,
    const std::string& requested_map,
    const fs::path& output_root) {
    const auto map_dbc = read_first_file(archives, "DBFilesClient\\Map.dbc");
    if (map_dbc.empty()) {
        throw std::runtime_error("client Map.dbc is absent from the MPQ set");
    }
    const auto maps = parse_map_dbc(map_dbc);
    const auto match = std::find_if(
        maps.begin(), maps.end(), [&](const auto& map) {
            return map.internal_name == requested_map;
        }
    );
    if (match == maps.end()) {
        throw std::runtime_error("requested map is absent from client Map.dbc");
    }
    const auto inventory = inventory_map_assets(archives, *match);
    if (!inventory.wdt_present && inventory.adt_tiles.empty()) {
        throw std::runtime_error("requested map has no WDT or ADT assets");
    }
    if (fs::exists(output_root)) {
        throw std::runtime_error("map extraction destination already exists");
    }
    fs::create_directories(output_root);
    const std::string prefix = "World\\Maps\\" + requested_map + "\\";
    bool wdt_extracted = false;
    if (inventory.wdt_present) {
        const std::string leaf = requested_map + ".wdt";
        const auto bytes = read_first_file(archives, prefix + leaf);
        if (bytes.empty()) {
            throw std::runtime_error("inventoried WDT cannot be read");
        }
        write_asset(output_root / leaf, bytes);
        wdt_extracted = true;
    }
    std::size_t adt_extracted = 0;
    for (const auto& [grid_x, grid_y] : inventory.adt_tiles) {
        const std::string leaf = requested_map + "_" + std::to_string(grid_x)
            + "_" + std::to_string(grid_y) + ".adt";
        const auto bytes = read_first_file(archives, prefix + leaf);
        if (bytes.empty()) {
            throw std::runtime_error("inventoried ADT cannot be read: " + leaf);
        }
        write_asset(output_root / leaf, bytes);
        ++adt_extracted;
    }
    std::cout << "{\"record_type\":\"client_map_asset_extraction\","
              << "\"schema_version\":\"1.0\","
              << "\"map_id\":" << inventory.map.map_id
              << ",\"internal_name\":\"" << json_escape(requested_map) << "\""
              << ",\"wdt_extracted\":" << (wdt_extracted ? "true" : "false")
              << ",\"adt_extracted\":" << adt_extracted
              << ",\"output_root\":\"" << json_escape(output_root.string()) << "\""
              << ",\"execution_authority\":false}\n";
}

void print_tirisfal_candidates(HANDLE archive) {
    SFILE_FIND_DATA data{};
    HANDLE search = SFileFindFirstFile(
        archive, "Interface\\WorldMap\\Tirisfal\\*", &data, nullptr
    );
    if (search == nullptr) {
        return;
    }
    do {
        std::cerr << "candidate: " << data.cFileName << "\n";
    } while (SFileFindNextFile(search, &data));
    SFileFindClose(search);
}

}  // namespace

int main(int argc, char** argv) {
    const bool single_asset = argc == 5 && std::string(argv[1]) == "--file";
    const bool inventory_world =
        argc == 3 && std::string(argv[1]) == "--inventory-world";
    const bool extract_map = argc == 5 && std::string(argv[1]) == "--extract-map";
    if (
        (argc != 3 || inventory_world)
        && !single_asset
        && !inventory_world
        && !extract_map
    ) {
        std::cerr << "usage: pa_client_asset_extract WOW_DATA_ROOT OUTPUT_ROOT\n"
                  << "   or: pa_client_asset_extract --file WOW_DATA_ROOT ASSET OUTPUT\n"
                  << "   or: pa_client_asset_extract --inventory-world WOW_DATA_ROOT\n"
                  << "   or: pa_client_asset_extract --extract-map WOW_DATA_ROOT MAP OUTPUT_ROOT\n";
        return 2;
    }

    const fs::path data_root = fs::absolute(
        single_asset || inventory_world || extract_map ? argv[2] : argv[1]
    );
    const fs::path output_root = fs::absolute(
        extract_map
            ? fs::path(argv[4])
            : single_asset
            ? fs::path(argv[4]).parent_path()
            : (inventory_world ? fs::path() : fs::path(argv[2]))
    );
    const std::array<const char*, 9> archives = {
        "enGB/patch-enGB-2.MPQ", "enGB/patch-enGB.MPQ",
        "enGB/expansion-locale-enGB.MPQ", "enGB/locale-enGB.MPQ",
        "enGB/base-enGB.MPQ",
        "patch-2.MPQ", "patch.MPQ", "expansion.MPQ", "common.MPQ"
    };
    std::vector<HANDLE> opened;
    try {
        for (const char* archive_name : archives) {
            HANDLE archive = nullptr;
            const fs::path path = data_root / archive_name;
            if (!SFileOpenArchive(path.string().c_str(), 0, MPQ_OPEN_READ_ONLY, &archive)) {
                throw std::runtime_error("cannot open archive: " + path.string());
            }
            opened.push_back(archive);
        }

        if (inventory_world) {
            print_world_inventory(opened);
            for (HANDLE archive : opened) {
                SFileCloseArchive(archive);
            }
            return 0;
        }

        if (extract_map) {
            extract_map_assets(opened, argv[3], output_root);
            for (HANDLE archive : opened) {
                SFileCloseArchive(archive);
            }
            return 0;
        }

        if (single_asset) {
            const std::string asset = argv[3];
            std::vector<unsigned char> bytes;
            for (HANDLE archive : opened) {
                bytes = read_file(archive, asset);
                if (!bytes.empty()) {
                    break;
                }
            }
            if (bytes.empty()) {
                throw std::runtime_error("asset not found: " + asset);
            }
            const fs::path destination = fs::absolute(argv[4]);
            fs::create_directories(destination.parent_path());
            std::ofstream output(destination, std::ios::binary | std::ios::trunc);
            output.write(reinterpret_cast<const char*>(bytes.data()),
                         static_cast<std::streamsize>(bytes.size()));
            if (!output) {
                throw std::runtime_error("cannot write asset: " + destination.string());
            }
            for (HANDLE archive : opened) {
                SFileCloseArchive(archive);
            }
            std::cout << "asset=" << asset << " output=" << destination.string() << "\n";
            return 0;
        }

        fs::create_directories(output_root);
        int extracted = 0;
        const auto extract_asset = [&](const std::string& asset, const fs::path& destination) {
            std::vector<unsigned char> bytes;
            for (HANDLE archive : opened) {
                bytes = read_file(archive, asset);
                if (!bytes.empty()) {
                    break;
                }
            }
            if (bytes.empty()) {
                std::cerr << "missing: " << asset << "\n";
                return false;
            }
            std::ofstream output(destination, std::ios::binary | std::ios::trunc);
            output.write(reinterpret_cast<const char*>(bytes.data()),
                         static_cast<std::streamsize>(bytes.size()));
            if (!output) {
                throw std::runtime_error("cannot write asset: " + destination.string());
            }
            return true;
        };
        for (int tile = 1; tile <= 12; ++tile) {
            const std::string asset =
                "Interface\\WorldMap\\Tirisfal\\Tirisfal" + std::to_string(tile) + ".blp";
            const fs::path destination = output_root / ("Tirisfal" + std::to_string(tile) + ".blp");
            if (extract_asset(asset, destination)) {
                ++extracted;
            }
        }
        const std::array<const char*, 16> overlays = {
            "Bulwark", "VenomwebVale", "Monastary", "ScarletWatchPost",
            "CrusaderOutpost", "BalnirFarmstead", "BrightwaterLake",
            "RuinsOfLordaeron", "GarrensHaunt", "Brill", "ColdHearthManor",
            "NightmareVale", "StillwaterPond", "AgamandMills",
            "SollidenFarmstead", "Deathknell"
        };
        int overlay_extracted = 0;
        for (const char* overlay : overlays) {
            for (int tile = 1; tile <= 4; ++tile) {
                const std::string leaf = std::string(overlay) + std::to_string(tile) + ".blp";
                const std::string asset = "Interface\\WorldMap\\Tirisfal\\" + leaf;
                if (!extract_asset(asset, output_root / leaf)) {
                    break;
                }
                ++overlay_extracted;
            }
        }
        for (HANDLE archive : opened) {
            print_tirisfal_candidates(archive);
        }
        for (HANDLE archive : opened) {
            SFileCloseArchive(archive);
        }
        std::cout << "base_extracted=" << extracted
                  << " overlay_extracted=" << overlay_extracted
                  << " output=" << output_root.string() << "\n";
        return extracted == 12 && overlay_extracted >= 16 ? 0 : 1;
    } catch (const std::exception& error) {
        for (HANDLE archive : opened) {
            SFileCloseArchive(archive);
        }
        std::cerr << error.what() << "\n";
        return 1;
    }
}
