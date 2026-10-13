"""Cenários escolares FICTÍCIOS e determinísticos para benchmark da Fase 4P.

Sem dados reais, autenticação, banco de dados ou efeitos colaterais.
O número de aulas aumenta proporcionalmente às turmas e há professores
compartilhados entre duas escolas, limites e laboratório restrito.
"""
from __future__ import annotations


DAYS = ("Seg", "Ter", "Qua", "Qui", "Sex")


def build_scenario(classes: int = 12, *, time_limit: int = 5) -> dict:
    if type(classes) is not int or classes < 2 or classes > 100 or classes % 2:
        raise ValueError("Use quantidade par de turmas de 2 a 100.")
    if type(time_limit) is not int or not 1 <= time_limit <= 15:
        raise ValueError("time_limit deve estar entre 1 e 15 segundos.")
    schools = {"Centro": {"organization_id": "benchmark-4p"},
               "Norte": {"organization_id": "benchmark-4p"}}
    classes_data = {}
    teachers = {}
    demands = []
    resources = {}
    for school in schools:
        rid = "Lab_" + school
        resources[rid] = {
            "school_id": school,
            "max_groups": 1,
            "max_students": 28,
            "availability": [
                {"day": d, "start": "07:30" if school == "Centro" else "12:30",
                 "end": "10:00" if school == "Centro" else "15:00"}
                for d in DAYS
            ]
        }
    for index in range(classes):
        school = "Centro" if index % 2 == 0 else "Norte"
        class_id = f"Turma_{index + 1:03d}"
        teacher_id = f"Docente_{index // 2 + 1:03d}"
        early = school == "Centro"
        slots = []
        for day in DAYS:
            times = (("08:00", "08:45"), ("08:55", "09:40")) if early else (
                ("13:00", "13:45"), ("13:55", "14:40"))
            for position, (start, end) in enumerate(times, 1):
                slots.append({"day": day, "order": position,
                              "start": start, "end": end,
                              "shift": "manha" if early else "tarde"})
        classes_data[class_id] = {
            "school_id": school, "students": 25, "slots": slots
        }
        if teacher_id not in teachers:
            teachers[teacher_id] = {
                "organization_id": "benchmark-4p",
                "availability": [
                    {"day": day, "start": "07:30", "end": "15:00"}
                    for day in DAYS
                ],
                "weekly_limit": 4,
                "daily_limits": {day: 2 for day in DAYS},
            }
        resource = f"Lab_{school}" if index % 4 == 0 else None
        demands.append({
            "class_id": class_id, "teacher_id": teacher_id,
            "subject": "Matemática", "lessons": 2,
            "max_consecutive": 2, "resource_id": resource,
        })
    return {
        "organization_id": "benchmark-4p",
        "mode": "lessons",
        "profile": "equilibrado",
        "time_limit": time_limit,
        "schools": schools,
        "classes": classes_data,
        "teachers": teachers,
        "resources": resources,
        "demands": demands,
        "travel_minutes": {
            "Centro->Norte": 40,
            "Norte->Centro": 40,
        },
    }


def build_feasible_scenario(classes: int = 12, *, time_limit: int = 5) -> dict:
    """Versão de 4R com laboratório dimensionado para toda a carga semanal.

    A capacidade é calculada a partir das janelas existentes (não presume
    que capacidade significa solução), mantendo as mesmas turmas, docentes
    compartilhados, deslocamentos e demandas da fixture 4P.
    """
    data = build_scenario(classes, time_limit=time_limit)
    for school, resource in (("Centro", "Lab_Centro"), ("Norte", "Lab_Norte")):
        assigned = [d for d in data["demands"]
                    if d.get("resource_id") == resource]
        required = sum(d["lessons"] for d in assigned)
        possible = set()
        for cfg in data["classes"].values():
            if cfg["school_id"] != school:
                continue
            for slot in cfg["slots"]:
                if any(a["day"] == slot["day"]
                       and a["start"] <= slot["start"]
                       and slot["end"] <= a["end"]
                       for a in data["resources"][resource]["availability"]):
                    possible.add((slot["day"], slot["start"], slot["end"]))
        if not possible:
            raise ValueError("Recurso do cenário sem janelas disponíveis.")
        groups = max(1, (required + len(possible) - 1) // len(possible))
        data["resources"][resource]["max_groups"] = groups
        data["resources"][resource]["max_students"] = 25 * groups
    return data


def feasible_reference_assignments(data: dict) -> list[dict]:
    """Grade construtiva para a fixture viável 4R, sem chamar um otimizador.

    Um professor leciona no Centro e no Norte em dias distintos; cada turma
    ocupa dois períodos consecutivos no mesmo dia. As turmas do laboratório
    são distribuídas entre cinco dias para respeitar a capacidade calculada.
    Serve SOMENTE de testemunha matemática para esta fixture artificial.
    """
    if not data["classes"] or len(data["classes"]) % 2:
        raise ValueError("Testemunha 4R exige pares de turmas.")
    output = []
    for pair in range(len(data["classes"]) // 2):
        for offset in (0, 1):
            idx = 2 * pair + offset
            class_id = f"Turma_{idx + 1:03d}"
            cls = data["classes"][class_id]
            day = DAYS[(pair + offset) % len(DAYS)]
            demand = next(d for d in data["demands"] if d["class_id"] == class_id)
            slots = sorted(
                (s for s in cls["slots"] if s["day"] == day),
                key=lambda s: s["order"])
            for slot in slots[:2]:
                output.append({
                    "class_id": class_id,
                    "school_id": cls["school_id"],
                    "subject": demand["subject"],
                    "teacher": demand["teacher_id"],
                    "day": day,
                    "order": slot["order"],
                    "start": slot["start"],
                    "end": slot["end"],
                    "shift": slot["shift"],
                    "resource_id": demand.get("resource_id"),
                    "students": cls["students"],
                })
    return output
