"""Fase 4S — as dicas de CP-SAT aceleram busca, nunca autorizam violação.

Os testes fixam contrato e garantia da solução. A comparação de qualidade
pedagógica em 100 turmas é feita pelos benchmarks reais da Fase 4R.
"""
import pytest

from app.solver_cpsat import CPSAT
from app.solver_preview import all_grid,validate_solution
from test_phase4o_cpsat_parity import _dataset


def test_hints_are_never_constraints():
    model=CPSAT()
    first=model.var("first")
    second=model.var("second")
    model.add({first:1,second:1},high=1)
    model.set_solution_hints({first:1,second:1}) # dica propositalmente inviável
    solution=model.solve({first:-1,second:-2},time_limit=2)
    assert solution.status==0
    assert solution.x.tolist()==[0.0,1.0]


@pytest.mark.parametrize(("index","value"),[
    (-1,1),(2,1),(0,2),(0,-1),(0,0.5),(0,True),("0",1)
])
def test_hints_refuse_invalid_indices_and_values(index,value):
    model=CPSAT()
    model.var("first")
    with pytest.raises(ValueError,match="Dica CP-SAT|Índice inválido"):
        model.set_solution_hints({index:value})
    assert model.solution_hints=={}


def test_cpsat_second_stage_hints_preserve_cover_and_grade_integrity():
    data=_dataset()
    result=all_grid(data,engine="cpsat")
    assert result["result"]=="complete",result
    assert result["total_assigned"]==2
    assert result["coverage_proven_optimal"] is True
    assert validate_solution(data,result["assignments"])==[]


def test_hint_calls_do_not_persist_between_models():
    a=CPSAT()
    i=a.var("a")
    a.set_solution_hints({i:1})
    assert a.solution_hints=={0:1}
    b=CPSAT()
    b.var("b")
    assert b.solution_hints=={}
