# Fase 4L — integridade e cenários com professores compartilhados

## Objetivo
Aumentar a confiabilidade do verificador independente do gerador de horários
antes de testes de escala com dados escolares reais.

## Alterações implementadas
1. Tanto `backend/app/solver_preview.py` quanto `solver_poc_v0_2/solver.py`
   rejeitam aulas que não correspondam a uma demanda/atribuição exata
   (**turma, disciplina, professor e recurso obrigatório**).
2. A correspondência com o período cadastrado também exige o turno
   (`shift`), além de dia, ordem, início e fim.
3. O backend recebe cinco testes de integridade para aceitar aula legítima
   e rejeitar disciplina inventada, troca de docente, troca de turno e
   omissão de laboratório obrigatório.
4. O protótipo recebe cinco testes equivalentes, evitando regressão
   caso os motores sejam mantidos ou comparados.
5. O backend recebe um teste sintético com seis turmas, duas escolas,
   dois docentes compartilhados, limites de carga e laboratório com
   disponibilidade/capacidade restritas.

## Evidências e aceitação
O pipeline padrão no GitHub executa testes Python contra PostgreSQL 16/RLS,
testes do gerador legado, build Next.js/TypeScript e navegação escolar com Chromium.

Critérios para concluir este marco:
- Os testes adicionais passam sem reduzir a cobertura anterior.
- `CI_POSTGRES_GATES_PASS` continua comprovando que os testes reais de PostgreSQL não foram ignorados.
- O gerador mantém soluções sem conflitos e com demanda integral no cenário sintético.

## Limitações (não homologado para produção)
- O teste de seis turmas é funcional e **não** demonstra escalabilidade,
  tempo de solução previsível ou capacidade de atender centenas de turmas.
- O motor ainda usa SciPy/HiGHS; OR-Tools CP-SAT continua pendente.
- O fluxo 4K de aprovação/publicação pelo Chromium está implementado como script,
  mas **ainda não está ativado no workflow CI**. Não declarar como executado.
- Ainda faltam revisão independente de segurança/LGPD, análise de custo,
  carga, usabilidade escolar, restauração de backup e aceite por escola piloto.

**Este marco não autoriza merge automático nem publicação de dados reais.**
