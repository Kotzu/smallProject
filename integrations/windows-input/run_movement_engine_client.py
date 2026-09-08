from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from math import cos, degrees, hypot, isfinite, pi, sin
import os
import argparse
from pathlib import Path
from queue import Empty, SimpleQueue
import subprocess
import sys
from threading import Event, Thread
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback
from typing import NamedTuple
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.movement_lab import MovementLabSnapshot
from perfect_assassin.movement.manual_path_recording import ManualPathRecording
from perfect_assassin.movement.operator_map_knowledge import (
    MapKnowledgeVertex, OperatorMapKnowledge,
)
from perfect_assassin.movement.operator_path import OperatorAuthoredPath
from perfect_assassin.movement.road_semantic_planner import ClientRoadSemanticPlanner
from perfect_assassin.movement.world_map_atlas import AtlasViewport, WorldMapAtlasGeometry
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.semantic_live_gate import (
    SemanticLiveGateIdentity,
    build_semantic_live_gate_record as _build_semantic_live_gate_record,
    semantic_live_gate_identity,
    semantic_live_gate_open,
)
from perfect_assassin.movement.stationary_pose import (
    LivePoseSample as LiveMapPose,
    evaluate_stationary_pose,
    load_expected_stationary_location,
    read_live_pose_file,
)
from perfect_assassin.movement.world_pack_viewer import (
    WorldPackViewerLaunch,
    build_world_pack_viewer_launch,
)
from perfect_assassin.movement.world_map_registry import (
    inspect_world_map_profile,
    load_world_map_registry,
)
from perfect_assassin.movement.zone_transform import tbc243_zone_transform
from perfect_assassin.brain.leveling import (
    LevelingBrain,
    LevelingRequest,
)
from perfect_assassin.knowledge import (
    load_knowledge_broker_catalog,
    load_leveling_plan,
)
from perfect_assassin.adapter.world_map_zone_catalog import (
    load_world_map_zone_transform_catalog,
)
from perfect_assassin.runtime_paths import (
    external_dependencies_root,
    external_runtime_root,
)
from run_navmesh_roaming import ClientVisibleStateError
from run_nav_viewer_pose_once import capture_pose_record as capture_nav_viewer_pose
from predator_codex_driver import ALLOWED_KEYS as CODEX_DRIVER_KEYS
from stay_online_control import StayOnlinePanel
from PIL import Image, ImageTk
from movement_map_rendering import render_atlas_image


LIVE_MAP_RENEW_BEFORE_EXPIRY_S = 300.0


def _session_authorization_remaining_s(
    path: Path, *, now: datetime | None = None,
) -> float | None:
    """Return the read-only session lifetime without granting any authority."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        approval = record["approval"]
        expires_at = datetime.fromisoformat(
            str(approval["expires_at"]).replace("Z", "+00:00")
        )
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or expires_at.tzinfo is None:
            return None
        return (expires_at - current).total_seconds()
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def build_semantic_live_gate_record(
    identity: SemanticLiveGateIdentity,
    *,
    validation_result: Path,
    status: str,
    live_authority_enabled: bool,
) -> dict[str, object]:
    """Stable Control Center facade for semantic-gate record construction."""

    return _build_semantic_live_gate_record(
        identity,
        validation_result=validation_result,
        status=status,
        live_authority_enabled=live_authority_enabled,
    )


def rebind_semantic_live_gate_authority(
    record: dict[str, object],
    *,
    expected: SemanticLiveGateIdentity,
    enabled: bool,
) -> dict[str, object]:
    """Change only operator authority on an already verified semantic gate.

    The disabled form is first probed as enabled.  That makes the existing
    validation-result hash and the exact WorldPack/worker identity prove
    themselves before the checkbox may re-arm them.  No route is regenerated
    and no stale or edited validation can be promoted by this operation.
    """

    authority_probe = dict(record)
    authority_probe["live_authority_enabled"] = True
    if not semantic_live_gate_open(authority_probe, expected=expected):
        raise ValueError(
            "semantic validation must still match the selected WorldPack and worker"
        )
    validation_result = record.get("validation_result")
    status = record.get("status")
    if not isinstance(validation_result, str) or not isinstance(status, str):
        raise ValueError("semantic gate is missing its validation result")
    return _build_semantic_live_gate_record(
        expected,
        validation_result=Path(validation_result),
        status=status,
        live_authority_enabled=enabled,
    )


def _world_map_readiness_label(profile: object) -> str:
    """Show geometry readiness separately from semantic travel readiness."""

    readiness = inspect_world_map_profile(profile)
    if readiness.autonomous_ready:
        return "GATA DE MERS"
    if readiness.topographic_ready:
        return "SE VEDE • NU ȘTIE ÎNCĂ LOCURILE"
    return "DOAR SE VEDE"


RUNTIME = ROOT / "data" / "runtime" / "operator"
EXTERNAL_RUNTIME_ROOT = external_runtime_root(ROOT)
EXTERNAL_DEPENDENCIES_ROOT = external_dependencies_root(ROOT)
CONTROL_FILE = RUNTIME / "movement-engine-control.json"
COMBAT_CONTROL_FILE = RUNTIME / "predator-ui-control.json"
SESSION_AUTH = RUNTIME / "tbc_243_lab.active.json"
SESSION_RECEIPT = RUNTIME / "lab-client-launch-receipt.json"
MOVEMENT_STATE = ROOT / "data" / "runtime" / "movement-lab" / "latest.json"
ROUTE_RUNNER = ROOT / "integrations" / "windows-input" / "run_navmesh_roaming.py"
JOURNEY_COMBAT_SUPERVISOR = (
    ROOT / "integrations" / "windows-input"
    / "run_journey_combat_supervisor.py"
)
COMBAT_RUNNER = ROOT / "integrations" / "windows-input" / "run_controlled_combat.py"
MANUAL_RECORDER = (
    ROOT / "integrations" / "windows-input" / "run_manual_path_recorder.py"
)
STRUCTURE_AWARENESS_SERVICE = (
    ROOT / "integrations" / "windows-input" / "run_structure_awareness_service.py"
)
OVERLAY_RUNNER = ROOT / "integrations" / "windows-input" / "run_movement_lab.py"
OVERLAY_CONTROL = RUNTIME / "movement-lab-overlay-control.json"
NAV_VIEWER = Path(
    EXTERNAL_DEPENDENCIES_ROOT / "navigation" / "namigator"
    / "build-pa-pinned-debug-v4" / "MapViewer" / "Debug" / "MapViewer.exe"
)
NAV_VIEWER_POSE_ONCE = (
    ROOT / "integrations" / "windows-input" / "run_nav_viewer_pose_once.py"
)
NAV_VIEWER_LIVE_BRIDGE = (
    ROOT / "integrations" / "windows-input" / "run_nav_viewer_live_bridge.py"
)
NAV_VIEWER_STATE = RUNTIME / "nav-viewer-live-state.txt"
NAV_VIEWER_DIAGNOSTIC = RUNTIME / "nav-viewer-diagnostic.json"
CONTROL_CENTER_LIVE_DIAGNOSTIC = (
    RUNTIME / "movement-engine-live-pose.json"
)
CODEX_DRIVER_ARM_FILE = RUNTIME / "predator-codex-driver-arm.json"
CODEX_DRIVER_ALLOWED_CONTROLS = tuple(sorted(CODEX_DRIVER_KEYS))
WORLD_PACK_PROFILE = (
    ROOT / "config" / "navigation"
    / "world-pack-runtime-tbc243-azeroth-full-v3.json"
)
WORLD_PACK_STORE = EXTERNAL_RUNTIME_ROOT / "worldpacks"
WORLD_STRUCTURE_INDEX = (
    ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606"
    / "azeroth-full-v3-world-structure-index-v1.json"
)
WORLD_MAP_REGISTRY = ROOT / "config" / "navigation" / "world-map-registry-tbc243.json"
WORLD_MAP_REGISTRY_SCHEMA = ROOT / "contracts" / "world-map-registry.schema.json"
STRUCTURE_ACCESS_GRAPH: Path | None = (
    ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606"
    / "azeroth-full-v3-structure-access-graph-v1.json"
)
OPERATOR = ROOT / "scripts" / "Invoke-LabClientOperator.ps1"
GODMODE = ROOT / "scripts" / "Set-LabCombatProtection.ps1"
WORKER = ROOT / "data" / "runtime" / "native-build" / "pa_nav_probe-v34" / "Debug" / "pa_nav_probe.exe"
WORKER_V35 = ROOT / "data" / "runtime" / "native-build" / "pa_nav_probe-v35" / "Debug" / "pa_nav_probe.exe"
NAVIGATION_WORKER_OVERRIDE: Path | None = None
HORIZONTAL_CLEARANCE_CANDIDATE = (
    ROOT / "data" / "runtime" / "native-build" / "pa-nav-clearance-test"
    / "Debug" / "pa_nav_probe.exe"
)
HORIZONTAL_CLEARANCE_CANDIDATE_SHA256 = "ca2b19def8517afbdad9ded7facde66e7e86d74182744a426a527f03db7935f3"


def _navigation_worker() -> Path:
    return NAVIGATION_WORKER_OVERRIDE or WORKER


def _configure_horizontal_clearance_candidate(enabled: bool) -> None:
    global NAVIGATION_WORKER_OVERRIDE
    if enabled:
        candidate = HORIZONTAL_CLEARANCE_CANDIDATE.resolve(strict=True)
        if _file_sha256(candidate) != HORIZONTAL_CLEARANCE_CANDIDATE_SHA256:
            raise RuntimeError("candidatul de clearance nu corespunde executabilului verificat")
        NAVIGATION_WORKER_OVERRIDE = candidate
    else:
        NAVIGATION_WORKER_OVERRIDE = None
WORLD_MAP_ATLAS = Path(
    EXTERNAL_RUNTIME_ROOT / "assets" / "tbc243" / "worldmap" / "Tirisfal"
    / "Tirisfal-fully-explored.png"
)
ROAD_SEMANTIC_ATLAS = WORLD_MAP_ATLAS.with_name("Tirisfal-road-semantics.png")
SEMANTIC_LOCATIONS = ROOT / "config" / "movement-lab" / "semantic-destinations-tbc243.json"
SEMANTIC_SEQUENCE_FILE = ROOT / "data" / "runtime" / "movement-lab" / "semantic-destination-sequence.json"
WORLD_MAP_ZONE_TRANSFORM_CATALOG = (
    ROOT / "config" / "pose" / "world-map-zone-transforms-tbc243-8606.json"
)
WORLD_MAP_ZONE_TRANSFORM_SCHEMA = (
    ROOT / "contracts" / "world-map-zone-transform-catalog.schema.json"
)
ZYGOR_GUIDE_COVERAGE = (
    ROOT / "data" / "runtime" / "navigation-f3b"
    / "zygor-guide-coverage-20260901.json"
)
ZYGOR_ROUTE_COVERAGE = (
    ROOT / "data" / "runtime" / "navigation-f3b"
    / "zygor-route-coverage-20260901.json"
)
ZYGOR_ROUTE_TRANSFORM_COVERAGE = (
    ROOT / "data" / "runtime" / "navigation-f3b"
    / "zygor-route-transform-coverage-20260901.json"
)
ZYGOR_NPCDATA_AUDIT = (
    ROOT / "data" / "runtime" / "navigation-f3b"
    / "zygor-npcdata-audit-20260901.json"
)
ZYGOR_WORLD_MAP_RECONCILIATION = (
    ROOT / "data" / "runtime" / "navigation-f3b"
    / "zygor-world-map-reconciliation-20260831.json"
)
SEMANTIC_GATE = RUNTIME / "movement-engine-semantic-gate.json"
CRYPT_TRIAL_GATE_REPORT = (
    ROOT / "data" / "runtime" / "movement-lab"
    / "crypt-egress-live-trial-gate.json"
)
STATIONARY_POSE_REPORT = (
    ROOT / "data" / "runtime" / "movement-lab"
    / "stationary-pose-latest.json"
)
STATIONARY_VALIDATION_LOCATION_ID = "landmark:deathknell-crypt"
ZYGOR_LEVELING_CATALOG = RUNTIME / "zygor-leveling-catalog.json"
LEVELING_PLAN_FILE = RUNTIME / "zygor-leveling-plan.json"
CONTINUOUS_MOTION_AUTHORIZATION_FILE = RUNTIME / "continuous-motion-authorization.json"
CONTINUOUS_MOTION_ARM_FILE = RUNTIME / "continuous-motion-arm.json"
CONTINUOUS_MOTION_REVALIDATION_FILE = RUNTIME / "movement-realm-revalidation.json"
MOTION_ARM_RENEW_LOG = RUNTIME / "movement-arm-renewal.log"
MOTION_ARM_RENEW_INTERVAL_S = 12.0
MOTION_AUTH_RENEW_INTERVAL_S = 8.0 * 60.0
SESSION_RENEW_INTERVAL_S = 20.0 * 60.0
LOG_PATH = RUNTIME / "movement-engine.log"
COMBAT_LOG_PATH = RUNTIME / "predator-ui-combat.log"
MANUAL_RECORDER_LOG = RUNTIME / "manual-path-recorder.log"
MANUAL_RECORDER_CONTROL = RUNTIME / "manual-path-recorder-control.json"
MANUAL_RECORDER_RESULT = (
    ROOT / "data" / "runtime" / "movement-lab" / "manual-path-recording.json"
)
SETTINGS_FILE = RUNTIME / "movement-engine-ui-settings.json"
OPERATOR_PATH_FILE = ROOT / "config" / "movement-lab" / "operator-path-draft.json"
OPERATOR_MAP_KNOWLEDGE_FILE = (
    ROOT / "config" / "movement-lab" / "operator-map-knowledge.json"
)
DRAW_MODES = {
    "Puncte de drum": "waypoint_path",
    "Zonă de plimbare": "roaming_zone",
    "Obstacol": "obstacle",
    "Drum în clădire": "interior_route",
    "Loc de întoarcere": "recovery_anchor",
}

OVERLAY_POLICY_LABELS = {
    "Never": "Niciodată",
    "Only while testing": "Doar când testez",
    "Always": "Mereu",
}
OVERLAY_POLICY_VALUES = {
    label: value for value, label in OVERLAY_POLICY_LABELS.items()
}


def _atomic_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _structure_awareness_worker(profile) -> Path:
    """Resolve an allowlisted worker matching one profile's graph hash.

    Candidate continental graphs were produced with v35 while the promoted
    Azeroth graph remains bound to v34.  Structure awareness is read-only, but
    the service must still reject a worker/graph mismatch.  Only the two
    locally pinned workers are eligible; the graph cannot provide an arbitrary
    executable path.
    """

    graph_path = getattr(profile, "structure_access_graph", None)
    if graph_path is None:
        return WORKER
    try:
        record = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        expected_sha256 = record.get("probe_worker_sha256")
    except (OSError, UnicodeError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("graful structure access nu poate fi citit") from error
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise RuntimeError("graful structure access nu are hash worker valid")
    for candidate in (WORKER, WORKER_V35):
        if candidate.is_file() and _file_sha256(candidate) == expected_sha256:
            return candidate
    raise RuntimeError(
        "graful structure access nu corespunde unui worker local allowlisted"
    )


def _zygor_guide_coverage_text(path: Path = ZYGOR_GUIDE_COVERAGE) -> str:
    """Render content-minimal RouteTeacher coverage as read-only UI text."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(record, dict)
            or record.get("record_type") != "zygor_guide_coverage"
            or record.get("schema_version") != "1.0"
            or record.get("execution_authority") is not False
            or record.get("coverage_state") != "SELECTED_NON_TRIAL_FILES"
        ):
            raise ValueError("auditul RouteTeacher nu este valid")
        steps = record.get("step_count")
        coordinates = record.get("coordinate_candidate_count")
        kind_counts = record.get("kind_counts")
        if (
            type(steps) is not int
            or type(coordinates) is not int
            or not isinstance(kind_counts, dict)
            or any(type(kind_counts.get(key)) is not int for key in (
                "class_trainer", "profession_trainer", "class_quest",
                "profession_quest",
            ))
        ):
            raise ValueError("counturile RouteTeacher lipsesc")
        return (
            "Zygor RouteTeacher (read-only): "
            f"{steps:,}".replace(",", ".") + " pași • "
            f"{coordinates:,}".replace(",", ".") + " coordonate candidate • "
            f"{kind_counts['class_trainer']} traineri clasă • "
            f"{kind_counts['profession_trainer']} traineri profesie • "
            f"{kind_counts['class_quest'] + kind_counts['profession_quest']} quest-uri"
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "Zygor RouteTeacher: audit indisponibil (nu acordă execuție)"


def _zygor_route_coverage_text(path: Path = ZYGOR_ROUTE_COVERAGE) -> str:
    """Render explicit multi-map RouteTeacher counts as read-only UI text."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        maps = record.get("map_coverage") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("record_type") != "zygor_route_coverage"
            or record.get("schema_version") != "1.0"
            or record.get("execution_authority") is not False
            or record.get("coverage_state") != "BOUND_EXPLICIT_ZONE_MAPS"
            or not isinstance(maps, list)
            or not maps
        ):
            raise ValueError("auditul RouteTeacher pe hărți nu este valid")
        summaries: list[str] = []
        for item in maps:
            if (
                not isinstance(item, dict)
                or type(item.get("map_id")) is not int
                or not isinstance(item.get("map_name"), str)
                or not item["map_name"]
                or type(item.get("step_count")) is not int
                or type(item.get("coordinate_candidate_count")) is not int
                or item["step_count"] < 0
                or item["coordinate_candidate_count"] < 0
            ):
                raise ValueError("counturile RouteTeacher pe hartă lipsesc")
            summaries.append(
                f"{item['map_name']} {item['step_count']:,}".replace(",", ".")
            )
        return "Zygor hărți (read-only): " + " • ".join(summaries)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "Zygor hărți: audit indisponibil (nu acordă execuție)"


def _zygor_route_transform_coverage_text(
    path: Path = ZYGOR_ROUTE_TRANSFORM_COVERAGE,
) -> str:
    """Render RouteTeacher/client 2D transform coverage as advisory text."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        maps = record.get("map_coverage") if isinstance(record, dict) else None
        candidates = record.get("coordinate_candidate_count") if isinstance(record, dict) else None
        transformed = record.get("transformed_coordinate_count") if isinstance(record, dict) else None
        unresolved = record.get("unresolved_coordinate_count") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("record_type") != "zygor_route_transform_coverage"
            or record.get("schema_version") != "1.0"
            or record.get("execution_authority") is not False
            or record.get("coverage_state") not in {
                "COMPLETE_CLIENT_2D_TRANSFORM", "PARTIAL_CLIENT_2D_TRANSFORM",
            }
            or not isinstance(maps, list)
            or not maps
            or type(candidates) is not int
            or type(transformed) is not int
            or type(unresolved) is not int
            or candidates < 0
            or transformed < 0
            or unresolved < 0
            or transformed > candidates
        ):
            raise ValueError("auditul transformării RouteTeacher nu este valid")
        summaries: list[str] = []
        for item in maps:
            if (
                not isinstance(item, dict)
                or type(item.get("map_id")) is not int
                or not isinstance(item.get("map_name"), str)
                or not item["map_name"]
                or type(item.get("coordinate_candidate_count")) is not int
                or type(item.get("transformed_coordinate_count")) is not int
                or item["coordinate_candidate_count"] < 0
                or item["transformed_coordinate_count"] < 0
                or item["transformed_coordinate_count"] > item["coordinate_candidate_count"]
            ):
                raise ValueError("counturile transformării pe hartă lipsesc")
            summaries.append(
                f"{item['map_name']} "
                f"{item['transformed_coordinate_count']:,}/"
                f"{item['coordinate_candidate_count']:,}".replace(",", ".")
            )
        return (
            "Zygor transformări 2D (read-only): "
            f"{transformed:,}/{candidates:,}".replace(",", ".")
            + " • " + " • ".join(summaries)
            + (f" • {unresolved:,} nerezolvate".replace(",", ".") if unresolved else "")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "Zygor transformări 2D: audit indisponibil (nu acordă execuție)"


def _zygor_npcdata_coverage_text(path: Path = ZYGOR_NPCDATA_AUDIT) -> str:
    """Render static NPCData coverage without implying exact live positions."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        kind_counts = record.get("kind_counts") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("record_type") != "zygor_npcdata_audit"
            or record.get("schema_version") != "1.0"
            or record.get("execution_authority") is not False
            or type(record.get("row_count")) is not int
            or type(record.get("map_area_count")) is not int
            or not isinstance(kind_counts, dict)
            or any(type(kind_counts.get(key)) is not int for key in (
                "class_trainer", "profession_trainer", "npc_static",
            ))
        ):
            raise ValueError("auditul NPCData nu este valid")
        return (
            "Zygor NPCData static (read-only): "
            f"{record['row_count']:,}".replace(",", ".") + " intrări • "
            f"{record['map_area_count']} zone • "
            f"{kind_counts['class_trainer']} traineri clasă • "
            f"{kind_counts['profession_trainer']} traineri profesie • "
            f"{kind_counts['npc_static']} NPC statici"
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "Zygor NPCData: audit indisponibil (nu acordă execuție)"


def _zygor_world_map_reconciliation_text(
    path: Path = ZYGOR_WORLD_MAP_RECONCILIATION,
) -> str:
    """Render static map-area binding coverage without implying live position."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        map_area_count = record.get("map_area_count") if isinstance(record, dict) else None
        resolved = record.get("resolved_map_area_count") if isinstance(record, dict) else None
        ambiguous = record.get("ambiguous_map_area_count") if isinstance(record, dict) else None
        unresolved = record.get("unresolved_map_area_count") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("record_type") != "zygor_world_map_reconciliation"
            or record.get("schema_version") != "1.0"
            or record.get("execution_authority") is not False
            or record.get("reconciliation_status") not in {"COMPLETE", "PARTIAL"}
            or any(type(value) is not int for value in (
                map_area_count, resolved, ambiguous, unresolved,
            ))
            or not 0 <= resolved <= map_area_count
            or not 0 <= ambiguous <= map_area_count
            or not 0 <= unresolved <= map_area_count
            or resolved + unresolved + ambiguous != map_area_count
        ):
            raise ValueError("reconcilierea map-area nu este validă")
        return (
            "Zygor map-area binding (read-only): "
            f"{resolved}/{map_area_count} rezolvate • "
            f"{ambiguous} ambigue • {unresolved} nerezolvate"
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "Zygor map-area binding: audit indisponibil (nu acordă execuție)"


def _world_map_zone_transform_text(
    path: Path = WORLD_MAP_ZONE_TRANSFORM_CATALOG,
    *,
    schema_path: Path = WORLD_MAP_ZONE_TRANSFORM_SCHEMA,
) -> str:
    """Render client-asset map-area transform coverage as read-only UI text."""

    try:
        catalog = load_world_map_zone_transform_catalog(
            path, schema_path=schema_path,
        )
        return (
            "WorldMapArea transforms (read-only): "
            f"{len(catalog.zones)} map-area-uri • "
            f"build {catalog.client_build} • fără înălțime/execuție"
        )
    except (OSError, TypeError, ValueError, RuntimeError):
        return "WorldMapArea transforms: catalog indisponibil (nu acordă execuție)"


def _friendly_3d_mesh_map_error(error: Exception) -> str:
    """Turn launcher failures into a short operator-facing explanation."""

    if not isinstance(error, subprocess.CalledProcessError):
        return str(error)
    output = "\n".join(
        part.strip()
        for part in (error.stderr, error.stdout)
        if isinstance(part, str) and part.strip()
    )
    if "config hash does not match authorization" in output:
        return "Harta s-a schimbat. Închide și deschide din nou Harta 3D."
    if "authorization is expired" in output or "authorization expired" in output:
        return "Legătura cu jocul a expirat. Închide și deschide din nou Harta 3D."
    return "Harta 3D nu a pornit. Vezi jurnalul."


def autonomous_start_readiness(
    *,
    structure_loading: bool,
    semantic_gate_open: bool,
    structure_index_loaded: bool,
    structure_graph_configured: bool,
    structure_graph_loaded: bool,
    structure_error: str | None,
    semantic_gate_reason: str | None = None,
) -> tuple[bool, str, str]:
    """Return the fail-closed autonomous start state and operator explanation."""

    if structure_loading:
        return (
            False,
            "VERIFIC HARTA…",
            "Verific pe unde poate merge…",
        )
    if structure_error is not None:
        return (
            False,
            "HARTA NU MERGE",
            "Harta are o problemă. Vezi jurnalul.",
        )
    if not structure_index_loaded:
        return (
            False,
            "HARTA NU ESTE GATA",
            "Lipsesc bucăți din hartă",
        )
    if not structure_graph_configured:
        return (
            False,
            "HARTA NU ESTE GATA",
            "Harta nu știe încă toate intrările și ieșirile",
        )
    if not structure_graph_loaded:
        return (
            False,
            "HARTA NU MERGE",
            "Harta nu poate citi intrările și ieșirile",
        )
    if not semantic_gate_open:
        if semantic_gate_reason == "VALIDATION_PASS_AUTHORITY_DISABLED":
            return (
                False,
                "BIFEAZĂ CĂSUȚA",
                "Harta e gata. Bifează căsuța de mers.",
            )
        return (
            False,
            "DRUMUL NU ESTE GATA",
            "Drumul nu a trecut testul",
        )
    return (
        True,
        "▶  PORNEȘTE MERSUL",
        "Gata de mers — fără luptă",
    )


@lru_cache(maxsize=4)
def _cached_world_pack_binding(profile_path: Path, store_root: Path):
    """Perform the expensive full-pack hash verification once per UI process."""

    return load_world_pack_runtime_profile(
        profile_path,
        store_root=store_root,
        profile_schema_path=ROOT
        / "contracts"
        / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT
        / "contracts"
        / "client-world-catalog.schema.json",
    )


def _verified_world_pack_binding():
    return _cached_world_pack_binding(
        WORLD_PACK_PROFILE.resolve(), WORLD_PACK_STORE.resolve(),
    )


def _validated_structure_service_ready(
    record: object,
) -> dict[str, object]:
    if not isinstance(record, dict) or record.get("event") != "READY":
        detail = record.get("detail") if isinstance(record, dict) else None
        raise RuntimeError(str(detail or "serviciul awareness nu a raportat READY"))
    string_fields = (
        "world_pack_id",
        "world_pack_content_sha256",
        "structure_index_id",
        "structure_index_sha256",
        "graph_id",
        "graph_content_sha256",
    )
    count_fields = (
        "structure_count", "wmo_count", "doodad_count", "access_opening_count",
    )
    if (
        any(not isinstance(record.get(field), str) for field in string_fields)
        or any(
            not isinstance(record.get(field), int) or int(record[field]) < 0
            for field in count_fields
        )
        or record.get("execution_authority") is not False
    ):
        raise RuntimeError("serviciul awareness a emis un READY invalid")
    semantic_identity = record.get("semantic_gate_identity")
    if (
        not isinstance(semantic_identity, dict)
        or set(semantic_identity) != set(SemanticLiveGateIdentity.__dataclass_fields__)
        or any(not isinstance(value, str) for value in semantic_identity.values())
    ):
        raise RuntimeError("serviciul awareness nu a legat semantic gate identity")
    for field in (
        "world_pack_content_sha256",
        "structure_index_sha256",
        "graph_content_sha256",
    ):
        value = str(record[field])
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise RuntimeError(f"serviciul awareness a emis {field} invalid")
    return record


def _validated_structure_nearby(record: object) -> dict[str, object]:
    if not isinstance(record, dict) or record.get("event") != "NEARBY":
        detail = record.get("detail") if isinstance(record, dict) else None
        raise RuntimeError(str(detail or "serviciul awareness nu a răspuns la query"))
    count_fields = (
        "wmo_count",
        "obstacle_count",
        "full_nav_count",
        "partial_nav_count",
        "no_nav_count",
    )
    if (
        not isinstance(record.get("request_id"), str)
        or any(
            not isinstance(record.get(field), int) or int(record[field]) < 0
            for field in count_fields
        )
        or record.get("execution_authority") is not False
        or not isinstance(record.get("hits"), list)
        or record.get("inside_wmo_asset") is not None
        and not isinstance(record.get("inside_wmo_asset"), str)
    ):
        raise RuntimeError("serviciul awareness a emis un răspuns NEARBY invalid")
    return record


def _semantic_gate_state_for_structure_summary(
    summary: dict[str, object],
    *,
    profile=None,
) -> str:
    raw_identity = summary.get("semantic_gate_identity")
    if not isinstance(raw_identity, dict):
        return "INVALID"
    try:
        if profile is not None and profile.runtime_profile is None:
            return "INVALID"
        values = {
            field: str(raw_identity[field])
            for field in SemanticLiveGateIdentity.__dataclass_fields__
        }
        profile_path = (
            WORLD_PACK_PROFILE.resolve()
            if profile is None
            else profile.runtime_profile.resolve()
        )
        worker_path = _navigation_worker().resolve()
        if (
            values["world_pack_profile"] != str(profile_path)
            or values["worker"] != str(worker_path)
        ):
            return "INVALID"
        values["world_pack_profile_sha256"] = _file_sha256(profile_path)
        values["worker_sha256"] = _file_sha256(worker_path)
        expected = SemanticLiveGateIdentity(**values)
        record = json.loads(SEMANTIC_GATE.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            return "INVALID"
        if semantic_live_gate_open(record, expected=expected):
            return "OPEN"
        # A PASS record with authority deliberately disabled is not a failed
        # road regression.  Probe the same signed identity with only that
        # boolean enabled so the UI can explain the true, operator-controlled
        # reason while still keeping input fail-closed.
        if record.get("live_authority_enabled") is False:
            authority_probe = dict(record)
            authority_probe["live_authority_enabled"] = True
            if semantic_live_gate_open(authority_probe, expected=expected):
                return "VALIDATION_PASS_AUTHORITY_DISABLED"
        return "INVALID"
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return "INVALID"


def _semantic_gate_open_for_structure_summary(
    summary: dict[str, object],
    *,
    profile=None,
) -> bool:
    return _semantic_gate_state_for_structure_summary(
        summary, profile=profile,
    ) == "OPEN"


def _read_movement_runtime_record() -> dict[str, object] | None:
    try:
        record = json.loads(MOVEMENT_STATE.read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else None
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _read_snapshot(
    record: dict[str, object] | None = None,
) -> MovementLabSnapshot | None:
    try:
        source = _read_movement_runtime_record() if record is None else record
        return None if source is None else MovementLabSnapshot.from_record(source)
    except (ValueError, KeyError, TypeError):
        return None


def _read_live_map_pose(
    path: Path,
    *,
    now_monotonic_s: float,
    maximum_age_s: float = 0.75,
) -> LiveMapPose | None:
    """Read only the compact pose prefix of the shared 3D-viewer stream."""

    return read_live_pose_file(
        path,
        now_monotonic_s=now_monotonic_s,
        maximum_age_s=maximum_age_s,
    )


def _live_observation_source_text(
    pose: LiveMapPose | None,
    *,
    now_monotonic_s: float,
) -> str:
    """Expose provenance and age for the exact live pose channels."""

    if pose is None:
        return "Locul: încă nu îl văd"
    age_ms = max(0, round((now_monotonic_s - pose.observed_monotonic_s) * 1000))
    facing_labels = {
        "COORDINATE_HUD_EXACT": "văd exact încotro privește",
        "MINIMAP_VISION_FALLBACK": "văd încotro privește pe harta mică",
        "VISIBLE_CLIENT_HEADING_FUSED": "am verificat încotro privește",
        "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED": "am verificat încotro privește",
    }
    facing_source = facing_labels.get(
        pose.facing_source or "", "nu văd încotro privește"
    )
    return f"Locul: îl văd • {facing_source} • acum {age_ms} ms"


def _body_camera_orientation_text(snapshot: MovementLabSnapshot | None) -> str:
    """Show exact body yaw apart from the controller's camera-yaw estimate."""

    if snapshot is None or snapshot.body_facing_rad is None:
        return "Fața: încă nu o văd"
    body_degrees = degrees(snapshot.body_facing_rad) % 360.0
    if snapshot.camera_yaw_estimate_rad is None:
        return f"Fața: {body_degrees:.1f}° • camera: nu o văd"
    camera_degrees = degrees(snapshot.camera_yaw_estimate_rad) % 360.0
    delta = snapshot.body_camera_yaw_delta_rad
    delta_text = (
        "diferența nu se vede"
        if delta is None else f"între ele {degrees(delta):+.1f}°"
    )
    return (
        f"Fața: {body_degrees:.1f}° • "
        f"camera: {camera_degrees:.1f}° • {delta_text}"
    )


def _plain_controller_state(state: str) -> str:
    """Turn internal movement states into short words for the main UI."""

    upper = state.upper()
    if "OBSERVE" in upper:
        return "doar privesc"
    if any(word in upper for word in ("PIVOT", "ALIGN", "FACE", "TURN")):
        return "se întoarce"
    if any(word in upper for word in ("RECOVER", "STUCK", "ESCAPE")):
        return "iese din blocaj"
    if "PAUSE" in upper:
        return "pauză"
    if any(word in upper for word in ("FOLLOW", "MOVE", "ADVANCE")):
        return "merge"
    return "lucrează"


def _plain_environment_state(state: object) -> str:
    labels = {
        "INSIDE_STATIC_WMO": "în clădire",
        "WMO_TRANSITION_OR_UNRESOLVED": "lângă intrarea unei clădiri",
        "OPEN_GROUND": "teren deschis",
        "CONFINED_STATIC_SPACE": "loc îngust",
        "STATIC_TRANSITION": "trecere între două locuri",
    }
    return labels.get(str(state), "loc necunoscut")


def _runtime_controller_text(
    snapshot: MovementLabSnapshot | None, *, state: str, process_running: bool,
) -> str:
    """Describe the managed motor, not inferred physical motion of the actor."""
    if state == "STARTING":
        return "Pregătesc mersul • aștept datele motorului"
    if state == "STOPPED" or not process_running:
        return "Motor oprit • poziția live se verifică separat"
    if state == "STOPPING":
        return "Am cerut oprirea motorului"
    if state == "PAUSED":
        return "Motor în pauză"
    if snapshot is None or "OBSERVE" in snapshot.controller_state.upper():
        return "Aștept date actuale de la motor"
    return f"Acum: {_plain_controller_state(snapshot.controller_state)}"


def _snapshot_with_live_pose(
    snapshot: MovementLabSnapshot | None,
    pose: LiveMapPose,
) -> MovementLabSnapshot:
    """Put fresh localization over the current topographic picture.

    A fresh movement snapshot keeps its corridor and local mesh.  When the
    navigator is idle, the pose-only bridge creates a deliberately empty
    topographic picture instead of showing old local geometry at a new place.
    """

    if snapshot is None:
        return MovementLabSnapshot(
            observed_monotonic_s=pose.observed_monotonic_s,
            tracking_state="LOST",
            target_identity_crc16=None,
            target_error_x_normalized=None,
            player_world_x=pose.world_x,
            player_world_y=pose.world_y,
            player_facing_rad=pose.facing_rad,
            body_facing_rad=pose.facing_rad,
            body_facing_source=pose.facing_source,
            controller_state="OBSERVE • LOCALIZARE LIVE",
        )
    body_camera_delta = (
        None
        if pose.facing_rad is None or snapshot.camera_yaw_estimate_rad is None
        else (
            pose.facing_rad - snapshot.camera_yaw_estimate_rad + pi
        ) % (2.0 * pi) - pi
    )
    return replace(
        snapshot,
        # This is still movement evidence from snapshot.observed_monotonic_s.
        # The pose has its own timestamp in last_live_pose; never rejuvenate
        # cached controller/geometry/camera evidence with a localization tick.
        player_world_x=pose.world_x,
        player_world_y=pose.world_y,
        player_facing_rad=pose.facing_rad,
        body_facing_rad=pose.facing_rad,
        body_facing_source=pose.facing_source,
        body_camera_yaw_delta_rad=body_camera_delta,
    )


def _movement_snapshot_is_fresh(
    snapshot: MovementLabSnapshot,
    *,
    now_monotonic_s: float,
    maximum_age_s: float = 1.5,
) -> bool:
    age = now_monotonic_s - snapshot.observed_monotonic_s
    return 0.0 <= age <= maximum_age_s


def _read_local_environment(
    record: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    try:
        source = _read_movement_runtime_record() if record is None else record
        if source is None:
            return None, None
        environment = source.get("local_environment_awareness")
        applicability = source.get("local_environment_applicability")
        if (
            not isinstance(environment, dict)
            or environment.get("record_type") != "local_environment_awareness"
            or environment.get("schema_version") != "1.0"
            or environment.get("execution_authority") is not False
            or not isinstance(environment.get("environment_state"), str)
            or not isinstance(environment.get("boundaries"), list)
            or not isinstance(environment.get("verified_egresses"), list)
            or not isinstance(applicability, dict)
            or applicability.get("execution_authority") is not False
            or not isinstance(applicability.get("applicable_to_live_pose"), bool)
            or not isinstance(
                applicability.get("horizontal_offset_yards"), (int, float),
            )
        ):
            return None, None
        return environment, applicability
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None, None


def _read_structure_access(
    record: dict[str, object] | None = None,
) -> dict[str, object] | None:
    try:
        source = _read_movement_runtime_record() if record is None else record
        if source is None:
            return None
        awareness = source.get("structure_access_awareness")
        if (
            not isinstance(awareness, dict)
            or not isinstance(awareness.get("graph_id"), str)
            or not isinstance(awareness.get("graph_content_sha256"), str)
            or awareness.get("coverage_state") not in {
                "COMPLETE_FOR_OBSERVED_COMPONENTS",
                "PARTIAL_OBSERVED_COMPONENTS",
            }
            or not isinstance(awareness.get("applicable_to_live_pose"), bool)
            or not isinstance(awareness.get("known_opening_count"), int)
            or not isinstance(awareness.get("known_openings"), list)
            or awareness.get("physical_door_semantics") != "UNKNOWN_NOT_INFERRED"
            or awareness.get("execution_authority") is not False
        ):
            return None
        return awareness
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _read_dynamic_entity_awareness(
    record: dict[str, object] | None = None,
) -> dict[str, object] | None:
    source = _read_movement_runtime_record() if record is None else record
    if source is None:
        return None
    awareness = source.get("dynamic_entity_awareness")
    observed_at_s = (
        awareness.get("observed_monotonic_s")
        if isinstance(awareness, dict)
        else None
    )
    visibility_ceiling_yards = (
        awareness.get("visibility_ceiling_yards")
        if isinstance(awareness, dict)
        else None
    )
    track_count = (
        awareness.get("track_count")
        if isinstance(awareness, dict)
        else None
    )
    if (
        not isinstance(awareness, dict)
        or awareness.get("record_type") != "dynamic_entity_awareness"
        or awareness.get("schema_version") != "1.0"
        or awareness.get("observation_scope")
        != "CURRENT_VIEWPORT_WITHIN_SERVER_VISIBILITY_SET"
        or awareness.get("position_semantics") != "SCREEN_SPACE_ONLY"
        or awareness.get("distance_semantics")
        != "UNKNOWN_UNLESS_SELECTED_TARGET_RANGE_WITNESS"
        or isinstance(observed_at_s, bool)
        or not isinstance(observed_at_s, (int, float))
        or not isfinite(float(observed_at_s))
        or float(observed_at_s) < 0.0
        or isinstance(visibility_ceiling_yards, bool)
        or not isinstance(visibility_ceiling_yards, (int, float))
        or not isfinite(float(visibility_ceiling_yards))
        or not 1.0 <= float(visibility_ceiling_yards) <= 500.0
        or isinstance(track_count, bool)
        or not isinstance(track_count, int)
        or not isinstance(awareness.get("tracks"), list)
        or track_count != len(awareness["tracks"])
        or awareness.get("execution_authority") is not False
    ):
        return None
    if not all(
        isinstance(track, dict)
        and track.get("reaction") in {"HOSTILE", "NEUTRAL", "FRIENDLY", "UNKNOWN"}
        and track.get("world_position") is None
        and track.get("distance_yards") is None
        for track in awareness["tracks"]
    ):
        return None
    return awareness


def _dynamic_awareness_text(
    awareness: dict[str, object] | None,
    *,
    now_monotonic_s: float,
    max_age_s: float = 1.5,
) -> str:
    """Render observed-only entity awareness without implying unseen ESP data."""

    if awareness is None:
        return (
            "Entități vizibile: fără snapshot proaspăt\n"
            "Acoperire: viewport în visibility-set-ul serverului"
        )
    observed_at_s = float(awareness["observed_monotonic_s"])
    age_s = now_monotonic_s - observed_at_s
    if age_s < 0.0 or age_s > max_age_s:
        return (
            "Entități vizibile: snapshot expirat\n"
            "Acoperire: viewport în visibility-set-ul serverului"
        )
    tracks = awareness["tracks"]
    assert isinstance(tracks, list)
    reactions = {
        reaction: 0
        for reaction in ("HOSTILE", "NEUTRAL", "FRIENDLY", "UNKNOWN")
    }
    for track in tracks:
        assert isinstance(track, dict)
        reactions[str(track["reaction"])] += 1
    detail = (
        f"Tracks visible/last_seen: {len(tracks)} • hostile {reactions['HOSTILE']} • "
        f"neutral {reactions['NEUTRAL']} • friendly {reactions['FRIENDLY']}"
    )
    semantics = (
        f"Viewport/server visibility ≤{float(awareness['visibility_ceiling_yards']):g} yd • "
        "poziții screen-space"
    )
    adapter_error = awareness.get("adapter_error")
    if isinstance(adapter_error, str) and adapter_error:
        return f"{detail}\n{semantics}\nDetector: {adapter_error}"
    return f"{detail}\n{semantics}"


def _read_selected_target_range_awareness(
    record: dict[str, object] | None = None,
) -> dict[str, object] | None:
    source = _read_movement_runtime_record() if record is None else record
    if source is None:
        return None
    awareness = source.get("selected_target_range_awareness")
    if not isinstance(awareness, dict):
        return None
    observed_at_s = awareness.get("observed_monotonic_s")
    expires_at_s = awareness.get("expires_monotonic_s")
    target_identity = awareness.get("target_identity_crc16")
    witnesses = awareness.get("witnesses")
    if (
        awareness.get("record_type") != "selected_target_range_awareness"
        or awareness.get("schema_version") != "1.0"
        or awareness.get("range_source") != "CLIENT_ACTION_RANGE_WITNESSES"
        or awareness.get("melee_minimum_yards") != 0.0
        or awareness.get("melee_maximum_yards") != 5.0
        or awareness.get("derived_relation") not in {
            "IN_RANGE_0_TO_5", "TOO_FAR_OVER_5", "INCONSISTENT", "UNKNOWN",
        }
        or isinstance(observed_at_s, bool)
        or not isinstance(observed_at_s, (int, float))
        or not isfinite(float(observed_at_s))
        or float(observed_at_s) < 0.0
        or isinstance(expires_at_s, bool)
        or not isinstance(expires_at_s, (int, float))
        or not isfinite(float(expires_at_s))
        or not float(observed_at_s)
        <= float(expires_at_s)
        <= float(observed_at_s) + 0.600001
        or isinstance(target_identity, bool)
        or not isinstance(target_identity, int)
        or not 1 <= target_identity <= 65_535
        or not isinstance(witnesses, list)
        or not 1 <= len(witnesses) <= 16
        or awareness.get("exact_distance_yards") is not None
        or awareness.get("execution_authority") is not False
    ):
        return None
    if not all(
        isinstance(witness, dict)
        and isinstance(witness.get("ability_id"), str)
        and witness.get("minimum_yards") == 0.0
        and witness.get("maximum_yards") == 5.0
        and (
            witness.get("client_in_range") is None
            or type(witness.get("client_in_range")) is bool
        )
        for witness in witnesses
    ):
        return None
    return awareness


def _selected_target_range_text(
    awareness: dict[str, object] | None,
    *,
    now_monotonic_s: float,
    target_identity_crc16: int | None,
) -> str:
    if awareness is None or target_identity_crc16 is None:
        return "Target range: fără witness proaspăt"
    if awareness["target_identity_crc16"] != target_identity_crc16:
        return "Target range: witness pentru alt target"
    observed_at_s = float(awareness["observed_monotonic_s"])
    expires_at_s = float(awareness["expires_monotonic_s"])
    if now_monotonic_s < observed_at_s or now_monotonic_s > expires_at_s:
        return "Target range: witness expirat"
    relation = awareness["derived_relation"]
    if relation == "IN_RANGE_0_TO_5":
        estimate = "0–5 yd"
    elif relation == "TOO_FAR_OVER_5":
        estimate = ">5 yd"
    elif relation == "INCONSISTENT":
        estimate = "inconsistent — acțiune refuzată"
    else:
        estimate = "necunoscut"
    return f"Target range: {estimate} • exact indisponibil în API"


def _read_dynamic_experience_summary(
    record: dict[str, object] | None = None,
) -> dict[str, object] | None:
    source = _read_movement_runtime_record() if record is None else record
    if source is None:
        return None
    summary = source.get("dynamic_experience_summary")
    if not isinstance(summary, dict):
        return None
    counts = summary.get("reaction_counts")
    navmesh_sha256 = summary.get("navmesh_sha256")
    observation_count = summary.get("observation_count")
    if (
        summary.get("record_type") != "dynamic_experience_summary"
        or summary.get("schema_version") != "2.0"
        or summary.get("database_schema_version") != 2
        or not isinstance(summary.get("map_name"), str)
        or not isinstance(navmesh_sha256, str)
        or len(navmesh_sha256) != 64
        or any(character not in "0123456789ABCDEF" for character in navmesh_sha256)
        or isinstance(observation_count, bool)
        or not isinstance(observation_count, int)
        or observation_count < 0
        or not isinstance(counts, dict)
        or set(counts) != {"HOSTILE", "NEUTRAL", "FRIENDLY", "UNKNOWN"}
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        )
        or sum(counts.values()) != observation_count
        or summary.get("experience_semantics")
        != "APPEND_ONLY_OBSERVER_POSE_ENCOUNTER_MEMORY"
        or summary.get("entity_position_semantics") != "UNKNOWN_NOT_INFERRED"
        or summary.get("execution_authority") is not False
    ):
        return None
    return summary


def _dynamic_experience_text(summary: dict[str, object] | None) -> str:
    if summary is None:
        return "Memorie permanentă: indisponibilă"
    counts = summary["reaction_counts"]
    assert isinstance(counts, dict)
    return (
        f"Memorie permanentă: {summary['observation_count']} întâlniri • "
        f"hostile {counts['HOSTILE']} • neutral {counts['NEUTRAL']}\n"
        "Dovadă: poziția Predatorului la întâlnire; poziția entității necunoscută"
    )


def _crypt_trial_gate_text(path: Path = CRYPT_TRIAL_GATE_REPORT) -> str:
    """Show verified live-test progress without granting movement authority."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("invalid Crypt trial gate document")
        declared = record.get("declared_trial_count")
        valid = record.get("valid_trial_count")
        required = record.get("required_trial_count")
        if (
            record.get("record_type") != "movement_live_trial_gate"
            or record.get("schema_version") != "1.0"
            or record.get("execution_authority") is not False
            or type(record.get("baseline_intact")) is not bool
            or any(type(value) is not int for value in (declared, valid, required))
            or not 0 <= valid <= declared <= 100
            or required != 10
        ):
            raise ValueError("invalid Crypt trial gate")
        baseline = "păstrat ✓" if record["baseline_intact"] else "nu este intact"
        # This is an archive/approval count, not a certificate for the code
        # currently running. Do not turn historical evidence into live authority.
        return (
            f"Ieșirea din criptă: etalon {baseline} • aprobate vizual {valid}/{required}\n"
            "Istoric de probe — nu certifică versiunea curentă."
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "Ieșirea din criptă: testele nu au fost citite"


def _stationary_pose_text(record: dict[str, object] | None) -> str:
    """Render the read-only stationary certification without implying authority."""

    if not isinstance(record, dict):
        return "Nu am verificat încă"
    sample_count = record.get("sample_count")
    duration_s = record.get("duration_s")
    passed = record.get("passed")
    failures = record.get("failures")
    if (
        record.get("record_type") != "stationary_pose_validation"
        or record.get("schema_version") != "1.0"
        or record.get("execution_authority") is not False
        or type(sample_count) is not int
        or isinstance(duration_s, bool)
        or not isinstance(duration_s, (int, float))
        or not isinstance(passed, bool)
        or not isinstance(failures, list)
        or any(not isinstance(item, str) for item in failures)
    ):
        return "Testul nu a putut fi citit"
    if passed:
        if (
            record.get("expected_location_id") != STATIONARY_VALIDATION_LOCATION_ID
            or record.get("within_expected_location") is not True
        ):
            return "Nu pot dovedi că Predatorul este în criptă"
        return (
            f"Ultimul test: BINE ✓ Predatorul era în criptă și nemișcat "
            f"({sample_count} citiri în {float(duration_s):.1f} secunde). "
            "Rezultat istoric, nu starea actuală."
        )
    if "insufficient_unique_samples" in failures:
        reason = "nu am primit destule date din joc"
    elif "exact_body_facing_missing" in failures:
        reason = "nu îi văd direcția exactă"
    elif "actor_not_stationary" in failures:
        reason = "Predatorul s-a mișcat"
    elif "body_facing_not_stationary" in failures:
        reason = "și-a schimbat direcția"
    elif "outside_expected_location" in failures:
        reason = "Predatorul nu este în Cryptă"
    else:
        reason = "testul nu a trecut"
    return f"Nu este bine: {reason} ({sample_count} citiri)"


def _world_pack_viewer_launch(
    snapshot: MovementLabSnapshot,
    *,
    fresh_world_position: tuple[float, float] | None = None,
    live_state_path: Path | None = None,
    profile=None,
) -> WorldPackViewerLaunch:
    world_x = (
        snapshot.player_world_x
        if fresh_world_position is None else fresh_world_position[0]
    )
    world_y = (
        snapshot.player_world_y
        if fresh_world_position is None else fresh_world_position[1]
    )
    if world_x is None or world_y is None:
        raise ValueError("poziția lui Predator nu este încă disponibilă")
    active_profile = profile
    if active_profile is None:
        active_profile = next(
            (item for item in load_world_map_registry(
                WORLD_MAP_REGISTRY, schema_path=WORLD_MAP_REGISTRY_SCHEMA,
            ) if item.map_id == 0),
            None,
        )
    if active_profile is None:
        raise RuntimeError("registry-ul WorldPack nu conține profilul implicit")
    if active_profile.runtime_profile is None:
        raise RuntimeError("profilul selectat nu are WorldPack runtime")
    binding = _cached_world_pack_binding(
        active_profile.runtime_profile.resolve(), WORLD_PACK_STORE.resolve(),
    )
    return build_world_pack_viewer_launch(
        binding,
        viewer_executable=NAV_VIEWER,
        map_id=active_profile.map_id,
        world_x=world_x,
        world_y=world_y,
        world_z=snapshot.player_world_z,
        live_state_path=live_state_path,
    )


def _nav_viewer_arguments(
    snapshot: MovementLabSnapshot,
    *,
    fresh_world_position: tuple[float, float] | None = None,
    live_state_path: Path | None = None,
) -> list[str]:
    """Backward-compatible argument view for diagnostics and contract tests."""
    return list(
        _world_pack_viewer_launch(
            snapshot,
            fresh_world_position=fresh_world_position,
            live_state_path=live_state_path,
        ).arguments
    )


def _nav_viewer_bridge_arguments(
    *, viewer_pid: int, snapshot: MovementLabSnapshot,
    launch: WorldPackViewerLaunch,
    expected_zone_index: int = 25,
    zone_transform_catalog: Path = WORLD_MAP_ZONE_TRANSFORM_CATALOG,
) -> list[str]:
    arguments = [
        sys.executable, str(NAV_VIEWER_LIVE_BRIDGE),
        "--session-authorization-file", str(SESSION_AUTH),
        "--session-receipt", str(SESSION_RECEIPT),
        "--state-file", str(NAV_VIEWER_STATE),
        "--movement-state", str(MOVEMENT_STATE),
        "--viewer-pid", str(viewer_pid),
        "--expected-zone-index", str(expected_zone_index),
        "--map-id", str(getattr(launch, "map_id", 0)),
        "--zone-transform-catalog", str(zone_transform_catalog),
        "--target-hz", "5",
        "--state-protocol", "5",
    ]
    if snapshot.player_world_z is not None:
        arguments.extend([
            "--awareness-worker", str(WORKER),
            "--awareness-nav-root", str(launch.nav_root),
            "--awareness-map-name", launch.internal_name,
            "--initial-world-z", repr(snapshot.player_world_z),
        ])
    return arguments


def _control_center_live_pose_arguments(
    *, owner_pid: int, expected_zone_index: int, map_id: int,
    zone_transform_catalog: Path = WORLD_MAP_ZONE_TRANSFORM_CATALOG,
    spatial_sonar_profile: Path | None = None,
    spatial_sonar_wmo_config: Path | None = None,
    spatial_sonar_continuity: bool = False,
) -> list[str]:
    """Build one long-lived, hidden, read-only localization stream."""

    return [
        sys.executable, str(NAV_VIEWER_LIVE_BRIDGE),
        "--session-authorization-file", str(SESSION_AUTH),
        "--session-receipt", str(SESSION_RECEIPT),
        "--state-file", str(NAV_VIEWER_STATE),
        "--diagnostic-file", str(CONTROL_CENTER_LIVE_DIAGNOSTIC),
        "--movement-state", str(MOVEMENT_STATE),
        "--viewer-pid", str(owner_pid),
        "--expected-zone-index", str(expected_zone_index),
        "--map-id", str(map_id),
        "--zone-transform-catalog", str(zone_transform_catalog),
        "--target-hz", "5",
        "--state-protocol", "5",
    ] + (["--spatial-sonar-profile", str(spatial_sonar_profile)]
         if spatial_sonar_profile is not None else []) + (
             ["--spatial-sonar-wmo-config", str(spatial_sonar_wmo_config)]
             if spatial_sonar_profile is not None and spatial_sonar_wmo_config is not None else []
         ) + (["--spatial-sonar-continuity"]
              if spatial_sonar_profile is not None and spatial_sonar_continuity else [])


def _focus_exact_wow_window() -> None:
    user32 = ctypes.windll.user32
    hwnd = int(user32.FindWindowW("GxWindowClassD3d", "World of Warcraft"))
    if not hwnd:
        raise RuntimeError("fereastra exactă WoW nu este deschisă")
    user32.ShowWindow(hwnd, 9)
    if not user32.SetForegroundWindow(hwnd):
        raise RuntimeError("WoW nu a putut primi focus pentru captură")


class GlobalRecordingHotkeys:
    """Two configurable, non-repeating global recording controls."""

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_NOREPEAT = 0x4000
    KEY_CODES = {f"F{index}": 0x6F + index for index in range(1, 13)}

    def __init__(self, start_key: str, stop_key: str, on_start, on_stop) -> None:
        normalized_start = start_key.upper()
        normalized_stop = stop_key.upper()
        if (
            normalized_start not in self.KEY_CODES
            or normalized_stop not in self.KEY_CODES
            or normalized_start == normalized_stop
        ):
            raise ValueError("recording hotkeys must be two different F1-F12 keys")
        self.start_key = normalized_start
        self.stop_key = normalized_stop
        self._callbacks = {1: on_start, 2: on_stop}
        self._thread: Thread | None = None
        self._thread_id = 0
        self._ready = Event()
        self.error: str | None = None

    def start(self) -> None:
        self._thread = Thread(target=self._run, name="recording-global-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        if self.error:
            raise RuntimeError(self.error)

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = int(kernel32.GetCurrentThreadId())
        registered: list[int] = []
        try:
            for hotkey_id, key in ((1, self.start_key), (2, self.stop_key)):
                if not user32.RegisterHotKey(
                    None, hotkey_id, self.MOD_NOREPEAT, self.KEY_CODES[key]
                ):
                    raise OSError(ctypes.get_last_error(), f"cannot register {key}")
                registered.append(hotkey_id)
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == self.WM_HOTKEY:
                    callback = self._callbacks.get(int(message.wParam))
                    if callback is not None:
                        callback()
        except Exception as error:
            self.error = str(error)
            self._ready.set()
        finally:
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)

    def close(self) -> None:
        if self._thread is None:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, self.WM_QUIT, 0, 0
            )
        self._thread.join(2.0)
        self._thread = None


class MovementEngineClient:
    def __init__(self, *, spatial_sonar_wmo_config: Path | None = None,
                 spatial_sonar_continuity: bool = False) -> None:
        self.spatial_sonar_wmo_config = spatial_sonar_wmo_config
        self.spatial_sonar_continuity = spatial_sonar_continuity
        self.root = tk.Tk()
        self.root.title("Predator")
        self.root.geometry("1500x1050+40+20")
        self.root.minsize(1300, 940)
        self.process: subprocess.Popen[str] | None = None
        self.motion_arm_renew_stop = Event()
        self.motion_arm_renew_results: SimpleQueue[tuple[str, str | None]] = (
            SimpleQueue()
        )
        self.combat_process: subprocess.Popen[str] | None = None
        self.manual_recorder_process: subprocess.Popen[str] | None = None
        self.overlay_process: subprocess.Popen[str] | None = None
        self.overlay_restart_not_before_s = 0.0
        self.nav_viewer_process: subprocess.Popen[str] | None = None
        self.nav_viewer_bridge_process: subprocess.Popen[str] | None = None
        self.live_pose_restart_not_before_s = 0.0
        self.live_session_renew_inflight = False
        self.live_session_renew_not_before_s = 0.0
        self.live_session_renew_results: SimpleQueue[str | None] = SimpleQueue()
        self.log_stream = None
        self.combat_log_stream = None
        self.manual_recorder_log_stream = None
        self.revision = 0
        self.combat_revision = 0
        self.manual_recorder_revision = 0
        self.state = "STOPPED"
        self.combat_state = "STOPPED"
        self.manual_recorder_state = "STOPPED"
        self.manual_recording_id: str | None = None
        self.manual_recording_draft: tuple[MapKnowledgeVertex, ...] = ()
        self.manual_result_mtime_ns: int | None = None
        self.last_snapshot: MovementLabSnapshot | None = None
        self.raw_movement_snapshot: MovementLabSnapshot | None = None
        self.movement_view_started_s: float | None = None
        self.last_live_pose: LiveMapPose | None = None
        self.movement_state_mtime_ns: int | None = -1
        self.cached_local_environment: tuple[dict[str, object] | None, dict[str, object] | None] = (None, None)
        self.cached_structure_access: dict[str, object] | None = None
        self.cached_dynamic_awareness: dict[str, object] | None = None
        self.cached_target_range_awareness: dict[str, object] | None = None
        self.cached_dynamic_experience_summary: dict[str, object] | None = None
        self.last_canvas_refresh_signature: object = object()
        self.canvas_resize_job = None
        self.canvas_to_world = None
        self.atlas_geometry = WorldMapAtlasGeometry(
            tbc243_zone_transform(2, 25), 1002, 668
        )
        self.atlas_viewport = AtlasViewport(1002, 668)
        self.atlas_pan_anchor: tuple[float, float] | None = None
        self.follow_predator = tk.BooleanVar(value=True)
        self.codex_driver_enabled = tk.BooleanVar(value=False)
        try:
            with Image.open(WORLD_MAP_ATLAS) as atlas:
                self.world_map_photo = atlas.convert("RGBA")
        except OSError:
            self.world_map_photo = None
        try:
            with Image.open(ROAD_SEMANTIC_ATLAS) as atlas:
                self.road_semantic_photo = atlas.convert("RGBA")
        except OSError:
            self.road_semantic_photo = None
        self.world_map_zoom_cache = {}
        self.road_semantic_zoom_cache = {}
        try:
            self.world_map_profiles = load_world_map_registry(
                WORLD_MAP_REGISTRY,
                schema_path=WORLD_MAP_REGISTRY_SCHEMA,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.world_map_profiles = ()
        self.active_world_map_profile = next(
            (profile for profile in self.world_map_profiles if profile.map_id == 0),
            None,
        )
        self.semantic_locations = self._load_semantic_locations()
        self.destination_id_by_name = {
            location[0]: destination_id
            for destination_id, location in self.semantic_locations.items()
        }
        self.semantic_destination_id = (
            "settlement:brill"
            if "settlement:brill" in self.semantic_locations
            else next(iter(self.semantic_locations))
        )
        self.sequence_destination_ids: list[str] = [self.semantic_destination_id]
        self.semantic_journey_anchor: tuple[float, float] | None = None
        self.semantic_journey, semantic_diagnostics = self._load_semantic_journey(
            self.semantic_destination_id
        )
        self.operator_path = self._load_operator_path()
        self.map_knowledge = self._load_map_knowledge()
        self.feature_draft: list[MapKnowledgeVertex] = []
        settings = self._load_settings()
        self.recording_start_hotkey = str(settings["recording_start_hotkey"])
        self.recording_stop_hotkey = str(settings["recording_stop_hotkey"])
        self.leveling_enabled = tk.BooleanVar(
            value=bool(settings["leveling_enabled"])
        )
        self.current_level = tk.IntVar(value=int(settings["current_level"]))
        self.zygor_catalog_path = tk.StringVar(
            value=str(settings["zygor_catalog_path"])
        )
        self.leveling_status = tk.StringVar(
            value="Ghidul nu este ales"
        )
        self.continuous_motion_ack = tk.BooleanVar(
            value=bool(settings["continuous_motion_ack"])
        )
        self.recording_hotkey_events: SimpleQueue[str] = SimpleQueue()
        self.recording_hotkeys: GlobalRecordingHotkeys | None = None
        self.structure_awareness_service: subprocess.Popen[str] | None = None
        self.structure_awareness_summary: dict[str, object] | None = None
        self.structure_nearby_summary: dict[str, object] | None = None
        self.structure_nearby_anchor: tuple[float, float, float | None] | None = None
        self.structure_query_in_flight = False
        self.structure_awareness_error: str | None = None
        self.structure_awareness_loading = True
        self.structure_awareness_results: SimpleQueue[
            tuple[
                subprocess.Popen[str] | None,
                dict[str, object] | None,
                str | None,
            ]
        ] = SimpleQueue()
        self.structure_query_results: SimpleQueue[
            tuple[dict[str, object] | None, tuple[float, float, float | None], str | None]
        ] = SimpleQueue()
        self.stationary_validation_running = False
        self.stationary_validation_results: SimpleQueue[
            tuple[dict[str, object] | None, str | None]
        ] = SimpleQueue()

        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        shell = ttk.Frame(self.root, padding=16)
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="PREDATOR — UNDE MERGE",
            font=("Segoe UI", 20, "bold"),
        ).pack(side="left")
        self.state_text = tk.StringVar(value="Oprit")
        ttk.Label(header, textvariable=self.state_text, font=("Segoe UI", 10)).pack(side="right")
        self.stay_online_panel = StayOnlinePanel(header, ROOT)

        self.workspace_tabs = ttk.Notebook(shell)
        self.workspace_tabs.pack(fill="both", expand=True, pady=(14, 0))
        navigation_tab = ttk.Frame(self.workspace_tabs, padding=2)
        future_tab = ttk.Frame(self.workspace_tabs, padding=8)
        self.workspace_tabs.add(navigation_tab, text="Mers")
        from sonar_panel import SonarPanel
        self.sonar_panel = SonarPanel(self.workspace_tabs)
        self.workspace_tabs.add(self.sonar_panel, text="Sonar")
        self.workspace_tabs.add(future_tab, text="Alte lucruri")
        self.workspace_tabs.select(navigation_tab)

        future_tabs = ttk.Notebook(future_tab)
        future_tabs.pack(fill="both", expand=True)
        combat_tab = ttk.Frame(future_tabs, padding=8)
        future_tools = ttk.Frame(future_tabs, padding=12)
        future_tabs.add(combat_tab, text="Luptă")
        future_tabs.add(future_tools, text="Setări")
        self._build_combat_tab(combat_tab)

        body = ttk.Panedwindow(navigation_tab, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(0, 12))
        left = ttk.Frame(body, padding=(0, 0, 12, 0))
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=5)

        ttk.Label(left, text="Harta", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.world_map_name = tk.StringVar(
            value=(
                self.active_world_map_profile.internal_name
                if self.active_world_map_profile is not None
                else "indisponibil"
            )
        )
        self.world_map_picker = ttk.Combobox(
            left,
            textvariable=self.world_map_name,
            state="readonly",
            values=tuple(profile.internal_name for profile in self.world_map_profiles),
            width=28,
        )
        self.world_map_picker.pack(anchor="w", pady=(5, 8))
        self.world_map_picker.bind(
            "<<ComboboxSelected>>", self._select_world_map_profile,
        )

        ttk.Label(left, text="Unde merge?", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.destination_name = tk.StringVar(
            value=self.semantic_locations[self.semantic_destination_id][0]
        )
        self.destination_picker = ttk.Combobox(
            left,
            textvariable=self.destination_name,
            state="readonly",
            values=tuple(self.destination_id_by_name),
            width=28,
        )
        self.destination_picker.pack(anchor="w", pady=(5, 4))
        self.destination_picker.bind(
            "<<ComboboxSelected>>", self._select_semantic_destination,
        )

        leveling_panel = ttk.LabelFrame(future_tools, text="Crește nivelul", padding=6)
        leveling_panel.pack(fill="x", pady=(2, 6))
        ttk.Checkbutton(
            leveling_panel,
            text="Folosește ghidul",
            variable=self.leveling_enabled,
            command=self._leveling_changed,
        ).pack(anchor="w")
        level_row = ttk.Frame(leveling_panel)
        level_row.pack(fill="x", pady=(5, 2))
        ttk.Label(level_row, text="Nivel:").pack(side="left")
        ttk.Spinbox(
            level_row,
            from_=1,
            to=70,
            width=5,
            textvariable=self.current_level,
            command=self._leveling_changed,
        ).pack(side="left", padx=(6, 0))
        catalog_row = ttk.Frame(leveling_panel)
        catalog_row.pack(fill="x", pady=(3, 0))
        ttk.Entry(
            catalog_row,
            textvariable=self.zygor_catalog_path,
            width=24,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            catalog_row,
            text="Alege",
            command=self._choose_zygor_catalog,
        ).pack(side="left", padx=(5, 0))
        ttk.Label(
            leveling_panel,
            textvariable=self.leveling_status,
            foreground="#555555",
            wraplength=250,
        ).pack(anchor="w", pady=(4, 0))

        ttk.Checkbutton(
            left,
            text="Îi dau voie să meargă singur",
            variable=self.continuous_motion_ack,
            command=self._continuous_motion_permission_changed,
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            left,
            text="Fără bifă, Predatorul stă pe loc.",
            foreground="#555555",
            wraplength=250,
        ).pack(anchor="w", pady=(0, 6))
        driver_panel = ttk.LabelFrame(
            left, text="Codex AI — control manual", padding=7,
        )
        driver_panel.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            driver_panel,
            text="Codex AI poate folosi tastatura și mouse-ul",
            variable=self.codex_driver_enabled,
            command=self._codex_driver_changed,
        ).pack(anchor="w")
        self.codex_driver_text = tk.StringVar(
            value="Oprit: Codex AI nu trimite comenzi. Funcționează doar în WoW."
        )
        ttk.Label(
            driver_panel,
            textvariable=self.codex_driver_text,
            foreground="#555555",
            wraplength=250,
        ).pack(anchor="w", pady=(3, 0))

        sequence_panel = ttk.LabelFrame(
            future_tools, text="Mai multe locuri", padding=6,
        )
        sequence_panel.pack(fill="x", pady=(2, 6))
        self.sequence_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            sequence_panel,
            text="Mergi la ele în ordine",
            variable=self.sequence_enabled,
            command=self._sequence_changed,
        ).pack(anchor="w")
        self.sequence_listbox = tk.Listbox(sequence_panel, height=3, width=28, exportselection=False)
        self.sequence_listbox.pack(fill="x", pady=(4, 4))
        self.sequence_loop_count = tk.IntVar(value=1)
        sequence_buttons = ttk.Frame(sequence_panel)
        sequence_buttons.pack(fill="x")
        ttk.Button(sequence_buttons, text="Adaugă locul", command=self._sequence_add_current).pack(side="left")
        ttk.Button(sequence_buttons, text="Șterge", command=self._sequence_remove_selected).pack(side="left", padx=(4, 0))
        ttk.Label(sequence_panel, text="De câte ori?").pack(anchor="w", pady=(4, 0))
        ttk.Spinbox(sequence_panel, from_=1, to=32, textvariable=self.sequence_loop_count, width=6).pack(anchor="w")
        self.sequence_close_loop = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            sequence_panel,
            text="La final, revino la primul loc",
            variable=self.sequence_close_loop,
            command=self._sequence_changed,
        ).pack(anchor="w", pady=(4, 0))
        self._sequence_render()
        # The foundation always opens in autonomous mode. Operator routes stay
        # available under "Mai târziu" and are never deleted.
        self.journey_mode = tk.StringVar(value="autonomous_destination")
        journey_modes = ttk.Frame(left)
        journey_modes.pack(anchor="w", pady=(4, 4))
        ttk.Radiobutton(
            journey_modes, text="Alege singur drumul",
            variable=self.journey_mode, value="autonomous_destination",
            command=self._journey_mode_changed,
        ).pack(anchor="w")
        ttk.Radiobutton(
            journey_modes, text="Mergi pe drumul meu",
            variable=self.journey_mode, value="operator_route",
            command=self._journey_mode_changed,
        ).pack(anchor="w")
        self.route_text = tk.StringVar(
            value=(
                f"Merge la: {self.destination_name.get()}\n"
                f"{semantic_diagnostics}"
            )
        )
        ttk.Label(left, textvariable=self.route_text, wraplength=250).pack(anchor="w", pady=(4, 14))
        ttk.Label(
            left,
            text="Test LAB cu godmode: continuă mersul prin aggro, fără să atace. Lupta se pornește separat.",
            wraplength=260,
        ).pack(anchor="w", pady=(0, 8))

        self.position_text = tk.StringVar(value="Loc: aștept jocul")
        from location_label_reader import LocationLabelReader
        self.location_label_reader = LocationLabelReader(
            CONTROL_CENTER_LIVE_DIAGNOSTIC, SESSION_RECEIPT, os.getpid(),
        )
        self.location_label_text = tk.StringVar(value="Regiune / subzonă: aștept API-ul")
        self.observation_source_text = tk.StringVar(
            value=_live_observation_source_text(None, now_monotonic_s=0.0)
        )
        self.orientation_value_text = tk.StringVar(
            value=_body_camera_orientation_text(None)
        )
        self.controller_text = tk.StringVar(value="Acum: stă pe loc")
        self.mesh_text = tk.StringVar(value="Harta drumului: nu e gata")
        for variable in (
            self.position_text,
            self.observation_source_text,
            self.orientation_value_text,
            self.controller_text,
            self.mesh_text,
        ):
            ttk.Label(left, textvariable=variable, wraplength=260).pack(anchor="w", pady=3)
        ttk.Label(
            left,
            text="Albastru = Predatorul • Portocaliu = privirea",
            foreground="#555555",
            wraplength=260,
        ).pack(anchor="w", pady=(0, 3))
        stationary_panel = ttk.LabelFrame(
            left, text="Verifică locul", padding=7,
        )
        stationary_panel.pack(fill="x", pady=(7, 2))
        self.stationary_validation_button = ttk.Button(
            stationary_panel,
            text="Verifică (4 secunde)",
            command=self._start_stationary_validation,
        )
        self.stationary_validation_button.pack(fill="x")
        self.stationary_validation_text = tk.StringVar(
            value=_stationary_pose_text(None)
        )
        ttk.Label(
            stationary_panel,
            textvariable=self.stationary_validation_text,
            foreground="#555555",
            wraplength=245,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            future_tools,
            text="Verific singur harta și ghidul.",
            foreground="#555555",
            wraplength=260,
        ).pack(anchor="w", pady=(0, 3))

        ttk.Separator(left).pack(fill="x", pady=14)
        ttk.Label(left, text="Ce este în jur", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.awareness_text = tk.StringVar(
            value=self._structure_awareness_text(None)
        )
        ttk.Label(
            left,
            textvariable=self.awareness_text,
            wraplength=260,
        ).pack(anchor="w", pady=(5, 12))

        recorder_panel = ttk.LabelFrame(
            future_tools, text="Arată-i un drum", padding=8,
        )
        recorder_panel.pack(fill="x", pady=(2, 10))
        self.record_manual_button = ttk.Button(
            recorder_panel,
            text="● PORNEȘTE ÎNREGISTRAREA",
            command=self._start_manual_recording,
        )
        self.stop_manual_button = ttk.Button(
            recorder_panel,
            text="■ OPREȘTE ȘI SALVEAZĂ",
            command=self._stop_manual_recording,
            state="disabled",
        )
        self.record_manual_button.pack(fill="x")
        self.stop_manual_button.pack(fill="x", pady=(5, 0))
        self.manual_recording_text = tk.StringVar(
            value=(
                f"Oprit • {self.recording_start_hotkey}=pornește • "
                f"{self.recording_stop_hotkey}=oprește"
            )
        )
        ttk.Label(
            recorder_panel,
            textvariable=self.manual_recording_text,
            foreground="#555555",
            wraplength=230,
        ).pack(anchor="w", pady=(5, 0))

        overlay_panel = ttk.LabelFrame(
            future_tools, text="Ce văd peste joc", padding=8,
        )
        overlay_panel.pack(fill="x", pady=(2, 10))
        self.overlay_policy = tk.StringVar(
            value=OVERLAY_POLICY_LABELS[str(settings["policy"])]
        )
        policy = ttk.Combobox(
            overlay_panel, textvariable=self.overlay_policy, state="readonly",
            values=tuple(OVERLAY_POLICY_VALUES), width=24,
        )
        policy.pack(anchor="w", pady=(6, 5))
        self.overlay_opacity = tk.DoubleVar(value=float(settings["opacity"]))
        ttk.Label(overlay_panel, text="Cât de tare se vede").pack(anchor="w")
        ttk.Scale(
            overlay_panel, from_=0.2, to=1.0, variable=self.overlay_opacity,
            orient="horizontal", length=230,
        ).pack(anchor="w")
        self.overlay_mesh = tk.BooleanVar(value=bool(settings["show_mesh"]))
        self.overlay_roads = tk.BooleanVar(value=bool(settings["show_roads"]))
        self.overlay_facing = tk.BooleanVar(value=bool(settings["show_facing"]))
        ttk.Checkbutton(
            overlay_panel,
            text="Arată drumurile",
            variable=self.overlay_roads,
            command=self._operator_editor_visibility_changed,
        ).pack(anchor="w")
        ttk.Checkbutton(overlay_panel, text="Arată suprafața pe care poate merge", variable=self.overlay_mesh).pack(anchor="w")
        ttk.Checkbutton(overlay_panel, text="Arată săgețile", variable=self.overlay_facing).pack(anchor="w")
        ttk.Button(overlay_panel, text="Aplică", command=self._apply_overlay_settings).pack(anchor="w", pady=(6, 0))
        ttk.Label(overlay_panel, text="La început nu se vede.", foreground="#666666").pack(anchor="w", pady=(3, 0))

        map_header = ttk.Frame(right)
        map_header.pack(fill="x")
        ttk.Label(
            map_header, text="Harta acum",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        self.live_map_text = tk.StringVar(value="Aștept poziția din joc")
        ttk.Label(
            map_header, textvariable=self.live_map_text,
            foreground="#126a34", font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(12, 0))
        map_tools = ttk.Frame(right)
        map_tools.pack(fill="x", pady=(4, 0))
        self.cursor_text = tk.StringVar(value="Harta arată locul din joc")
        ttk.Label(right, textvariable=self.cursor_text, foreground="#555555").pack(anchor="w")
        # Keep location context beside the map, without growing the already
        # dense controls column and pushing the start/pause row off-screen.
        ttk.Label(right, textvariable=self.location_label_text).pack(anchor="w")
        self.zoom_text = tk.StringVar(value="Încadrare automată")
        ttk.Checkbutton(
            map_tools,
            text="Urmărește Predatorul",
            variable=self.follow_predator,
            command=self._follow_predator_changed,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(map_tools, text="Toată harta", command=self._reset_atlas_view).pack(side="left", padx=(0, 8))
        self.nav_viewer_button = ttk.Button(
            map_tools, text="Hartă 3D", command=self._open_3d_navmesh_viewer,
        )
        self.nav_viewer_button.pack(side="left", padx=(0, 8))
        ttk.Label(map_tools, textvariable=self.zoom_text).pack(side="left")
        self.canvas = tk.Canvas(right, bg="#08110c", highlightthickness=1, highlightbackground="#31493a")
        self.canvas.pack(fill="both", expand=True, pady=(6, 0))
        self.canvas.bind("<Configure>", self._canvas_resized)
        self.canvas.bind("<Button-1>", self._canvas_click)
        self.canvas.bind("<Motion>", self._canvas_motion)
        self.canvas.bind("<Leave>", self._canvas_leave)
        self.canvas.bind("<MouseWheel>", self._canvas_zoom)
        self.canvas.bind("<ButtonPress-3>", self._canvas_pan_start)
        self.canvas.bind("<B3-Motion>", self._canvas_pan_drag)
        self.canvas.bind("<ButtonRelease-3>", self._canvas_pan_end)

        path_editor = ttk.LabelFrame(
            future_tools, text="Desenează un drum", padding=8,
        )
        path_editor.pack(fill="x", pady=(8, 0))
        editor_top = ttk.Frame(path_editor)
        editor_top.pack(fill="x")
        ttk.Label(editor_top, text="Numele drumului").pack(side="left")
        self.path_name = tk.StringVar(value=self.operator_path.name)
        ttk.Entry(editor_top, textvariable=self.path_name, width=28).pack(side="left", padx=(6, 10))
        self.click_add_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            editor_top, text="Pun puncte cu mouse-ul", variable=self.click_add_enabled,
            command=self._operator_editor_visibility_changed,
        ).pack(side="left")
        self.draw_mode = tk.StringVar(value="Puncte de drum")
        ttk.Combobox(
            editor_top, textvariable=self.draw_mode, state="readonly",
            values=tuple(DRAW_MODES), width=20,
        ).pack(side="left", padx=(8, 0))
        editor_actions = ttk.Frame(path_editor)
        editor_actions.pack(fill="x", pady=(7, 0))
        ttk.Button(editor_actions, text="+ Locul de acum", command=self._add_current_waypoint).pack(side="left")
        ttk.Button(editor_actions, text="↶ Șterge ultimul punct", command=self._undo_waypoint).pack(side="left", padx=6)
        ttk.Button(editor_actions, text="Gata cu desenul", command=self._finish_feature).pack(side="left")
        ttk.Button(editor_actions, text="↶ Șterge ultima formă", command=self._undo_feature).pack(side="left", padx=6)
        ttk.Button(editor_actions, text="Șterge desenul", command=self._clear_waypoints).pack(side="left")
        ttk.Button(editor_actions, text="Salvează traseul", command=self._save_operator_path).pack(side="right")
        self.path_status = tk.StringVar(value="")
        ttk.Label(path_editor, textvariable=self.path_status, foreground="#555555").pack(anchor="w", pady=(5, 0))
        self._update_path_status("Desen încărcat")
        self._journey_mode_changed()

        controls = ttk.Frame(navigation_tab)
        controls.pack(fill="x")
        self.start_button = ttk.Button(
            controls, text="AȘTEAPTĂ…", command=self.start,
            state="disabled",
        )
        self.pause_button = ttk.Button(controls, text="Ⅱ  PAUZĂ", command=self.pause_resume, state="disabled")
        self.stop_button = ttk.Button(controls, text="■  OPREȘTE", command=self.stop, state="disabled")
        self.start_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.pause_button.pack(side="left", expand=True, fill="x", padx=6)
        self.stop_button.pack(side="left", expand=True, fill="x", padx=(6, 0))
        self._apply_autonomous_start_readiness(update_status=True)

        # Manual-input consent belongs only to this Control Center process.
        # Replace any record left by an older process immediately, so the UI
        # cannot look OFF while a stale file still says ON.  Codex remains
        # disabled until the operator explicitly ticks this process's box.
        self._codex_driver_changed()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<F9>", lambda _event: self._open_3d_navmesh_viewer())
        self.recording_hotkeys = GlobalRecordingHotkeys(
            self.recording_start_hotkey,
            self.recording_stop_hotkey,
            lambda: self.recording_hotkey_events.put("START"),
            lambda: self.recording_hotkey_events.put("STOP"),
        )
        try:
            self.recording_hotkeys.start()
        except RuntimeError as error:
            self.manual_recording_text.set(f"Tastele alese nu merg: {error}")
        self.root.after(100, self._refresh)
        Thread(target=self._load_structure_awareness_background, daemon=True).start()

    def _active_pose_zone_index(self) -> int:
        profile = self.active_world_map_profile
        semantic_catalog = getattr(profile, "semantic_catalog", None)
        if isinstance(semantic_catalog, Path) and semantic_catalog.is_file():
            return self._semantic_catalog_zone_index(
                semantic_catalog,
                expected_map_name=str(getattr(profile, "internal_name", "Azeroth")),
            )
        return 25

    def _ensure_live_pose_bridge(self) -> None:
        """Keep one hidden pose stream alive for both 2D and 3D maps."""

        process = self.nav_viewer_bridge_process
        if process is not None and process.poll() is None:
            return
        now_s = time.monotonic()
        if now_s < self.live_pose_restart_not_before_s:
            return
        self.live_pose_restart_not_before_s = now_s + 2.0
        if not SESSION_AUTH.is_file() or not SESSION_RECEIPT.is_file():
            return
        profile = self.active_world_map_profile
        try:
            expected_zone_index = self._active_pose_zone_index()
            arguments = _control_center_live_pose_arguments(
                owner_pid=os.getpid(),
                expected_zone_index=expected_zone_index,
                map_id=int(getattr(profile, "map_id", 0)),
                spatial_sonar_profile=getattr(profile, "runtime_profile", None),
                spatial_sonar_wmo_config=self.spatial_sonar_wmo_config,
                spatial_sonar_continuity=self.spatial_sonar_continuity,
            )
            self.nav_viewer_bridge_process = subprocess.Popen(
                arguments,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            self.nav_viewer_bridge_process = None

    def _schedule_live_map_session_renewal(self) -> None:
        """Keep passive map observation alive without extending input access."""

        if self.state != "STOPPED" or self.live_session_renew_inflight:
            return
        now_s = time.monotonic()
        if now_s < self.live_session_renew_not_before_s:
            return
        remaining_s = _session_authorization_remaining_s(SESSION_AUTH)
        if (
            remaining_s is not None
            and remaining_s > LIVE_MAP_RENEW_BEFORE_EXPIRY_S
        ):
            self.live_session_renew_not_before_s = now_s + max(
                1.0, remaining_s - LIVE_MAP_RENEW_BEFORE_EXPIRY_S,
            )
            return
        self.live_session_renew_inflight = True
        Thread(target=self._renew_live_map_session, daemon=True).start()

    def _renew_live_map_session(self) -> None:
        error: str | None = None
        try:
            receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
            parent_sha = str(receipt["authorization_sha256"])
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                    "--acknowledge-fixed-ui-session",
                    "--renewal-parent-sha256", parent_sha,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=30.0,
                creationflags=0x08000000,
            )
            subprocess.run(
                [
                    "pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR),
                    "-Action", "RenewSessionIdentity", "-RepositoryRoot", str(ROOT),
                    "-AuthorizationFile", str(SESSION_AUTH),
                    "-AcknowledgeSessionIdentity", "-AcknowledgeWindowRebind",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=45.0,
                creationflags=0x08000000,
            )
        except (
            FileNotFoundError, OSError, KeyError, TypeError, ValueError,
            json.JSONDecodeError, subprocess.SubprocessError,
        ) as exc:
            error = str(exc)
        self.live_session_renew_results.put(error)

    def _consume_live_map_session_renewal(self) -> None:
        latest: str | None | object = Ellipsis
        while True:
            try:
                latest = self.live_session_renew_results.get_nowait()
            except Empty:
                break
        if latest is Ellipsis:
            return
        self.live_session_renew_inflight = False
        if latest is None:
            remaining_s = _session_authorization_remaining_s(SESSION_AUTH)
            self.live_session_renew_not_before_s = time.monotonic() + max(
                60.0,
                (remaining_s or 600.0) - LIVE_MAP_RENEW_BEFORE_EXPIRY_S,
            )
        else:
            # Keep the bridge fail-closed and retry quietly. The main page
            # continues to say that the game is not visible until renewed.
            self.live_session_renew_not_before_s = time.monotonic() + 10.0

    def _start_stationary_validation(self) -> None:
        """Collect a bounded read-only pose window from the shared live stream."""

        if self.stationary_validation_running:
            return
        if self.state != "STOPPED":
            self.stationary_validation_text.set("Oprește Predatorul mai întâi")
            return
        self.stationary_validation_running = True
        self.stationary_validation_button.configure(
            state="disabled", text="Verific…"
        )
        self.stationary_validation_text.set(
            "Privesc 4 secunde fără să apăs nimic…"
        )
        Thread(target=self._collect_stationary_validation, daemon=True).start()

    def _collect_stationary_validation(self) -> None:
        samples: list[LiveMapPose] = []
        last_sequence = 0
        deadline = time.monotonic() + 4.0
        try:
            while time.monotonic() < deadline:
                now_s = time.monotonic()
                sample = read_live_pose_file(
                    NAV_VIEWER_STATE,
                    now_monotonic_s=now_s,
                    maximum_age_s=0.60,
                )
                if sample is not None and sample.sequence > last_sequence:
                    samples.append(sample)
                    last_sequence = sample.sequence
                time.sleep(0.05)
            expected_location = load_expected_stationary_location(
                SEMANTIC_LOCATIONS,
                location_id=STATIONARY_VALIDATION_LOCATION_ID,
            )
            record = evaluate_stationary_pose(
                samples,
                expected_location=expected_location,
            ).to_record()
            _atomic_json(STATIONARY_POSE_REPORT, record)
            self.stationary_validation_results.put((record, None))
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            self.stationary_validation_results.put((None, str(error)))

    def _consume_stationary_validation_result(self) -> None:
        latest: tuple[dict[str, object] | None, str | None] | None = None
        while True:
            try:
                latest = self.stationary_validation_results.get_nowait()
            except Empty:
                break
        if latest is None:
            return
        record, error = latest
        self.stationary_validation_running = False
        self.stationary_validation_button.configure(
            state="normal", text="Verifică (4 secunde)"
        )
        self.stationary_validation_text.set(
            f"Nu am putut verifica: {error}" if error is not None else _stationary_pose_text(record)
        )

    def _load_structure_awareness_background(self) -> None:
        process = None
        try:
            profile = self.active_world_map_profile
            if profile is None or any(
                item is None for item in (
                    profile.structure_index,
                    profile.structure_access_graph,
                )
            ):
                raise RuntimeError("profilul de hartă nu are structure index/access graph")
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(STRUCTURE_AWARENESS_SERVICE),
                    "--world-pack-profile", str(profile.runtime_profile),
                    "--world-pack-store", str(WORLD_PACK_STORE),
                    "--world-structure-index", str(profile.structure_index),
                    "--structure-access-graph", str(profile.structure_access_graph),
                    # Select only an allowlisted local worker matching the
                    # graph hash; graph data cannot supply an executable path.
                    "--worker", str(_structure_awareness_worker(profile)),
                    "--navigation-worker", str(_navigation_worker()),
                ],
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=0x08000000,
            )
            if process.stdout is None:
                raise RuntimeError("serviciul awareness nu are canal de răspuns")
            line = process.stdout.readline()
            if not line:
                raise RuntimeError(
                    f"serviciul awareness s-a închis cu cod {process.poll()}"
                )
            summary = _validated_structure_service_ready(json.loads(line))
            error = None
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.terminate()
            process = None
            summary = None
            error = f"{type(exc).__name__}: {exc}"
        self.structure_awareness_results.put((process, summary, error))

    def _consume_structure_awareness_result(self) -> None:
        try:
            process, summary, error = self.structure_awareness_results.get_nowait()
        except Empty:
            return
        self._finish_structure_awareness_load(
            process=process,
            summary=summary,
            error=error,
        )

    def _finish_structure_awareness_load(
        self,
        *,
        process: subprocess.Popen[str] | None,
        summary: dict[str, object] | None,
        error: str | None,
    ) -> None:
        self.structure_awareness_service = process
        self.structure_awareness_summary = summary
        self.structure_awareness_error = error
        self.structure_awareness_loading = False
        if self.state == "STOPPED":
            motion_ack = getattr(self, "continuous_motion_ack", None)
            if (
                error is None
                and summary is not None
                and motion_ack is not None
                and motion_ack.get()
            ):
                try:
                    self._set_semantic_live_authority(True)
                except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
                    self.continuous_motion_ack.set(False)
                    self._save_ui_settings()
            self._apply_autonomous_start_readiness(update_status=True)

    def _query_structure_awareness_background(
        self, anchor: tuple[float, float, float | None],
    ) -> None:
        error = None
        response = None
        try:
            process = self.structure_awareness_service
            if (
                process is None
                or process.poll() is not None
                or process.stdin is None
                or process.stdout is None
            ):
                raise RuntimeError("serviciul awareness nu mai rulează")
            request_id = f"nearby:{uuid4()}"
            process.stdin.write(json.dumps({
                "request_id": request_id,
                "command": "NEARBY",
                "x": anchor[0],
                "y": anchor[1],
                "z": anchor[2],
                "radius_yards": 100.0,
                "include_hits": False,
            }, separators=(",", ":")) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                raise RuntimeError(
                    f"serviciul awareness s-a închis cu cod {process.poll()}"
                )
            response = _validated_structure_nearby(json.loads(line))
            if response["request_id"] != request_id:
                raise RuntimeError("serviciul awareness a răspuns la alt request")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        self.structure_query_results.put((response, anchor, error))

    def _consume_structure_query_result(self) -> None:
        try:
            response, anchor, error = self.structure_query_results.get_nowait()
        except Empty:
            return
        self.structure_query_in_flight = False
        if error is not None:
            self.structure_awareness_error = error
            self.structure_awareness_summary = None
            process = self.structure_awareness_service
            if process is not None and process.poll() is None:
                process.terminate()
            self.structure_awareness_service = None
            if self.state == "STOPPED":
                self._apply_autonomous_start_readiness(update_status=True)
            return
        self.structure_nearby_summary = response
        self.structure_nearby_anchor = anchor

    def _schedule_structure_awareness_query(
        self, snapshot: MovementLabSnapshot | None,
    ) -> None:
        if (
            snapshot is None
            or snapshot.player_world_x is None
            or snapshot.player_world_y is None
            or self.structure_awareness_summary is None
            or self.structure_query_in_flight
        ):
            return
        anchor = (
            snapshot.player_world_x,
            snapshot.player_world_y,
            snapshot.player_world_z,
        )
        previous = self.structure_nearby_anchor
        if previous is not None:
            vertical_change = (
                0.0
                if previous[2] is None or anchor[2] is None
                else abs(previous[2] - anchor[2])
            )
            if hypot(previous[0] - anchor[0], previous[1] - anchor[1]) < 1.5 and vertical_change < 2.0:
                return
        self.structure_query_in_flight = True
        Thread(
            target=self._query_structure_awareness_background,
            args=(anchor,),
            daemon=True,
        ).start()

    def _structure_awareness_text(
        self,
        snapshot: MovementLabSnapshot | None,
        local_environment: dict[str, object] | None = None,
        applicability: dict[str, object] | None = None,
        structure_access: dict[str, object] | None = None,
    ) -> str:
        crypt_trials = _crypt_trial_gate_text()
        summary = self.structure_awareness_summary
        if summary is None:
            detail = (
                "verificare în curs"
                if self.structure_awareness_loading
                else "nu pot citi harta"
            )
            return f"Harta: încă nu este gata ({detail})\n{crypt_trials}"
        inventory = (
            f"Pe hartă: {summary['wmo_count']} clădiri • "
            f"{summary['doodad_count']} lucruri de ocolit"
        )
        if (
            snapshot is None
            or snapshot.player_world_x is None
            or snapshot.player_world_y is None
        ):
            return f"{inventory}\nAștept să văd unde este\n{crypt_trials}"
        nearby = self.structure_nearby_summary
        if nearby is None:
            wmo_count = obstacle_count = full = partial = no_route = 0
            location = "În clădire: verific…"
        else:
            wmo_count = int(nearby["wmo_count"])
            obstacle_count = int(nearby["obstacle_count"])
            full = int(nearby["full_nav_count"])
            partial = int(nearby["partial_nav_count"])
            no_route = int(nearby["no_nav_count"])
            inside_asset = nearby.get("inside_wmo_asset")
            if isinstance(inside_asset, str):
                asset_name = inside_asset.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                location = f"În clădire: {asset_name}"
            else:
                location = "În clădire: nu"
        topology = "Podeaua: verific…"
        if local_environment is not None and applicability is not None:
            if applicability["applicable_to_live_pose"]:
                topology = (
                    f"Podeaua: "
                    f"{_plain_environment_state(local_environment['environment_state'])}\n"
                    f"Pereți: {len(local_environment['boundaries'])} • "
                    f"ieșiri: {len(local_environment['verified_egresses'])}"
                )
            else:
                topology = "Podeaua: o citesc din nou"
        access = "Uși și ieșiri: verific…"
        if structure_access is not None:
            if structure_access["applicable_to_live_pose"]:
                coverage = (
                    "mai lipsesc locuri"
                    if structure_access["coverage_state"]
                    == "PARTIAL_OBSERVED_COMPONENTS"
                    else "gata în zona văzută"
                )
                access = (
                    f"Uși și ieșiri: "
                    f"{structure_access['known_opening_count']} • {coverage}"
                )
            else:
                access = "Uși și ieșiri: le citesc din nou"
        return (
            f"{inventory}\n"
            f"Lângă el: {wmo_count} clădiri • {obstacle_count} lucruri de ocolit\n"
            f"{location}\n"
            f"Drumuri: {full} bune • {partial} pe jumătate • {no_route} lipsă\n"
            f"{topology}\n"
            f"{access}\n"
            f"{crypt_trials}"
        )

    @staticmethod
    def _load_settings() -> dict[str, object]:
        defaults: dict[str, object] = {
            "policy": "Never", "opacity": 0.85,
            "show_mesh": True, "show_roads": True, "show_facing": True,
            "journey_mode": "autonomous_destination",
            "leveling_enabled": False,
            "current_level": 1,
            "zygor_catalog_path": str(ZYGOR_LEVELING_CATALOG),
            "continuous_motion_ack": False,
            "recording_start_hotkey": "F1",
            "recording_stop_hotkey": "F2",
        }
        try:
            record = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return defaults
        if not isinstance(record, dict):
            return defaults
        result = {**defaults, **record}
        if result["policy"] not in {"Never", "Only while testing", "Always"}:
            return defaults
        if result["journey_mode"] not in {"autonomous_destination", "operator_route"}:
            return defaults
        if (
            type(result["leveling_enabled"]) is not bool
            or type(result["current_level"]) is not int
            or not 1 <= result["current_level"] <= 70
            or not isinstance(result["zygor_catalog_path"], str)
            or not result["zygor_catalog_path"].strip()
            or type(result["continuous_motion_ack"]) is not bool
        ):
            return defaults
        valid_hotkeys = GlobalRecordingHotkeys.KEY_CODES
        if (
            result["recording_start_hotkey"] not in valid_hotkeys
            or result["recording_stop_hotkey"] not in valid_hotkeys
            or result["recording_start_hotkey"] == result["recording_stop_hotkey"]
        ):
            return defaults
        return result

    @staticmethod
    def _load_semantic_locations(
        catalog_path: Path = SEMANTIC_LOCATIONS,
        *,
        expected_map_name: str | None = None,
        expected_zone_index: int | None = None,
        expected_atlas_calibration: str | None = None,
    ) -> dict[str, tuple[str, float, float]]:
        """Load destinations without silently reusing another map's catalog.

        The default call remains the exact Tirisfal/Azeroth catalog used by the
        current LAB profile.  A registry-selected profile may supply its own
        catalog, but the map identity must be provided by that profile.  We do
        not infer a missing map/atlas binding from coordinates; unsupported
        profiles therefore fail closed at the UI boundary.
        """

        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("catalogul destinațiilor nu poate fi citit") from error
        is_default_catalog = (
            catalog_path.resolve() == SEMANTIC_LOCATIONS.resolve()
            and expected_map_name is None
            and expected_zone_index is None
            and expected_atlas_calibration is None
        )
        if is_default_catalog:
            expected_map_name = "Azeroth"
            expected_zone_index = 25
            expected_atlas_calibration = "WorldMapArea.dbc:Tirisfal"
        if (
            not isinstance(catalog, dict)
            or catalog.get("record_type") != "semantic_location_catalog"
            or catalog.get("schema_version") != "1.0"
            or not isinstance(catalog.get("map_name"), str)
            or not catalog.get("map_name")
            or (
                expected_map_name is not None
                and catalog.get("map_name") != expected_map_name
            )
            or not isinstance(catalog.get("zone_index"), int)
            or catalog.get("zone_index") < 0
            or (
                expected_zone_index is not None
                and catalog.get("zone_index") != expected_zone_index
            )
            or catalog.get("coordinate_system") != "tbc243_client_world_xy"
            or not isinstance(catalog.get("atlas_calibration"), str)
            or not catalog.get("atlas_calibration")
            or (
                expected_atlas_calibration is not None
                and catalog.get("atlas_calibration") != expected_atlas_calibration
            )
            or not isinstance(catalog.get("locations"), list)
        ):
            raise RuntimeError("catalogul destinațiilor nu este legat de profilul WorldPack")
        result: dict[str, tuple[str, float, float]] = {}
        names: set[str] = set()
        for item in catalog["locations"]:
            if not isinstance(item, dict):
                raise RuntimeError("destinația semantică nu este un obiect")
            destination_id = item.get("id")
            name = item.get("name")
            world = item.get("world")
            if (
                not isinstance(destination_id, str)
                or not destination_id
                or not isinstance(name, str)
                or not name
                or not isinstance(world, list)
                or len(world) != 2
                or not all(isinstance(value, (int, float)) for value in world)
                or destination_id in result
                or name in names
            ):
                raise RuntimeError("catalogul conține o destinație invalidă sau duplicată")
            result[destination_id] = (name, float(world[0]), float(world[1]))
            names.add(name)
        if not result:
            raise RuntimeError("catalogul destinațiilor este gol")
        return result

    @staticmethod
    def _semantic_catalog_zone_index(
        catalog_path: Path,
        *,
        expected_map_name: str,
    ) -> int:
        """Read the selected catalog's explicit client WorldMapArea binding.

        The first Azeroth slice used zone ``25`` as a launch constant.  A
        registry-selected catalog must carry its own area ID instead, otherwise
        a future Kalimdor/Outland catalog could be silently converted through
        Tirisfal's transform.  This helper reads metadata only; the child
        runner still validates the catalog and transform before any input.
        """

        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("catalogul semantic nu poate fi citit") from error
        zone_index = catalog.get("zone_index") if isinstance(catalog, dict) else None
        if (
            not isinstance(catalog, dict)
            or catalog.get("record_type") != "semantic_location_catalog"
            or catalog.get("schema_version") != "1.0"
            or catalog.get("map_name") != expected_map_name
            or type(zone_index) is not int
            or not 0 <= zone_index <= 65_535
            or catalog.get("coordinate_system") != "tbc243_client_world_xy"
            or not isinstance(catalog.get("atlas_calibration"), str)
            or not catalog.get("atlas_calibration")
        ):
            raise RuntimeError("catalogul semantic nu are binding WorldMapArea valid")
        return zone_index

    def _leveling_changed(self) -> None:
        """Refresh the small level selector without starting anything."""

        try:
            level = int(self.current_level.get())
        except (TypeError, ValueError, tk.TclError):
            self.leveling_status.set("Nivel invalid: alege 1 până la 70")
            return
        if not 1 <= level <= 70:
            self.leveling_status.set("Nivel invalid: alege 1 până la 70")
            return
        if not self.leveling_enabled.get():
            self.leveling_status.set("Ghid oprit")
            self._journey_mode_changed()
            return
        catalog_path = Path(self.zygor_catalog_path.get()).expanduser()
        if not catalog_path.is_file():
            self.leveling_status.set(
                "Ghid pornit, dar fișierul lipsește; apasă Alege"
            )
            self._journey_mode_changed()
            return
        self.leveling_status.set(
            f"Ghid pornit de la nivelul {level}; îl verific la PORNEȘTE"
        )
        self._journey_mode_changed()

    def _choose_zygor_catalog(self) -> None:
        """Choose a locally built catalog, never the original addon payload."""

        selected = filedialog.askopenfilename(
            title="Alege fișierul ghidului",
            initialdir=str(Path(self.zygor_catalog_path.get()).expanduser().parent),
            filetypes=(("Catalogă JSON", "*.json"), ("Toate fișierele", "*.*")),
        )
        if not selected:
            return
        self.zygor_catalog_path.set(selected)
        self._leveling_changed()

    def _prepare_leveling_plan(self, profile):
        """Build the next advisory Zygor slice for the selected current level."""

        if not self.leveling_enabled.get():
            return None
        try:
            current_level = int(self.current_level.get())
        except (TypeError, ValueError, tk.TclError) as error:
            raise RuntimeError("nivelul de leveling este invalid") from error
        if not 1 <= current_level <= 70:
            raise RuntimeError("nivelul de leveling trebuie să fie între 1 și 70")
        catalog_path = Path(self.zygor_catalog_path.get()).expanduser().resolve()
        catalog = load_knowledge_broker_catalog(catalog_path)
        if catalog.target_profile != "tbc243_lab":
            raise RuntimeError("catalogă Zygor pentru alt profil TBC")
        plan = LevelingBrain().plan(
            catalog,
            LevelingRequest(
                current_level=current_level,
                map_id=int(profile.map_id),
                limit=16,
            ),
            plan_id=f"ui:zygor-leveling:{uuid4()}",
        )
        if plan.status != "READY" or plan.next_goal is None:
            raise RuntimeError(
                "ghidul nu are încă un pas cu poziție pentru harta aleasă "
                f"(status={plan.status})"
            )
        _atomic_json(LEVELING_PLAN_FILE, plan.to_record())
        self.leveling_status.set(
            f"Ghid gata • nivel {current_level} • "
            f"{len(plan.steps)} pași de urmat"
        )
        return plan

    def _load_semantic_journey(
        self, destination_id: str,
    ) -> tuple[tuple[tuple[float, float], ...], str]:
        snapshot = self.last_snapshot
        if (
            snapshot is None
            or snapshot.player_world_x is None
            or snapshot.player_world_y is None
        ):
            self.semantic_journey_anchor = None
            return (
                (),
                "Aleg drumul când apeși PORNEȘTE",
            )
        try:
            destination = self.semantic_locations[destination_id]
            start_x = snapshot.player_world_x
            start_y = snapshot.player_world_y
            profile = getattr(self, "active_world_map_profile", None)
            if profile is None or profile.runtime_profile is None:
                raise RuntimeError("profilul WorldPack activ nu are runtime profile")
            binding = _cached_world_pack_binding(
                profile.runtime_profile.resolve(), WORLD_PACK_STORE.resolve(),
            )
            route = ClientRoadSemanticPlanner(
                sidecar_root=binding.pack.pack_root / "semantics"
            ).plan(
                start_x=start_x, start_y=start_y,
                destination_x=destination[1], destination_y=destination[2],
            )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError):
            return (), "Nu pot alege drumul. Vezi jurnalul."
        self.semantic_journey_anchor = (start_x, start_y)
        return (
            tuple((point.x, point.y) for point in route.waypoints),
            f"Am ales drumul: {len(route.waypoints)} puncte",
        )

    def _refresh_live_semantic_journey(
        self, snapshot: MovementLabSnapshot | None,
    ) -> None:
        if self.journey_mode.get() != "autonomous_destination":
            return
        if (
            snapshot is None
            or snapshot.player_world_x is None
            or snapshot.player_world_y is None
        ):
            if self.state == "STOPPED" and self.semantic_journey:
                self.semantic_journey = ()
                self.semantic_journey_anchor = None
                self.route_text.set(
                    f"Merge la: {self.destination_name.get()}\n"
                    "Aleg drumul când apeși PORNEȘTE"
                )
            return
        anchor = self.semantic_journey_anchor
        if anchor is not None and hypot(
            snapshot.player_world_x - anchor[0],
            snapshot.player_world_y - anchor[1],
        ) < 25.0:
            return
        self.semantic_journey, diagnostics = self._load_semantic_journey(
            self.semantic_destination_id
        )
        self.route_text.set(
            f"Merge la: {self.destination_name.get()}\n{diagnostics}"
        )

    def _select_semantic_destination(self, _event: tk.Event | None = None) -> None:
        destination_id = self.destination_id_by_name.get(self.destination_name.get())
        if destination_id is None:
            self.route_text.set("Destinația aleasă nu mai există în listă")
            return
        self.semantic_destination_id = destination_id
        self.semantic_journey, diagnostics = self._load_semantic_journey(destination_id)
        self.route_text.set(
            f"Merge la: {self.destination_name.get()}\n{diagnostics}"
        )
        self._draw_snapshot(self.last_snapshot)

    def _select_world_map_profile(self, _event: tk.Event | None = None) -> None:
        """Select an inventory profile without silently mixing map evidence.

        The registry is authoritative for map/profile identity.  Until a map
        has its own semantic catalog and compatible structure graph, the UI
        exposes it for inspection but keeps autonomous execution disabled.
        """

        selected_name = self.world_map_name.get()
        profile = next(
            (item for item in self.world_map_profiles
             if item.internal_name == selected_name),
            None,
        )
        if profile is None:
            self.route_text.set("Harta aleasă nu mai există")
            return
        if self.state != "STOPPED":
            self.world_map_name.set(
                self.active_world_map_profile.internal_name
                if self.active_world_map_profile is not None
                else "indisponibil"
            )
            self.route_text.set("Oprește mersul înainte să schimbi harta")
            return
        self.active_world_map_profile = profile
        old_service = self.structure_awareness_service
        if old_service is not None and old_service.poll() is None:
            old_service.terminate()
        self.structure_awareness_service = None
        self.structure_awareness_summary = None
        self.structure_nearby_summary = None
        self.structure_awareness_error = None
        self.structure_awareness_loading = True
        if profile.structure_index is not None and profile.structure_access_graph is not None:
            Thread(
                target=self._load_structure_awareness_background,
                daemon=True,
            ).start()
        # Never leave Azeroth destinations visible after switching to another
        # registry profile.  A profile's semantic catalog is optional evidence;
        # when absent or malformed the map remains inspectable but cannot be
        # started autonomously.
        try:
            if profile.semantic_catalog is None:
                raise RuntimeError("profilul nu are catalog semantic")
            locations = self._load_semantic_locations(
                profile.semantic_catalog,
                expected_map_name=profile.internal_name,
            )
        except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
            locations = {}
        self.semantic_locations = locations
        self.destination_id_by_name = {
            location[0]: destination_id
            for destination_id, location in locations.items()
        }
        self.sequence_destination_ids = []
        self.semantic_destination_id = next(iter(locations), "")
        self.semantic_journey = ()
        self.semantic_journey_anchor = None
        self.destination_picker.configure(
            values=tuple(self.destination_id_by_name),
        )
        if locations:
            self.destination_name.set(locations[self.semantic_destination_id][0])
            self.sequence_destination_ids = [self.semantic_destination_id]
        else:
            self.destination_name.set("indisponibil")
        self._sequence_render()
        artifacts = (
            profile.runtime_profile,
            profile.semantic_catalog,
            profile.structure_index,
            profile.structure_access_graph,
        )
        if not locations or any(item is None or not item.is_file() for item in artifacts):
            self.destination_picker.configure(state="disabled")
            self.sequence_enabled.set(False)
            self.route_text.set(
                f"{profile.internal_name}: harta poate fi văzută, "
                "dar nu are încă toate datele pentru mers singur"
            )
            self._apply_autonomous_start_readiness(update_status=True)
            return
        self.destination_picker.configure(state="readonly")
        self.route_text.set(
            f"{profile.internal_name}: harta este gata; drumul se calculează "
            "din locul în care este Predatorul"
        )
        self._apply_autonomous_start_readiness(update_status=True)
        self._draw_snapshot(self.last_snapshot)

    def _sequence_render(self) -> None:
        if not hasattr(self, "sequence_listbox"):
            return
        self.sequence_listbox.delete(0, tk.END)
        for destination_id in self.sequence_destination_ids:
            name = self.semantic_locations.get(destination_id, (destination_id,))[0]
            self.sequence_listbox.insert(tk.END, name)

    def _sequence_add_current(self) -> None:
        destination_id = self.destination_id_by_name.get(self.destination_name.get())
        if destination_id is None or destination_id in self.sequence_destination_ids:
            return
        if len(self.sequence_destination_ids) >= 16:
            self.route_text.set("Lista poate avea cel mult 16 destinații")
            return
        self.sequence_destination_ids.append(destination_id)
        self._sequence_render()
        self._sequence_changed()

    def _sequence_remove_selected(self) -> None:
        if not hasattr(self, "sequence_listbox"):
            return
        selected = self.sequence_listbox.curselection()
        if not selected:
            return
        del self.sequence_destination_ids[selected[0]]
        self._sequence_render()
        self._sequence_changed()

    def _sequence_changed(self) -> None:
        if self.sequence_enabled.get() and len(self.sequence_destination_ids) < 2:
            self.route_text.set("Adaugă cel puțin două destinații în listă")
        elif self.sequence_enabled.get():
            self.route_text.set(
                f"Listă: {len(self.sequence_destination_ids)} locuri × "
                f"{self.sequence_loop_count.get()} repetări"
                + (" • apoi revine la primul" if self.sequence_close_loop.get() else "")
            )
        elif self.journey_mode.get() == "autonomous_destination":
            self.route_text.set(f"Merge la: {self.destination_name.get()}")
        self._draw_snapshot(self.last_snapshot)

    def _journey_mode_changed(self) -> None:
        if not hasattr(self, "destination_picker"):
            return
        if self.journey_mode.get() == "operator_route":
            self.destination_picker.configure(state="disabled")
            self.route_text.set(
                f"Drum desenat: {self.operator_path.name}\n"
                f"{len(self.operator_path.waypoints)} puncte"
            )
        else:
            if self.state == "STOPPED":
                self.destination_picker.configure(state="readonly")
            self.route_text.set(
                f"Merge la: {self.destination_name.get()}\n"
                + (
                    f"Am ales drumul: {len(self.semantic_journey)} puncte"
                    if self.semantic_journey
                    else "Aleg drumul când apeși PORNEȘTE"
                )
            )
            if (
                getattr(self, "leveling_enabled", None) is not None
                and self.leveling_enabled.get()
            ):
                self.destination_picker.configure(state="disabled")
                self.route_text.set(
                    f"Nivel {self.current_level.get()}\n"
                    "Aleg următorul pas când apeși PORNEȘTE"
                )
        self._draw_snapshot(self.last_snapshot)

    def _operator_editor_visibility_changed(self) -> None:
        """Refresh editor-only layers without making them navigation inputs."""
        self._draw_snapshot(self.last_snapshot)

    def _show_operator_editor_layers(self) -> bool:
        """Keep operator-authored drawings out of the autonomous map view."""
        return (
            self.journey_mode.get() == "operator_route"
            or self.click_add_enabled.get()
        )

    @staticmethod
    def _semantic_gate_open() -> bool:
        try:
            record = json.loads(SEMANTIC_GATE.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                return False
            binding = _verified_world_pack_binding()
            expected = semantic_live_gate_identity(
                binding,
                profile_path=WORLD_PACK_PROFILE,
                worker_path=_navigation_worker(),
            )
            return semantic_live_gate_open(record, expected=expected)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            return False

    def _autonomous_start_readiness(self) -> tuple[bool, str, str]:
        profile = getattr(self, "active_world_map_profile", None)
        # Small contract tests construct the client with __new__ to exercise
        # the readiness gate without Tk initialization.  Preserve the legacy
        # default in that diagnostic-only shape; a real UI instance always has
        # an explicit registry selection.
        profile_selection_present = hasattr(self, "active_world_map_profile")
        if profile_selection_present and profile is None:
            return (
                False,
                "HARTA NU ESTE GATA",
                "Nu pot porni: harta aleasă nu are încă toate datele de drum",
            )
        if profile_selection_present and any(
            item is None or not item.is_file()
            for item in (
                profile.runtime_profile,
                profile.semantic_catalog,
                profile.structure_index,
                profile.structure_access_graph,
            )
        ):
            return (
                False,
                "HARTA NU ESTE GATA",
                "Nu pot porni: hărții alese îi lipsesc date",
            )
        if self.structure_awareness_loading:
            return autonomous_start_readiness(
                structure_loading=True,
                semantic_gate_open=False,
                structure_index_loaded=False,
                structure_graph_configured=(
                    STRUCTURE_ACCESS_GRAPH is not None
                    if profile is None
                    else profile.structure_access_graph is not None
                ),
                structure_graph_loaded=False,
                structure_error=None,
            )
        summary = self.structure_awareness_summary
        semantic_gate_state = (
            "INVALID"
            if summary is None
            else _semantic_gate_state_for_structure_summary(
                summary, profile=profile,
            )
        )
        return autonomous_start_readiness(
            structure_loading=False,
            semantic_gate_open=semantic_gate_state == "OPEN",
            structure_index_loaded=summary is not None,
            structure_graph_configured=(
                STRUCTURE_ACCESS_GRAPH is not None
                if profile is None
                else profile.structure_access_graph is not None
            ),
            structure_graph_loaded=summary is not None,
            structure_error=self.structure_awareness_error,
            semantic_gate_reason=semantic_gate_state,
        )

    def _apply_autonomous_start_readiness(
        self, *, update_status: bool = False,
    ) -> tuple[bool, str]:
        ready, button_text, explanation = self._autonomous_start_readiness()
        self.start_button.configure(
            state="normal" if ready else "disabled",
            text=button_text,
        )
        if update_status:
            self.state_text.set("Oprit" if ready else explanation)
        return ready, explanation

    def _set_semantic_live_authority(self, enabled: bool) -> None:
        """Bind the plain movement checkbox to the verified map certificate."""

        profile = self.active_world_map_profile
        if profile is None or profile.runtime_profile is None:
            raise RuntimeError("harta aleasă nu are WorldPack pentru mers")
        binding = _cached_world_pack_binding(
            profile.runtime_profile.resolve(), WORLD_PACK_STORE.resolve(),
        )
        expected = semantic_live_gate_identity(
            binding,
            profile_path=profile.runtime_profile,
            worker_path=_navigation_worker(),
        )
        record = json.loads(SEMANTIC_GATE.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise RuntimeError("certificatul hărții nu poate fi citit")
        rebound = rebind_semantic_live_gate_authority(
            record, expected=expected, enabled=enabled,
        )
        _atomic_json(SEMANTIC_GATE, rebound)

    @staticmethod
    def _load_operator_path() -> OperatorAuthoredPath:
        try:
            return OperatorAuthoredPath.from_record(
                json.loads(OPERATOR_PATH_FILE.read_text(encoding="utf-8"))
            )
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return OperatorAuthoredPath("operator-path-draft", "Traseu nou", "Azeroth")

    @staticmethod
    def _load_map_knowledge() -> OperatorMapKnowledge:
        try:
            return OperatorMapKnowledge.from_record(
                json.loads(OPERATOR_MAP_KNOWLEDGE_FILE.read_text(encoding="utf-8"))
            )
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return OperatorMapKnowledge("Azeroth")

    def _update_path_status(self, prefix: str) -> None:
        count = len(self.operator_path.waypoints)
        self.path_status.set(f"{prefix} • {count} punct{'e' if count != 1 else ''}")

    def _add_waypoint(self, *, x: float, y: float, z: float | None = None) -> None:
        self.operator_path = self.operator_path.add(x=x, y=y, z=z)
        self._update_path_status("Punct adăugat")
        self._draw_snapshot(self.last_snapshot)

    def _add_current_waypoint(self) -> None:
        snapshot = self.last_snapshot
        if snapshot is None or snapshot.player_world_x is None or snapshot.player_world_y is None:
            self._update_path_status("Poziția curentă nu este disponibilă")
            return
        self._add_waypoint(
            x=snapshot.player_world_x, y=snapshot.player_world_y, z=snapshot.player_world_z
        )

    def _canvas_click(self, event: tk.Event) -> None:
        if not self.click_add_enabled.get() or self.canvas_to_world is None:
            return
        try:
            x, y = self.canvas_to_world(float(event.x), float(event.y))
        except ValueError:
            self._update_path_status("Click-ul este în afara hărții")
            return
        kind = DRAW_MODES[self.draw_mode.get()]
        if kind == "waypoint_path":
            self._add_waypoint(x=x, y=y)
            return
        self.feature_draft.append(MapKnowledgeVertex(x, y))
        self._update_path_status(
            f"{self.draw_mode.get()}: punct {len(self.feature_draft)} adăugat"
        )
        if kind == "recovery_anchor":
            self._finish_feature()
        else:
            self._draw_snapshot(self.last_snapshot)

    def _canvas_motion(self, event: tk.Event) -> None:
        if self.canvas_to_world is None:
            return
        try:
            x, y = self.canvas_to_world(float(event.x), float(event.y))
        except ValueError:
            self.cursor_text.set("Nu este pe această hartă")
            return
        self.cursor_text.set(f"Loc: X {x:.2f} • Y {y:.2f}")

    def _canvas_leave(self, _event: tk.Event) -> None:
        self.cursor_text.set("Harta arată locul din joc")

    def _canvas_zoom(self, event: tk.Event) -> None:
        if self.world_map_photo is None or event.delta == 0:
            return
        target = max(1, min(8, self.atlas_viewport.zoom + (1 if event.delta > 0 else -1)))
        if target == self.atlas_viewport.zoom:
            return
        # Manual inspection owns the view until follow is explicitly re-enabled.
        self.follow_predator.set(False)
        self.atlas_viewport = self.atlas_viewport.zoom_at(
            target,
            cursor_x=float(event.x), cursor_y=float(event.y),
            canvas_width=float(max(1, self.canvas.winfo_width())),
            canvas_height=float(max(1, self.canvas.winfo_height())),
        )
        self.zoom_text.set("Încadrare automată" if target == 1 else f"Zoom {target}×")
        self._draw_snapshot(self.last_snapshot)

    def _canvas_pan_start(self, event: tk.Event) -> None:
        self.follow_predator.set(False)
        self.atlas_pan_anchor = (float(event.x), float(event.y))

    def _canvas_pan_drag(self, event: tk.Event) -> None:
        if self.atlas_pan_anchor is None:
            return
        current = (float(event.x), float(event.y))
        dimensions = dict(canvas_width=max(1, self.canvas.winfo_width()),
                          canvas_height=max(1, self.canvas.winfo_height()))
        scale = self.atlas_viewport.scale(**dimensions)
        self.atlas_viewport = self.atlas_viewport.constrained(**dimensions).pan_by(
            (current[0] - self.atlas_pan_anchor[0]) / scale,
            (current[1] - self.atlas_pan_anchor[1]) / scale,
        ).constrained(**dimensions)
        self.atlas_pan_anchor = current
        self._draw_snapshot(self.last_snapshot)

    def _canvas_pan_end(self, _event: tk.Event) -> None:
        self.atlas_pan_anchor = None

    def _reset_atlas_view(self) -> None:
        self.follow_predator.set(False)
        self.atlas_viewport = AtlasViewport(
            self.atlas_geometry.pixel_width, self.atlas_geometry.pixel_height
        )
        self.zoom_text.set("Încadrare automată")
        self._draw_snapshot(self.last_snapshot)

    def _follow_predator_changed(self) -> None:
        if self.follow_predator.get() and self.last_snapshot is not None:
            self._center_atlas_on_predator(self.last_snapshot)
        self._draw_snapshot(self.last_snapshot)

    def _center_atlas_on_predator(self, snapshot: MovementLabSnapshot) -> None:
        if snapshot.player_world_x is None or snapshot.player_world_y is None:
            return
        try:
            pixel_x, pixel_y = self.atlas_geometry.pixel_from_world(
                snapshot.player_world_x, snapshot.player_world_y,
            )
        except ValueError:
            return
        self.atlas_viewport = self.atlas_viewport.centered_on(pixel_x, pixel_y)

    def _canvas_resized(self, _event: tk.Event) -> None:
        if self.canvas_resize_job is None:
            self.canvas_resize_job = self.root.after(40, self._redraw_resized_canvas)

    def _redraw_resized_canvas(self) -> None:
        self.canvas_resize_job = None
        self._draw_snapshot(self.last_snapshot)

    def _atlas_photo(self, base: Image.Image, cache: dict,
                     width: int, height: int) -> ImageTk.PhotoImage:
        dimensions = dict(canvas_width=width, canvas_height=height)
        key = (id(base), width, height, self.atlas_viewport.scale(**dimensions),
               self.atlas_viewport.origin(**dimensions))
        if key not in cache:
            photo = ImageTk.PhotoImage(render_atlas_image(
                base, self.atlas_viewport, width, height), master=self.root)
            cache.clear()  # One viewport only, not eight full enlarged atlases.
            cache[key] = photo
        return cache[key]

    def _draw_recorded_facing_arrows(
        self, vertices: tuple[MapKnowledgeVertex, ...], screen, *, color: str,
    ) -> None:
        if not vertices:
            return
        stride = max(1, len(vertices) // 28)
        for vertex in vertices[::stride]:
            if vertex.facing_rad is None:
                continue
            try:
                start_x, start_y = screen((vertex.x, vertex.y))
                guide_x, guide_y = screen((
                    vertex.x + cos(vertex.facing_rad) * 20.0,
                    vertex.y + sin(vertex.facing_rad) * 20.0,
                ))
            except ValueError:
                continue
            length = hypot(guide_x - start_x, guide_y - start_y)
            if length < 0.1:
                continue
            arrow_length = 14.0
            end_x = start_x + (guide_x - start_x) / length * arrow_length
            end_y = start_y + (guide_y - start_y) / length * arrow_length
            self.canvas.create_line(
                start_x, start_y, end_x, end_y,
                fill=color, width=2, arrow=tk.LAST, arrowshape=(7, 8, 3),
            )

    def _undo_waypoint(self) -> None:
        if self.feature_draft:
            self.feature_draft.pop()
            self._update_path_status("Ultimul punct al formei a fost anulat")
            self._draw_snapshot(self.last_snapshot)
            return
        if not self.operator_path.waypoints:
            self._update_path_status("Nu există punct de anulat")
            return
        self.operator_path = self.operator_path.undo()
        self._update_path_status("Ultimul punct a fost anulat")
        self._draw_snapshot(self.last_snapshot)

    def _finish_feature(self) -> None:
        kind = DRAW_MODES[self.draw_mode.get()]
        if kind == "waypoint_path":
            self._update_path_status("Waypoints se salvează direct; alege un layer de hartă")
            return
        required = 3 if kind in {"roaming_zone", "obstacle"} else 2 if kind == "interior_route" else 1
        if len(self.feature_draft) < required:
            self._update_path_status(
                f"{self.draw_mode.get()} necesită minimum {required} puncte"
            )
            return
        base_name = self.path_name.get().strip() or "Knowledge"
        self.map_knowledge = self.map_knowledge.add_feature(
            kind=kind,
            name=f"{base_name} — {self.draw_mode.get()} {len(self.map_knowledge.features) + 1}",
            vertices=tuple(self.feature_draft),
        )
        self.feature_draft.clear()
        self._update_path_status(
            f"Layer încheiat • {len(self.map_knowledge.features)} forme nesalvate/salvate"
        )
        self._draw_snapshot(self.last_snapshot)

    def _undo_feature(self) -> None:
        if self.feature_draft:
            self.feature_draft.clear()
            self._update_path_status("Forma în lucru a fost anulată")
        elif self.map_knowledge.features:
            self.map_knowledge = self.map_knowledge.undo()
            self._update_path_status("Ultimul layer a fost anulat")
        else:
            self._update_path_status("Nu există layer de anulat")
        self._draw_snapshot(self.last_snapshot)

    def _clear_waypoints(self) -> None:
        if not self.operator_path.waypoints and not self.map_knowledge.features and not self.feature_draft:
            return
        if not messagebox.askyesno(
            "Șterge desenul", "Șterg toate punctele și formele desenate?"
        ):
            return
        self.operator_path = self.operator_path.clear()
        self.map_knowledge = self.map_knowledge.clear()
        self.feature_draft.clear()
        self._update_path_status("Draft golit")
        self._draw_snapshot(self.last_snapshot)

    def _save_operator_path(self) -> None:
        name = self.path_name.get().strip()
        if not name:
            self._update_path_status("Introdu un nume pentru traseu")
            return
        self.operator_path = self.operator_path.rename(name)
        _atomic_json(OPERATOR_PATH_FILE, self.operator_path.to_record())
        _atomic_json(OPERATOR_MAP_KNOWLEDGE_FILE, self.map_knowledge.to_record())
        self._update_path_status(
            f"Salvat: {OPERATOR_PATH_FILE.name} + {OPERATOR_MAP_KNOWLEDGE_FILE.name}"
        )

    def _write_manual_recorder_command(self, command: str) -> int:
        self.manual_recorder_revision += 1
        _atomic_json(MANUAL_RECORDER_CONTROL, {
            "schema_version": "1.0",
            "command": command,
            "revision": self.manual_recorder_revision,
        })
        return self.manual_recorder_revision

    def _prepare_manual_recording(
        self, *, recording_id: str, name: str, start_revision: int,
    ) -> None:
        try:
            receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
            parent_sha = str(receipt["authorization_sha256"])
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                    "--acknowledge-fixed-ui-session",
                    "--renewal-parent-sha256",
                    parent_sha,
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
                creationflags=0x08000000,
            )
            common = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR)]
            subprocess.run(
                common + [
                    "-Action", "RenewSessionIdentity", "-RepositoryRoot", str(ROOT),
                    "-AuthorizationFile", str(SESSION_AUTH), "-AcknowledgeSessionIdentity",
                    "-AcknowledgeWindowRebind",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
                creationflags=0x08000000,
            )
            # The visible-HUD capture boundary requires the exact game window
            # to be foreground. Starting from the external editor would
            # otherwise fail closed before the operator can take one step.
            _focus_exact_wow_window()
            time.sleep(0.15)
            MANUAL_RECORDER_LOG.parent.mkdir(parents=True, exist_ok=True)
            self.manual_recorder_log_stream = MANUAL_RECORDER_LOG.open(
                "w", encoding="utf-8"
            )
            self.manual_recorder_process = subprocess.Popen(
                [
                    sys.executable,
                    str(MANUAL_RECORDER),
                    "--session-authorization-file", str(SESSION_AUTH),
                    "--session-receipt", str(SESSION_RECEIPT),
                    "--control-file", str(MANUAL_RECORDER_CONTROL),
                    "--result-file", str(MANUAL_RECORDER_RESULT),
                    "--recording-id", recording_id,
                    "--name", name,
                    "--start-revision", str(start_revision),
                    "--expected-zone-index", "25",
                    "--minimum-spacing-world", "0.75",
                ],
                cwd=ROOT,
                stdout=self.manual_recorder_log_stream,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=0x08000000,
            )
            self.root.after(0, self._manual_recorder_running)
        except Exception as error:
            self.root.after(
                0, lambda detail=str(error): self._manual_recorder_error(detail)
            )

    def _start_manual_recording(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.manual_recording_text.set(
                "Oprește mersul singur înainte să mergi tu"
            )
            return
        if (
            self.manual_recorder_process is not None
            and self.manual_recorder_process.poll() is None
        ):
            return
        recording_id = f"manual:{uuid4()}"
        name = (self.path_name.get().strip() or "Traseu nou") + " — demonstrație manuală"
        self.manual_recording_id = recording_id
        self.manual_recording_draft = ()
        self.manual_result_mtime_ns = None
        start_revision = self._write_manual_recorder_command("RECORD")
        self.manual_recorder_state = "STARTING"
        self.manual_recording_text.set(
            "Pregătesc înregistrarea; apoi mergi normal…"
        )
        self.record_manual_button.configure(state="disabled")
        self.stop_manual_button.configure(state="normal")
        Thread(
            target=self._prepare_manual_recording,
            kwargs={
                "recording_id": recording_id,
                "name": name,
                "start_revision": start_revision,
            },
            daemon=True,
        ).start()

    def _manual_recorder_running(self) -> None:
        if self.manual_recorder_state != "STARTING":
            return
        self.manual_recorder_state = "RECORDING"
        self.manual_recording_text.set(
            "ÎNREGISTREZ ● mergi normal"
        )

    def _manual_recorder_error(self, detail: str) -> None:
        self.manual_recorder_state = "STOPPED"
        self.manual_recording_text.set("Nu pot înregistra. Vezi jurnalul.")
        self.record_manual_button.configure(state="normal")
        self.stop_manual_button.configure(state="disabled")

    def _stop_manual_recording(self) -> None:
        if self.manual_recorder_state not in {"STARTING", "RECORDING"}:
            return
        self._write_manual_recorder_command("STOP")
        self.manual_recorder_state = "STOPPING"
        self.manual_recording_text.set("Oprind și salvând…")
        self.stop_manual_button.configure(state="disabled")

    def _refresh_manual_recording_result(self) -> None:
        try:
            stat = MANUAL_RECORDER_RESULT.stat()
            if stat.st_mtime_ns == self.manual_result_mtime_ns:
                return
            result = ManualPathRecording.from_record(
                json.loads(MANUAL_RECORDER_RESULT.read_text(encoding="utf-8"))
            )
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return
        self.manual_result_mtime_ns = stat.st_mtime_ns
        if result.recording_id != self.manual_recording_id:
            return
        if result.status == "RECORDING":
            self.manual_recording_draft = result.as_map_knowledge_vertices()
            self.manual_recording_text.set(
                f"REC ● {len(result.vertices)} puncte • {result.distance_world:.1f} yd"
            )
            return
        if result.status == "INSUFFICIENT_PATH":
            self.manual_recording_draft = result.as_map_knowledge_vertices()
            self.manual_recording_text.set(
                "Nu ai parcurs încă 0,75 yd; traseul nu a fost importat"
            )
            return
        if result.status == "INTERRUPTED":
            self.manual_recording_draft = ()
            self.manual_recording_text.set(
                f"Salvat parțial ⚠ video + input + {len(result.vertices)} poziții"
            )
            self._update_path_status(
                "Recorderul a păstrat dovezile până la întrerupere; nu a creat o rută"
            )
            return
        if result.status == "IMPORTED":
            self.manual_recording_draft = ()
            return
        if result.status != "COMPLETE":
            return
        # A human demonstration is training/evaluation evidence, never an
        # executable route and never an automatic autonomy prior.  A separate
        # reviewed analysis may extract general follower behavior from it.
        self.manual_recording_draft = ()
        self.manual_recording_text.set(
            f"Salvat ✓ film + taste + {len(result.vertices)} locuri"
        )
        self._update_path_status("Drumul arătat a fost salvat")

    def _write_command(self, command: str) -> None:
        self.revision += 1
        _atomic_json(CONTROL_FILE, {
            "schema_version": "1.0", "command": command, "revision": self.revision,
        })

    def _save_ui_settings(self) -> None:
        """Save choices without making the Apply button carry hidden duties."""

        _atomic_json(SETTINGS_FILE, {
            "policy": OVERLAY_POLICY_VALUES.get(self.overlay_policy.get(), "Never"),
            "opacity": round(self.overlay_opacity.get(), 2),
            "show_mesh": self.overlay_mesh.get(),
            "show_roads": self.overlay_roads.get(),
            "show_facing": self.overlay_facing.get(),
            "journey_mode": self.journey_mode.get(),
            "leveling_enabled": self.leveling_enabled.get(),
            "current_level": int(self.current_level.get()),
            "zygor_catalog_path": self.zygor_catalog_path.get(),
            "continuous_motion_ack": self.continuous_motion_ack.get(),
            "recording_start_hotkey": self.recording_start_hotkey,
            "recording_stop_hotkey": self.recording_stop_hotkey,
        })

    def _continuous_motion_permission_changed(self) -> None:
        """Make the plain checkbox an immediate and unsurprising stop switch."""

        self._save_ui_settings()
        if self.continuous_motion_ack.get():
            try:
                self._set_semantic_live_authority(True)
            except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
                self.continuous_motion_ack.set(False)
                self._save_ui_settings()
                self.state_text.set(
                    "Nu pot porni: verificarea hărții nu mai corespunde"
                )
                self._apply_autonomous_start_readiness()
                return
            self._apply_autonomous_start_readiness(update_status=True)
            return
        self.motion_arm_renew_stop.set()
        if self.process is not None and self.process.poll() is None:
            self.stop()
        else:
            self._apply_autonomous_start_readiness(update_status=True)
        try:
            self._set_semantic_live_authority(False)
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            # An invalid or missing gate is already closed. Motion has also
            # been stopped above, so no input authority survives this error.
            return

    @staticmethod
    def _run_hidden_checked(arguments: list[str]) -> None:
        subprocess.run(
            arguments,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            creationflags=0x08000000,
        )

    def _renew_continuous_motion_arm_once(
        self,
        *,
        refresh_motion_authorization: bool,
        refresh_session_identity: bool,
    ) -> None:
        """Renew short evidence files; never grant scope beyond the checked UI."""

        common = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR)]
        if refresh_session_identity:
            receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
            parent_sha = str(receipt["authorization_sha256"])
            self._run_hidden_checked([
                sys.executable,
                str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                "--acknowledge-fixed-ui-session",
                "--renewal-parent-sha256", parent_sha,
            ])
            self._run_hidden_checked(common + [
                "-Action", "RenewSessionIdentity",
                "-RepositoryRoot", str(ROOT),
                "-AuthorizationFile", str(SESSION_AUTH),
                "-AcknowledgeSessionIdentity",
            ])
            self._run_hidden_checked(common + [
                "-Action", "ArmSession",
                "-RepositoryRoot", str(ROOT),
                "-AuthorizationFile", str(SESSION_AUTH),
                "-AcknowledgeRuntimeArm",
            ])
        if refresh_motion_authorization:
            parent_sha = hashlib.sha256(
                CONTINUOUS_MOTION_AUTHORIZATION_FILE.read_bytes()
            ).hexdigest().upper()
            self._run_hidden_checked([
                sys.executable,
                str(ROOT / "scripts" / "issue_continuous_motion_authorization.py"),
                "--output", str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
                "--acknowledge-continuous-motion",
                "--evidence-ref", "control_center:movement_permission_checked",
                "--renewal-parent-sha256", parent_sha,
            ])
        self._run_hidden_checked(common + [
            "-Action", "IssueMovementRealmRevalidation",
            "-RepositoryRoot", str(ROOT),
            "-AuthorizationFile", str(SESSION_AUTH),
            "-MovementAuthorizationFile", str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
            "-AcknowledgeContinuousMotion",
        ])
        self._run_hidden_checked([
            sys.executable,
            str(ROOT / "scripts" / "issue_continuous_motion_runtime_arm.py"),
            "--continuous-authorization-file",
            str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
            "--session-authorization-file", str(SESSION_AUTH),
            "--session-receipt", str(SESSION_RECEIPT),
            "--realm-revalidation-file", str(CONTINUOUS_MOTION_REVALIDATION_FILE),
            "--output", str(CONTINUOUS_MOTION_ARM_FILE),
            "--acknowledge-continuous-motion",
        ])

    def _maintain_continuous_motion_arm(
        self,
        process: subprocess.Popen[str],
        stop_event: Event,
    ) -> None:
        """Keep the checked journey continuous while its exact process lives."""

        next_motion_auth_s = time.monotonic() + MOTION_AUTH_RENEW_INTERVAL_S
        next_session_s = time.monotonic() + SESSION_RENEW_INTERVAL_S
        while not stop_event.wait(MOTION_ARM_RENEW_INTERVAL_S):
            if process.poll() is not None:
                return
            now_s = time.monotonic()
            refresh_session = now_s >= next_session_s
            refresh_motion = refresh_session or now_s >= next_motion_auth_s
            try:
                self._renew_continuous_motion_arm_once(
                    refresh_motion_authorization=refresh_motion,
                    refresh_session_identity=refresh_session,
                )
            except Exception as error:
                MOTION_ARM_RENEW_LOG.parent.mkdir(parents=True, exist_ok=True)
                with MOTION_ARM_RENEW_LOG.open("a", encoding="utf-8") as stream:
                    stream.write(
                        f"{time.time():.6f}\t{type(error).__name__}\t{error}\n"
                    )
                self.motion_arm_renew_results.put(("ERROR", str(error)))
                stop_event.set()
                return
            if refresh_motion:
                next_motion_auth_s = now_s + MOTION_AUTH_RENEW_INTERVAL_S
            if refresh_session:
                next_session_s = now_s + SESSION_RENEW_INTERVAL_S

    def _consume_motion_arm_renew_result(self) -> None:
        try:
            status, _detail = self.motion_arm_renew_results.get_nowait()
        except Empty:
            return
        if status == "ERROR" and self.state in {"STARTING", "RUNNING", "PAUSED"}:
            self.state_text.set("Mersul se oprește: nu mai pot verifica permisiunea")

    def _build_combat_tab(self, parent: ttk.Frame) -> None:
        """Keep hunting controls and navigation in one operator window."""

        panel = ttk.Frame(parent, padding=(8, 4))
        panel.pack(fill="x", anchor="nw")
        ttk.Label(panel, text="LUPTĂ", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            panel,
            text="Predator alege singur un inamic. În test nu poate muri.",
            foreground="#555555",
        ).pack(anchor="w", pady=(2, 14))
        self.combat_status_text = tk.StringVar(value="Oprit")
        ttk.Label(panel, textvariable=self.combat_status_text, font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(
            panel,
            text="Își alege singur inamicul",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(14, 12))
        buttons = ttk.Frame(panel)
        buttons.pack(fill="x")
        self.combat_start_button = ttk.Button(
            buttons, text="▶  PORNEȘTE LUPTA", command=self._combat_start,
        )
        self.combat_pause_button = ttk.Button(
            buttons, text="Ⅱ  PAUZĂ", command=self._combat_pause_resume, state="disabled",
        )
        self.combat_stop_button = ttk.Button(
            buttons, text="■  OPREȘTE", command=self._combat_stop, state="disabled",
        )
        self.combat_start_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.combat_pause_button.pack(side="left", expand=True, fill="x", padx=5)
        self.combat_stop_button.pack(side="left", expand=True, fill="x", padx=(5, 0))
        ttk.Separator(panel).pack(fill="x", pady=18)
        ttk.Label(
            panel,
            text=(
                "Harta este în fila Mers."
            ),
            foreground="#555555", wraplength=640,
        ).pack(anchor="w")

    def _refresh_runtime_view(
        self,
    ) -> tuple[
        MovementLabSnapshot | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
    ]:
        """Merge the navigator picture with the persistent live localization."""

        try:
            current_mtime_ns: int | None = MOVEMENT_STATE.stat().st_mtime_ns
        except OSError:
            current_mtime_ns = None
        if current_mtime_ns != self.movement_state_mtime_ns:
            self.movement_state_mtime_ns = current_mtime_ns
            runtime_record = _read_movement_runtime_record()
            if runtime_record is None:
                snapshot = None
                self.cached_local_environment = (None, None)
                self.cached_structure_access = None
                self.cached_dynamic_awareness = None
                self.cached_target_range_awareness = None
                self.cached_dynamic_experience_summary = None
            else:
                snapshot = _read_snapshot(runtime_record)
                self.cached_local_environment = _read_local_environment(runtime_record)
                self.cached_structure_access = _read_structure_access(runtime_record)
                self.cached_dynamic_awareness = _read_dynamic_entity_awareness(
                    runtime_record
                )
                self.cached_target_range_awareness = (
                    _read_selected_target_range_awareness(runtime_record)
                )
                self.cached_dynamic_experience_summary = (
                    _read_dynamic_experience_summary(runtime_record)
                )
            # Invalid/missing replacement must invalidate the previous frame.
            self.raw_movement_snapshot = snapshot
        now_s = time.monotonic()
        snapshot = self.raw_movement_snapshot
        process_running = self.process is not None and self.process.poll() is None
        if (
            snapshot is None
            or not process_running
            or self.state == "STOPPED"
            or not _movement_snapshot_is_fresh(snapshot, now_monotonic_s=now_s)
            or (
                self.movement_view_started_s is not None
                and snapshot.observed_monotonic_s < self.movement_view_started_s
            )
        ):
            snapshot = None
            self.cached_local_environment = (None, None)
            self.cached_structure_access = None
            self.cached_dynamic_awareness = None
            self.cached_target_range_awareness = None
            self.cached_dynamic_experience_summary = None
        self.last_snapshot = snapshot
        self.last_live_pose = _read_live_map_pose(
            NAV_VIEWER_STATE,
            now_monotonic_s=now_s,
        )
        if self.last_live_pose is not None:
            self.last_snapshot = _snapshot_with_live_pose(
                self.last_snapshot,
                self.last_live_pose,
            )
        return (
            self.last_snapshot,
            self.cached_local_environment[0],
            self.cached_local_environment[1],
            self.cached_structure_access,
        )

    def _write_combat_command(self, command: str) -> None:
        self.combat_revision += 1
        _atomic_json(COMBAT_CONTROL_FILE, {
            "schema_version": "1.0",
            "command": command,
            "revision": self.combat_revision,
        })

    def _prepare_and_launch_combat(self) -> None:
        try:
            receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
            parent_sha = str(receipt["authorization_sha256"])
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                    "--acknowledge-fixed-ui-session",
                    "--renewal-parent-sha256", parent_sha,
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            common = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR)]
            subprocess.run(
                common + [
                    "-Action", "RenewSessionIdentity", "-RepositoryRoot", str(ROOT),
                    "-AuthorizationFile", str(SESSION_AUTH), "-AcknowledgeSessionIdentity",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                common + [
                    "-Action", "ArmSession", "-RepositoryRoot", str(ROOT),
                    "-AuthorizationFile", str(SESSION_AUTH), "-AcknowledgeRuntimeArm",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "issue_continuous_motion_authorization.py"),
                    "--output", str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
                    "--acknowledge-continuous-motion",
                    "--evidence-ref", "control_center:f4a_ack",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                common + [
                    "-Action", "IssueMovementRealmRevalidation",
                    "-RepositoryRoot", str(ROOT),
                    "-AuthorizationFile", str(SESSION_AUTH),
                    "-MovementAuthorizationFile", str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
                    "-AcknowledgeContinuousMotion",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "issue_continuous_motion_runtime_arm.py"),
                    "--continuous-authorization-file", str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
                    "--session-authorization-file", str(SESSION_AUTH),
                    "--session-receipt", str(SESSION_RECEIPT),
                    "--realm-revalidation-file", str(CONTINUOUS_MOTION_REVALIDATION_FILE),
                    "--output", str(CONTINUOUS_MOTION_ARM_FILE),
                    "--acknowledge-continuous-motion",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [
                    "pwsh", "-NoProfile", "-NonInteractive", "-File", str(GODMODE),
                    "-State", "On", "-PlayerName", "Predator",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            COMBAT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.combat_log_stream = COMBAT_LOG_PATH.open("w", encoding="utf-8")
            self.combat_process = subprocess.Popen(
                [
                    sys.executable, str(COMBAT_RUNNER),
                    "--session-authorization-file", str(SESSION_AUTH),
                    "--session-receipt", str(SESSION_RECEIPT),
                    "--acknowledge-controlled-combat",
                    "--operator-control-file", str(COMBAT_CONTROL_FILE),
                ],
                cwd=ROOT,
                stdout=self.combat_log_stream,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=0x08000000,
            )
            self.root.after(0, self._set_combat_running)
        except Exception as error:
            self.root.after(0, lambda detail=str(error): self._set_combat_error(detail))

    def _combat_start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.combat_status_text.set("Oprește mersul singur înainte de luptă")
            return
        if self.combat_process is not None and self.combat_process.poll() is None:
            return
        self._write_combat_command("RUN")
        self.combat_state = "STARTING"
        self.combat_status_text.set("Pregătesc lupta de test…")
        self.combat_start_button.configure(state="disabled")
        Thread(target=self._prepare_and_launch_combat, daemon=True).start()

    def _set_combat_running(self) -> None:
        self.combat_state = "RUNNING"
        self.combat_status_text.set("Merge — caută un inamic și luptă")
        self.combat_start_button.configure(state="disabled")
        self.combat_pause_button.configure(state="normal", text="Ⅱ  PAUZĂ")
        self.combat_stop_button.configure(state="normal")

    def _set_combat_error(self, detail: str) -> None:
        self.combat_state = "STOPPED"
        self.combat_status_text.set(f"Lupta nu poate porni: {detail[:150]}")
        self.combat_start_button.configure(state="normal")
        self.combat_pause_button.configure(state="disabled", text="Ⅱ  PAUZĂ")
        self.combat_stop_button.configure(state="disabled")

    def _combat_pause_resume(self) -> None:
        if self.combat_state == "RUNNING":
            self._write_combat_command("PAUSE")
            self.combat_state = "PAUSED"
            self.combat_status_text.set("Lupta este în pauză")
            self.combat_pause_button.configure(text="▶  CONTINUĂ")
        elif self.combat_state == "PAUSED":
            self._write_combat_command("RUN")
            self._set_combat_running()

    def _combat_stop(self) -> None:
        self._write_combat_command("STOP")
        self.combat_state = "STOPPING"
        self.combat_status_text.set("Opresc lupta…")
        self.combat_pause_button.configure(state="disabled")
        self.combat_stop_button.configure(state="disabled")

    def _prepare_and_launch(self, destination_id: str, journey_mode: str,
        motion_allowed: bool,
        motion_stop_event: Event,
        sequence_destination_ids: tuple[str, ...] = (),
        sequence_loop_count: int = 1,
        sequence_close_loop: bool = False,
    ) -> None:
        try:
            # The preparation work runs outside Tk's event loop. A queued
            # second click, or a stop/start transition while preparation is
            # still renewing the LAB receipt, must not create two supervisors
            # that write to the same control file and send competing input.
            if (
                self.state != "STARTING"
                or motion_stop_event is not self.motion_arm_renew_stop
                or motion_stop_event.is_set()
            ):
                return
            if not motion_allowed:
                raise RuntimeError(
                    "bifează mai întâi «Îi dau voie să meargă singur»"
                )
            # Re-check the same immutable validation immediately before the
            # session and short-lived motion arms are issued. This closes the
            # gap between the checkbox event and the first possible input.
            self._set_semantic_live_authority(True)
            profile = self.active_world_map_profile
            if profile is None or profile.semantic_catalog is None:
                raise RuntimeError(
                    "profilul activ nu are catalog semantic pentru rutare autonomă"
                )
            leveling_plan = self._prepare_leveling_plan(profile)
            receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
            parent_sha = str(receipt["authorization_sha256"])
            self._run_hidden_checked([
                sys.executable,
                str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                "--acknowledge-fixed-ui-session",
                "--renewal-parent-sha256",
                parent_sha,
            ])
            common = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR)]
            self._run_hidden_checked(common + [
                "-Action", "RenewSessionIdentity", "-RepositoryRoot", str(ROOT),
                "-AuthorizationFile", str(SESSION_AUTH), "-AcknowledgeSessionIdentity",
            ])
            self._run_hidden_checked(common + [
                "-Action", "ArmSession", "-RepositoryRoot", str(ROOT),
                "-AuthorizationFile", str(SESSION_AUTH), "-AcknowledgeRuntimeArm",
            ])
            # Operator-requested LAB test setup. The script fails unless the
            # local world server confirms protection ON for Predator; do this
            # before arming or launching the movement child.
            self._run_hidden_checked([
                "pwsh", "-NoProfile", "-NonInteractive", "-File", str(GODMODE),
                "-State", "On", "-PlayerName", "Predator",
            ])
            if motion_stop_event.is_set():
                raise RuntimeError("mersul a fost oprit")
            self._renew_continuous_motion_arm_once(
                refresh_motion_authorization=True,
                refresh_session_identity=False,
            )
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.log_stream = LOG_PATH.open("w", encoding="utf-8")
            expected_zone_index = self._semantic_catalog_zone_index(
                profile.semantic_catalog,
                expected_map_name=profile.internal_name,
            )
            if leveling_plan is not None and leveling_plan.next_goal is not None:
                journey_arguments = [
                    "--goal-normalized-x", f"{leveling_plan.next_goal[0]:.8f}",
                    "--goal-normalized-y", f"{leveling_plan.next_goal[1]:.8f}",
                ]
            elif journey_mode == "operator_route":
                journey_arguments = ["--operator-path", str(OPERATOR_PATH_FILE)]
            elif len(sequence_destination_ids) >= 2:
                _atomic_json(
                    SEMANTIC_SEQUENCE_FILE,
                    {
                        "record_type": "semantic_destination_sequence",
                        "schema_version": "1.0",
                        "sequence_id": f"ui:{uuid4()}",
                        "destination_ids": list(sequence_destination_ids),
                        "loop_count": max(1, min(32, int(sequence_loop_count))),
                        "map_id": (
                            None
                            if self.active_world_map_profile is None
                            else self.active_world_map_profile.map_id
                        ),
                        "close_loop": bool(sequence_close_loop),
                        "execution_authority": False,
                    },
                )
                journey_arguments = [
                    "--destination-sequence-file", str(SEMANTIC_SEQUENCE_FILE),
                ]
            else:
                journey_arguments = ["--semantic-destination-id", destination_id]
            structure_access_arguments = (
                ["--structure-access-graph", str(profile.structure_access_graph),
                 "--structure-probe-worker", str(_structure_awareness_worker(profile))]
                if profile.structure_access_graph is not None
                else []
            )
            # Compatibility markers for the original Azeroth-only launch
            # contract; the actual values below come from the registry profile.
            # "--world-pack-profile", str(WORLD_PACK_PROFILE)
            # "--world-structure-index", str(WORLD_STRUCTURE_INDEX)
            # ["--structure-access-graph", str(STRUCTURE_ACCESS_GRAPH)]
            self.process = subprocess.Popen(
                [
                    # Legacy default spellings retained for source-level
                    # diagnostics; runtime values are registry-selected.
                    # "--world-pack-profile", str(WORLD_PACK_PROFILE)
                    # "--world-structure-index", str(WORLD_STRUCTURE_INDEX)
                    sys.executable, str(JOURNEY_COMBAT_SUPERVISOR),
                    "--session-authorization-file", str(SESSION_AUTH),
                    "--session-receipt", str(SESSION_RECEIPT),
                    "--continuous-motion-authorization-file",
                    str(CONTINUOUS_MOTION_AUTHORIZATION_FILE),
                    "--continuous-motion-arm-file", str(CONTINUOUS_MOTION_ARM_FILE),
                    "--continuous-motion-revalidation-file",
                    str(CONTINUOUS_MOTION_REVALIDATION_FILE),
                    "--worker", str(_navigation_worker()),
                    "--map-id", str(profile.map_id),
                    "--world-pack-profile", str(profile.runtime_profile),
                    "--world-pack-store", str(WORLD_PACK_STORE),
                    "--world-structure-index", str(profile.structure_index),
                    *structure_access_arguments,
                    "--semantic-catalog", str(profile.semantic_catalog),
                    "--expected-zone-index", str(expected_zone_index),
                    "--zone-transform-catalog", str(WORLD_MAP_ZONE_TRANSFORM_CATALOG),
                    "--start-world-z-hint", "100",
                    "--operator-control-file", str(CONTROL_FILE),
                    *(
                        ["--leveling-plan-file", str(LEVELING_PLAN_FILE)]
                        if leveling_plan is not None
                        else []
                    ),
                    "--max-control-frames", "12000",
                    # Use the same adaptive controller as the validated LAB
                    # holdout.  Ordinary terrain remains deterministic; only
                    # narrow/risk topology is handed to bounded MPPI.  This
                    # keeps the UI launch path aligned with the controller
                    # that proved the crypt egress, instead of silently
                    # falling back to the older continuous-only profile.
                    "--steering-controller", "adaptive_trajectory_v1",
                    "--mppi-batch-size", "256",
                    "--mppi-time-steps", "56",
                    # Movement tab never delegates to a combat child. Ordinary
                    # aggro is allowed below, but cannot enable automatic attacks.
                    "--maximum-combat-handoffs", "0",
                    # Each F4a arm is intentionally short-lived.  After a
                    # fail-closed expiry the supervisor may start one more
                    # bounded slice from the child checkpoint, but only while
                    # the operator replaces the arm during this finite wait.
                    # It never issues or extends authority itself.
                    "--runtime-arm-wait-seconds", "120",
                    "--resume-on-runtime-arm-expiry",
                    # Aggro is expected in the operator's godmode LAB tests.
                    # Keep the existing health/observation safety checks intact.
                    "--continue-through-routine-aggro",
                    # The legacy acknowledgement names the supervisor, not a
                    # combat permission; the explicit zero budget above rules.
                    "--acknowledge-autonomous-journey-combat",
                    *journey_arguments,
                ],
                cwd=ROOT,
                stdout=self.log_stream,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=0x08000000,
            )
            Thread(
                target=self._maintain_continuous_motion_arm,
                args=(self.process, motion_stop_event),
                daemon=True,
            ).start()
            self.root.after(0, self._set_running)
        except Exception as error:
            self.root.after(0, lambda detail=str(error): self._set_error(detail))

    def start(self) -> None:
        # ``self.process`` is assigned only after the background preparation
        # finishes. Guard the synchronous STARTING interval as well, otherwise
        # two queued UI activations can launch concurrent movement supervisors.
        if self.state != "STOPPED":
            return
        ready, explanation = self._apply_autonomous_start_readiness()
        if not ready:
            self.state_text.set(explanation)
            return
        if self.process is not None and self.process.poll() is None:
            return
        journey_mode = self.journey_mode.get()
        if self.leveling_enabled.get() and journey_mode != "autonomous_destination":
            self.state_text.set(
                "Ghidul merge numai cu «Alege singur drumul»"
            )
            return
        if self.leveling_enabled.get() and self.sequence_enabled.get():
            self.state_text.set(
                "Ghidul folosește câte un pas; oprește lista de destinații"
            )
            return
        if journey_mode == "operator_route":
            name = self.path_name.get().strip()
            if not name or not self.operator_path.waypoints:
                self.state_text.set(
                    "Nu pot porni: desenul trebuie să aibă nume și puncte"
                )
                return
            self.operator_path = self.operator_path.rename(name)
            _atomic_json(OPERATOR_PATH_FILE, self.operator_path.to_record())
            _atomic_json(OPERATOR_MAP_KNOWLEDGE_FILE, self.map_knowledge.to_record())
        sequence_destination_ids = (
            tuple(self.sequence_destination_ids)
            if journey_mode == "autonomous_destination" and self.sequence_enabled.get()
            else ()
        )
        if sequence_destination_ids and len(sequence_destination_ids) < 2:
            self.state_text.set("Adaugă cel puțin două locuri")
            return
        self._write_command("RUN")
        # UI-only generation boundary; this grants no execution authority.
        self.movement_view_started_s = time.monotonic()
        self.raw_movement_snapshot = None
        self.state = "STARTING"
        self.state_text.set("Pregătesc drumul…")
        self.start_button.configure(state="disabled")
        self.destination_picker.configure(state="disabled")
        self.motion_arm_renew_stop.set()
        motion_stop_event = Event()
        self.motion_arm_renew_stop = motion_stop_event
        Thread(
            target=self._prepare_and_launch,
            args=(
                self.semantic_destination_id,
                journey_mode,
                bool(self.continuous_motion_ack.get()),
                motion_stop_event,
                sequence_destination_ids,
                int(self.sequence_loop_count.get()),
                bool(self.sequence_close_loop.get()),
            ),
            daemon=True,
        ).start()

    def _set_running(self) -> None:
        self.state = "RUNNING"
        self.state_text.set("Merge singur")
        self.start_button.configure(state="disabled")
        self.pause_button.configure(state="normal", text="Ⅱ  PAUZĂ")
        self.stop_button.configure(state="normal")

    def _set_error(self, detail: str) -> None:
        self.motion_arm_renew_stop.set()
        self.state = "STOPPED"
        self.state_text.set("Nu pot porni. Vezi jurnalul.")
        self._apply_autonomous_start_readiness()
        self._journey_mode_changed()
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")

    def pause_resume(self) -> None:
        if self.state == "RUNNING":
            self._write_command("PAUSE")
            self.state = "PAUSED"
            self.state_text.set("Pauză")
            self.pause_button.configure(text="▶  CONTINUĂ")
        elif self.state == "PAUSED":
            self._write_command("RUN")
            self._set_running()

    def stop(self) -> None:
        self.motion_arm_renew_stop.set()
        self._write_command("STOP")
        self.state = "STOPPING"
        self.state_text.set("Opresc…")
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")

    def _overlay_should_run(self) -> bool:
        policy = OVERLAY_POLICY_VALUES.get(self.overlay_policy.get(), "Never")
        return policy == "Always" or (
            policy == "Only while testing" and self.state in {"STARTING", "RUNNING", "PAUSED"}
        )

    def _codex_driver_changed(self) -> None:
        enabled = self.codex_driver_enabled.get()
        record: dict[str, object] = {
            "record_type": "predator_codex_driver_arm",
            "schema_version": "1.0",
            "enabled": False,
            "control_center_pid": os.getpid(),
            "allowed_controls": list(CODEX_DRIVER_ALLOWED_CONTROLS),
        }
        if enabled:
            try:
                receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
                target_pid = int(receipt["pid"])
                target_hwnd = int(str(receipt["hwnd"]), 0)
                if (
                    not ctypes.windll.user32.IsWindow(target_hwnd)
                    or not target_pid > 0
                ):
                    raise RuntimeError("fereastra WoW din sesiunea LAB nu este deschisă")
                record.update({
                    "enabled": True,
                    "target_pid": target_pid,
                    "target_hwnd": f"0x{target_hwnd:X}",
                })
                _atomic_json(CODEX_DRIVER_ARM_FILE, record)
            except (
                FileNotFoundError, OSError, KeyError, TypeError, ValueError,
                json.JSONDecodeError, RuntimeError,
            ) as error:
                self.codex_driver_enabled.set(False)
                self.codex_driver_text.set("Nu a pornit. Verifică dacă WoW este deschis.")
                return
            self.codex_driver_text.set(
                "Pornit: Codex AI poate controla Predatorul. Funcționează doar în WoW."
            )
            return
        _atomic_json(CODEX_DRIVER_ARM_FILE, record)
        self.codex_driver_text.set(
            "Oprit: Codex AI nu trimite comenzi. Funcționează doar în WoW."
        )

    def _stop_overlay(self) -> None:
        if self.overlay_process is not None and self.overlay_process.poll() is None:
            self._write_overlay_command("STOP")
            try:
                self.overlay_process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.overlay_process.terminate()
                try:
                    self.overlay_process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    self.overlay_process.kill()
        self.overlay_process = None
        self.overlay_restart_not_before_s = 0.0

    @staticmethod
    def _write_overlay_command(command: str) -> None:
        if command not in {"START", "STOP"}:
            raise ValueError("invalid overlay command")
        try:
            current = json.loads(OVERLAY_CONTROL.read_text(encoding="utf-8"))
            revision = int(current.get("revision", 0)) if isinstance(current, dict) else 0
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            revision = 0
        _atomic_json(OVERLAY_CONTROL, {
            "record_type": "movement_lab_overlay_control",
            "schema_version": "1.0",
            "revision": revision + 1,
            "command": command,
            "execution_authority": False,
        })

    def _sync_overlay(self, *, restart: bool = False) -> None:
        if restart:
            self._stop_overlay()
        if not self._overlay_should_run():
            self._stop_overlay()
            return
        if self.overlay_process is not None and self.overlay_process.poll() is None:
            return
        if time.monotonic() < self.overlay_restart_not_before_s:
            return
        arguments = [
            sys.executable, str(OVERLAY_RUNNER),
            "--opacity", f"{self.overlay_opacity.get():.2f}",
            "--control-file", str(OVERLAY_CONTROL),
        ]
        if not self.overlay_mesh.get():
            arguments.append("--hide-mesh")
        if not self.overlay_facing.get():
            arguments.append("--hide-facing")
        self._write_overlay_command("START")
        self.overlay_process = subprocess.Popen(
            arguments, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        # A broken overlay must never create a focus-stealing restart storm.
        # One bounded retry window is enough for transient startup races.
        self.overlay_restart_not_before_s = time.monotonic() + 5.0

    def _apply_overlay_settings(self) -> None:
        self._save_ui_settings()
        self._sync_overlay(restart=True)

    def _prepare_3d_navmesh_viewer(self, snapshot: MovementLabSnapshot) -> None:
        try:
            _atomic_json(NAV_VIEWER_DIAGNOSTIC, {"status": "PREPARING"})
            if self.nav_viewer_process is not None and self.nav_viewer_process.poll() is None:
                self.nav_viewer_process.terminate()
                self.nav_viewer_process.wait(timeout=2.0)
            live_session_ready = True
            live_session_detail: str | None = None
            try:
                receipt = json.loads(SESSION_RECEIPT.read_text(encoding="utf-8"))
                parent_sha = str(receipt["authorization_sha256"])
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                        "--acknowledge-fixed-ui-session",
                        "--renewal-parent-sha256", parent_sha,
                    ],
                    cwd=ROOT, check=True, capture_output=True, text=True,
                )
                subprocess.run(
                    [
                        "pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR),
                        "-Action", "RenewSessionIdentity", "-RepositoryRoot", str(ROOT),
                        "-AuthorizationFile", str(SESSION_AUTH),
                        "-AcknowledgeSessionIdentity", "-AcknowledgeWindowRebind",
                    ],
                    cwd=ROOT, check=True, capture_output=True, text=True,
                )
            except subprocess.CalledProcessError as error:
                output = "\n".join(
                    part for part in (error.stderr, error.stdout)
                    if isinstance(part, str)
                )
                semantic_rebind_needed = (
                    "exact fixed-UI semantic profile" in output
                    or "config hash does not match authorization" in output
                )
                if semantic_rebind_needed:
                    try:
                        # A deliberate local LAB configuration update needs a
                        # fresh zero-input identity binding, not a falsely
                        # labelled temporal-only renewal of the old profile.
                        subprocess.run(
                            [
                                sys.executable,
                                str(ROOT / "scripts" / "issue_lab_session_authorization.py"),
                                "--acknowledge-fixed-ui-session",
                            ],
                            cwd=ROOT, check=True, capture_output=True, text=True,
                        )
                        subprocess.run(
                            [
                                "pwsh", "-NoProfile", "-NonInteractive", "-File",
                                str(OPERATOR), "-Action", "RenewSessionIdentity",
                                "-RepositoryRoot", str(ROOT), "-AuthorizationFile",
                                str(SESSION_AUTH), "-AcknowledgeSessionIdentity",
                                "-AcknowledgeWindowRebind",
                                "-AcknowledgeAuthorizationRebind",
                            ],
                            cwd=ROOT, check=True, capture_output=True, text=True,
                        )
                    except subprocess.CalledProcessError as rebind_error:
                        live_session_ready = False
                        live_session_detail = _friendly_3d_mesh_map_error(rebind_error)
                else:
                    # The mesh map is read-only. A stale session identity must
                    # stop fresh HUD capture, but not hide the last verified pose.
                    live_session_ready = False
                    live_session_detail = _friendly_3d_mesh_map_error(error)
            # The Tk event that opened the viewer can regain foreground after
            # the initial focus request. Reassert the exact WoW HWND directly
            # before the read-only HUD probe.
            _focus_exact_wow_window()
            live_pose_ready = live_session_ready
            active_profile = self.active_world_map_profile
            profile_map_id = int(
                getattr(active_profile, "map_id", 0)
            )
            expected_zone_index = 25
            semantic_catalog = getattr(active_profile, "semantic_catalog", None)
            if isinstance(semantic_catalog, Path) and semantic_catalog.is_file():
                expected_zone_index = self._semantic_catalog_zone_index(
                    semantic_catalog,
                    expected_map_name=str(
                        getattr(active_profile, "internal_name", "Azeroth")
                    ),
                )
            profile_map_name = str(
                getattr(active_profile, "internal_name", "Azeroth")
            )
            if live_session_ready:
                try:
                    pose = capture_nav_viewer_pose(
                        authorization_file=SESSION_AUTH,
                        receipt_file=SESSION_RECEIPT,
                        expected_zone_index=expected_zone_index,
                        map_id=profile_map_id,
                        map_name=profile_map_name,
                        transform_catalog=WORLD_MAP_ZONE_TRANSFORM_CATALOG,
                    )
                except ClientVisibleStateError:
                    if (
                        snapshot.player_world_x is None
                        or snapshot.player_world_y is None
                    ):
                        raise
                    live_pose_ready = False
                    pose = {
                        "record_type": "nav_viewer_pose",
                        "execution_authority": False,
                        "world_position": [
                            snapshot.player_world_x,
                            snapshot.player_world_y,
                        ],
                    }
            else:
                if (
                    snapshot.player_world_x is None
                    or snapshot.player_world_y is None
                ):
                    raise RuntimeError(live_session_detail or "poziția Predatorului lipsește")
                pose = {
                    "record_type": "nav_viewer_pose",
                    "execution_authority": False,
                    "world_position": [
                        snapshot.player_world_x,
                        snapshot.player_world_y,
                    ],
                }
            if (
                not isinstance(pose, dict)
                or pose.get("record_type") != "nav_viewer_pose"
                or pose.get("execution_authority") is not False
                or not isinstance(pose.get("world_position"), list)
                or len(pose["world_position"]) != 2
            ):
                raise RuntimeError("poziția fresh pentru viewer este invalidă")
            fresh_world = (
                float(pose["world_position"][0]),
                float(pose["world_position"][1]),
            )
            NAV_VIEWER_STATE.unlink(missing_ok=True)
            launch = _world_pack_viewer_launch(
                snapshot, fresh_world_position=fresh_world,
                live_state_path=NAV_VIEWER_STATE,
                profile=self.active_world_map_profile,
            )
            self.nav_viewer_process = subprocess.Popen(
                launch.arguments,
                cwd=launch.working_directory,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.2)
            if self.nav_viewer_process.poll() is not None:
                raise RuntimeError("viewerul 3D s-a închis în timpul pornirii")
            if live_session_ready:
                _focus_exact_wow_window()
                if (
                    self.nav_viewer_bridge_process is not None
                    and self.nav_viewer_bridge_process.poll() is None
                ):
                    self.nav_viewer_bridge_process.terminate()
                    self.nav_viewer_bridge_process.wait(timeout=2.0)
                self.nav_viewer_bridge_process = subprocess.Popen(
                    _nav_viewer_bridge_arguments(
                        # One shared stream follows Control Center's lifetime;
                        # closing/reopening the 3D view does not stop the 2D map.
                        viewer_pid=os.getpid(),
                        snapshot=snapshot,
                        launch=launch,
                        expected_zone_index=expected_zone_index,
                        zone_transform_catalog=WORLD_MAP_ZONE_TRANSFORM_CATALOG,
                    ),
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,
                )
                time.sleep(0.2)
                if self.nav_viewer_bridge_process.poll() is not None:
                    self.nav_viewer_process.terminate()
                    raise RuntimeError("urmărirea HUD live nu a putut porni")
                # The read-only bridge now captures the exact WoW HWND even
                # while the Center or 3D viewer is in front. Do not steal the
                # operator's focus after opening the map.
            _atomic_json(NAV_VIEWER_DIAGNOSTIC, {
                "status": "LIVE" if live_pose_ready else "WAITING_FOR_IN_WORLD_HUD",
                "viewer_pid": self.nav_viewer_process.pid,
                "bridge_pid": (
                    None if self.nav_viewer_bridge_process is None
                    else self.nav_viewer_bridge_process.pid
                ),
                "fresh_world_position": list(fresh_world),
                "world_pack_profile_id": launch.profile_id,
                "world_pack_id": launch.pack_id,
                "world_pack_content_sha256": launch.content_sha256,
                "client_installation_required": False,
                "execution_authority": False,
                "live_session_detail": live_session_detail,
            })
            if live_pose_ready:
                viewer_status = (
                    f"Harta 3D îl urmărește: {fresh_world[0]:.2f}, {fresh_world[1]:.2f}"
                )
            elif live_session_detail:
                viewer_status = (
                    f"Harta 3D arată locul: {fresh_world[0]:.2f}, {fresh_world[1]:.2f}"
                )
            else:
                viewer_status = (
                    f"Harta 3D: ultimul loc {fresh_world[0]:.2f}, "
                    f"{fresh_world[1]:.2f}; intră cu Predatorul în joc"
                )
            self.root.after(
                0,
                lambda message=viewer_status: (
                    self.cursor_text.set(message),
                    self.nav_viewer_button.configure(
                        state="normal", text="Hartă 3D",
                    ),
                ),
            )
        except Exception as exc:
            _atomic_json(NAV_VIEWER_DIAGNOSTIC, {
                "status": "ERROR",
                "error_type": type(exc).__name__,
                "detail": str(exc),
                "traceback": traceback.format_exc(),
            })
            detail = _friendly_3d_mesh_map_error(exc)
            self.root.after(
                0,
                lambda detail=detail: (
                    self.nav_viewer_button.configure(
                        state="normal", text="Hartă 3D",
                    ),
                    messagebox.showerror("Harta 3D", detail),
                ),
            )

    def _open_3d_navmesh_viewer(self) -> None:
        snapshot = self.last_snapshot or _read_snapshot()
        if snapshot is None:
            messagebox.showerror(
                "Harta 3D", "Nu văd încă poziția Predatorului."
            )
            return
        if not NAV_VIEWER.is_file():
            messagebox.showerror("Harta 3D", "Harta 3D nu este gata.")
            return
        profile = self.active_world_map_profile
        if (
            profile is None
            or profile.runtime_profile is None
            or not profile.runtime_profile.is_file()
            or not WORLD_PACK_STORE.is_dir()
        ):
            messagebox.showerror("Harta 3D", "Lipsesc datele hărții 3D.")
            return
        try:
            _focus_exact_wow_window()
        except RuntimeError as exc:
            messagebox.showerror("Harta 3D", str(exc))
            return
        self.nav_viewer_button.configure(state="disabled", text="Citesc poziția…")
        self.cursor_text.set("Harta 3D: citesc poziția din joc…")
        Thread(
            target=self._prepare_3d_navmesh_viewer,
            args=(snapshot,), daemon=True,
        ).start()

    def _draw_snapshot(self, snapshot: MovementLabSnapshot | None) -> None:
        if snapshot is not None and self.follow_predator.get():
            self._center_atlas_on_predator(snapshot)
        self.canvas.delete("all")
        self.canvas_to_world = None
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        if self.world_map_photo is not None:
            world_map_photo = self._atlas_photo(
                self.world_map_photo, self.world_map_zoom_cache, width, height
            )
            self.canvas.create_image(
                0, 0, image=world_map_photo, anchor="nw",
                tags=("client-world-map",),
            )
            if self.road_semantic_photo is not None and self.overlay_roads.get():
                road_semantic_photo = self._atlas_photo(
                    self.road_semantic_photo, self.road_semantic_zoom_cache, width, height
                )
                self.canvas.create_image(
                    0, 0, image=road_semantic_photo,
                    anchor="nw", tags=("adt-road-semantics",),
                )

            def screen(point: tuple[float, float]) -> tuple[float, float]:
                pixel_x, pixel_y = self.atlas_geometry.pixel_from_world(*point)
                return self.atlas_viewport.screen_from_pixel(
                    pixel_x, pixel_y,
                    canvas_width=float(width), canvas_height=float(height),
                )

            def canvas_world(screen_x: float, screen_y: float) -> tuple[float, float]:
                pixel_x, pixel_y = self.atlas_viewport.pixel_from_screen(
                    screen_x, screen_y,
                    canvas_width=float(width), canvas_height=float(height),
                )
                return self.atlas_geometry.world_from_pixel(pixel_x, pixel_y)

            self.canvas_to_world = canvas_world
            if (
                snapshot is not None
                and self.journey_mode.get() == "autonomous_destination"
                and len(self.semantic_journey) >= 2
            ):
                semantic_visible = []
                for point in self.semantic_journey:
                    try:
                        semantic_visible.append(screen(point))
                    except ValueError:
                        continue
                if len(semantic_visible) >= 2:
                    line = [value for point in semantic_visible for value in point]
                    self.canvas.create_line(
                        *line, fill="#34d9ff", width=3, dash=(9, 4),
                        tags=("semantic-road-corridor",),
                    )
                    px, py = semantic_visible[0]
                    self.canvas.create_text(
                        px + 10, py - 10,
                        text="ALES ACUM",
                        anchor="sw", fill="#34d9ff",
                        font=("Segoe UI", 9, "bold"),
                    )
            for polygon in (() if snapshot is None else snapshot.navmesh_polygons_world):
                try:
                    flat = [value for point in polygon for value in screen(point)]
                except ValueError:
                    continue
                self.canvas.create_polygon(
                    *flat, fill="#143d25", stipple="gray50",
                    outline="#55d979", width=1,
                )
            if snapshot is not None and len(snapshot.corridor_centerline_world) >= 2:
                visible = []
                for point in snapshot.corridor_centerline_world:
                    try:
                        visible.append(screen(point))
                    except ValueError:
                        continue
                if len(visible) >= 2:
                    line = [value for point in visible for value in point]
                    self.canvas.create_line(*line, fill="#ffe369", width=4)
            if snapshot is not None and len(snapshot.traversed_path_world) >= 2:
                visible_trace = []
                for point in snapshot.traversed_path_world:
                    try:
                        visible_trace.append(screen(point))
                    except ValueError:
                        continue
                if len(visible_trace) >= 2:
                    self.canvas.create_line(
                        *[value for point in visible_trace for value in point],
                        fill="#ff35d3", width=4,
                    )
            if snapshot is not None and len(snapshot.tether_centerline_world) >= 2:
                visible_tether = []
                for point in snapshot.tether_centerline_world:
                    try:
                        visible_tether.append(screen(point))
                    except ValueError:
                        continue
                if len(visible_tether) >= 2:
                    tether_color = (
                        "#ffc857"
                        if snapshot.tether_state.startswith("DETOUR")
                        else "#72ff59"
                        if snapshot.tether_state.startswith("PARTIAL_ADVANCE")
                        else "#ff5757"
                        if snapshot.tether_state == "PARTIAL_BLOCKED"
                        else "#ff35d3"
                    )
                    self.canvas.create_line(
                        *[value for point in visible_tether for value in point],
                        fill=tether_color, width=5, arrow=tk.LAST,
                    )
            if snapshot is not None and snapshot.player_world_x is not None:
                try:
                    px, py = screen((snapshot.player_world_x, snapshot.player_world_y))
                except ValueError:
                    pass
                else:
                    self.canvas.create_oval(
                        px - 7, py - 7, px + 7, py + 7,
                        fill="#39e6ff", outline="white", width=2,
                    )
                    def draw_orientation_arrow(
                        angle_rad: float | None,
                        *,
                        color: str,
                        width_px: int,
                        length_px: float,
                        dash: tuple[int, int] | None = None,
                    ) -> None:
                        if angle_rad is None:
                            return
                        try:
                            facing_x, facing_y = screen((
                                snapshot.player_world_x
                                + cos(angle_rad) * 20.0,
                                snapshot.player_world_y
                                + sin(angle_rad) * 20.0,
                            ))
                        except ValueError:
                            return
                        else:
                            length = hypot(facing_x - px, facing_y - py)
                            if length >= 0.1:
                                end_x = px + (facing_x - px) / length * length_px
                                end_y = py + (facing_y - py) / length * length_px
                                self.canvas.create_line(
                                    px, py, end_x, end_y,
                                    fill=color, width=width_px, dash=dash,
                                    arrow=tk.LAST, arrowshape=(10, 12, 5),
                                )
                    draw_orientation_arrow(
                        snapshot.body_facing_rad,
                        color="#1677ff",
                        width_px=4,
                        length_px=28.0,
                    )
                    draw_orientation_arrow(
                        snapshot.camera_yaw_estimate_rad,
                        color="#ff9f43",
                        width_px=3,
                        length_px=21.0,
                        dash=(5, 3),
                    )
            show_operator_layers = self._show_operator_editor_layers()
            feature_colors = {
                "roaming_zone": "#62e36f",
                "obstacle": "#ff5252",
                "interior_route": "#d66bff",
                "recovery_anchor": "#4da3ff",
                "manual_demonstration": "#ffffff",
            }
            for feature in (() if not show_operator_layers else self.map_knowledge.features):
                try:
                    visible_feature = [
                        screen((vertex.x, vertex.y)) for vertex in feature.vertices
                    ]
                except ValueError:
                    continue
                color = feature_colors[feature.kind]
                flat = [value for point in visible_feature for value in point]
                if feature.kind in {"roaming_zone", "obstacle"}:
                    self.canvas.create_polygon(
                        *flat, fill=color, stipple="gray50",
                        outline=color, width=3,
                    )
                elif feature.kind == "recovery_anchor":
                    px, py = visible_feature[0]
                    self.canvas.create_rectangle(
                        px - 8, py - 8, px + 8, py + 8,
                        fill=color, outline="white", width=2,
                    )
                else:
                    self.canvas.create_line(*flat, fill=color, width=4, dash=(5, 3))
                    if feature.kind == "manual_demonstration":
                        self._draw_recorded_facing_arrows(
                            feature.vertices, screen, color=color,
                        )
            if show_operator_layers and self.manual_recording_draft:
                try:
                    visible_recording = [
                        screen((vertex.x, vertex.y))
                        for vertex in self.manual_recording_draft
                    ]
                except ValueError:
                    visible_recording = []
                if len(visible_recording) >= 2:
                    self.canvas.create_line(
                        *[value for point in visible_recording for value in point],
                        fill="#ffffff", width=5,
                    )
                    self._draw_recorded_facing_arrows(
                        self.manual_recording_draft, screen, color="#00ffcc",
                    )
            if show_operator_layers and self.feature_draft:
                try:
                    visible_draft = [
                        screen((vertex.x, vertex.y)) for vertex in self.feature_draft
                    ]
                except ValueError:
                    visible_draft = []
                if len(visible_draft) >= 2:
                    self.canvas.create_line(
                        *[value for point in visible_draft for value in point],
                        fill="#ffffff", width=2, dash=(3, 3),
                    )
                for px, py in visible_draft:
                    self.canvas.create_oval(
                        px - 5, py - 5, px + 5, py + 5,
                        fill="#ffffff", outline="#111111",
                    )
            show_operator_path = show_operator_layers
            authored_points = (
                [(point.x, point.y) for point in self.operator_path.waypoints]
                if show_operator_path else []
            )
            visible_authored = []
            for point in authored_points:
                try:
                    visible_authored.append(screen(point))
                except ValueError:
                    continue
            if len(visible_authored) >= 2:
                line = [value for point in visible_authored for value in point]
                self.canvas.create_line(*line, fill="#ff9f43", width=3, dash=(7, 4))
            for point in (() if not show_operator_path else self.operator_path.waypoints):
                try:
                    px, py = screen((point.x, point.y))
                except ValueError:
                    continue
                self.canvas.create_oval(
                    px - 9, py - 9, px + 9, py + 9,
                    fill="#ff9f43", outline="white",
                )
                self.canvas.create_text(
                    px, py, text=str(point.order), fill="#111111",
                    font=("Segoe UI", 8, "bold"),
                )
            return
        mesh_points = [] if snapshot is None else [
            point for polygon in snapshot.navmesh_polygons_world for point in polygon
        ]
        show_operator_path = self._show_operator_editor_layers()
        authored_points = (
            [(point.x, point.y) for point in self.operator_path.waypoints]
            if show_operator_path else []
        )
        diagnostic_points = [] if snapshot is None else [
            *snapshot.corridor_centerline_world,
            *snapshot.traversed_path_world,
            *(
                ()
                if snapshot.player_world_x is None
                else ((snapshot.player_world_x, snapshot.player_world_y),)
            ),
        ]
        points = [*mesh_points, *diagnostic_points, *authored_points]
        if not points:
            self.canvas.create_text(
                width / 2, height / 2,
                text="Drumul va apărea după prima alegere\n"
                     "sau după ce adaugi un punct",
                fill="#8ca998", font=("Segoe UI", 12),
            )
            return
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        margin = 28.0
        scale = min(
            (width - margin * 2) / max(1.0, max(xs) - min(xs)),
            (height - margin * 2) / max(1.0, max(ys) - min(ys)),
        )

        def screen(point: tuple[float, float]) -> tuple[float, float]:
            return (
                margin + (point[0] - min(xs)) * scale,
                height - margin - (point[1] - min(ys)) * scale,
            )

        self.canvas_to_world = lambda sx, sy: (
            min(xs) + (sx - margin) / scale,
            min(ys) + (height - margin - sy) / scale,
        )

        for polygon in (() if snapshot is None else snapshot.navmesh_polygons_world):
            flat = [value for point in polygon for value in screen(point)]
            self.canvas.create_polygon(*flat, fill="#102a1a", outline="#39784d", width=1)
        if snapshot is not None and len(snapshot.corridor_centerline_world) >= 2:
            line = [value for point in snapshot.corridor_centerline_world for value in screen(point)]
            self.canvas.create_line(*line, fill="#ffe369", width=3)
        if snapshot is not None and len(snapshot.traversed_path_world) >= 2:
            line = [value for point in snapshot.traversed_path_world for value in screen(point)]
            self.canvas.create_line(*line, fill="#ff35d3", width=4)
        if snapshot is not None and snapshot.player_world_x is not None:
            px, py = screen((snapshot.player_world_x, snapshot.player_world_y))
            self.canvas.create_oval(px - 6, py - 6, px + 6, py + 6, fill="#39e6ff", outline="white")
        if len(authored_points) >= 2:
            line = [value for point in authored_points for value in screen(point)]
            self.canvas.create_line(*line, fill="#ff9f43", width=3, dash=(7, 4))
        for point in (() if not show_operator_path else self.operator_path.waypoints):
            px, py = screen((point.x, point.y))
            self.canvas.create_oval(px - 9, py - 9, px + 9, py + 9, fill="#ff9f43", outline="white")
            self.canvas.create_text(px, py, text=str(point.order), fill="#111111", font=("Segoe UI", 8, "bold"))

    def _refresh(self) -> None:
        self.stay_online_panel.refresh()
        now_s = time.monotonic()
        self.location_label_text.set(self.location_label_reader.poll_text(now_s))
        self.sonar_panel.update_details(self.location_label_reader.details(now_s))
        self._consume_live_map_session_renewal()
        self._schedule_live_map_session_renewal()
        self._ensure_live_pose_bridge()
        while True:
            try:
                hotkey_command = self.recording_hotkey_events.get_nowait()
            except Empty:
                break
            if hotkey_command == "START":
                self._start_manual_recording()
            elif hotkey_command == "STOP":
                self._stop_manual_recording()
        self._consume_structure_awareness_result()
        self._consume_structure_query_result()
        self._consume_stationary_validation_result()
        self._consume_motion_arm_renew_result()
        self._refresh_manual_recording_result()
        (
            snapshot,
            local_environment,
            environment_applicability,
            structure_access,
        ) = self._refresh_runtime_view()
        self._schedule_structure_awareness_query(snapshot)
        if snapshot is not None:
            if snapshot.player_world_x is None:
                self.position_text.set("Loc: nu se vede")
            else:
                self.position_text.set(
                    f"Loc: {snapshot.player_world_x:.2f}, {snapshot.player_world_y:.2f}"
                )
            if self.last_live_pose is not None:
                age_ms = max(
                    0,
                    round(
                        (time.monotonic() - self.last_live_pose.observed_monotonic_s)
                        * 1000
                    ),
                )
                facing_label = {
                    "COORDINATE_HUD_EXACT": "privire exactă",
                    "MINIMAP_VISION_FALLBACK": "privire de pe harta mică",
                    "VISIBLE_CLIENT_HEADING_FUSED": "privire verificată",
                    "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED": "privire verificată",
                }.get(
                    self.last_live_pose.facing_source or "",
                    "privire necunoscută",
                )
                self.live_map_text.set(
                    f"Acum • {age_ms} ms în urmă • {facing_label}"
                )
                self.observation_source_text.set(
                    _live_observation_source_text(
                        self.last_live_pose,
                        now_monotonic_s=time.monotonic(),
                    )
                )
            else:
                self.live_map_text.set("Aștept jocul")
                self.observation_source_text.set(
                    _live_observation_source_text(None, now_monotonic_s=0.0)
                )
            self.orientation_value_text.set(
                _body_camera_orientation_text(snapshot)
            )
            self.mesh_text.set(
                f"Harta drumului: {len(snapshot.navmesh_polygons_world)} bucăți • "
                f"{len(snapshot.corridor_centerline_world)} pași"
            )
        elif self.manual_recording_draft:
            current = self.manual_recording_draft[-1]
            self.position_text.set(f"Loc: {current.x:.2f}, {current.y:.2f}")
            self.observation_source_text.set(
                "Locul: copiez drumul tău"
            )
            self.orientation_value_text.set(_body_camera_orientation_text(None))
            self.controller_text.set("Acum: mergi tu")
            self.mesh_text.set("Harta drumului: o copiez")
        else:
            self.position_text.set("Loc: aștept jocul")
            self.observation_source_text.set(
                _live_observation_source_text(None, now_monotonic_s=0.0)
            )
            self.orientation_value_text.set(_body_camera_orientation_text(None))
            self.mesh_text.set("Harta drumului: nu există")
            self.live_map_text.set(
                "Intră cu personajul în joc; harta îl va găsi"
            )
        self.awareness_text.set(self._structure_awareness_text(
            snapshot,
            local_environment=local_environment,
            applicability=environment_applicability,
            structure_access=structure_access,
        ))
        self._refresh_live_semantic_journey(snapshot)
        if (
            snapshot is not None
            and self.follow_predator.get()
        ):
            self._center_atlas_on_predator(snapshot)
        canvas_signature = (
            self.canvas.winfo_width(),
            self.canvas.winfo_height(),
            self.atlas_viewport,
            self.follow_predator.get(),
            self.overlay_roads.get(),
            None if snapshot is None else (
                None if snapshot.player_world_x is None
                else round(snapshot.player_world_x, 2),
                None if snapshot.player_world_y is None
                else round(snapshot.player_world_y, 2),
                None if snapshot.player_facing_rad is None
                else round(snapshot.player_facing_rad, 3),
                snapshot.navmesh_polygons_world,
                snapshot.corridor_centerline_world,
                snapshot.traversed_path_world,
                snapshot.tether_centerline_world,
                snapshot.tether_state,
            ),
            self.manual_recording_draft,
            tuple((point.order, point.x, point.y) for point in self.operator_path.waypoints),
        )
        if canvas_signature != self.last_canvas_refresh_signature:
            self._draw_snapshot(snapshot)
            self.last_canvas_refresh_signature = canvas_signature

        # The preparation thread normally schedules ``_set_running`` through
        # Tk. A busy live-map redraw can delay or lose that one callback even
        # though the exact child process is already running. Reconcile from
        # the authoritative process handle on every UI refresh so the screen
        # cannot remain stuck at "Pregătesc drumul…" while Predator moves.
        if (
            self.state == "STARTING"
            and self.process is not None
            and self.process.poll() is None
        ):
            self._set_running()
        if self.process is not None and self.process.poll() is not None:
            self.motion_arm_renew_stop.set()
            code = self.process.returncode
            if self.log_stream is not None:
                self.log_stream.close()
                self.log_stream = None
            self.process = None
            self.state = "STOPPED"
            self.state_text.set("A ajuns ✓" if code == 0 else "S-a oprit cu o problemă")
            self._apply_autonomous_start_readiness()
            self._journey_mode_changed()
            self.pause_button.configure(state="disabled", text="Ⅱ  PAUZĂ")
            self.stop_button.configure(state="disabled")
        if self.combat_process is not None and self.combat_process.poll() is not None:
            code = self.combat_process.returncode
            if self.combat_log_stream is not None:
                self.combat_log_stream.close()
                self.combat_log_stream = None
            self.combat_process = None
            self.combat_state = "STOPPED"
            self.combat_status_text.set(
                "Lupta s-a terminat ✓" if code == 0 else "Lupta s-a oprit cu o problemă"
            )
            self.combat_start_button.configure(state="normal")
            self.combat_pause_button.configure(state="disabled", text="Ⅱ  PAUZĂ")
            self.combat_stop_button.configure(state="disabled")
            # Operator requested persistent LAB godmode. Completion of a combat
            # child must not silently disable that test setup.
        if (
            self.manual_recorder_process is not None
            and self.manual_recorder_process.poll() is not None
        ):
            code = self.manual_recorder_process.returncode
            if self.manual_recorder_log_stream is not None:
                self.manual_recorder_log_stream.close()
                self.manual_recorder_log_stream = None
            self.manual_recorder_process = None
            self.manual_recorder_state = "STOPPED"
            self.record_manual_button.configure(state="normal")
            self.stop_manual_button.configure(state="disabled")
            # Import may have become visible in the same refresh after its
            # first result read. Force one final read after process exit.
            self.manual_result_mtime_ns = None
            self._refresh_manual_recording_result()
            if code not in {0, 2}:
                self.manual_recording_text.set(
                    "Înregistrarea s-a oprit cu o problemă"
                )
        # Lifecycle reconciliation above wins over the last FOLLOW snapshot.
        # A motor can be stopped while the user moves the character manually.
        if not (snapshot is None and self.manual_recording_draft):
            self.controller_text.set(_runtime_controller_text(
                snapshot,
                state=self.state,
                process_running=self.process is not None and self.process.poll() is None,
            ))
        self._sync_overlay()
        self.root.after(250, self._refresh)

    def close(self) -> None:
        self.motion_arm_renew_stop.set()
        self.stay_online_panel.close()
        self.codex_driver_enabled.set(False)
        self._codex_driver_changed()
        if self.recording_hotkeys is not None:
            self.recording_hotkeys.close()
        if self.process is not None and self.process.poll() is None:
            self._write_command("STOP")
        if self.combat_process is not None and self.combat_process.poll() is None:
            self._write_combat_command("STOP")
        if (
            self.manual_recorder_process is not None
            and self.manual_recorder_process.poll() is None
        ):
            self._write_manual_recorder_command("STOP")
        self._stop_overlay()
        if (
            self.nav_viewer_bridge_process is not None
            and self.nav_viewer_bridge_process.poll() is None
        ):
            self.nav_viewer_bridge_process.terminate()
        if self.nav_viewer_process is not None and self.nav_viewer_process.poll() is None:
            self.nav_viewer_process.terminate()
        awareness_process = self.structure_awareness_service
        if awareness_process is not None and awareness_process.poll() is None:
            try:
                if awareness_process.stdin is not None:
                    awareness_process.stdin.write(json.dumps({
                        "request_id": f"shutdown:{uuid4()}",
                        "command": "SHUTDOWN",
                    }, separators=(",", ":")) + "\n")
                    awareness_process.stdin.flush()
            except (BrokenPipeError, OSError):
                awareness_process.terminate()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predator Control Center")
    parser.add_argument("--horizontal-clearance-candidate", action="store_true")
    parser.add_argument("--spatial-sonar-wmo-config", type=Path)
    parser.add_argument("--spatial-sonar-continuity", action="store_true")
    options = parser.parse_args()
    _configure_horizontal_clearance_candidate(options.horizontal_clearance_candidate)
    MovementEngineClient(spatial_sonar_wmo_config=options.spatial_sonar_wmo_config,
                         spatial_sonar_continuity=options.spatial_sonar_continuity).run()
