from copy import deepcopy

import pytest
from test_spatial_sonar import labels, record
from test_wmo_bundle import build, context  # noqa: F401 - shared synthetic fixture

from perfect_assassin.adapter.sonar_details import sonar_details
from perfect_assassin.adapter.vertical_candidates import VerticalSurfaceCandidates
from perfect_assassin.adapter.wmo_presentation import wmo_presentation


@pytest.fixture
def evidence(context):  # noqa: F811 - pytest fixture injection
    bundle, _ = build(context)
    candidates = VerticalSurfaceCandidates((0.0, 20.0), 20.0)
    r = record()
    r["vertical_candidates"] = candidates.to_record()
    r["wmo_surface_association"] = bundle.query(
        map_id=0, xy=(0, 0), candidates=candidates
    )
    r["wmo_surface_error"] = None
    return r


def test_real_bundle_packet_renders_matches_missing_coverage_and_retained_alternatives(
    evidence,
):
    rows, notes = wmo_presentation(evidence)
    assert len(rows) == 2
    assert "potriviri" in rows[0][3]
    assert "În afara segmentului" in rows[1][3]
    assert all("etaj neconfirmat" in row[3] for row in rows)
    assert "1/2 instanțe" in notes and "0:wmo:1" in notes
    model = sonar_details(evidence, labels=labels(), now_s=10.5)
    assert model.rows[:2] == rows
    assert "acoperire parțială" in model.notes
    assert "Etaj neconfirmat" in model.status
    assert not sonar_details(evidence, labels=labels(), now_s=14).rows
    assert not sonar_details(
        evidence, labels={**labels(), "session_tag": 456}, now_s=10.5
    ).rows


@pytest.mark.parametrize(
    "field,value",
    [
        ("map_id", 1),
        ("map_id", False),
        ("world_pack_sha256", "b" * 64),
        ("query_xy", [0.2, 0]),
        ("execution_authority", True),
        ("confirmed_floor_id", 4),
        ("coverage", "ALL_WORLD"),
        ("loaded_model_count", True),
        ("bundle_sha256", "wrong"),
        ("column_wmo_count", 0),
        ("terrain_and_doodads_checked", True),
    ],
)
def test_malformed_or_foreign_optional_evidence_does_not_suppress_base_sonar(
    evidence, field, value
):
    evidence["wmo_surface_association"][field] = value
    rows, note = wmo_presentation(evidence)
    assert rows == () and "invalidă" in note
    model = sonar_details(evidence, labels=labels(), now_s=10.5)
    assert len(model.rows) == 17


@pytest.mark.parametrize(
    "mutation", ["height", "match", "status", "infinite", "discard", "selected"]
)
def test_candidate_evidence_cannot_select_floor_or_invent_triangle_match(
    evidence, mutation
):
    association = evidence["wmo_surface_association"]["structures"][0]["association"]
    c = association["candidates"][0]
    if mutation == "height":
        c["candidate_z"] = 1
    elif mutation == "match":
        c["matches"][0]["surface_z"] = 30
    elif mutation == "status":
        c["status"] = "NO_WMO_MATCH"
    elif mutation == "infinite":
        association["segment_z"][1] = float("inf")
    elif mutation == "discard":
        c["candidate_retained"] = False
    else:
        association["selected_surface_z_unchanged"] = 0
    assert "invalidă" in wmo_presentation(evidence)[1]


def test_disabled_error_and_empty_column_never_claim_open_world(evidence):
    assert "neactivată" in wmo_presentation(record())[1]
    failed = {**evidence, "wmo_surface_error": "private filesystem exception"}
    rows, notes = wmo_presentation(failed)
    assert rows == () and "private" not in notes and "indisponibilă" in notes
    e = evidence["wmo_surface_association"]
    e.update(structures=[], uncovered_structure_ids=[], column_wmo_count=0)
    assert "nu înseamnă spațiu liber" in wmo_presentation(evidence)[1]


def test_display_rows_are_bounded_and_truncation_is_explicit(evidence):
    e = evidence["wmo_surface_association"]
    heights = list(range(64))
    evidence["vertical_candidates"]["heights"] = heights
    a = e["structures"][0]["association"]
    template = a["candidates"][1]
    a["candidates"] = []
    for i, height in enumerate(heights):
        c = deepcopy(template)
        c.update(
            candidate_index=i,
            candidate_z=height,
            status="NO_WMO_MATCH" if height <= 11 else "OUTSIDE_TESTED_SEGMENT",
        )
        a["candidates"].append(c)
    rows, note = wmo_presentation(evidence)
    assert len(rows) == 32 and "32/64" in note
