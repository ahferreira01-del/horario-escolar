# Horário Inteligente — PoC v0.2

**Protótipo executável local** do motor de geração de horários; não é um aplicativo SaaS publicado. Todos os nomes e dados são fictícios. Continuação da PoC v0.1.

## O que está implementado e testado

- Uma organização por execução, com duas ou mais escolas. O docente tem identificador único dentro dessa organização e pode atender escolas diferentes.
- Disponibilidade do professor cadastrada por intervalos reais (sem arredondamento). Não é permitido atribuir aula que comece antes ou termine depois de uma faixa.
- Sobreposição de professores e de turmas, inclusive com horários diferentes de períodos.
- Tempo mínimo de deslocamento **direcional** entre unidades, sem presumir zero quando ausente.
- Limites diários e semanais de docentes.
- Disciplina/turma com cotas **fixas por professor**. Limite absoluto configurado em 1 ou 2 períodos consecutivos da mesma disciplina, mesmo havendo recreio.
- Espaço opcional com disponibilidade, máximo de turmas simultâneas e lotação máxima por número de alunos; valida ambos.
- Priorização **lexicográfica** da cobertura de aulas; nenhuma preferência pode sacrificar cobertura encontrada.
- Perfis `equilibrado`, `menos_janelas`, `menos_dias` e `personalizado` (pesos inteiros totalizando 100). Penalidade para preferências `avoid_days` em demandas.
- Geração parcial com quantidade e localização das pendências; diagnósticos apenas básicos (sem afirmar prova de causa global).
- Verificador independente da grade gerada, retornos JSON e CSV e relatório HTML estático.

## Dependências

Python 3.11+; `numpy`, `scipy`, `pytest` para testes (somente bibliotecas abertas, executadas localmente).

```bash
python -m pip install -r requirements.txt
python solver.py exemplo_duas_escolas.json --out outputs/resultado_completo.json --csv outputs/grade_completa.csv
python solver.py exemplo_disponibilidade_incompativel.json --out outputs/resultado_parcial.json --csv outputs/grade_parcial.csv
python render_report.py exemplo_duas_escolas.json outputs/resultado_completo.json --out outputs/grade_completa.html --title "Grade completa"
python render_report.py exemplo_disponibilidade_incompativel.json outputs/resultado_parcial.json --out outputs/grade_parcial.html --title "Grade parcial"
pytest -q tests/
```

## Resultados executados (cenários de demonstração)

| Cenário | Quantidade | Resultado |
| --- | --- | --- |
| 3 turmas em 2 escolas, professor compartilhado e 2 laboratórios | 28 aulas | 28/28 distribuídas |
| Mesma rede, mas Paulo disponível apenas terça das 10:45 às 12:00 | 28 aulas | 17/28 distribuídas; 11 pendentes |

Os horários dos alunos nas duas escolas estão em turnos diferentes, e o professor compartilhado tem deslocamentos Centro→Norte de 25 minutos e Norte→Centro de 35 minutos. O solver trata tempos diferentes por direção.

## Limitações — ler antes de usar

1. **Ainda não é OR-Tools/CP-SAT**: usa SciPy/HiGHS MILP para validar conceitos. Não é solução homologada em produção.
2. Não há persistência, login, organizações reais, políticas RLS, APIs, auditoria, filas, publicação, aprovação, versionamento ou reservas transacionais.
3. Somente modo `lessons` foi implementado; cargas em minutos com tolerâncias P05-A ainda não estão programadas.
4. Não há alocação automática de professor entre habilitados, obrigações de aula fixa, regras pedagógicas completas, janelas obrigatórias de turma, nem publicação de grade parcial.
5. O objetivo de **janelas intraturno** é aproximado por períodos disponíveis. O termo `additional_shifts` penaliza atuar em vários turnos no mesmo dia, mas **não mede minutos reais de espera interturno**. Essas métricas não devem ser utilizadas para decisões oficiais sem modelo aprimorado.
6. Os resultados pequenos não são benchmark de escala; nenhuma meta de tempo de processamento foi validada.
7. O motor representa semana recorrente de uma organização e não vigência, feriados, datas concretas ou fusos horários diversos.
8. Mesmo com status `OPTIMAL` em cenários pequenos, isso significa otimalidade **apenas para o modelo simplificado implementado**.
9. O campo `coverage_proven_optimal` diferencia resultado ótimo matematicamente comprovado de melhor solução encontrada dentro do tempo.
10. Mudanças em perfis, pesos ou dados geram nova execução; os arquivos HTML são somente relatórios estáticos.

## Próximos passos

- Substituir/validar o MILP por CP-SAT e modelar janelas/esperas em minutos reais.
- Implementar carga em minutos, aulas fixas, regras de turma, recursos adicionais, preferências granulares e políticas de publicação P15.
- Criar PostgreSQL com RLS testada, APIs e autenticação RBAC, jobs assíncronos, versionamento/publicação transacional por grupos.
- Ensaiar carga/escala e calibrar tempo por porte de escola, sem definir meta antecipada.

**Governança aprovada:** diretrizes P07, P08, P09, P10, P11, P12, P14 e P-TZ; prazos de retenção e metas de desempenho permanecem pendentes de validação. Não confundir a PoC com implementação dessas regras operacionais.
