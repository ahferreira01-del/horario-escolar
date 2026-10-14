# Horário Inteligente — Fase 4D: resultado verificável

**Data da entrega:** 13/10/2026. **Estado:** desenvolvimento; não homologado para escolas reais.

## Alterações implementadas

1. **Verificação da carga semanal entre versões:** ao publicar uma grade de segunda e terça, o backend também considera compromissos oficiais de quarta a domingo da mesma semana ISO, mesmo que venham de outra versão com vigência não sobreposta. Isso fecha uma brecha que permitiria ultrapassar o máximo de aulas semanais de professor.
2. **Deslocamento entre unidades em dias diferentes:** aulas em dias distintos não exigem automaticamente uma matriz de deslocamento; em uma mesma jornada, o tempo mínimo continua obrigatório. Um intervalo curto que desrespeite um mínimo explicitamente configurado também é bloqueado, inclusive atravessando a meia-noite.
3. **Teste PostgreSQL real para corrida de publicação:** teste parametrizado para duas requisições concorrentes do mesmo lote, conferindo exatamente um sucesso, um conflito e apenas uma versão oficial. Só executa com os dois DSNs de uma instância efêmera de testes.
4. **Exportação oficial PDF:** nova rota autorizada `/api/tenants/{tenant_id}/publications/{publication_id}/export.pdf`, páginas A4 paisagem separadas por turma; professores, disciplinas, vigência e pendências; nova opção de download na tela de publicações.
5. **Regressões:** novos testes para limites semanais separados por versões, semanas diferentes, deslocamento interdiário e autorização do PDF.

## Evidências executadas neste ambiente

| Verificação | Resultado |
|---|---|
| Testes backend | 46 aprovados, 2 ignorados (dependem de PostgreSQL) |
| Testes do gerador experimental | 16 aprovados |
| Verificação de parser TS/TSX | 10 arquivos TS/TSX sem erros de parser; não substitui typecheck/build |
| PDF exemplo | Gerado e renderizado em 2 páginas A4 paisagem; conferido visualmente |
| PostgreSQL real/RLS/conexões simultâneas | **NÃO executado**: servidor indisponível |
| Build Next.js completo | **NÃO executado**: npm registry indisponível |
| OR-Tools CP-SAT | **NÃO implementado**: protótipo ainda em SciPy/HiGHS |

## Como completar a homologação em ambiente de testes isolado

1. Provisionar PostgreSQL 16 **descartável**, com owner e runtime separados. Fazer backup de qualquer banco existente antes de qualquer migração; nunca apontar testes de publicação para produção.
2. Aplicar as migrações Alembic `0001 -> 0003` com o usuário owner.
3. Configurar `HI_TEST_PG_OWNER_URL` e `HI_TEST_PG_RUNTIME_URL`, verificar RLS e executar `cd backend && pytest -q tests/test_postgres_rls_integration.py tests/test_phase4d_postgres_publication.py`. Este último teste cria uma organização e contas de teste e é destinado a banco efêmero.
4. Executar `pytest -q` no backend e no `solver_poc_v0_2`.
5. Executar `cd frontend && npm install --no-audit --no-fund && npm run lint:types && npm run build` em ambiente com npm disponível.
6. Testar ponta a ponta: cadastro -> convite -> turma -> disponibilidade -> proposta -> revisão por outra pessoa -> publicação concorrente -> consulta e exportação PDF.
7. Revalidar limites semanais, deslocamentos, espaço de recursos, versões futuras e acesso negado entre organizações.

## Limitações preservadas

- A prova PostgreSQL real e concorrência não foi concluída; **não liberar publicação oficial em produção**.
- O novo PDF é uma exportação de grades **já publicadas**; ainda não implementamos exportação XLSX nem publicação de versões com substituição controlada.
- Permanece necessário migrar o solver para CP-SAT e provar cobertura das regras complexas em testes reais.
- Retenção de dados, testes de desempenho, MFA, rate limiting, observabilidade e política jurídica ainda precisam ser concluídos antes de comercialização.
