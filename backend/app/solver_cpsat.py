"""Adaptador experimental OR-Tools CP-SAT para o modelo binário do Horário Inteligente.

Reutiliza as restrições construídas pelo gerador existente, mas com um motor
inteiro alternativo. Não publica horários, não altera a API nem substitui MILP.
Paridade funcional e desempenho precisam ser medidos antes de ativação padrão.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from ortools.sat.python import cp_model


@dataclass
class CPSATResult:
    x: np.ndarray | None
    status: int
    message: str


class CPSAT:
    """Mesmo contrato binário de MILP: var, add, solve.

    CP-SAT exige coeficientes inteiros. As restrições do gerador são inteiras;
    a função objetivo fracionária de cobertura usa precisão de 1e-6.
    """

    OBJECTIVE_SCALE = 1_000_000

    def __init__(self):
        self.names: list[str] = []
        self.constraints: list[tuple[dict[int, int], float, float]] = []
        self.solution_hints: dict[int, int] = {}

    def var(self, name: str) -> int:
        idx = len(self.names)
        self.names.append(name)
        return idx

    def add(self, terms, low=-math.inf, high=math.inf):
        coefficients = {}
        for index, value in terms.items():
            number = float(value)
            if not math.isfinite(number) or abs(number - round(number)) > 1e-8:
                raise ValueError("CP-SAT exige coeficientes inteiros nas restrições.")
            if number:
                coefficients[int(index)] = int(round(number))
        self.constraints.append((coefficients, float(low), float(high)))

    def set_solution_hints(self, values: dict[int, int]):
        """Dicas apenas para a segunda etapa. Não mudam as restrições.

        O resultado de cobertura da primeira etapa é uma solução viável
        para suas variáveis; a etapa secundária pode então continuar a busca.
        """
        for index, value in values.items():
            if type(index) is not int or not 0 <= index < len(self.names):
                raise ValueError("Índice inválido em dica CP-SAT.")
            if type(value) is not int or value not in (0, 1):
                raise ValueError("Dica CP-SAT precisa ser binária.")
        self.solution_hints = dict(values)

    def solve(self, costs, time_limit):
        model = cp_model.CpModel()
        xs = [model.NewBoolVar(f"x{i}") for i in range(len(self.names))]
        for coefficients, low, high in self.constraints:
            expr = sum(value * xs[i] for i, value in coefficients.items())
            if math.isfinite(low):
                model.Add(expr >= math.ceil(low - 1e-8))
            if math.isfinite(high):
                model.Add(expr <= math.floor(high + 1e-8))

        # Escala somente quando há pesos fracionários. Para custos inteiros,
        # usa as magnitudes originais para reduzir o esforço de presolve.
        values = [float(v) for v in costs.values()]
        if any(not math.isfinite(v) for v in values):
            raise ValueError("Objetivo CP-SAT com peso inválido.")
        scale = (self.OBJECTIVE_SCALE
                 if any(abs(v-round(v)) > 1e-9 for v in values) else 1)
        objective = sum(
            int(round(float(weight) * scale)) * xs[int(index)]
            for index, weight in costs.items() if weight
        )
        model.Minimize(objective)
        for i, value in self.solution_hints.items():
            model.AddHint(xs[i], value)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        # Etapa de cobertura mantém busca determinística; na etapa secundária
        # com dicas de solução, quatro workers exploram distribuições melhores.
        solver.parameters.num_search_workers = 4 if self.solution_hints else 1
        solver.parameters.random_seed = 42
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solution = np.array([float(solver.Value(x)) for x in xs])
        else:
            solution = None
        return CPSATResult(
            x=solution,
            status=0 if status == cp_model.OPTIMAL else 1 if status == cp_model.FEASIBLE else 2,
            message=solver.StatusName(status),
        )
