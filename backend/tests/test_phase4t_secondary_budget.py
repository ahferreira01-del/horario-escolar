"""Fase 4T: orçamento secundário de CP-SAT por chamada, sem ativar na API."""
from copy import deepcopy
import json
import os
import platform
from time import perf_counter
import warnings

import pytest

from app.solver_preview import all_grid, validate_solution
from app.solver_controlled import controlled_preview
from app.solver_cpsat import CPSAT
from app.solver_scenarios_4p import build_feasible_scenario, feasible_reference_assignments
from test_phase4o_cpsat_parity import _dataset


@pytest.mark.parametrize("bad", [0,-1,16,True,False,2.0,"6",None if False else []])
def test_invalid_secondary_budgets_are_rejected_before_solver(bad):
    with pytest.raises(ValueError,match="Limite secundário"):
        all_grid(_dataset(),engine="cpsat",secondary_time_limit=bad)
    with pytest.raises(ValueError,match="Limite secundário"):
        controlled_preview(_dataset(),engine="cpsat",enable_experimental=True,
                           secondary_time_limit=bad)


def test_budget_cannot_change_milp_behavior():
    with pytest.raises(ValueError,match="Limite secundário"):
        all_grid(_dataset(),engine="milp",secondary_time_limit=4)
    with pytest.raises(ValueError,match="Limite secundário"):
        controlled_preview(_dataset(),secondary_time_limit=4)


def test_cp_sat_still_requires_explicit_activation():
    with pytest.raises(PermissionError,match="desativado"):
        controlled_preview(_dataset(),engine="cpsat",secondary_time_limit=6)


def test_secondary_budget_only_applies_to_second_solver_stage(monkeypatch):
    data=_dataset()
    data["time_limit"]=2
    budgets=[]
    original=CPSAT.solve
    def spy(self,costs,time_limit):
        budgets.append(time_limit)
        return original(self,costs,time_limit)
    monkeypatch.setattr(CPSAT,"solve",spy)
    result=controlled_preview(data,engine="cpsat",enable_experimental=True,
                              secondary_time_limit=6)
    assert budgets==[2,6],budgets
    assert result["result"]=="complete"
    assert result["engine_control"]["secondary_time_limit"]==6
    assert result["engine_control"]["fallback_used"] is False
    assert validate_solution(data,result["assignments"])==[]


def test_quality_benchmark_100_classes_budgets_2_vs_8_seconds(record_property):
    """Registra os resultados, sem supor monotonicidade sob busca paralela."""
    data=build_feasible_scenario(100,time_limit=2)
    witness=feasible_reference_assignments(data)
    assert len(witness)==200
    assert validate_solution(data,witness)==[]
    measures=[]
    for budget in (2,8):
        started=perf_counter()
        result=all_grid(deepcopy(data),engine="cpsat",secondary_time_limit=budget)
        errors=validate_solution(data,result["assignments"])
        assert errors==[],(budget,errors)
        assert result["result"]=="complete",(budget,result)
        assert result["total_required"]==result["total_assigned"]==200
        assert result["coverage_proven_optimal"]
        metrics=result["teacher_metrics"]
        days=sum(v["working_days"] for v in metrics.values())
        gaps=sum(v["gap_periods"] for v in metrics.values())
        shifts=sum(v["additional_shifts"] for v in metrics.values())
        weights=result["weights"]
        # As fixtures não têm avoid_days; custo secundário é diretamente
        # ponderável sem identificadores de docente, turma ou escola.
        score=days*weights["days"]+gaps*weights["gaps"]+shifts*weights["shifts"]
        measures.append({
            "secondary_seconds_budget":budget,
            "elapsed_total_seconds":round(perf_counter()-started,3),
            "status":result["solver_status"],
            "assigned":result["total_assigned"],
            "days":days,"gaps":gaps,"additional_shifts":shifts,
            "weighted_secondary_cost":score
        })
    payload={"runner":platform.platform(),"cpu_count":os.cpu_count(),
             "classes":100,"lessons":200,"coverage_seconds_budget":2,
             "profiles":"equilibrado","measurements":measures}
    evidence=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    record_property("fase4t_secondary_budget_evidence",evidence)
    warnings.warn("FASE4T_SECONDARY_BUDGET_EVIDENCE "+evidence,UserWarning,stacklevel=1)
