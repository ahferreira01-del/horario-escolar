"""Fase 4R — escolas sem escassez estrutural; dois solvers medidos no CI.

Prova a viabilidade por uma grade independente dos otimizadores e mede os
resultados de cada motor com limite de 2 segundos por etapa de otimização.
"""
import json
import os
import platform
import sys
import warnings
from pathlib import Path

import pytest

from app.solver_preview import validate_solution
from app.solver_scenarios_4p import build_feasible_scenario, feasible_reference_assignments

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from benchmark_solver_fase4r import run_feasible_benchmark


@pytest.mark.parametrize("size,groups",[(24,2),(48,3),(100,5)])
def test_full_feasibility_has_independent_constructive_witness(size,groups):
    data=build_feasible_scenario(size,time_limit=2)
    assert data["resources"]["Lab_Centro"]["max_groups"]==groups
    witness=feasible_reference_assignments(data)
    assert len(witness)==2*size
    assert validate_solution(data,witness)==[]
    assert set(a["class_id"] for a in witness)==set(data["classes"])
    assert len({a["teacher"] for a in witness})==size//2


def test_real_milp_cpsat_benchmark_feasible_24_48_100_in_ci(record_property):
    report=run_feasible_benchmark([24,48,100],2)
    assert report["any_invalid"] is False,report
    assert [c["classes"] for c in report["cases"]]==[24,48,100]
    for case in report["cases"]:
        assert case["witness_complete_and_valid"]
        assert len(case["results"])==2
        assert {r["engine"] for r in case["results"]}=={"milp","cpsat"}
        for item in case["results"]:
            assert item["validation_ok"],(case["classes"],item)
            assert item["result"] in ("complete","partial"),(case["classes"],item)
            assert 0<item["total_assigned"]<=item["total_required"]
            assert item["quality_metrics"] is not None
            assert item["elapsed_seconds"]>=0
    details={
        "runner":platform.platform(),
        "cpu_count":os.cpu_count(),
        "python":report["python"],
        "scipy":report["scipy"],
        "ortools":report["ortools"],
        "profile":report["profile"],
        "time_limit_per_stage_seconds":2,
        "cases":[{
            "classes":case["classes"],
            "witness_valid":case["witness_complete_and_valid"],
            "lab_groups":case["lab_centro_max_groups"],
            "same_coverage":case["same_coverage"],
            "engines":[{
                "engine":r["engine"],
                "seconds":r["elapsed_seconds"],
                "assigned":r["total_assigned"],
                "required":r["total_required"],
                "full":r["full_coverage"],
                "solver_status":r["solver_status"],
                "coverage_proven_optimal":r["coverage_proven_optimal"],
                "quality_metrics":r["quality_metrics"]
            } for r in case["results"]]
        } for case in report["cases"]]
    }
    evidence=json.dumps(details,ensure_ascii=False,separators=(",",":"))
    record_property("fase4r_benchmark_evidence",evidence)
    warnings.warn("FASE4R_BENCHMARK_EVIDENCE "+evidence,UserWarning,stacklevel=1)
