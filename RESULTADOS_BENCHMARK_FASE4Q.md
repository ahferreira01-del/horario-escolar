# Horário Inteligente — Fase 4Q: benchmark real em GitHub Actions

## Objetivo e configuração
Primeira medição **real** dos motores MILP/HiGHS e OR-Tools CP-SAT
com dados **100% fictícios** e duas escolas, 24/48/100 turmas. O teste
foi executado nos runners ubuntu-latest do GitHub Actions, com Python
3.12.15, SciPy 1.18.1, OR-Tools 9.15.6755 e quatro CPUs lógicas
informadas pelo runner.

Cada motor recebeu limite de **2 segundos para cada uma das duas
etapas de otimização**. Os tempos totais incluem montagem e validação
e podem ultrapassar 2 segundos. Não houve aquecimento prévio fixo nem
controle estrito de CPU concorrente. Portanto este resultado é
**exploratório, não SLA, p95, certificação de produção nem teste de carga
multiusuário**.

## Evidências reproduzíveis, duas execuções independentes

- [GitHub Actions run 38437405530](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38437405530) — 3/3 jobs PASS, commit `3360979bd7592bc7d4a811997a77e818ed11dfd9`.
- [GitHub Actions run 38437414763](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38437414763) — 3/3 jobs PASS, mesmo commit.
- Em cada execução, `backend_postgres` passou com **130 testes**, incluindo
  cinco gates PostgreSQL/RLS críticos realmente executados.
- A mensagem `FASE4Q_BENCHMARK_EVIDENCE` no log e a propriedade
  `fase4q_benchmark_evidence` no JUnit registram os tempos individuais,
  ambiente, cobertura, estado e prova da primeira etapa.
- O job `solver_legacy` e o job `frontend_browser_postgres` também
  passaram, incluindo os smokes Chromium 4H/4J (não o 4K).

| Turmas | Aulas requeridas | Aulas obtidas, ambos | MILP, execução 1/2 | CP-SAT, execução 1/2 |
| ---: | ---: | ---: | ---: | ---: |
| 24 | 48 | 46 | 0,877 s / 1,065 s | 2,048 s / 2,061 s |
| 48 | 96 | 82 | 0,675 s / 0,819 s | 2,111 s / 2,145 s |
| 100 | 200 | 160 | 2,399 s / 2,465 s | 2,341 s / 2,451 s |

**Atenção à interpretação:** ambas as engines alcançaram a mesma
*quantidade* de aulas em cada cenário, e todas passaram na validação
independente. Isso não garante que os mesmos horários sejam atribuídos.
A etapa de **cobertura** foi provada ótima nas seis combinações
deste benchmark (`coverage_proven_optimal=True`). No objetivo secundário
de preferência pedagógica, o CP-SAT retornou `FEASIBLE` em todos os
cenários e o MILP `FEASIBLE` para 100 turmas; portanto **não está
provada a otimalidade final desses horários**.

## Por que as grades maiores são parciais

A fixture do experimento tem um laboratório compartilhado no Centro,
com dez períodos possíveis por semana e uma turma por período.
As turmas de índice múltiplo de 4 necessitam de duas aulas no laboratório,
logo os maiores cenários exigem mais aulas do que essas dez vagas:

| Turmas | Aulas de laboratório requeridas | Capacidade | Déficit inevitável | Limite superior total |
| ---: | ---: | ---: | ---: | ---: |
| 24 | 12 | 10 | 2 | 46 |
| 48 | 24 | 10 | 14 | 82 |
| 100 | 50 | 10 | 40 | 160 |

O teste `backend/tests/test_phase4q_capacity_bounds.py` calcula esse
teto a partir da fixture de cada tamanho. Portanto o déficit
observado não significa, por si só, falha dos motores: **ambos atingiram
o limite físico desse conjunto fictício de recursos**.

## Arquivos e reprodução

- `backend/tests/test_phase4q_benchmark_ci.py`: medição automática
  24/48/100 turmas em MILP/CP-SAT, com validação independente e
  evidências visíveis no log e JUnit.
- `backend/tests/test_phase4q_capacity_bounds.py`: prova do limite
  de capacidade do laboratório para o cenário sintético.
- `backend/app/solver_scenarios_4p.py`: gerador sintético determinístico.
- `scripts/benchmark_solver_fase4p.py`: benchmark manual com tamanhos
  e tempos configuráveis, saída JSON.

```bash
cd backend
pytest -q -rs tests/test_phase4q_benchmark_ci.py tests/test_phase4q_capacity_bounds.py
cd ..
python scripts/benchmark_solver_fase4p.py --sizes 24,48,100 --time-limit 2 --output evidencias/fase4q-local.json
```

## Próximas verificações necessárias
1. Testar cenários **sem gargalo estrutural de laboratório**, para medir
   distribuição de aulas em grade totalmente viável, e casos mais complexos
   com múltiplas disciplinas e cargas em minutos.
2. Repetir benchmarks em runner com recursos fixos, medir p50/p95, memória,
   consumo de CPU, timeout e concorrência; validar grade de 100+ turmas.
3. Manter CP-SAT **experimental e desligado da API** até comparação ampla,
   plano de rollback, observabilidade e aceite pedagógico.
4. Ativar e executar o script de homologação **4K de publicação oficial no
   Chromium**, ainda fora do workflow por bloqueio de edição identificado.
5. Revisão independente de segurança, LGPD, backups/restauração e piloto.

**Sem dados escolares reais, merge ou deploy de produção.**
