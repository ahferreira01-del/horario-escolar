#!/usr/bin/env python3
"""Fase 4R: benchmark MILP vs CP-SAT com solução integral *comprovada*.

Usa apenas fixture fictícia e uma grade construtiva validada como testemunha.
Compara cobertura, qualidade aproximada e tempo; não habilita API/produção.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "backend"))

from app.solver_preview import all_grid, validate_solution
from app.solver_scenarios_4p import build_feasible_scenario, feasible_reference_assignments
from benchmark_solver_fase4p import parse_sizes


def run_feasible_benchmark(sizes: list[int], time_limit: int, profile: str = "equilibrado") -> dict:
    if profile not in ("equilibrado", "menos_dias", "menos_janelas"):
        raise ValueError("Perfil inválido.")
    cases=[]
    any_invalid=False
    for count in sizes:
        data=build_feasible_scenario(count,time_limit=time_limit)
        data["profile"]=profile
        witness=feasible_reference_assignments(data)
        witness_errors=validate_solution(data,witness)
        if len(witness)!=2*count or witness_errors:
            raise RuntimeError("Fixture indicada como viável não possui testemunha validada: "+str(witness_errors))
        outcomes=[]
        for engine in ("milp","cpsat"):
            started=perf_counter()
            try:
                result=all_grid(deepcopy(data),engine=engine)
                elapsed=round(perf_counter()-started,3)
                status=result.get("result")
                assignments=result.get("assignments")
                errors=validate_solution(data,assignments) if isinstance(assignments,list) else ["Aulas ausentes"]
                assigned=result.get("total_assigned",0)
                valid=(status in ("complete","partial","unsolved")
                       and not errors and isinstance(assigned,int)
                       and 0<=assigned<=2*count
                       and (status!="unsolved" or not assignments))
                metrics=result.get("teacher_metrics",{})
                quality={
                    "teacher_working_days":sum(t["working_days"] for t in metrics.values()),
                    "gap_periods":sum(t["gap_periods"] for t in metrics.values()),
                    "additional_shifts":sum(t["additional_shifts"] for t in metrics.values())
                } if valid and status!="unsolved" else None
                entry={
                    "engine":engine,
                    "elapsed_seconds":elapsed,
                    "result":status,
                    "solver_status":result.get("solver_status"),
                    "coverage_proven_optimal":result.get("coverage_proven_optimal",False),
                    "total_assigned":assigned,
                    "total_required":2*count,
                    "full_coverage":valid and assigned==2*count and status=="complete",
                    "quality_metrics":quality,
                    "validation_ok":valid,
                    "validation_errors":errors
                }
                any_invalid |= not valid
            except Exception as exc:
                any_invalid=True
                entry={
                    "engine":engine,
                    "elapsed_seconds":round(perf_counter()-started,3),
                    "validation_ok":False,
                    "error":type(exc).__name__+": "+str(exc)
                }
            outcomes.append(entry)
        same_coverage=(all(x.get("validation_ok") and x.get("result") in ("complete","partial")
                           for x in outcomes)
                       and outcomes[0]["total_assigned"]==outcomes[1]["total_assigned"])
        cases.append({
            "classes":count,"schools":2,"teachers":count//2,
            "required_lessons":2*count,
            "witness_complete_and_valid":True,
            "lab_centro_max_groups":data["resources"]["Lab_Centro"]["max_groups"],
            "same_coverage":same_coverage,
            "results":outcomes
        })
    return {
        "purpose":"benchmark exploratório em cenários viáveis, NÃO é SLA",
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version.split()[0],
        "scipy":version("scipy"),
        "ortools":version("ortools"),
        "profile":profile,
        "time_limit_per_stage_seconds":time_limit,
        "any_invalid":any_invalid,
        "cases":cases
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes",type=parse_sizes,default=[24,48,100])
    parser.add_argument("--time-limit",type=int,default=2)
    parser.add_argument("--profile",choices=["equilibrado","menos_dias","menos_janelas"],default="equilibrado")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not 1<=args.time_limit<=15:
        parser.error("--time-limit precisa estar entre 1 e 15 segundos.")
    result=run_feasible_benchmark(args.sizes,args.time_limit,args.profile)
    data=json.dumps(result,ensure_ascii=False,indent=2)
    print(data)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(data+"\n",encoding="utf-8")
    if result["any_invalid"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
