"""Optional asynchronous asset observer, never a navigation/input provider."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from math import isfinite
from pathlib import Path

from persistent_navmesh_awareness import PersistentNavmeshAwarenessService

from perfect_assassin.adapter.spatial_sonar import (
    observation_key,
    sonar_applicable,
    sonar_record,
)
from perfect_assassin.movement.world_pack_runtime import load_world_pack_runtime_profile
from perfect_assassin.runtime_paths import external_runtime_root

ROOT = Path(__file__).resolve().parents[2]
WORKER = (
    ROOT / "data/runtime/native-build/pa-nav-height-observer/Debug/pa_nav_probe.exe"
)
WORKER_SHA256 = "a19c6947d7bbbe4ecd1702477cf2c3a6bb431a6712ba98df18ddd678565a1404"


class SpatialSonarObserver:
    def __init__(self, profile, *, wmo_bundle_spec=None, vertical_continuity=False):
        self.profile = profile
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pa-spatial-sonar"
        )
        self.future = None
        self.latest = None
        self.service = None
        self.binding = None
        self.service_map = None
        self.next_query_s = 0.0
        self.last_error = None
        self.closed = False
        self.wmo_bundle_spec = wmo_bundle_spec
        self.wmo_bundle = None
        self.wmo_load_attempted = False
        self.wmo_error = None
        self.transition_observer = None
        if vertical_continuity:
            from vertical_transition_observer import VerticalTransitionObserver
            self.transition_observer = VerticalTransitionObserver()

    def _wmo_association(self, sample, map_id):
        if self.wmo_bundle_spec is None:
            return None
        # Called only inside the existing background query, never on Tk/capture.
        if not self.wmo_load_attempted:
            self.wmo_load_attempted = True
            try:
                from perfect_assassin.adapter.wmo_bundle import load_wmo_bundle
                from perfect_assassin.movement.world_structure_index import (
                    load_world_structure_index,
                )

                spec = self.wmo_bundle_spec
                if isinstance(spec, (str, Path)):
                    from perfect_assassin.adapter.wmo_bundle import read_bounded

                    spec = json.loads(read_bounded(spec, 16384))
                if not isinstance(spec, dict) or set(spec) != {
                    "index",
                    "directory",
                    "sha256",
                }:
                    raise ValueError("invalid optional WMO configuration")

                def local_path(value):
                    path = Path(value)
                    return path if path.is_absolute() else ROOT / path

                index = load_world_structure_index(
                    local_path(spec["index"]),
                    pack=self.binding.pack,
                    schema_path=ROOT / "contracts/world-structure-index.schema.json",
                )
                self.wmo_bundle = load_wmo_bundle(
                    local_path(spec["directory"]),
                    expected_sha256=spec["sha256"],
                    pack=self.binding.pack,
                    index=index,
                )
            except Exception as error:  # noqa: BLE001 - optional evidence must not suppress base sonar
                self.wmo_error = type(error).__name__ + ": " + str(error)
        if self.wmo_bundle is None:
            return None
        try:
            result = self.wmo_bundle.query(
                map_id=map_id,
                xy=(sample.source.x, sample.source.y),
                candidates=sample.vertical_candidates,
            )
            self.wmo_error = None
            return result
        except Exception as error:  # noqa: BLE001 - no match/query error is not free space
            self.wmo_error = type(error).__name__ + ": " + str(error)
            return None

    def _query(self, key, xy, pose_s, requested_s, seed_z):
        try:
            return self._query_inner(key, xy, pose_s, requested_s, seed_z)
        except Exception:
            if self.transition_observer is not None:
                self.transition_observer.close()
            if self.service is not None:
                self.service.close()
                self.service = None
            raise

    def _query_inner(self, key, xy, pose_s, requested_s, seed_z):
        if self.binding is None:
            if hashlib.sha256(WORKER.read_bytes()).hexdigest() != WORKER_SHA256:
                raise ValueError("spatial observer worker hash mismatch")
            self.binding = load_world_pack_runtime_profile(
                Path(self.profile),
                store_root=external_runtime_root(ROOT) / "worldpacks",
                profile_schema_path=ROOT
                / "contracts/world-pack-runtime-profile.schema.json",
                pack_schema_path=ROOT / "contracts/standalone-world-pack.schema.json",
                catalog_schema_path=ROOT / "contracts/client-world-catalog.schema.json",
            )
        maps = [m for m in self.binding.pack.catalog.maps if m.map_id == key[2]]
        if len(maps) != 1:
            raise ValueError("sonar map does not match verified WorldPack")
        if self.service is not None and self.service_map != key[2]:
            self.service.close()
            self.service = None
        if self.service is None:
            self.service = PersistentNavmeshAwarenessService(
                worker=WORKER,
                nav_root=self.binding.pack.nav_root,
                map_name=maps[0].internal_name,
                protocol_timeout_s=5.0,
                spatial_scan=True,
            )
            self.service_map = key[2]
        if self.closed:
            self.service.close()
            raise RuntimeError("sonar observer closed")
        sample = self.service.sample(*xy, seed_z)
        record = sonar_record(
            sample,
            key=key,
            pack_sha256=self.binding.pack.manifest["content_sha256"],
            pose_xy=xy,
            pose_observed_s=pose_s,
            requested_s=requested_s,
        )
        if self.wmo_bundle_spec is not None:
            record["wmo_surface_association"] = self._wmo_association(sample, key[2])
            record["wmo_surface_error"] = self.wmo_error
        if self.transition_observer is not None:
            self.transition_observer.observe(record, nav_root=self.binding.pack.nav_root,
                                             map_name=maps[0].internal_name)
        return record

    def poll(self, *, labels, map_id, xy, pose_s, now_s):
        if self.closed:
            return None
        key = observation_key(labels, map_id, now_s=now_s)
        if (
            not isinstance(xy, (tuple, list))
            or len(xy) != 2
            or any(
                type(v) not in (float, int) or not isfinite(v)
                for v in (*xy, pose_s, now_s)
            )
            or not 0 <= now_s - pose_s <= 2
        ):
            key = None
        if self.future is not None and self.future.done():
            try:
                self.latest = self.future.result()
                self.last_error = None
            except Exception as error:  # noqa: BLE001 - isolate optional worker failures from pose capture
                self.latest = None
                self.last_error = type(error).__name__ + ": " + str(error)
                self.next_query_s = now_s + 10
            self.future = None
        valid = sonar_applicable(self.latest, key=key, xy=xy, now_s=now_s)
        if key is not None and self.future is None and now_s >= self.next_query_s:
            # This is a declared geometric seed, never an observed actor Z.
            seed = self.latest["resolved_query_xyz"][2] if valid else 100.0
            self.next_query_s = now_s + 1
            self.future = self.executor.submit(
                self._query, key, tuple(xy), pose_s, now_s, seed
            )
        return self.latest if valid else None

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.service is not None:
            self.service.close()
        if self.transition_observer is not None:
            # Queue cleanup behind any active query; never race its pipe on Tk.
            self.executor.submit(self.transition_observer.close)
        self.executor.shutdown(wait=False, cancel_futures=self.transition_observer is None)
