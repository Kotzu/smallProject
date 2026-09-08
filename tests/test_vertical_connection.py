import copy

import pytest

from perfect_assassin.adapter.vertical_connection import parse_connection


def record():
    return {"status":"OK", "sequence":7, "requested_start":[1,2,3], "requested_stop":[4,5,6],
            "resolved_start":[1,2,3.5], "resolved_stop":[4,5,6.2], "path_stop":[4,5,6.2],
            "start_poly":"281475225223196", "stop_poly":"281475224174616", "complete":True,
            "search_limited":False, "polygon_count":9, "point_count":2, "funnel_length_yards":6,
            "source":"CLIENT_NAVMESH_TOPOLOGY", "observed_actor_z":None, "floor_id":None,
            "execution_authority":False}


def parse(r):
    return parse_connection(r, sequence=7, start=(1,2,3), stop=(4,5,6))


def test_projection_and_non_authority_are_preserved():
    r=record(); original=copy.deepcopy(r)
    result=parse(r)
    assert result["start_projection_yards"] == .5
    assert result["stop_projection_yards"] == pytest.approx(.2)
    assert result["actor_transition_confirmed"] is False
    assert result["volumetric_clearance_checked"] is False
    assert r == original


@pytest.mark.parametrize("field,value", [("sequence",8), ("sequence",True),
    ("source","SERVER"), ("requested_start",[2,2,3]), ("requested_stop",[4,5,7]),
    ("resolved_stop",[4,float("inf"),6]), ("complete",1), ("point_count",513),
    ("polygon_count",0), ("start_poly",123), ("start_poly","-1"),
    ("stop_poly",str(2**64)), ("funnel_length_yards",-1), ("funnel_length_yards",float("nan")),
    ("floor_id","room"), ("observed_actor_z",6), ("execution_authority",True),
    ("path_stop",[5,5,6.2]), ("search_limited",True)])
def test_invalid_or_misbound_packet_rejected(field,value):
    r=record(); r[field]=value
    with pytest.raises(ValueError): parse(r)


def test_incomplete_search_remains_explicit():
    r=record(); r.update(complete=False,search_limited=True,path_stop=[2,3,4])
    result=parse(r)
    assert result["complete"] is False
    assert result["search_limited"] is True


def test_extra_and_missing_fields():
    r=record(); r["assume_floor"]=4
    with pytest.raises(ValueError): parse(r)
    del r["assume_floor"]; del r["resolved_start"]
    with pytest.raises(ValueError): parse(r)
