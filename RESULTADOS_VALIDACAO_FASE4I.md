# Horário Inteligente — Resultado de validação da Fase 4I

Data: 13/10/2026

## Executados

- Backend: **70 aprovados e 5 ignorados** (os cinco dependem de PostgreSQL real).
- Gerador legado: **16 aprovados** em conjunto separado de testes.
- Smoke HTTP da API: **PASS** em SQLite efêmero, com autenticação, CSRF, convite e negação entre organizações.
- Contrato estático do job integrado (PostgreSQL + RLS + Chromium): **PASS**, sem execução do job remoto.
- Testes novos de deslocamento entre escolas na virada do dia e sobreposição de horários UTC: **PASS**.
- Parse do frontend TypeScript/TSX: **sem erros de parser**, não equivale à compilação Next.js.

## Não executados / não concluídos

- PostgreSQL 16, migrações nesse banco, isolamento RLS, teste transacional e concorrência: **NÃO EXECUTADOS**.
- Build completo do frontend Next.js e fluxo real no Chromium contra PostgreSQL: **NÃO EXECUTADOS**.
- OR-Tools CP-SAT: **NÃO IMPLEMENTADO**.

## Conclusão

**Fase 4I implementada, parcialmente validada em ambiente local, não homologada para produção.** A próxima etapa obrigatória é executar o workflow em um ambiente de homologação descartável com PostgreSQL e navegador instalados. Não existe evidência de publicação real sem conflitos sob concorrência PostgreSQL nesta entrega.
