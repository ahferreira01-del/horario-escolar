"""Execução CONTROLADA do CP-SAT (Fase 4P), sem integração com a API.

O motor oficial da aplicação continua SciPy/HiGHS. Este wrapper somente pode
ser chamado explicitamente em testes, benchmark ou ferramenta experimental.
Falhas de verificação de uma solução NUNCA ativam fallback silencioso.
"""
from __future__ import annotations

from copy import deepcopy
from time import perf_counter

from .solver_preview import all_grid, validate_solution


def controlled_preview(data: dict, *, engine: str = "milp",
                       enable_experimental: bool = False,
                       fallback_on_unsolved: bool = False) -> dict:
    """Executa engine explicitamente selecionado, verifica saída e registra rollback.

    Apenas 'unsolved' do CP-SAT pode cair para MILP, e SOMENTE com dois
    consentimentos explícitos (enable_experimental e fallback_on_unsolved).
    Input inválido, exceção, resultado desconhecido ou violação de regras
    falham fechados. Nenhuma alteração em variáveis de ambiente/endpoints.
    """
    if engine not in ("milp", "cpsat"):
        raise ValueError("Motor inválido; escolha milp ou cpsat.")
    if engine == "cpsat" and not enable_experimental:
        raise PermissionError("CP-SAT experimental desativado; habilite explicitamente.")
    if fallback_on_unsolved and engine != "cpsat":
        raise ValueError("Rollback experimental só se aplica ao CP-SAT.")

    started = perf_counter()
    result = all_grid(deepcopy(data), engine=engine)
    if not isinstance(result, dict):
        raise RuntimeError("Motor retornou resposta inválida.")
    state = result.get("result")
    if state not in ("complete", "partial", "unsolved"):
        raise RuntimeError("Motor retornou estado desconhecido.")
    if state in ("complete", "partial"):
        if not isinstance(result.get("assignments"), list):
            raise RuntimeError("Motor não retornou lista de aulas.")
        errors = validate_solution(data, result["assignments"])
        if errors:
            raise RuntimeError("Grade experimental reprovada pelo verificador independente.")
    elif result.get("assignments") not in ([], None):
        raise RuntimeError("Motor declarou falha, mas retornou aulas.")
    elapsed_primary = round(perf_counter() - started, 3)

    rolled_back = False
    elapsed_fallback = 0.0
    if engine == "cpsat" and state == "unsolved" and fallback_on_unsolved:
        fallback_start = perf_counter()
        alternate = all_grid(deepcopy(data), engine="milp")
        if not isinstance(alternate, dict) or alternate.get("result") not in ("complete", "partial"):
            raise RuntimeError("Rollback MILP não retornou grade validável.")
        if not isinstance(alternate.get("assignments"), list):
            raise RuntimeError("Rollback MILP não retornou lista de aulas.")
        if validate_solution(data, alternate["assignments"]):
            raise RuntimeError("Rollback MILP reprovado pelo verificador independente.")
        result = alternate
        rolled_back = True
        elapsed_fallback = round(perf_counter() - fallback_start, 3)

    # Não registrar identificadores de estudantes, professores ou turmas.
    return {
        **result,
        "engine_control": {
            "requested": engine,
            "executed": "milp" if rolled_back else engine,
            "fallback_used": rolled_back,
            "fallback_reason": "experimental_unsolved" if rolled_back else None,
            "primary_elapsed_seconds": elapsed_primary,
            "fallback_elapsed_seconds": elapsed_fallback,
        }
    }
