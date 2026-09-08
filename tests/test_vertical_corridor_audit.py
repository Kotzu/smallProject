import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from perfect_assassin.movement.client_navmesh import NavPoint

spec = importlib.util.spec_from_file_location("vertical_corridor_audit",
    Path(__file__).resolve().parents[1] / "tools/audit_vertical_corridors.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def corridor(complete=True):
    return SimpleNamespace(start=NavPoint(0, 0, 10.5), stop=NavPoint(3, 4, 10.5),
        points=(NavPoint(0, 0, 10.5), NavPoint(3, 4, 10.5)), complete=complete,
        topology_gap_direct_shortcut_applied=False, doodad_unresolved_segment_count=0)


def test_snap_displacement_and_path_length_remain_explicit():
    result = module.describe_corridor(corridor(), NavPoint(0, 0, 10), NavPoint(3, 4, 10), 1)
    assert result["path_length_yards"] == 5
    assert result["start_displacement_yards"] == .5
    assert result["stop_displacement_yards"] == .5
    assert result["observed_actor_z"] is None
    assert result["floor_id"] is None
    assert result["execution_authority"] is False


def test_incomplete_route_and_shortcut_are_not_hidden():
    source = corridor(False)
    source.topology_gap_direct_shortcut_applied = True
    result = module.describe_corridor(source, NavPoint(0, 0, 10), NavPoint(30, 40, 10), 1)
    assert result["complete"] is False
    assert result["topology_shortcut"] is True
    assert result["stop_displacement_yards"] > 40


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_invalid_time_interval(seconds):
    with pytest.raises(ValueError):
        module.describe_corridor(corridor(), NavPoint(0, 0, 10), NavPoint(3, 4, 10), seconds)
