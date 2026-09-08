import ast
from pathlib import Path

import pytest

from perfect_assassin.movement.trace_evidence import control_cycle_timing_record


def test_refresh_does_not_hide_time_before_replaced_decision_sample():
    result = control_cycle_timing_record(
        previous_observed_s=100, decision_observed_s=100.267,
        post_observed_s=100.354, checkpoints=[('loop_entry',100.002),('planning',100.24)])
    assert result['post_to_post_ms'] == pytest.approx(354)
    assert result['before_decision_sample_ms'] == pytest.approx(267)
    assert result['decision_to_post_ms'] == pytest.approx(87)
    assert result['stage_wall_ms']['planning'] == pytest.approx(238)
    assert result['execution_authority'] is False


def test_normal_frame_has_zero_hidden_interval_and_copies_checkpoints():
    marks = [('entry',1),('input',1.005)]
    result = control_cycle_timing_record(previous_observed_s=1,decision_observed_s=1,
                                        post_observed_s=1.05,checkpoints=marks)
    marks.append(('later',2))
    assert result['before_decision_sample_ms'] == 0
    assert result['post_to_post_ms'] == pytest.approx(50)
    assert 'later' not in result['stage_wall_ms']


@pytest.mark.parametrize('marks', [[('a',0.9)],[('a',1),('a',1.1)], [('a',float('nan'))]])
def test_bad_checkpoint_evidence_is_rejected(marks):
    with pytest.raises(ValueError):
        control_cycle_timing_record(previous_observed_s=1,decision_observed_s=1,
                                    post_observed_s=1.2,checkpoints=marks)


def test_runner_keeps_previous_sample_before_refresh_and_exports_timing():
    path = Path(__file__).resolve().parents[1] / 'integrations/windows-input/run_navmesh_roaming.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    loops = [n for n in ast.walk(tree) if isinstance(n,ast.While)
             and 'control_frames' in ast.unparse(n.test)]
    assert len(loops) == 1
    loop=loops[0]
    assert ast.unparse(loop.body[0]) == 'cycle_previous_observed_s = last_observed_s'
    calls=[n for n in ast.walk(loop) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Name) and n.func.id=='control_cycle_timing_record']
    assert len(calls)==1
    args={k.arg:ast.unparse(k.value) for k in calls[0].keywords}
    assert args['previous_observed_s']=='cycle_previous_observed_s'
    assert args['post_observed_s']=='observed_s'
    assert args['decision_observed_s']=="decision_observation['observed_monotonic_s']"
