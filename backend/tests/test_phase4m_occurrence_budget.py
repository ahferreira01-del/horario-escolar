"""Fase 4M: orçamento de ocorrências antes da conversão de datas.

Um intervalo longo não deve consumir milhares de conversões timezone para
somente então falhar no limite global de publicação.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.publication import _events, MAX_OCCURRENCES


SCHOOLS={"centro":SimpleNamespace(timezone="America/Sao_Paulo")}


def lesson(weekday=0):
    return {
        "school_id":"centro", "class_id":"turma",
        "teacher_id":"prof", "resource_id":None, "students":25,
        "weekday":weekday,"start_minute":430,"end_minute":475,
    }


def test_exact_dates_and_weekly_recurrence():
    events=_events([lesson(0)], SCHOOLS, date(2028,2,7), date(2028,2,21))
    assert [e["date"].isoformat() for e in events]==[
        "2028-02-07", "2028-02-14", "2028-02-21"]
    assert all((e["end_utc"]-e["start_utc"]).total_seconds()==45*60 for e in events)


def test_date_range_single_day_and_no_match():
    monday=date(2028,2,7)
    assert len(_events([lesson(0)],SCHOOLS,monday,monday))==1
    assert _events([lesson(1)],SCHOOLS,monday,monday)==[]
    assert _events([lesson(0)],SCHOOLS,date(2028,2,9),monday)==[]


def test_budget_applied_before_timezone_conversion(monkeypatch):
    # Se o código tentar converter qualquer ocorrência antes de conferir a
    # soma do calendário, este stub faz o teste falhar imediatamente.
    import app.publication as publication
    def should_not_convert(*args):
        raise AssertionError("O orçamento deve falhar antes de converter datas")
    monkeypatch.setattr(publication, "_local_utc", should_not_convert)
    with pytest.raises(HTTPException) as err:
        _events([lesson(0),lesson(0)],SCHOOLS,date(2028,2,7),
                date(2028,2,7),max_events=1)
    assert err.value.status_code==422
    assert "ocorrências" in err.value.detail.lower()


def test_global_budget_rejects_large_year_before_expansion(monkeypatch):
    import app.publication as publication
    def should_not_convert(*args):
        raise AssertionError("A conversão não deve começar antes do orçamento")
    monkeypatch.setattr(publication,"_local_utc",should_not_convert)
    with pytest.raises(HTTPException,match="Quantidade elevada"):
        _events([lesson(0)]*500,SCHOOLS,date(2028,1,1),date(2028,12,31),
                max_events=MAX_OCCURRENCES)


def test_zero_budget_rejects_single_occurrence():
    with pytest.raises(HTTPException,match="Quantidade elevada"):
        _events([lesson(0)],SCHOOLS,date(2028,2,7),date(2028,2,7),
                max_events=0)


def test_invalid_weekday_and_unknown_school_fail_closed():
    with pytest.raises(HTTPException,match="Dia da semana"):
        _events([lesson(7)],SCHOOLS,date(2028,2,7),date(2028,2,7))
    broken=lesson(0)
    broken["school_id"]="outra"
    with pytest.raises(HTTPException,match="Unidade da aula"):
        _events([broken],SCHOOLS,date(2028,2,7),date(2028,2,7))
