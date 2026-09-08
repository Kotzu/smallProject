"""Bounded topology comparisons between observations, without floor selection."""

from math import hypot, isfinite
from time import monotonic

from .vertical_connection import parse_connection, point


def snapshot(record):
    candidates = record["vertical_candidates"]
    heights = candidates["heights"]
    xy = record["pose_xy_at_query"]
    stamp = record["pose_observed_monotonic_s"]
    key = record["observation_key"]
    pack = record["world_pack_sha256"]
    if (record["execution_authority"] is not False
            or candidates["execution_authority"] is not False
            or candidates["source"] != "CLIENT_ASSET_HEIGHT_QUERY"
            or candidates["observed_actor_z"] is not None
            or candidates["confirmed_floor_id"] is not None
            or not isinstance(heights, list) or not 1 <= len(heights) <= 64
            or not isinstance(xy, list) or len(xy) != 2
            or not isinstance(key, list) or len(key) != 3
            or not isinstance(key[0], str) or not key[0]
            or type(key[1]) is not int or type(key[2]) is not int
            or not isinstance(pack, str) or len(pack) != 64
            or any(c not in "0123456789abcdef" for c in pack)
            or type(stamp) not in (float, int) or not isfinite(stamp)):
        raise ValueError("invalid transition observation")
    for height in heights:
        point([*xy, height])
    return {"key": list(key), "pack": pack, "xy": list(xy), "stamp": stamp,
            "heights": list(heights)}


def compatible(before, after, now_s):
    return (before["key"] == after["key"] and before["pack"] == after["pack"]
            and 0 <= now_s - after["stamp"] <= 3
            and 0 <= now_s - before["stamp"] <= 3
            and 0 < after["stamp"] - before["stamp"] <= 3
            and hypot(*(b-a for a, b in zip(before["xy"], after["xy"]))) <= 64)


def compare(before, after, query, *, clock=monotonic):
    """Single background batch. No cancellation claim for an in-flight query."""
    started = clock()
    if not compatible(before, after, started):
        raise ValueError("incompatible or expired transition")
    pairs = []
    total = len(before["heights"]) * len(after["heights"])
    for i, z1 in enumerate(before["heights"]):
        for j, z2 in enumerate(after["heights"]):
            if len(pairs) >= 16 or clock() - started >= 0.5:
                break
            result = query(start=(*before["xy"], z1), stop=(*after["xy"], z2))
            pairs.append({"from_index": i, "to_index": j, "connection": result})
        else:
            continue
        break
    return {"schema_version": 1, "source": "CLIENT_NAVMESH_TOPOLOGY",
            "before": before, "after": after, "pairs": pairs,
            "unqueried_count": total-len(pairs), "exhaustive_surfaces": False,
            "observed_actor_z": None, "floor_id": None, "execution_authority": False}


def presentation(record, *, now_s):
    batch = record.get("vertical_transition")
    if batch is None:
        status = record.get("vertical_transition_status")
        text = {"WAITING": "Continuitate: aștept două observații compatibile.",
                "UNAVAILABLE": "Continuitate indisponibilă; sonarul de bază rămâne separat."}
        return (), text.get(status, "")
    try:
        before, after = batch["before"], batch["after"]
        if (batch["schema_version"] != 1 or batch["source"] != "CLIENT_NAVMESH_TOPOLOGY"
                or batch["execution_authority"] is not False
                or batch["observed_actor_z"] is not None or batch["floor_id"] is not None
                or batch["exhaustive_surfaces"] is not False
                or after != snapshot(record) or not compatible(before, after, now_s)):
            raise ValueError("unbound transition")
        # Validate the embedded preceding snapshot using the same observation parser.
        prior = {**record, "observation_key": before["key"],
                 "world_pack_sha256": before["pack"], "pose_xy_at_query": before["xy"],
                 "pose_observed_monotonic_s": before["stamp"],
                 "vertical_candidates": {**record["vertical_candidates"], "heights": before["heights"]}}
        if before != snapshot(prior):
            raise ValueError("invalid preceding snapshot")
        pairs = batch["pairs"]
        if not isinstance(pairs, list) or len(pairs) > 16:
            raise ValueError("invalid pair count")
        missing = batch["unqueried_count"]
        if type(missing) is not int or missing != len(before["heights"])*len(after["heights"])-len(pairs):
            raise ValueError("invalid coverage")
        rows, seen = [], set()
        derived = {"start_projection_yards", "stop_projection_yards",
                   "actor_transition_confirmed", "volumetric_clearance_checked"}
        for pair in pairs:
            i, j = pair["from_index"], pair["to_index"]
            if (type(i) is not int or type(j) is not int or (i,j) in seen
                    or not 0 <= i < len(before["heights"]) or not 0 <= j < len(after["heights"])):
                raise ValueError("invalid pair identity")
            seen.add((i,j))
            z1, z2 = before["heights"][i], after["heights"][j]
            raw = pair["connection"]
            if raw["actor_transition_confirmed"] is not False or raw["volumetric_clearance_checked"] is not False:
                raise ValueError("invalid transition claim")
            result = parse_connection({k:v for k,v in raw.items() if k not in derived},
                sequence=raw["sequence"], start=(*before["xy"],z1), stop=(*after["xy"],z2))
            status = "completă topologic" if result["complete"] else "incompletă / căutare limitată"
            rows.append((f"Nivel candidat {i+1} → {j+1}", f"Z {z1:.2f} → {z2:.2f}",
                         f"Funnel {result['funnel_length_yards']:.2f} yd · {status}",
                         f"Proiecții {result['start_projection_yards']:.2f}/{result['stop_projection_yards']:.2f} yd; mers necertificat"))
        return tuple(rows), (f"Continuitate geometrică: {len(pairs)} perechi verificate, {missing} neverificate. "
                             "Suprafețe neexhaustive; etaj și deplasare reală neconfirmate.")
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, AttributeError):
        return (), "Continuitate expirată/incompatibilă; fără concluzie despre etaj."
