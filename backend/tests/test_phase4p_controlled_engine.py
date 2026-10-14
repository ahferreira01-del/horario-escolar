"""Fase 4P: opt-in, validação e rollback experimental sem tocar nos endpoints."""
from copy import deepcopy

import pytest
from app import solver_controlled
from app.solver_controlled import controlled_preview
from app.solver_preview import validate_solution
from test_phase4o_cpsat_parity import _dataset


def test_default_is_milp_and_does_not_require_any_opt_in():
    data=_dataset()
    got=controlled_preview(data)
    assert got["result"]=="complete"
    assert got["engine_control"]["requested"]=="milp"
    assert got["engine_control"]["executed"]=="milp"
    assert got["engine_control"]["fallback_used"] is False
    assert validate_solution(data,got["assignments"])==[]


def test_cpsat_explicitly_denied_by_default():
    with pytest.raises(PermissionError,match="desativado"):
        controlled_preview(_dataset(),engine="cpsat")


def test_explicit_cpsat_with_independent_validation():
    data=_dataset()
    got=controlled_preview(data,engine="cpsat",enable_experimental=True)
    assert got["result"]=="complete"
    assert got["engine_control"]["executed"]=="cpsat"
    assert got["engine_control"]["fallback_used"] is False
    assert validate_solution(data,got["assignments"])==[]


def test_unknown_engine_rejected_before_execution():
    with pytest.raises(ValueError,match="inválido"):
        controlled_preview(_dataset(),engine="desconhecido")


def test_fallback_flag_not_allowed_for_milp():
    with pytest.raises(ValueError,match="só se aplica"):
        controlled_preview(_dataset(),engine="milp",fallback_on_unsolved=True)


def test_cpsat_unsolved_no_implicit_rollback(monkeypatch):
    calls=[]
    def fake(data,*,engine):
        calls.append(engine)
        return {"result":"unsolved","assignments":[],"solver_status":"UNKNOWN"}
    monkeypatch.setattr(solver_controlled,"all_grid",fake)
    got=controlled_preview(_dataset(),engine="cpsat",enable_experimental=True)
    assert got["result"]=="unsolved"
    assert calls==["cpsat"]
    assert got["engine_control"]["fallback_used"] is False


def test_cpsat_unsolved_explicitly_rolls_back_to_milp(monkeypatch):
    real=solver_controlled.all_grid
    calls=[]
    def fake(data,*,engine):
        calls.append(engine)
        if engine=="cpsat":
            return {"result":"unsolved","assignments":[],"solver_status":"UNKNOWN"}
        return real(data,engine=engine)
    monkeypatch.setattr(solver_controlled,"all_grid",fake)
    data=_dataset()
    result=controlled_preview(data,engine="cpsat",enable_experimental=True,
                              fallback_on_unsolved=True)
    assert calls==["cpsat","milp"]
    assert result["result"]=="complete"
    assert result["engine_control"]["fallback_used"] is True
    assert result["engine_control"]["fallback_reason"]=="experimental_unsolved"
    assert result["engine_control"]["executed"]=="milp"
    assert validate_solution(data,result["assignments"])==[]


def test_invalid_cpsat_assignments_never_fallback(monkeypatch):
    calls=[]
    def fake(data,*,engine):
        calls.append(engine)
        return {"result":"complete","assignments":[{
            "class_id":"A","school_id":"Centro","subject":"inventada",
            "teacher":"Ana","day":"Seg","order":1,
            "start":"08:00","end":"08:45","shift":"manha","resource_id":None,
            "students":25
        }]}
    monkeypatch.setattr(solver_controlled,"all_grid",fake)
    with pytest.raises(RuntimeError,match="verificador independente"):
        controlled_preview(_dataset(),engine="cpsat",enable_experimental=True,
                           fallback_on_unsolved=True)
    assert calls==["cpsat"]


@pytest.mark.parametrize("invalid_result",[
    None, {}, {"result":"unknown","assignments":[]},
    {"result":"unsolved","assignments":[{"invalid":"row"}]},
])
def test_invalid_solver_contract_rejected_without_fallback(monkeypatch,invalid_result):
    calls=[]
    def fake(data,*,engine):
        calls.append(engine)
        return deepcopy(invalid_result)
    monkeypatch.setattr(solver_controlled,"all_grid",fake)
    with pytest.raises(RuntimeError):
        controlled_preview(_dataset(),engine="cpsat",enable_experimental=True,
                           fallback_on_unsolved=True)
    assert calls==["cpsat"]


def test_solver_exception_never_silently_retried(monkeypatch):
    calls=[]
    def fake(data,*,engine):
        calls.append(engine)
        raise ValueError("Entrada inválida")
    monkeypatch.setattr(solver_controlled,"all_grid",fake)
    with pytest.raises(ValueError,match="Entrada inválida"):
        controlled_preview(_dataset(),engine="cpsat",enable_experimental=True,
                           fallback_on_unsolved=True)
    assert calls==["cpsat"]
