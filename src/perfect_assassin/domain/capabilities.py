from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    profile: str
    version: str
    default: str
    capabilities: Mapping[str, str]

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "CapabilityProfile":
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ValueError("Capability profile requires a capabilities object")
        return cls(
            profile=str(value["profile"]),
            version=str(value["version"]),
            default=str(value["default"]),
            capabilities={str(key): str(status) for key, status in capabilities.items()},
        )

    def status_for(self, capability: str) -> str:
        return self.capabilities.get(capability, self.default)

    def canonical_hash(self) -> str:
        payload = {
            "profile": self.profile,
            "version": self.version,
            "default": self.default,
            "capabilities": dict(sorted(self.capabilities.items())),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
