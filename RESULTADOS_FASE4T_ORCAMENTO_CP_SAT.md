# Horário Inteligente — Fase 4T: orçamento independente para preferência pedagógica

## Objetivo
Validar experimentalmente se aumentar o tempo da **segunda etapa** do
OR-Tools CP-SAT melhora a qualidade da distribuição de aulas sem relaxar
as restrições, mudar o limite da **primeira etapa de cobertura**, nem
habilitar o motor novo na API. O motor de produção continua
**SciPy/HiGHS MILP**.

## Implementado
- `backend/app/solver_preview.py`: argumento opcional
  `secondary_time_limit=None` em `all_grid`, aceito **apenas com
  `engine="cpsat"`**, como inteiro (não booleano) entre **1 e 15**.
  O tempo da primeira etapa segue `data["time_limit"]`.
  O MILP mantém seus parâmetros e a validação independente.
- `backend/app/solver_controlled.py`: permite repassar o orçamento
  apenas em execução CP-SAT **explicitamente autorizada**; o resultado
  `engine_control` identifica o valor. O rollback para MILP permanece
  exclusivo de `unsolved` e de autorização separada.
- `backend/tests/test_phase4t_secondary_budget.py`: testes de limites
  inválidos, preservação do MILP, bloqueio de CP-SAT sem autorização,
  instrumentação comprovando chamadas distintas de tempo na cobertura e
  na segunda etapa, e benchmark de 100 turmas reproduzível com saída
  `FASE4T_SECONDARY_BUDGET_EVIDENCE` no log e propriedade JUnit.

## Evidências — duas execuções independentes, mesmo commit
Código do benchmark `f597cfddc5461a231e77e87ce442cb51a50c225f`,
runner compartilhado GitHub Actions Linux/Azure, **quatro CPUs lógicas**.
São dados escolares **inteiramente fictícios**, cenário matematicamente
viável de duas escolas/100 turmas/200 aulas, perfil `equilibrado`.
O orçamento da cobertura foi fixado em **2 segundos**; o da segunda
etapa CP-SAT, alternado entre **2 e 8 segundos**. As medidas de tempo
incluem preparação do modelo e ambas as etapas.

- [Execução 38445489514](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38445489514).
- [Execução 38445481885](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38445481885).
- Ambas com **160 testes de backend PASS**, cinco gates reais
  PostgreSQL/RLS executados. As duas rodadas do gerador legado também
  passaram. A aprovação final dos três jobs deve ser conferida pelo
  status de cada execução.

| Execução | Limite secundário | Duração total | Aulas | Dias docentes somados | Turnos adicionais | Custo ponderado | Status secundário |
|---|---:|---:|---:|---:|---:|---:|---|
| 38445489514 | 2 s | 2,265 s | 200/200 | 103 | 40 | 3.490 | FEASIBLE |
| 38445489514 | 8 s | 8,261 s | 200/200 | 101 | 22 | **3.250** | FEASIBLE |
| 38445481885 | 2 s | 2,405 s | 200/200 | 106 | 36 | 3.540 | FEASIBLE |
| 38445481885 | 8 s | 8,422 s | 200/200 | 101 | 28 | **3.310** | FEASIBLE |

Custo do perfil `equilibrado` nesta fixture:
`30 × dias docentes + 10 × turnos adicionais + 40 × janelas`.
As janelas foram zero nos quatro resultados e a fixture não inclui
penalidades por dias evitados.

Nesta amostra, o custo caiu aproximadamente **6,9%** e **6,5%** ao
aumentar o orçamento. Houve **cobertura integral de 200 aulas** nos
quatro resultados; a primeira etapa teve cobertura ótima comprovada.
A segunda etapa retornou `FEASIBLE`, portanto **não há prova de
otimalidade pedagógica**.

### Comparação com MILP
No benchmark 4R equivalente, o MILP encontrou **100 dias docentes,
0 turnos adicionais e custo ponderado 3.000**, com `OPTIMAL`. Assim
o CP-SAT de oito segundos **melhorou em relação ao CP-SAT de dois
segundos, mas continua inferior ao MILP** nesse cenário. Além disso,
exigiu cerca de quatro vezes o tempo por execução.

## Limitações da evidência e decisão
- São **duas execuções**, não cálculo confiável de p95/SLA.
  Runners compartilhados e busca paralela do CP-SAT geram variação.
- Este benchmark é de dados falsos com **uma disciplina por turma**,
  dois períodos por dia e laboratórios artificialmente dimensionados.
  Não valida exigências pedagógicas de uma escola real.
- Um orçamento maior **não garante** melhoria em todas as instâncias
  nem implica superioridade do CP-SAT.
- O limite de 15 segundos é uma proteção do experimento por chamada,
  não um timeout total de requisição ou isolamento de jobs; cobertura
  e montagem também consomem tempo.
- **Decisão:** manter o novo orçamento configurável somente no
  experimento. Não alterar o comportamento da API nem substituir o MILP.

## Próximos passos
1. Estudar qualidade e memória em cenários com múltiplas disciplinas,
   cargas em minutos, trocas de professores e deslocamentos.
2. Definir métricas e orçamento global por job, fila, cancelamento e
   isolamento da execução antes de pensar em ativação.
3. Resolver a **Issue #3** somente após comprovar paridade pedagógica
   e desempenho com benchmarks mais representativos.
4. Executar a homologação **4K de aprovação e publicação oficial no
   navegador**, cujo script permanece fora do workflow pela restrição
   anterior de edição. CI atual executa somente smokes 4H/4J.
5. Revisão independente de segurança/LGPD, backup/restauração e
   piloto de aceitação escolar.

**Sem merge na main, deploy de produção ou dados reais.**
