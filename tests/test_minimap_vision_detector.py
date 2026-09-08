from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path

import numpy as np

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

detector_module = importlib.import_module("minimap_detector")


def capture_manifest(
    width: int = 640,
    height: int = 480,
    *,
    decision_context: str = "champion",
    instance_id: str | None = None,
    actor_id: str | None = None,
    memory_namespace: str | None = None,
    authorization_sha256: str = "C" * 64,
    live: bool = False,
) -> dict:
    actor_role = "champion_journey" if decision_context == "champion" else "lab_clone"
    namespace_prefix = "memory:champion:" if decision_context == "champion" else "memory:lab:"
    origin = "window_capture" if live else "replay_fixture"
    scope = (
        "synthetic_fixture"
        if not live
        else (
            "unpromoted_evaluation_only"
            if decision_context == "champion"
            else "lab_evaluation_only"
        )
    )
    return {
        "record_type": "capture_frame_manifest",
        "schema_version": "2.0",
        "frame_id": "frame:minimap:fixture:0001",
        "session_id": "session:minimap-fixture",
        "target_profile": "tbc_243_lab",
        "authorization_sha256": authorization_sha256,
        "actor_binding": {
            "schema_version": "1.0",
            "instance_id": instance_id or f"instance:fixture:{decision_context}",
            "actor_role": actor_role,
            "actor_id": actor_id or f"actor:predator:fixture-{decision_context}",
            "decision_context": decision_context,
            "memory_namespace": memory_namespace or f"{namespace_prefix}fixture",
            "expected_character_name": "Predator",
            "credential_alias": "credential:fixture:champion",
            "binding_assurance": {
                "state": "configured_expected_only",
                "evidence_refs": ["authorization:fixture:actor-expected"],
            },
        },
        "decision_context": decision_context,
        "client_build": "2.4.3.8606",
        "build_signature": "wow-tbc-2.4.3.8606-enGB:sha256:406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6",
        "provider_id": "capture_window_fixture" if live else "capture_replay_fixture",
        "provider_version": "0.1.0",
        "backend": "dxgi_desktop_duplication" if live else "replay_fixture",
        "source": {
            "source_kind": "window_region" if live else "replay_fixture",
            "device_index": 0 if live else None,
            "output_index": 0 if live else None,
            "coordinate_space": (
                "output_physical_pixels" if live else "replay_fixture_pixels"
            ),
            "region": {"left": 0, "top": 0, "width": width, "height": height},
            "window_ref": "pid:101:hwnd:0xCAFE" if live else None,
        },
        "image": {
            "width": width,
            "height": height,
            "row_stride_bytes": width * 4,
            "pixel_format": "BGRA8",
            "orientation": "top_down",
        },
        "timing": {
            "captured_at": "2026-08-22T20:00:00Z",
            "source_timestamp_s": 10.0,
            "monotonic_timestamp_s": 20.0,
            "frame_age_ms": 2.0,
        },
        "provenance": {
            "origin": origin,
            "capability": "screen_capture",
            "scope": scope,
            "confidence": 1.0,
            "evidence_refs": ["fixture:minimap:synthetic:0001"],
        },
        "artifact": {
            "persisted": False,
            "media_type": "application/x-perfect-assassin-bgra8",
            "path": None,
            "sha256": None,
        },
        "privacy": {
            "content_class": "game_client_pixels",
            "redaction_state": "in_memory_only",
            "retention": "none",
        },
        "execution_authority": False,
    }


def synthetic_frame(*, marker: bool = True, circle: bool = True) -> np.ndarray:
    height, width = 480, 640
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    frame[:, :, 3] = 255
    center_x, center_y, radius = 608, 50, 30
    yy, xx = np.indices((height, width))
    distance = np.hypot(xx - center_x, yy - center_y)
    interior = distance < radius - 2
    frame[interior, 0] = 45 + ((xx[interior] + yy[interior]) % 25).astype(np.uint8)
    frame[interior, 1] = 65 + ((2 * xx[interior]) % 35).astype(np.uint8)
    frame[interior, 2] = 55 + ((3 * yy[interior]) % 30).astype(np.uint8)
    if circle:
        ring = np.abs(distance - radius) <= 1.5
        frame[ring, :3] = (220, 220, 220)
    if marker:
        marker_mask = np.zeros((height, width), dtype=bool)
        for delta_x in range(-7, 10):
            if delta_x < 1:
                half_height = 2
            else:
                half_height = max(0, (9 - delta_x) // 2)
            marker_mask[
                center_y - half_height : center_y + half_height + 1,
                center_x + delta_x,
            ] = True
        frame[marker_mask, :3] = (20, 190, 245)
    return frame


class MinimapVisionDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capture_validator = ContractValidator(
            ROOT / "contracts" / "capture-frame.schema.json"
        )
        self.minimap_validator = ContractValidator(
            ROOT / "contracts" / "minimap-vision.schema.json"
        )
        self.profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "minimap-tbc243-8606.json",
            self.minimap_validator,
        )
        self.detector = detector_module.MinimapVisionDetector(
            self.profile,
            self.capture_validator,
            self.minimap_validator,
        )

    def detect(self, frame: np.ndarray) -> dict:
        return self.detector.detect(
            capture_manifest(),
            frame,
            observation_id="minimap:visual:fixture:0001",
        )

    def test_profile_is_versioned_and_controlled_live_heading_calibrated(self) -> None:
        self.minimap_validator.validate(self.profile)
        self.assertEqual(self.profile["client_build"], "2.4.3.8606")
        self.assertEqual(
            self.profile["calibration_state"], "controlled_live_verified"
        )
        self.assertGreaterEqual(
            len(self.profile["heading_calibration"]["evidence_refs"]), 2
        )

    def test_detects_circle_and_center_marker_without_claiming_world_pose(self) -> None:
        observation = self.detect(synthetic_frame())

        self.assertEqual(observation["tracking_state"], "FOUND")
        self.assertAlmostEqual(observation["minimap"]["center_x_px"], 608, delta=4)
        self.assertAlmostEqual(observation["minimap"]["center_y_px"], 50, delta=4)
        self.assertAlmostEqual(observation["minimap"]["radius_px"], 30, delta=3)
        self.assertAlmostEqual(
            observation["player_marker"]["orientation_deg_screen"], 90, delta=20
        )
        self.assertFalse(observation["absolute_pose_available"])
        self.assertFalse(observation["execution_authority"])
        self.assertEqual(observation["schema_version"], "1.0")
        self.assertEqual(observation["provenance"]["scope"], "synthetic_fixture")
        self.assertEqual(
            observation["actor_binding"], capture_manifest()["actor_binding"]
        )
        self.assertEqual(
            observation["authorization_sha256"],
            capture_manifest()["authorization_sha256"],
        )

    def test_profile_detects_scaled_live_minimap_circle(self) -> None:
        """The current Windows DPI scale must not hide the minimap heading fallback."""

        width, height = 3621, 2037
        center_x, center_y, radius = 3411, 211, 162
        frame = np.zeros((height, width, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        yy, xx = np.indices((height, width))
        distance = np.hypot(xx - center_x, yy - center_y)
        interior = distance < radius - 2
        frame[interior, 0] = 45 + ((xx[interior] + yy[interior]) % 25).astype(np.uint8)
        frame[interior, 1] = 65 + ((2 * xx[interior]) % 35).astype(np.uint8)
        frame[interior, 2] = 55 + ((3 * yy[interior]) % 30).astype(np.uint8)
        ring = np.abs(distance - radius) <= 1.5
        frame[ring, :3] = (220, 220, 220)

        observation = detector_module.MinimapVisionDetector(
            self.profile,
            self.capture_validator,
            self.minimap_validator,
        ).detect(
            capture_manifest(width=width, height=height),
            frame,
            observation_id="minimap:visual:scaled-live-fixture:0001",
        )

        self.assertEqual(observation["tracking_state"], "DEGRADED")
        self.assertAlmostEqual(observation["minimap"]["radius_px"], radius, delta=8)

    def test_circle_without_marker_is_degraded(self) -> None:
        observation = self.detect(synthetic_frame(marker=False))

        self.assertEqual(observation["tracking_state"], "DEGRADED")
        self.assertIsNotNone(observation["minimap"])
        self.assertIsNone(observation["player_marker"])

    def test_neutral_mdx_marker_is_preferred_and_converts_to_world_heading(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["marker"]["neutral_model"]["min_pixels"] = 8
        profile["marker"]["neutral_model"]["max_pixels"] = 100
        detector = detector_module.MinimapVisionDetector(
            profile,
            self.capture_validator,
            self.minimap_validator,
        )
        frame = synthetic_frame(marker=False)
        center_x, center_y = 608, 50
        for delta_y in range(-7, 6):
            half_width = 1 if delta_y < 1 else 3
            frame[
                center_y + delta_y,
                center_x - half_width : center_x + half_width + 1,
                :3,
            ] = (205, 205, 205)

        observation = detector.detect(
            capture_manifest(),
            frame,
            observation_id="minimap:visual:neutral-mdx",
        )

        marker = observation["player_marker"]
        self.assertEqual(marker["detection_model"], "neutral_mdx")
        self.assertAlmostEqual(marker["orientation_deg_screen"], 0.0, delta=20.0)
        heading = detector_module.world_heading_from_marker(
            detector_module.MarkerCandidate(
                center_x_px=marker["center_x_px"],
                center_y_px=marker["center_y_px"],
                orientation_deg_screen=marker["orientation_deg_screen"],
                pixel_count=marker["pixel_count"],
                confidence=marker["confidence"],
                detection_model=marker["detection_model"],
            ),
            profile,
        )
        expected = profile["heading_calibration"]["offset_rad"] % (2 * np.pi)
        self.assertAlmostEqual(heading, expected, delta=0.35)

    def test_neutral_mdx_accepts_render_model_center_offset_within_profile(self) -> None:
        profile = copy.deepcopy(self.profile)
        neutral = profile["marker"]["neutral_model"]
        neutral["central_radius_fraction"] = 0.35
        neutral["min_pixels"] = 8
        neutral["max_pixels"] = 100
        detector = detector_module.MinimapVisionDetector(
            profile,
            self.capture_validator,
            self.minimap_validator,
        )
        frame = synthetic_frame(marker=False)
        center_x, center_y = 608 + 5, 50
        for delta_y in range(-7, 6):
            half_width = 1 if delta_y < 1 else 3
            frame[
                center_y + delta_y,
                center_x - half_width : center_x + half_width + 1,
                :3,
            ] = (205, 205, 205)

        observation = detector.detect(
            capture_manifest(),
            frame,
            observation_id="minimap:visual:neutral-mdx-offset",
        )

        marker = observation["player_marker"]
        self.assertEqual(observation["tracking_state"], "FOUND")
        self.assertEqual(marker["detection_model"], "neutral_mdx")
        self.assertAlmostEqual(marker["center_x_px"], center_x, delta=2.0)

    def test_loading_screen_and_unstructured_noise_fail_closed(self) -> None:
        loading = np.zeros((480, 640, 4), dtype=np.uint8)
        loading[:, :, 3] = 255
        noise = np.random.default_rng(7).integers(
            0, 256, size=(480, 640, 4), dtype=np.uint8
        )
        noise[:, :, 3] = 255

        for frame in (loading, noise):
            with self.subTest(kind="loading" if frame is loading else "noise"):
                observation = self.detect(frame)
                self.assertEqual(observation["tracking_state"], "NOT_FOUND")
                self.assertIsNone(observation["minimap"])
                self.assertEqual(observation["confidence"], 0)

    def test_profile_identity_mismatch_is_rejected(self) -> None:
        manifest = capture_manifest()
        manifest["client_build"] = "2.5.6.unknown"
        with self.assertRaisesRegex(
            detector_module.MinimapDetectionError, "client_build"
        ):
            self.detector.detect(
                manifest,
                synthetic_frame(),
                observation_id="minimap:visual:mismatch",
            )

    def test_buffer_size_and_shape_are_checked(self) -> None:
        with self.assertRaisesRegex(
            detector_module.MinimapDetectionError, "buffer size mismatch"
        ):
            self.detector.detect(
                capture_manifest(),
                memoryview(bytearray(12)),
                observation_id="minimap:visual:short-buffer",
            )

    def test_contract_rejects_absolute_pose_claim(self) -> None:
        observation = self.detect(synthetic_frame())
        invalid = copy.deepcopy(observation)
        invalid["absolute_pose_available"] = True
        with self.assertRaises(ContractValidationError):
            self.minimap_validator.validate(invalid)

    def test_live_scope_is_actor_bound_and_never_champion_eligible(self) -> None:
        champion = self.detector.detect(
            capture_manifest(live=True, decision_context="champion"),
            synthetic_frame(),
            observation_id="minimap:visual:champion-live",
        )
        lab = self.detector.detect(
            capture_manifest(live=True, decision_context="lab_clone"),
            synthetic_frame(),
            observation_id="minimap:visual:lab-live",
        )
        self.assertEqual(
            champion["provenance"]["scope"],
            "unpromoted_evaluation_only",
        )
        self.assertEqual(lab["provenance"]["scope"], "lab_evaluation_only")
        self.assertNotEqual(champion["actor_binding"], lab["actor_binding"])

    def test_two_lab_clones_preserve_distinct_actor_and_memory_namespaces(self) -> None:
        manifest_a = capture_manifest(
            decision_context="lab_clone",
            instance_id="instance:fixture:clone-a",
            actor_id="actor:predator:clone-a",
            memory_namespace="memory:lab:fixture:clone-a",
        )
        manifest_b = capture_manifest(
            decision_context="lab_clone",
            instance_id="instance:fixture:clone-b",
            actor_id="actor:predator:clone-b",
            memory_namespace="memory:lab:fixture:clone-b",
            authorization_sha256="D" * 64,
        )
        observation_a = self.detector.detect(
            manifest_a,
            synthetic_frame(),
            observation_id="minimap:visual:clone-a",
        )
        observation_b = self.detector.detect(
            manifest_b,
            synthetic_frame(),
            observation_id="minimap:visual:clone-b",
        )
        self.assertEqual(observation_a["actor_binding"], manifest_a["actor_binding"])
        self.assertEqual(observation_b["actor_binding"], manifest_b["actor_binding"])
        self.assertNotEqual(
            observation_a["actor_binding"]["memory_namespace"],
            observation_b["actor_binding"]["memory_namespace"],
        )
        self.assertNotEqual(
            observation_a["authorization_sha256"],
            observation_b["authorization_sha256"],
        )

    def test_replay_provenance_cannot_be_relabelled(self) -> None:
        observation = self.detect(synthetic_frame())
        relabelled_observation = copy.deepcopy(observation)
        relabelled_observation["provenance"]["scope"] = (
            "unpromoted_evaluation_only"
        )
        with self.assertRaises(ContractValidationError):
            self.minimap_validator.validate(relabelled_observation)

        relabelled_manifest = capture_manifest()
        relabelled_manifest["provenance"]["scope"] = (
            "unpromoted_evaluation_only"
        )
        with self.assertRaises(ContractValidationError):
            self.detector.detect(
                relabelled_manifest,
                synthetic_frame(),
                observation_id="minimap:visual:relabelled-replay",
            )

    def test_detection_is_deterministic(self) -> None:
        frame = synthetic_frame()
        self.assertEqual(self.detect(frame), self.detect(frame.copy()))


if __name__ == "__main__":
    unittest.main()
