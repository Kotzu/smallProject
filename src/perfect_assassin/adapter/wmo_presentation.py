"""Bounded read-only WMO evidence presentation; never selects an actor floor."""

from math import isfinite
from re import fullmatch


def _number(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("invalid WMO display number")
    return value


def _list(value, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("invalid WMO display list")
    return value


def _unknown_floor(record):
    if (
        record["execution_authority"] is not False
        or record["confirmed_floor_id"] is not None
        or record["terrain_and_doodads_checked"] is not False
    ):
        raise ValueError("invalid WMO evidence scope")


def wmo_presentation(sonar):
    """Caller must first apply the outer sonar session/pose/time gate.

    Optional errors suppress only WMO details. Raw exception text is not rendered.
    """
    if "wmo_surface_association" not in sonar:
        return (), "Asociere WMO neactivată în acest raport."
    if sonar.get("wmo_surface_error") or sonar["wmo_surface_association"] is None:
        return (), "Asociere WMO indisponibilă; sonarul de bază rămâne separat."
    try:
        return _present(sonar)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        return (), "Asociere WMO invalidă; fără concluzii despre etaj sau spațiu liber."


def _present(sonar):
    evidence = sonar["wmo_surface_association"]
    _unknown_floor(evidence)
    if (
        type(evidence["schema_version"]) is not int
        or evidence["schema_version"] != 1
        or evidence["source"] != "VERIFIED_WMO_GROUP_BUNDLE"
        or evidence["coverage"] != "LISTED_MODELS_ONLY"
        or evidence["world_pack_sha256"] != sonar["world_pack_sha256"]
        or type(evidence["map_id"]) is not int
        or evidence["map_id"] != sonar["observation_key"][2]
        or not fullmatch("[a-f0-9]{64}", evidence["bundle_sha256"])
        or evidence["query_xy"] != sonar["query_origin_xyz"][:2]
    ):
        raise ValueError("foreign WMO display evidence")
    xy = _list(evidence["query_xy"], 2)
    if len(xy) != 2:
        raise ValueError("invalid column")
    for value in xy:
        _number(value)
    count = evidence["loaded_model_count"]
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError("invalid model count")
    structures = _list(evidence["structures"], 16)
    missing = _list(evidence["uncovered_structure_ids"], 16)
    ids = [s["structure_id"] for s in structures] + missing
    if (
        any(not isinstance(i, str) or len(i) > 100 for i in ids)
        or len(set(ids)) != len(ids)
        or len(ids) > 16
        or type(evidence["column_wmo_count"]) is not int
        or evidence["column_wmo_count"] != len(ids)
    ):
        raise ValueError("invalid instance coverage")
    rows = []
    hit_budget = 8192
    for structure in structures:
        association = structure["association"]
        _unknown_floor(association)
        if (
            type(association["schema_version"]) is not int
            or association["schema_version"] != 1
            or association["candidate_source"] != "CLIENT_ASSET_HEIGHT_QUERY"
            or association["surface_source"] != "CLIENT_WMO_GROUP_TRIANGLES"
            or association["source"] != "SAME_COLUMN_ASSET_SURFACE_ASSOCIATION"
            or association["query_xy"] != xy
            or association["observed_actor_z"] is not None
            or association["selected_surface_z_unchanged"]
            != sonar["vertical_candidates"]["selected_surface_z"]
        ):
            raise ValueError("foreign candidate association")
        candidates = _list(association["candidates"], 64)
        if [c["candidate_z"] for c in candidates] != sonar["vertical_candidates"][
            "heights"
        ]:
            raise ValueError("candidate set changed")
        low, high = _list(association["segment_z"], 2)
        if not 0 < _number(high) - _number(low) <= 10000:
            raise ValueError("invalid finite segment")
        tolerance = _number(association["numerical_matching_tolerance_yards"])
        if not 0 < tolerance <= 0.01:
            raise ValueError("invalid matching budget")
        for i, candidate in enumerate(candidates):
            z = _number(candidate["candidate_z"])
            matches = _list(candidate["matches"], 4096)
            hit_budget -= len(matches)
            if hit_budget < 0:
                raise ValueError("display hit budget exceeded")
            status = (
                "MATCHED_GEOMETRY"
                if matches
                else "NO_WMO_MATCH"
                if low <= z <= high
                else "OUTSIDE_TESTED_SEGMENT"
            )
            if (
                type(candidate["candidate_index"]) is not int
                or candidate["candidate_index"] != i
                or candidate["candidate_retained"] is not True
                or candidate["status"] != status
                or (matches and not low <= z <= high)
            ):
                raise ValueError("invalid candidate status")
            identities = []
            for hit in matches:
                for key in ("group_id", "triangle_index"):
                    if type(hit[key]) is not int or not 0 <= hit[key] <= 0xFFFFFFFF:
                        raise ValueError("invalid triangle identity")
                delta = _number(hit["height_delta_yards"])
                if (
                    not 0 <= delta <= tolerance
                    or abs(abs(z - _number(hit["surface_z"])) - delta) > 1e-8
                ):
                    raise ValueError("invalid triangle match")
                if len(identities) < 2:
                    identities.append(
                        f"grup {hit['group_id']}/triunghi {hit['triangle_index']}"
                    )
            description = (
                f"{len(matches)} potriviri: {', '.join(identities)}"
                if matches
                else "Fără potrivire WMO în segment"
                if status == "NO_WMO_MATCH"
                else "În afara segmentului WMO testat"
            )
            if len(rows) < 32:
                rows.append(
                    (
                        f"Suprafață candidată {i + 1}",
                        structure["structure_id"],
                        f"Altitudine {z:.3f} yd",
                        description + "; alternativă păstrată, etaj neconfirmat",
                    )
                )
    total = sum(len(s["association"]["candidates"]) for s in structures)
    notes = (
        f"WMO: acoperire parțială, {count} modele încărcate; "
        f"{len(structures)}/{len(ids)} instanțe din coloană verificate. "
        "Terenul și obiectele mici nu sunt verificate de această asociere."
    )
    if missing:
        notes += " Lipsesc modele pentru: " + ", ".join(missing) + "."
    if not ids:
        notes += " Nicio instanță WMO în coloană nu înseamnă spațiu liber."
    if total > len(rows):
        notes += f" Afișare limitată: {len(rows)}/{total} rânduri."
    notes += " Potrivirea geometrică nu confirmă nivelul personajului."
    return tuple(rows), notes
