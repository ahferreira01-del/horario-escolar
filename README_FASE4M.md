# Horário Inteligente — Fase 4M: orçamento de publicação e expansão semanal

## Correção aplicada
A rotina de publicação oficial e sua pré-validação recebem agora um limite
**antecipado** de ocorrências datadas (atualmente 25.000 no máximo),
reutilizando o teto que já era verificado após criar todos os eventos.

Antes, `_events` construía uma lista percorrendo *todos os dias da vigência*
para cada aula semanal, e o limite só era verificado na etapa seguinte.
Um pedido de calendário extenso poderia usar CPU e memória desnecessárias
antes de falhar com HTTP 422.

Agora:
- O código calcula a quantidade de datas que correspondem ao dia da semana
  de cada aula, sem alocar/convertê-las.
- Rejeita o pedido **antes da expansão** quando excede o limite, com HTTP 422
  e mensagem de redução da vigência.
- Gera datas por saltos de **sete dias** por aula (não itera pelos dias sem aula).
- Divide o mesmo orçamento entre os compromissos já publicados nas semanas
  envolvidas e os novos compromissos, sem relaxar a regra de limites docentes.
- Rejeita horários com dia da semana inválido ou unidade ausente.
- Mantém o teste de conflitos/recursos/professores e a verificação final
  de volume como barreira redundante.

## Testes de regressão
`backend/tests/test_phase4m_occurrence_budget.py` cobre:
1. Expansão de recorrência semanal por datas exatas;
2. Janela de um dia sem falso encontro e período invertido;
3. Limite de ocorrência atingido **antes** da conversão de fuso;
4. Ano longo rejeitado sem consumir memória em eventos;
5. Orçamento zero rejeitando qualquer ocorrência;
6. Dia de semana inválido e escola desconhecida rejeitados.

## Status de certificação
Esta fase melhora desempenho de expansão e protege recursos da API, mas
**não é benchmark** do tempo de otimização do gerador. O limite de 25 mil
ocorrências é uma restrição técnica deliberada; calendários maiores deverão
ser divididos em lotes ou passar por outro mecanismo de validação escalável.

**Bloqueios que permanecem:**
- O smoke 4K (aprovação + publicação oficial pelo Chromium) está no repositório,
  mas sua inclusão no CI continua bloqueada; não está homologado no navegador.
- O motor usa MILP SciPy/HiGHS, não CP-SAT.
- Testes com escolas grandes, validação de LGPD/segurança, backup/restauração
  e preparação de produção permanecem pendentes.

Não realizar merge automático nem implantação em produção.
