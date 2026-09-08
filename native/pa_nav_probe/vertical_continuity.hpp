// Included inside the probe namespace after shared read-only map helpers.
// Separate protocol, never a movement route or an actor-height selection.
int run_vertical_continuity_server(const char* root, const char* name) {
    PathfindResultType created = 255;
    auto* map = pathfind_new_map(root, name, &created);
    require_success(created, "create_continuity_map");
    if (!map) throw std::runtime_error("missing continuity map");
    struct Guard { pathfind::Map* map; ~Guard() { pathfind_free_map(map); } } guard{map};
    std::cout << "{\"status\":\"READY\",\"protocol\":1,\"mode\":\"VERTICAL_CONTINUITY\"}\n" << std::flush;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line == "QUIT") break;
        unsigned long long sequence = 0;
        std::array<float, 3> source{}, destination{};
        try {
            if (line.size() > 512) throw std::runtime_error("oversized request");
            std::istringstream in(line);
            std::string extra;
            if (!(in >> sequence >> source[0] >> source[1] >> source[2]
                     >> destination[0] >> destination[1] >> destination[2]) || (in >> extra))
                throw std::runtime_error("malformed request");
            for (const auto& point : {source, destination})
                for (float v : point)
                    if (!std::isfinite(v) || std::abs(v) > 100000)
                        throw std::runtime_error("invalid coordinate");
            if (std::hypot(source[0]-destination[0], source[1]-destination[1]) > 64)
                throw std::runtime_error("transition exceeds horizontal scope");
            float ax, ay, bx, by;
            require_success(pathfind_load_adt_at(map, source[0], source[1], &ax, &ay), "load_start");
            require_success(pathfind_load_adt_at(map, destination[0], destination[1], &bx, &by), "load_stop");
            for (int x = static_cast<int>(std::min(ax,bx)); x <= static_cast<int>(std::max(ax,bx)); ++x)
                for (int y = static_cast<int>(std::min(ay,by)); y <= static_cast<int>(std::max(ay,by)); ++y) {
                    float loaded_x, loaded_y;
                    require_success(pathfind_load_adt(map,x,y,&loaded_x,&loaded_y), "load_local_rectangle");
                }
            const auto& query = map->GetNavMeshQuery();
            dtQueryFilter filter; // Neutral costs: topology diagnostic, not v34 movement preferences.
            constexpr float extents[] = {5,5,5};
            const auto a = to_recast(source[0],source[1],source[2]);
            const auto b = to_recast(destination[0],destination[1],destination[2]);
            std::array<float,3> start{}, stop{};
            dtPolyRef start_ref=0, stop_ref=0;
            require_detour(query.findNearestPoly(a.data(),extents,&filter,&start_ref,start.data()), "start_poly");
            require_detour(query.findNearestPoly(b.data(),extents,&filter,&stop_ref,stop.data()), "stop_poly");
            if (!start_ref || !stop_ref) throw std::runtime_error("endpoint has no polygon");
            constexpr int capacity=512;
            std::array<dtPolyRef,capacity> polys{};
            int count=0;
            const auto path_status=query.findPath(start_ref,stop_ref,start.data(),stop.data(),&filter,polys.data(),&count,capacity);
            require_detour(path_status,"path");
            if (!count) throw std::runtime_error("no path");
            const bool limited=(path_status & (DT_BUFFER_TOO_SMALL|DT_OUT_OF_NODES|DT_PARTIAL_RESULT)) != 0;
            const bool reaches=polys[count-1]==stop_ref && !limited;
            auto path_stop=stop;
            if (!reaches) {
                bool over=false;
                require_detour(query.closestPointOnPoly(polys[count-1],stop.data(),path_stop.data(),&over),"partial_stop");
            }
            std::array<float,capacity*3> points{};
            std::array<unsigned char,capacity> flags{};
            std::array<dtPolyRef,capacity> refs{};
            int point_count=0;
            const auto straight_status=query.findStraightPath(start.data(),path_stop.data(),polys.data(),count,
                points.data(),flags.data(),refs.data(),&point_count,capacity);
            require_detour(straight_status,"funnel");
            if (!point_count) throw std::runtime_error("empty funnel");
            const bool straight_limited=(straight_status & (DT_BUFFER_TOO_SMALL|DT_PARTIAL_RESULT)) != 0;
            double length=0;
            for(int i=1;i<point_count;++i) {
                double squared=0;
                for(int k=0;k<3;++k) { double d=points[i*3+k]-points[(i-1)*3+k]; squared+=d*d; }
                length+=std::sqrt(squared);
            }
            std::cout << std::fixed << std::setprecision(6)
                << "{\"status\":\"OK\",\"sequence\":" << sequence << ",\"requested_start\":";
            print_point(source); std::cout << ",\"requested_stop\":"; print_point(destination);
            std::cout << ",\"resolved_start\":"; print_point(to_wow(start.data()));
            std::cout << ",\"resolved_stop\":"; print_point(to_wow(stop.data()));
            std::cout << ",\"path_stop\":"; print_point(to_wow(path_stop.data()));
            std::cout << ",\"start_poly\":\"" << start_ref << "\",\"stop_poly\":\"" << stop_ref
                << "\",\"complete\":" << (reaches && !straight_limited ? "true":"false")
                << ",\"search_limited\":" << (limited || straight_limited ? "true":"false")
                << ",\"polygon_count\":" << count << ",\"point_count\":" << point_count
                << ",\"funnel_length_yards\":" << length
                << ",\"source\":\"CLIENT_NAVMESH_TOPOLOGY\",\"observed_actor_z\":null,"
                << "\"floor_id\":null,\"execution_authority\":false}\n" << std::flush;
        } catch(const std::exception&) {
            std::cout << "{\"status\":\"ERROR\",\"sequence\":" << sequence
                << ",\"detail\":\"continuity query unresolved\"}\n" << std::flush;
        }
    }
    return 0;
}
