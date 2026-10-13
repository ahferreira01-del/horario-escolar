"""Fase 4P: validação sintética controlada sem inventar limites de SLA."""
from copy import deepcopy

import pytest

from app.solver_preview import all_grid, validate_solution
from app.solver_scenarios_4p import build_scenario


@pytest.mark.parametrize("size",[2,8,12])
def test_deterministic_school_fixture_structure(size):
    data=build_scenario(size,time_limit=4)
    assert len(data["classes"])==size
    assert len(data["teachers"])==size//2
    assert len(data["demands"])==size
    assert sum(d["lessons"] for d in data["demands"])==size*2
    assert set(data["schools"])=={"Centro","Norte"}
    for teacher in data["teachers"]:
        linked={data["classes"][d["class_id"]]["school_id"]
                for d in data["demands"] if d["teacher_id"]==teacher}
        assert linked=={"Centro","Norte"}
    assert data==build_scenario(size,time_limit=4)


@pytest.mark.parametrize("invalid",[0,1,3,101,True,10.0])
def test_refuse_invalid_fixture_sizes(invalid):
    with pytest.raises(ValueError):
        build_scenario(invalid)


def test_comparable_multischool_twelve_classes_milp_and_cpsat():
    """24 aulas em 12 turmas, professores compartilhados e lab. Não é SLA."""
    data=build_scenario(12,time_limit=5)
    runs={}
    for engine in ("milp","cpsat"):
        result=all_grid(deepcopy(data),engine=engine)
        assert result["result"]=="complete",(engine,result)
        assert result["total_assigned"]==result["total_required"]==24,(engine,result)
        assert result["conflicts"]==0,(engine,result)
        assert result["coverage_proven_optimal"],(engine,result)
        assert validate_solution(data,result["assignments"])==[],(engine,result)
        runs[engine]=result
    assert {d["class_id"] for d in runs["milp"]["assignments"]}==set(data["classes"])
    assert {d["class_id"] for d in runs["cpsat"]["assignments"]}==set(data["classes"])
