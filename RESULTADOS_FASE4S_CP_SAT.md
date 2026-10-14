# Horário Inteligente — Fase 4S: exploração da qualidade do CP-SAT

## Resultado e decisão
**Avanço parcial, sem conclusão de paridade pedagógica.** Foi implementada uma
otimização experimental da etapa secundária: CP-SAT usa uma dica das aulas
encontradas na primeira etapa de cobertura e busca em até **4 trabalhadores**
(somente nessa segunda etapa). A primeira etapa e o motor MILP da API
permanecem inalterados. A dica NÃO é restrição e a solução continua passando
por validação independente.

A tentativa de incluir *também* todas as variáveis auxiliares de dias/turnos
nas dicas foi medida, apresentou qualidade ponderada inferior e **foi
revertida**. O código final conserva apenas as dicas das aulas.

## Métodos e limitações
- Os dados continuam **100% fictícios**, da fixture 4R: duas escolas,
  24/48/100 turmas com uma disciplina e dois períodos por dia.
- Limite de 2 segundos **por etapa** do motor, em runner GitHub compartilhado
  com quatro CPUs lógicas. Durações totais podem superar esse valor.
- Métricas da preferência equilibrada: 30 pontos por dia de trabalho docente
  acumulado e 10 pontos por turno adicional, além de janelas e pedagógica
  (ambas zero nesses exemplos).
- Todos os ensaios mencionados tiveram **100% de cobertura**: 48/48,
  96/96 e 200/200 aulas. O CP-SAT permaneceu `FEASIBLE` para a
  otimização secundária; **não foi demonstrado `OPTIMAL`**.
- A qualidade é a métrica modelada (não satisfação pedagógica real).
  Poucas rodadas não fundamentam p95, SLA, previsão de produção ou mudança
  de motor por padrão.

## Baseline anterior — Fase 4R

[Run 38440660010](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38440660010)
e [run 38440667631](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38440667631):

| Turmas | MILP: dias / turnos | CP-SAT anterior: dias / turnos |
| ---: | --- | --- |
| 24 | 24 / 0 | 24 / 0 |
| 48 | 48 / 0 | 48 / 0 |
| 100 | 100 / 0 | **143 / 36** |

No caso de 100 turmas, custo ponderado secundário CP-SAT:
`143 × 30 + 36 × 10 = 4.650`.

## Primeiro experimento 4S — dicas de aula + quatro workers

| Run de CI | CP-SAT 24 turmas: dias/turnos | CP-SAT 48: dias/turnos | CP-SAT 100: dias/turnos | Custo ponderado 100 |
| --- | --- | --- | --- | ---: |
| [38442685599](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38442685599) | 24 / 0 | 48 / 6 | **105 / 34** | 3.490 |
| [38442691941](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38442691941) | 24 / 6 | 48 / 4 | **107 / 38** | 3.590 |
| [38442758041](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38442758041) | 24 / 0 | 48 / 4 | **105 / 44** | 3.590 |

A soma ponderada para 100 turmas melhorou cerca de **23% a 25%** em relação
ao baseline, sem perda de aulas. Contudo, apareceram mais turnos adicionais
em parte das rodadas pequenas. A otimização não é universal nem determinística
sob concorrência dos runners e não cumpre ainda a paridade com o MILP.

Os testes do backend, do solver legado e os smokes do navegador 4H/4J
passaram nesses commits. Ao acrescentar
`backend/tests/test_phase4s_cpsat_hints.py`, o backend atingiu
**148 testes PASS**. Esse arquivo verifica que dicas incorretas não obrigam
o solucionador a aceitar uma solução inválida, recusa índices/valores
inválidos e mantém a grade validada independentemente.

## Segundo experimento — também sugerir dia e turno (DESCARTADO)

| Run de CI | 24 turmas: dias/turnos | 48: dias/turnos | 100: dias/turnos | Custo ponderado 100 |
| --- | --- | --- | --- | ---: |
| [38443219815](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38443219815) | 24 / 4 | 48 / 10 | 123 / 16 | 3.850 |
| [38443229029](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38443229029) | 24 / 4 | 48 / 10 | 123 / 17 | 3.860 |

A dica auxiliar piorou a qualidade ponderada em 100 turmas em comparação
com a primeira versão do 4S e foi removida no commit de reversão.
Essa reversão NÃO restaura o comportamento antigo anterior à Fase 4S:
preserva hints de aula e a busca secundária de 4 workers.

## Estado e trabalhos seguintes
- **MILP/HiGHS continua como motor da API.** CP-SAT segue apenas
  experimental, sem ativação para escolas.
- Não existe regressão demonstrada na *cobertura*; a melhoria secundária
  em dias/turnos exige mais pesquisa antes de liberar.
- Estudar otimização do objetivo secundário, busca local, orçamentos
  diferentes, múltiplas sementes e cenários com múltiplas disciplinas.
- O teste da **Fase 4K (aprovação/publicação/exportação oficial via Chromium)**
  ainda está fora do workflow. Os testes 4H/4J não o substituem.
- Pendente: segurança/LGPD, isolamento/cancelamento de jobs de solver,
  memória e carga, backups/restauração e piloto controlado.
- **Não realizar merge, deploy ou usar dados escolares reais.**
