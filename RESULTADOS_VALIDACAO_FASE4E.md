# Horário Inteligente — Relatório de validação Fase 4E

**Data:** 13/10/2026. **Classificação:** desenvolvimento experimental. **Não homologado para produção.**

## Escopo implementado

1. Endpoint `GET /api/tenants/{tenant_id}/publications/{publication_id}/export.xlsx` com a mesma autorização de leitura da publicação usada por PDF e CSV. Responde com tipo MIME XLSX e `Cache-Control: private, no-store`.
2. Formato Excel aberto (sem macros, fórmulas, links externos ou execução de expressões de usuário), produzido por biblioteca padrão Python e validado como arquivo XLSX. Uma aba `Resumo`, abas `Quadro Geral` (em grupos de até seis turmas) e abas próprias para cada turma; grades parciais incluem lista de pendências. Orientação de impressão A4 paisagem.
3. Interface de histórico com link Excel; alterações dos campos vigência/justificativa invalidam a pré-validação previamente exibida.
4. Testes: conteúdo da planilha, nomes de abas válidos/sem duplicatas, XML bem formado, tentativa de fórmula injetada mantida como texto, autorização do endpoint e negação de acesso entre organizações.
5. Planilha com **dados fictícios de demonstração** disponibilizada como artefato separado (`Horario_Inteligente_Exemplo_Grade_Fase4E.xlsx`). Não representa uma grade escolar produzida por solver certificado.

## Evidências efetivamente obtidas

| Verificação | Resultado |
| --- | --- |
| Backend pytest | **48 passaram**, **2 ignorados**, porque PostgreSQL não está disponível |
| Solver experimental (SciPy/HiGHS) | **16 passaram** |
| Importação XLSX por motor de planilhas independente | **PASSOU**: resumo + quadro geral + 3 turmas; conteúdo conferido |
| TypeScript sintaxe | **7 arquivos** `.ts/.tsx` da pasta `frontend/app` sem erros de parser |
| Build completo Next.js e navegação integrada | **NÃO EXECUTADOS**, dependências npm ausentes |
| Migrações/RLS e publicação concorrente em PostgreSQL real | **NÃO EXECUTADOS**, servidor indisponível |
| OR-Tools CP-SAT | **NÃO IMPLEMENTADO** |
| Política de retenção e benchmark de desempenho | **PENDENTES** |

**Não confundir teste de endpoint com homologação da operação oficial:** o teste de exportação injeta publicação fictícia num banco SQLite exclusivamente para testar o relatório e sua autorização. A função de *publicar* oficialmente continua bloqueada em SQLite e depende da validação em PostgreSQL.

## Ordem de homologação recomendada

1. Usar um PostgreSQL 16 **descartável**, sem dados escolares reais; configurar papéis `owner`/`runtime` e aplicar migrações `0001`–`0003`.
2. Executar `HI_TEST_PG_OWNER_URL` e `HI_TEST_PG_RUNTIME_URL` com `pytest -q` e validar RLS e duas publicações simultâneas. Se falhar, corrigir o código e repetir antes de liberar publicação oficial.
3. Em ambiente com npm, `cd frontend && npm install --no-audit --no-fund && npm run lint:types && npm run build`.
4. Exercitar navegador: cadastro, disponibilidade, geração, proposta, aprovação independente, publicação, consulta e exportação PDF/CSV/XLSX; conferir exportação entre unidades e contas.
5. Evoluir motor para CP-SAT e testar cenários reais, inclusive impossibilidade, bloqueios, múltiplas unidades, fusos e deslocamentos.

**Não subir em produção até conclusão dessas etapas e da revisão de segurança.**
