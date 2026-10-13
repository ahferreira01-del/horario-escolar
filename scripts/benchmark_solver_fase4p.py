#!/usr/bin/env python3
"""Fase 4P: benchmark controlado CP-SAT versus MILP em dados fictícios.

Não inclui dados reais de escolas, não altera serviços/bancos e não é SLA.
Exemplo:
  python scripts/benchmark_solver_fase4p.py --sizes 8,12,24 --time-limit 5 \
    --output evidencias/benchmark-4p.json
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "backend"))

from app.solver_preview import all_grid, validate_solution
from app.solver_scenarios_4p import build_scenario


def parse_sizes(raw: str) -> list[int]:
    try:
        parsed=[int(v.strip()) for v in raw.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Informe números pares separados por vírgulas.") from exc
    if not parsed or len(parsed)>5 or len(set(parsed))!=len(parsed) or any(
            v<2 or v>100 or v%2 for v in parsed):
        raise argparse.ArgumentTypeError(
            "Informe até 5 tamanhos distintos e pares, entre 2 e 100 turmas.")
    return parsed


def run_benchmark(sizes: list[int], time_limit: int) -> dict:
    cases=[]
    any_invalid=False
    for size in sizes:
        data=build_scenario(size,time_limit=time_limit)
        result_set=[]
        for engine in ("milp","cpsat"):
            started=perf_counter()
            try:
                result=all_grid(deepcopy(data),engine=engine)
                elapsed=round(perf_counter()-started,3)
                errors=validate_solution(data,result.get("assignments",[]))
                total=result.get("total_assigned",0)
                status=result.get("result","unknown")
                valid=status in ("complete","partial","unsolved") and not errors
                if status=="unsolved" and result.get("assignments"):
                    valid=False
                report={
                    "engine":engine,"elapsed_seconds":elapsed,
                    "result":status,"solver_status":result.get("solver_status"),
                    "coverage_proven_optimal":result.get("coverage_proven_optimal",False),
                    "total_assigned":total,
                    "total_required":2*size,
                    "validation_ok":valid,
                    "validation_errors":errors,
                }
                any_invalid |= not valid
            except Exception as exc:
                any_invalid=True
                report={"engine":engine,"elapsed_seconds":round(perf_counter()-started,3),
                        "validation_ok":False,"error":type(exc).__name__ + ": " + str(exc)}
            result_set.append(report)
        comparable=all(x.get("validation_ok") for x in result_set)
        cases.append({
            "schools":2,"classes":size,"teachers":size//2,
            "required_lessons":2*size,"profile":"equilibrado",
            "comparable_coverage":comparable and result_set[0].get("total_assigned")==result_set[1].get("total_assigned"),
            "results":result_set,
        })
    return {
        "purpose":"benchmark experimental; não certifica desempenho de produção",
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version.split()[0],
        "scipy":version("scipy"),
        "ortools":version("ortools"),
        "time_limit_per_solver_stage_seconds":time_limit,
        "any_invalid":any_invalid,
        "cases":cases,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes",type=parse_sizes,default=[8,12,24])
    parser.add_argument("--time-limit",type=int,default=5)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not 1 <= args.time_limit <= 15:
        parser.error("--time-limit deve estar entre 1 e 15 segundos.")
    outcome=run_benchmark(args.sizes,args.time_limit)
    rendered=json.dumps(outcome,indent=2,ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered + "\n",encoding="utf-8")
    if outcome["any_invalid"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
