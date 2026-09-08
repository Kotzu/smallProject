"""Bounded presentation of conditional geometry; no input or file access."""

from dataclasses import dataclass
from math import degrees, floor, isfinite

from .client_environment import environment_display
from .height_scan import parse_height_scan
from .spatial_sonar import observation_key, sonar_applicable, sonar_display
from .wmo_presentation import wmo_presentation
from .vertical_transition import presentation as transition_presentation


@dataclass(frozen=True)
class SonarDetails:
    status: str
    rows: tuple[tuple[str, str, str, str], ...] = ()
    notes: str = ""


def _number(value, *, nonnegative=False):
    if type(value) not in (float, int) or not isfinite(value):
        raise ValueError("invalid sonar number")
    if nonnegative and value < 0:
        raise ValueError("negative sonar distance")
    return value


def world_direction(bearing):
    """WoW world axes: +X north, +Y west, not screen/camera axes."""
    angle = _number(bearing) % 360
    name = ("N", "NV", "V", "SV", "S", "SE", "E", "NE")[floor((angle + 22.5) / 45) % 8]
    return f"{name} · {angle:.1f}°"


def sonar_details(record, *, labels, now_s):
    unavailable = SonarDetails("Sonar indisponibil sau expirat; fără distanțe actuale.")
    if not isinstance(record, dict):
        return unavailable
    try:
        key = observation_key(labels, record["observation_key"][2], now_s=now_s)
        if not sonar_applicable(
            record, key=key, xy=record["pose_xy_at_query"], now_s=now_s
        ):
            return unavailable
        if (
            record.get("distance_scope")
            != "CONDITIONAL_RESOLVED_QUERY_ORIGIN_NOT_CURRENT_ACTOR"
        ):
            return unavailable
        origin = record["resolved_query_xyz"]
        if not isinstance(origin, list) or len(origin) != 3:
            return unavailable
        origin = tuple(_number(v) for v in origin)
        rows = []
        for field, limit in (
            ("nearest_boundaries_at_query", 8),
            ("openings_at_query", 8),
        ):
            items = record.get(field, [])
            if not isinstance(items, list) or len(items) > limit:
                return unavailable
            for index, item in enumerate(items, 1):
                direction = world_direction(item["bearing_world_deg"])
                distance = _number(item["distance_yards"], nonnegative=True)
                if field == "nearest_boundaries_at_query":
                    rows.append(
                        (
                            f"Limită navmesh {index}",
                            direction,
                            f"{distance:.2f} yd până la segment",
                            "Nu identifică singură un zid fizic",
                        )
                    )
                else:
                    width = _number(item["width_yards"], nonnegative=True)
                    route = _number(item["route_distance_yards"], nonnegative=True)
                    rows.append(
                        (
                            f"Deschidere candidată {index}",
                            direction,
                            f"{distance:.2f} yd · lățime {width:.2f} yd",
                            f"Rută geometrică {route:.2f} yd; tip, înălțime și destinație necunoscute",
                        )
                    )
        probes = record.get("radial_probes_at_query", [])
        if not isinstance(probes, list) or len(probes) > 64:
            return unavailable
        if probes:
            radius = _number(record["probe_radius_yards"], nonnegative=True)
            if radius <= 0:
                return unavailable
            for index, probe in enumerate(probes, 1):
                distance = _number(
                    probe["tested_clear_distance_yards"], nonnegative=True
                )
                if (
                    distance > radius + 0.01
                    or probe.get("hit_distance_yards") is not None
                ):
                    return unavailable
                endpoint = probe["navmesh_endpoint_status"]
                if endpoint not in ("REACHABLE_BY_RAYCAST", "NOT_CONFIRMED"):
                    return unavailable
                result = (
                    "Nimic detectat până la limita sondei"
                    if distance >= radius
                    else "Obstacol limitează sonda; distanță exactă necunoscută"
                )
                nav = (
                    "navmesh până la capăt"
                    if endpoint == "REACHABLE_BY_RAYCAST"
                    else "capăt navmesh neconfirmat"
                )
                rows.append(
                    (
                        f"Sondă {index}",
                        world_direction(probe["bearing_world_deg"]),
                        f"Segment liber testat {distance:.2f} / {radius:.2f} yd",
                        f"{result}; {nav}",
                    )
                )
        height_scan = parse_height_scan(
            record.get("height_scan"), expected_origin=origin
        )
        if height_scan:
            for index, ray in enumerate(height_scan.rays):
                measure = (
                    f"Obstacol între {ray.clear_prefix_yards:.2f} și {ray.blocked_by_yards:.2f} yd"
                    if ray.blocked_by_yards is not None
                    else "Nimic detectat până la 12.00 yd"
                )
                rows.append(
                    (
                        f"Z+{ray.height_offset_yards:.2f} yd · raza {index % 16 + 1}",
                        world_direction(degrees(ray.bearing_rad)),
                        measure,
                        "La înălțimea sondei; nu certifică volumul corpului sau mersul",
                    )
                )
        age = now_s - record["pose_observed_monotonic_s"]
        wmo_rows, wmo_notes = wmo_presentation(record)
        transition_rows, transition_notes = transition_presentation(record, now_s=now_s)
        rows = list(transition_rows) + list(wmo_rows) + rows
        notes = (
            f"Origine geometrică estimată: X {origin[0]:.2f}, Y {origin[1]:.2f}, Z {origin[2]:.2f} yd. "
            "Distanțe XY de la această origine, nu de la un XYZ confirmat al personajului.\n"
            "Direcții pe hartă: 0° N, 90° V, 180° S, 270° E; nu față/spate. "
            "Eroarea poziției este necunoscută. Sondele nu acoperă spațiul dintre ele ori volumul corpului.\n"
            "Limite/deschideri absente nu înseamnă lipsa obstacolelor. "
            "Entități mobile: neobservate de acest canal. Nicio autorizare de mers."
        )
        if not probes:
            notes += "\nDetaliile sondelor nu sunt disponibile în acest raport."
        if height_scan:
            notes += "\nScanare la 4 înălțimi față de Z estimat; între raze și înălțimi rămâne spațiu neverificat."
        else:
            notes += (
                "\nScanarea la mai multe înălțimi nu este disponibilă în acest raport."
            )
        if (
            any(
                record.get(f) is True
                for f in (
                    "boundary_set_truncated",
                    "component_truncated",
                    "openings_truncated",
                )
            )
            or record.get("egress_inference_complete") is not True
        ):
            notes += "\nGeometrie/treceri parțiale: lista nu este exhaustivă."
        return SonarDetails(
            sonar_display(record, labels=labels, now_s=now_s)
            + "\n"
            + environment_display(labels.get("api_environment"))
            + f"\nVârsta poziției folosite: {age:.1f} s",
            tuple(rows),
            notes + "\n" + wmo_notes + "\n" + transition_notes,
        )
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        return unavailable
