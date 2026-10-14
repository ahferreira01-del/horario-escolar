"""Fase 4Q — medição real, limitada e reproduzível no CI.

Cenários sintéticos de 24/48/100 turmas; cada motor recebe até 2 segundos
POR etapa de otimização, mais tempo de montagem/validação. Não é SLA.
As métricas aparecem também no JUnit e no resumo de avisos do pytest para
que cada GitHub Actions run comprove a execução efetiva.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import warnings
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))

from benchmark_solver_fase4p import parse_sizes, run_benchmark


def test_synthetic_benchmark_24_48_100_classes_in_real_ci(record_property):
    sizes=[24,48,100]
    report=run_benchmark(sizes,2)
    assert [item["classes"] for item in report["cases"]]==sizes
    assert report["any_invalid"] is False,report
    assert all(len(item["results"])==2 for item in report["cases"])
    assert all({x["engine"] for x in item["results"]}=={"milp","cpsat"}
               for item in report["cases"])
    assert all(r["validation_ok"] for item in report["cases"]
               for r in item["results"]),report
    assert all(r["total_assigned"]<=r["total_required"]
               for item in report["cases"] for r in item["results"])
    assert all(r["elapsed_seconds"]>=0 for item in report["cases"]
               for r in item["results"])

    compact={
        "runner":platform.platform(),
        "cpu_count":os.cpu_count(),
        "python":report["python"],
        "scipy":report["scipy"],
        "ortools":report["ortools"],
        "time_limit_per_solver_stage_seconds":2,
        "cases":[{
            "classes":c["classes"],
            "same_coverage":c["comparable_coverage"],
            "engines":[{
                "engine":r["engine"],
                "seconds":r["elapsed_seconds"],
                "assigned":r["total_assigned"],
                "required":r["total_required"],
                "result":r["result"],
                "solver_status":r["solver_status"],
                "coverage_proven_optimal":r["coverage_proven_optimal"]
            } for r in c["results"]]
        } for c in report["cases"]]
    }
    evidence=json.dumps(compact,ensure_ascii=False,separators=(",",":"))
    record_property("fase4q_benchmark_evidence",evidence)
    # O GitHub Actions usa pytest -q: stdout normal ficaria oculto.
    # Aviso intencional preserva a medição no log do job aprovado.
    warnings.warn("FASE4Q_BENCHMARK_EVIDENCE "+evidence,UserWarning,stacklevel=1)


def test_benchmark_rejects_invalid_sizes_and_duplicate_measurements():
    import argparse
    for text in ("1","3","0","102","24,24","24,48,100,12,16,8","foo","24,"):
        try:
            parse_sizes(text)
        except argparse.ArgumentTypeError:
            continue
        raise AssertionError("Parâmetro de benchmark inválido aceito: "+text)
    assert parse_sizes("24,48,100")==[24,48,100]
