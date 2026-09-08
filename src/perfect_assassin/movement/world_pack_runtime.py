from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    StandaloneWorldPackError,
    VerifiedStandaloneWorldPack,
    open_standalone_world_pack,
)


@dataclass(frozen=True, slots=True)
class WorldPackRuntimeBinding:
    profile_id: str
    pack: VerifiedStandaloneWorldPack


def load_world_pack_runtime_profile(
    profile_path: Path,
    *,
    store_root: Path,
    profile_schema_path: Path,
    pack_schema_path: Path,
    catalog_schema_path: Path,
) -> WorldPackRuntimeBinding:
    try:
        profile: dict[str, Any] = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StandaloneWorldPackError(
            f"cannot read WorldPack runtime profile: {error}"
        ) from error
    ContractValidator(profile_schema_path).validate(profile)
    directory_name = str(profile["pack_directory_name"])
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", directory_name) is None:
        raise StandaloneWorldPackError("WorldPack directory identity is unsafe")
    store_root = store_root.resolve()
    pack_root = (store_root / directory_name).resolve()
    if pack_root.parent != store_root:
        raise StandaloneWorldPackError("WorldPack directory escaped its store")
    opened = open_standalone_world_pack(
        pack_root,
        pack_schema_path=pack_schema_path,
        catalog_schema_path=catalog_schema_path,
        expected_pack_id=str(profile["pack_id"]),
        expected_content_sha256=str(profile["content_sha256"]),
    )
    catalog = opened.catalog
    identity_pairs = (
        ("catalog_id", catalog.catalog_id),
        ("target_profile", catalog.target_profile),
        ("client_version", catalog.client_version),
        ("client_build", catalog.client_build),
        ("nav_profile_id", catalog.nav_profile_id),
    )
    for field, actual in identity_pairs:
        if profile[field] != actual:
            raise StandaloneWorldPackError(
                f"WorldPack runtime profile {field} is inconsistent"
            )
    expected_maps = {
        (int(item["map_id"]), str(item["internal_name"]))
        for item in profile["maps"]
    }
    actual_maps = {(item.map_id, item.internal_name) for item in catalog.maps}
    if expected_maps != actual_maps or len(expected_maps) != len(profile["maps"]):
        raise StandaloneWorldPackError(
            "WorldPack runtime profile map coverage is inconsistent"
        )
    return WorldPackRuntimeBinding(
        profile_id=str(profile["profile_id"]),
        pack=opened,
    )
