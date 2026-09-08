from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal

from perfect_assassin.capture.ports import CaptureRegion


CaptureBackend = Literal[
    "dxgi_desktop_duplication",
    "winrt_monitor_capture",
    "win32_print_window",
]
DecisionContext = Literal["champion", "lab_clone"]


@dataclass(frozen=True, slots=True)
class InMemoryCaptureFrame:
    frame_id: str
    session_id: str
    target_profile: str
    instance_id: str
    actor_role: str
    actor_id: str
    decision_context: DecisionContext
    memory_namespace: str
    expected_character_name: str
    credential_alias: str
    binding_assurance_state: str
    binding_assurance_evidence_refs: tuple[str, ...]
    authorization_sha256: str
    client_build: str
    build_signature: str
    provider_id: str
    provider_version: str
    backend: CaptureBackend
    device_index: int
    output_index: int
    region: CaptureRegion | None
    window_ref: str | None
    width: int
    height: int
    row_stride_bytes: int
    captured_at: str
    monotonic_timestamp_s: float
    source_timestamp_s: float | None
    frame_age_ms: float
    evidence_refs: tuple[str, ...]
    confidence: float = 1.0

    def __post_init__(self) -> None:
        text_fields = (
            self.frame_id,
            self.session_id,
            self.target_profile,
            self.instance_id,
            self.actor_role,
            self.actor_id,
            self.memory_namespace,
            self.expected_character_name,
            self.credential_alias,
            self.client_build,
            self.build_signature,
            self.provider_id,
            self.provider_version,
            self.captured_at,
        )
        if any(not value for value in text_fields):
            raise ValueError("capture manifest text fields must not be empty")
        expected_context = {
            "champion_journey": "champion",
            "lab_clone": "lab_clone",
        }.get(self.actor_role)
        if expected_context is None or self.decision_context != expected_context:
            raise ValueError("capture actor role and decision context are inconsistent")
        expected_namespace_prefix = (
            "memory:champion:"
            if self.actor_role == "champion_journey"
            else "memory:lab:"
        )
        if not self.memory_namespace.startswith(expected_namespace_prefix):
            raise ValueError("capture memory namespace does not match actor role")
        if (
            self.binding_assurance_state != "configured_expected_only"
            or not self.binding_assurance_evidence_refs
            or len(self.binding_assurance_evidence_refs) > 4
            or len(set(self.binding_assurance_evidence_refs))
            != len(self.binding_assurance_evidence_refs)
            or any(
                not isinstance(reference, str)
                or not reference
                or len(reference) > 256
                for reference in self.binding_assurance_evidence_refs
            )
        ):
            raise ValueError("capture actor binding assurance must remain configured-only")
        if (
            not isinstance(self.authorization_sha256, str)
            or len(self.authorization_sha256) != 64
            or any(character not in "0123456789ABCDEF" for character in self.authorization_sha256)
        ):
            raise ValueError("capture authorization SHA-256 must be 64 uppercase hex characters")
        if self.device_index < 0 or self.output_index < 0:
            raise ValueError("capture device/output indexes must be non-negative")
        if self.width <= 0 or self.height <= 0 or self.row_stride_bytes < self.width * 4:
            raise ValueError("capture image dimensions or stride are invalid")
        timing_values = (self.monotonic_timestamp_s, self.frame_age_ms)
        if (
            any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
                for value in timing_values
            )
            or (
                self.source_timestamp_s is not None
                and (
                    isinstance(self.source_timestamp_s, bool)
                    or not isinstance(self.source_timestamp_s, (int, float))
                    or not isfinite(self.source_timestamp_s)
                    or self.source_timestamp_s < 0
                )
            )
        ):
            raise ValueError("capture timing values must be finite and non-negative")
        if not self.evidence_refs:
            raise ValueError("capture evidence_refs must not be empty")
        if self.window_ref is not None and self.region is None:
            raise ValueError("window capture requires an output-relative region")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not isfinite(self.confidence)
            or not 0 < self.confidence <= 1
        ):
            raise ValueError("capture confidence must be finite and in (0, 1]")

    def to_manifest(self) -> dict[str, Any]:
        region = None
        if self.region is not None:
            region = {
                "left": self.region.left,
                "top": self.region.top,
                "width": self.region.width,
                "height": self.region.height,
            }
        return {
            "record_type": "capture_frame_manifest",
            "schema_version": "2.0",
            "frame_id": self.frame_id,
            "session_id": self.session_id,
            "target_profile": self.target_profile,
            "actor_binding": {
                "schema_version": "1.0",
                "instance_id": self.instance_id,
                "actor_role": self.actor_role,
                "actor_id": self.actor_id,
                "decision_context": self.decision_context,
                "memory_namespace": self.memory_namespace,
                "expected_character_name": self.expected_character_name,
                "credential_alias": self.credential_alias,
                "binding_assurance": {
                    "state": self.binding_assurance_state,
                    "evidence_refs": list(self.binding_assurance_evidence_refs),
                },
            },
            "authorization_sha256": self.authorization_sha256,
            "decision_context": self.decision_context,
            "client_build": self.client_build,
            "build_signature": self.build_signature,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "backend": self.backend,
            "source": {
                "source_kind": "window_region" if self.window_ref else "monitor",
                "device_index": self.device_index,
                "output_index": self.output_index,
                "coordinate_space": "output_physical_pixels",
                "region": region,
                "window_ref": self.window_ref,
            },
            "image": {
                "width": self.width,
                "height": self.height,
                "row_stride_bytes": self.row_stride_bytes,
                "pixel_format": "BGRA8",
                "orientation": "top_down",
            },
            "timing": {
                "captured_at": self.captured_at,
                "source_timestamp_s": self.source_timestamp_s,
                "monotonic_timestamp_s": self.monotonic_timestamp_s,
                "frame_age_ms": self.frame_age_ms,
            },
            "provenance": {
                "origin": "window_capture",
                "capability": "screen_capture",
                "scope": (
                    "unpromoted_evaluation_only"
                    if self.decision_context == "champion"
                    else "lab_evaluation_only"
                ),
                "confidence": self.confidence,
                "evidence_refs": list(self.evidence_refs),
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
