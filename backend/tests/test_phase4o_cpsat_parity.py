"""Fase 4O — comparação real MILP/HiGHS versus OR-Tools CP-SAT.

O experimento é opcional e não ativa CP-SAT em endpoints ou publicações.
Os dois motores passam pelo mesmo validador independente do domínio.
"""
from copy import deepcopy

import pytest
from app.solver_preview import all_grid, validate_solution
from app.solver_cpsat import CPSAT


def _period(day="Seg", start="08:00", end="08:45"):
    return dict(day=day,order=1,start=start,end=end,shift="manha")


def _teacher():
    return dict(organization_id="tenant",availability=[
        dict(day="Seg",start="07:00",end="12:00"),
        dict(day="Ter",start="07:00",end="12:00"),
    ],weekly_limit=4,daily_limits={"Seg":2,"Ter":2})


def _dataset():
    return dict(
        organization_id="tenant", mode="lessons",profile="equilibrado",time_limit=4,
        schools={"Centro":{"organization_id":"tenant"}},
        classes={"A":dict(school_id="Centro",students=25,
                          slots=[_period("Seg"),_period("Ter")])},
        teachers={"Ana":_teacher()},
        resources={},travel_minutes={},
        demands=[dict(class_id="A",subject="Matemática",teacher_id="Ana",lessons=2)]
    )


def _compare(dataset, count):
    for engine in ("milp","cpsat"):
        result=all_grid(deepcopy(dataset),engine=engine)
        assert result["total_assigned"]==count,(engine,result)
        assert validate_solution(dataset,result["assignments"])==[],(engine,result)
        if count==sum(d["lessons"] for d in dataset["demands"]):
            assert result["result"]=="complete" and not result["pending"]
        else:
            assert result["result"]=="partial" and result["pending"]
        if engine=="cpsat":
            assert "CP-SAT" in result["optimizer"]
        else:
            assert "MILP" in result["optimizer"]


def test_cpsat_adapter_exact_binary_constraints():
    model=CPSAT()
    a=model.var("a")
    b=model.var("b")
    model.add({a:1,b:1},high=1)
    result=model.solve({a:-1.0,b:-0.5},time_limit=2)
    assert result.status==0
    assert result.x.tolist()==[1.0,0.0]


def test_cpsat_rejects_fractional_constraint_coefficients():
    model=CPSAT()
    index=model.var("x")
    with pytest.raises(ValueError,match="inteiros"):
        model.add({index:0.5},high=1)


def test_two_days_complete_in_both_engines():
    _compare(_dataset(),2)


def test_exact_availability_blocks_both_engines():
    dataset=_dataset()
    dataset["teachers"]["Ana"]["availability"]=[dict(day="Seg",start="07:00",end="12:00")]
    _compare(dataset,1)


def test_resource_capacity_is_hard_constraint_in_both_engines():
    dataset=_dataset()
    dataset["classes"]={
        "A":dict(school_id="Centro",students=25,slots=[_period()]),
        "B":dict(school_id="Centro",students=25,slots=[_period()])
    }
    dataset["teachers"]["Bruno"]=_teacher()
    dataset["resources"]={"Lab":dict(school_id="Centro",max_groups=1,max_students=30,
                                     availability=[dict(day="Seg",start="07:00",end="12:00")])}
    dataset["demands"]=[
        dict(class_id="A",subject="Ciências",teacher_id="Ana",lessons=1,resource_id="Lab"),
        dict(class_id="B",subject="Ciências",teacher_id="Bruno",lessons=1,resource_id="Lab")
    ]
    _compare(dataset,1)


@pytest.mark.parametrize("gap,expected",[("08:55",1),("09:15",2)])
def test_directional_school_travel_in_both_engines(gap,expected):
    dataset=_dataset()
    dataset["schools"]["Norte"]={"organization_id":"tenant"}
    dataset["classes"]={
        "A":dict(school_id="Centro",students=25,slots=[_period()]),
        "B":dict(school_id="Norte",students=25,slots=[_period(start=gap,end="10:00")])
    }
    dataset["teachers"]["Ana"]=_teacher()
    dataset["travel_minutes"]={"Centro->Norte":20,"Norte->Centro":20}
    dataset["demands"]=[
        dict(class_id="A",subject="Matemática",teacher_id="Ana",lessons=1),
        dict(class_id="B",subject="Matemática",teacher_id="Ana",lessons=1),
    ]
    _compare(dataset,expected)


def test_default_engine_stays_milp():
    result=all_grid(_dataset())
    assert "MILP" in result["optimizer"]


def test_cpsat_multischool_shared_teachers_lab():
    # A mesma fixture utilizada para homologar MILP na Fase 4L.
    from test_phase4l_multischool_fixture import multischool_fixture
    dataset=multischool_fixture()
    result=all_grid(deepcopy(dataset),engine="cpsat")
    assert result["result"]=="complete",result
    assert result["total_required"]==result["total_assigned"]==6
    assert validate_solution(dataset,result["assignments"])==[]
    assert {row["school_id"] for row in result["assignments"]}=={"Centro","Norte"}
