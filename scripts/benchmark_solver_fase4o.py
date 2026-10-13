#!/usr/bin/env python3
"""Benchmark manual e reproduzível de MILP/HiGHS x CP-SAT.

NÃO é teste de carga nem atestado de viabilidade em produção.
Usa apenas dados fictícios do repositório, jamais bancos reais.
Executar: python scripts/benchmark_solver_fase4o.py --time-limit 8
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.solver_preview import all_grid, validate_solution


def main():
    parser = argparse.ArgumentParser(description="Comparação experimental de motores")
    parser.add_argument("--input", type=Path,
                        default=ROOT / "solver_poc_v0_2" / "exemplo_duas_escolas.json")
    parser.add_argument("--time-limit", type=int, default=8, choices=range(1, 16),
                        metavar="[1-15]")
    parser.add_argument("--output", type=Path, default=None,
                        help="Opcional: caminho para salvar evidência JSON")
    args = parser.parse_args()
    source = args.input.resolve()
    if not source.is_file():
        raise SystemExit("Arquivo de teste não encontrado: " + str(source))
    data = json.loads(source.read_text(encoding="utf-8"))
    data["time_limit"] = args.time_limit

    results = []
    for engine in ("milp", "cpsat"):
        start = perf_counter()
        try:
            result = all_grid(copy.deepcopy(data), engine=engine)
            errors = validate_solution(data, result["assignments"])
            report = {
                "engine": engine,
                "elapsed_seconds": round(perf_counter() - start, 3),
                "result": result["result"],
                "solver_status": result.get("solver_status"),
                "coverage_proven_optimal": result.get("coverage_proven_optimal"),
                "total_assigned": result["total_assigned"],
                "total_required": result["total_required"],
                "pending_demands": len(result.get("pending", [])),
                "independent_validation_errors": errors,
            }
            results.append(report)
            if errors:
                raise RuntimeError("Inconsistência no validador independente: " + str(errors))
        except Exception as exc:
            results.append({
                "engine": engine,
                "elapsed_seconds": round(perf_counter() - start, 3),
                "error": str(exc),
            })
    payload = {
        "purpose": "benchmark exploratorio; sem homologacao de escala",
        "input": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "time_limit_per_stage_seconds": args.time_limit,
        "results": results,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if any("error" in item for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
