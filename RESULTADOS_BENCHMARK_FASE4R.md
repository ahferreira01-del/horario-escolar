# Horário Inteligente — Fase 4R: benchmark sem gargalo estrutural

## Objetivo e método
Comparar **SciPy/HiGHS MILP** (motor padrão) com **OR-Tools CP-SAT** (experimental, opt-in) quando todas as aulas podem, demonstravelmente, ser alocadas. Foram usados dados **inteiramente fictícios**, com 24, 48 e 100 turmas em duas escolas, professores compartilhados e laboratórios dimensionados de acordo com o número de turmas.

A função `build_feasible_scenario` deriva os dados do benchmark 4Q e amplia a capacidade simultânea do laboratório Centro para **2, 3 e 5 grupos**, respectivamente, com o limite correspondente de estudantes. Esses laboratórios ampliados são **hipóteses sintéticas**, não uma promessa de capacidade física de laboratórios escolares reais.

A função `feasible_reference_assignments` constrói uma grade completa **sem chamar MILP ou CP-SAT**. O verificador independente aprova todas as aulas, respeitando cargas, limites diários/semanais, capacidade, disponibilidade e deslocamentos. Assim sabemos que os cenários **são viáveis matematicamente**, mesmo que um motor possa não encontrar a solução dentro do tempo configurado.

## Evidências — execuções completas do GitHub Actions
| Configuração | Valor |
|---|---|
| Sistema | Linux ubuntu-latest / Azure GitHub Actions |
| Python | 3.12.15 |
| SciPy | 1.18.1 |
| OR-Tools | 9.15.6755 |
| CPUs lógicas reportadas | 4 |
| Limite por etapa de otimização | 2 segundos por motor |
| Perfil de preferência | equilibrado |
| Código | Commit `39fec302e84c19a643d4fbe3a35e84b920a483d5` |

Duas execuções do **mesmo commit**:
- [Run 38440660010](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38440660010): backend **138 PASS**, 5 gates PostgreSQL/RLS reais; solver legado PASS; navegador foi iniciado e teve sucesso na outra execução.
- [Run 38440667631](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38440667631): **3/3 jobs SUCCESS**, backend **138 PASS**; 5 gates reais PostgreSQL/RLS; Next.js/Chromium PASS; solver legado PASS.
- Métricas verificáveis pelo marcador `FASE4R_BENCHMARK_EVIDENCE` nos logs do job `backend_postgres` e na propriedade `fase4r_benchmark_evidence` do JUnit.

### Cobertura e tempo — ambas as medições
| Turmas | Aulas exigidas | Aulas distribuídas MILP/CP-SAT | MILP, run 1 / run 2 | CP-SAT, run 1 / run 2 |
|---:|---:|---:|---:|---:|
| 24 | 48 | **48/48 ambos** | 0,324 / 0,482 s | 2,034 / 2,055 s |
| 48 | 96 | **96/96 ambos** | 1,359 / 2,053 s | 2,089 / 2,140 s |
| 100 | 200 | **200/200 ambos** | 1,390 / 2,140 s | 2,267 / 2,460 s |

Tempos são durações totais observadas (construção do modelo, duas etapas de otimização, verificação), portanto podem ultrapassar o limite de 2 segundos de cada etapa.

### Qualidade da distribuição — duas medições, resultados idênticos
| Turmas | Motor | Soma de dias de trabalho dos docentes | Janelas intraturno | Turnos adicionais | Status do objetivo secundário |
|---:|---|---:|---:|---:|---|
| 24 | MILP | 24 | 0 | 0 | OPTIMAL |
| 24 | CP-SAT | 24 | 0 | 0 | FEASIBLE |
| 48 | MILP | 48 | 0 | 0 | OPTIMAL |
| 48 | CP-SAT | 48 | 0 | 0 | FEASIBLE |
| 100 | MILP | **100** | 0 | **0** | OPTIMAL |
| 100 | CP-SAT | **143** | 0 | **36** | FEASIBLE |

Os números de **dias de trabalho são somados por professor** (não são dias letivos distintos). Todos os resultados foram aprovados no validador independente e a **otimalidade da primeira etapa de cobertura** foi comprovada em ambos os motores. O CP-SAT retornou `FEASIBLE` para o objetivo secundário e, portanto, **não comprovou ótima qualidade pedagógica**, mesmo com cobertura completa. Em 100 turmas, a qualidade do CP-SAT mostrou-se inferior ao MILP sob este orçamento.

Nenhum desses resultados certifica calendário real de escola: a fixture tem apenas uma disciplina por turma e dois períodos por dia, e os limites de laboratório foram aumentados artificialmente para tornar a grade totalmente viável.

## Arquivos reproduzíveis
- `backend/app/solver_scenarios_4p.py`: `build_feasible_scenario` e `feasible_reference_assignments`.
- `scripts/benchmark_solver_fase4r.py`: mede tempo, cobertura, prova de otimalidade da cobertura, métricas de dias/janelas/turnos e erros do verificador.
- `backend/tests/test_phase4r_feasible_benchmark.py`: testemunhas matemáticas em 24/48/100 turmas e benchmark executado no CI com propriedades JUnit e logs.

Para repetir com dependências do backend instaladas:

```bash
cd backend
pytest -q -rs tests/test_phase4r_feasible_benchmark.py
cd ..
python scripts/benchmark_solver_fase4r.py --sizes 24,48,100 --time-limit 2 --output evidencias/fase4r.json
```

## Interpretação, limites e próximos passos
- **Não é p50/p95, SLA nem teste de carga multiusuário**: há somente duas execuções em runners compartilhados.
- Os valores de memória **não foram medidos por motor**. A amostra não comprova comportamento de centenas de turmas com múltiplas matérias, turnos, escolas, matrículas e restrições reais.
- No próximo marco, priorizar melhorar **a segunda etapa de preferência do CP-SAT** (days/shifts/gaps) sem perder cobertura; medir novamente com orçamento comparável e modelos mais complexos.
- CP-SAT continua desativado na API; não substituir MILP automaticamente.
- O teste completo de **aprovação/publicação oficial 4K pelo Chromium** existe, mas permanece fora do workflow por bloqueio prévio de edição da conexão. Os testes atuais do navegador são Fases 4H/4J, não o 4K.
- Segurança/LGPD, backup/restauração e aceite de escola piloto ainda pendentes.

**Fase 4R: benchmark funcional concluído; produto NÃO liberado para produção. Sem merge na main nem dados reais.**
