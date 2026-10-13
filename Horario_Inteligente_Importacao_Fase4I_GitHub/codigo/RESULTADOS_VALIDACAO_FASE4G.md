# Horário Inteligente — Validação da Fase 4G

Data: 13/10/2026 · **Código de desenvolvimento; NÃO homologado para produção**

## Alterações implementadas nesta fase

1. `backend/app/runtime_checks.py`: endurecimento do *startup guard* de RLS do PostgreSQL. Além de ENABLE/FORCE RLS e privilégios da conta, confere políticas de isolamento, exige `NOINHERIT`, recusa políticas extras ou alteradas e detecta tabelas novas que contenham `tenant_id` sem revisão formal. O teste verifica metadados do catálogo; **não substitui teste com registros reais de tenants diferentes**.
2. `backend/tests/test_phase4g_policy_guard.py`: **7 novos casos** para o contrato de segurança RLS, incluindo política permissiva extra, expressão `OR true`, dono de tabela incorreto e leitura própria de memberships.
3. `backend/tests/test_postgres_rls_integration.py`: **1 novo teste para PostgreSQL descartável**, que introduz temporariamente uma política insegura e exige que a aplicação a rejeite. Não foi executado neste ambiente. A política de teste é removida no `finally`.
4. `scripts/smoke_http_fase4g.py`: inicializa FastAPI num subprocesso real, banco SQLite efêmero, conta local fictícia e verifica fluxo HTTP de login, convite, escola, CSRF e isolamento entre duas organizações. Não utiliza Docker e não cria dados persistentes.
5. `.github/workflows/ci.yml`: acrescentada etapa de smoke HTTP para rodar no CI; os testes PostgreSQL já existentes permanecem no mesmo job, com o servidor de serviço temporário.

## Execuções realizadas aqui

| Gate | Resultado | Escopo |
|---|---|---|
| Backend pytest | **58 PASS, 3 SKIP** | Testes unitários/funcionais locais; 3 dependem do PostgreSQL |
| Gerador experimental | **16 PASS** | SciPy/HiGHS; ainda não é CP-SAT |
| Smoke HTTP do FastAPI | **PASS** | Processo Uvicorn real + SQLite efêmero, duas organizações |
| Migrações Alembic | **PASS apenas em SQLite** | Upgrade 0001 → 0002 → 0003, sem RLS |
| Parser TypeScript/TSX | **10 arquivos / 0 erro sintático** | Não equivale a typecheck ou build |
| PostgreSQL RLS e concorrência | **NÃO EXECUTADO** | PostgreSQL/Docker indisponíveis aqui |
| Next.js typecheck/build | **NÃO CONCLUÍDO** | `node_modules` do frontend ausente; sem acesso ao npm |
| OR-Tools CP-SAT | **NÃO IMPLEMENTADO** | Motor experimental permanece SciPy/HiGHS |
| Navegador: fluxo completo | **NÃO EXECUTADO** | Depende de frontend e PostgreSQL funcionais |

**Conclusão:** houve progresso verificado na proteção de RLS e no fluxo real da API. Não existe autorização para usar dados de escolas reais ou declarar a publicação oficial homologada.

## Como reproduzir

Em uma instalação Python com dependências de `backend/requirements.txt`:

```bash
cd backend
pytest -q
cd ..
python scripts/smoke_http_fase4g.py
cd solver_poc_v0_2
pytest -q
```

Para executar **os três testes PostgreSQL** (isolation, política insegura e publicação concorrente), usar apenas PostgreSQL **descartável**, instalar as dependências, aplicar as migrações como owner e definir `HI_TEST_PG_OWNER_URL` / `HI_TEST_PG_RUNTIME_URL`; a configuração de referência encontra-se no job `backend` de `.github/workflows/ci.yml`. **Nunca apontar os testes de integração para a base de produção**.

## Próximos gates obrigatórios

1. CI verde com PostgreSQL 16, migrações, RLS e publicação concorrente; investigar e corrigir qualquer falha.
2. Instalação do Next.js e `npm run lint:types && npm run build` em ambiente com dependências.
3. Execução via Docker Compose e testes reais em navegador (login → cadastro → geração → proposta → aprovação → publicação e exportação).
4. Validação independente de limites, conflitos, deslocamentos e vigência em dados realistas; homologar publicação por grupos.
5. Integração do OR-Tools CP-SAT com provas de comportamento/diagnóstico, preservando regras rígidas.
