"""Fase 4Q: explicar o limite matemático de cobertura do benchmark sintético.

Este limite vale SOMENTE para a fixture de 4P/4Q: duas escolas, cinco dias,
dois períodos por dia, um laboratório Centro com max_groups=1 e apenas
turmas de índice múltiplo de 4 exigindo esse recurso.
"""
import pytest

from app.solver_scenarios_4p import build_scenario


@pytest.mark.parametrize(("size","expected_max"), [
    (12,24),(24,46),(48,82),(100,160),
])
def test_expected_lab_capacity_bottleneck(size,expected_max):
    data=build_scenario(size,time_limit=2)
    lab=data["resources"]["Lab_Centro"]
    assert lab["max_groups"]==1
    school_slots={
        (slot["day"],slot["start"],slot["end"])
        for cls in data["classes"].values()
        if cls["school_id"]=="Centro"
        for slot in cls["slots"]
    }
    eligible={
        key for key in school_slots
        if any(interval["day"]==key[0]
               and interval["start"]<=key[1] and key[2]<=interval["end"]
               for interval in lab["availability"])
    }
    assert len(eligible)==10
    demand=sum(row["lessons"] for row in data["demands"]
               if row.get("resource_id")=="Lab_Centro")
    total=sum(row["lessons"] for row in data["demands"])
    unavoidable_shortage=max(0,demand-len(eligible)*lab["max_groups"])
    assert total-unavoidable_shortage==expected_max
