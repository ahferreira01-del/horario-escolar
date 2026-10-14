# Fase 4X.2-E.8 — Correções e prontidão pré-push

**Data:** 14/10/2026
**Projeção isolada:** `integration/fase4x2-pr-draft`
**Base validada:** `9a8dae2e1807d278d252e4d6c4befc2330042639`
**Ancestral indicado:** `1cc0ab902cfd552281834ae73fff48b5593c54a5`
**Candidata original preservada:** `integration/fase4x2-candidate` em `a99c2baec90722255b3d13377e679759c70a5dd7`

## Decisão

- **GO — candidata local pronta para revisão e para solicitar autorização de push/abertura de PR.**
- **NO-GO — merge, publicação e liberação de produção.** O GitHub Actions oficial ainda não foi executado; os E2Es 4H, 4J e 4K no Chromium dependem desse runner.
- A projeção continua **local, com alterações não commitadas**. Não houve push, criação/alteração de branch remota, PR, merge ou publicação.

## Integridade e isolamento

- Conferidos explicitamente o diretório de trabalho, branch e HEAD usando o gitdir da worktree.
- Projeção: `integration/fase4x2-pr-draft`, HEAD `9a8dae2e1807d278d252e4d6c4befc2330042639`.
- Candidata original: `integration/fase4x2-candidate`, HEAD `a99c2baec90722255b3d13377e679759c70a5dd7`, limpa e sem alterações.
- A raiz GitHub continua sendo o checkout plano da projeção, onde `.github/workflows/ci.yml` está localizado na raiz correta.
- A instalação Python foi feita em diretório temporário com `--target`; o PostgreSQL nativo 17.5 usou diretório e socket temporários, TCP limitado a `127.0.0.1:5432`, usuários/senhas sintéticos e remoção ao terminar. Os testes Redis iniciaram serviços reais descartáveis com credenciais de teste.
- Não houve conexão ao Neon ou ao banco de produção. Nenhuma Secret foi lida, modificada ou exibida.
- Nenhum workflow Replit foi reiniciado ou alterado; nenhum deployment público foi acessado para escrita.

## Correções aplicadas na projeção

| Área | Arquivos | Resultado |
|---|---|---|
| CI GitHub | `.github/workflows/ci.yml`, `.github/workflows/source-check.yml` | Actions fixadas em SHA completo; `workflow_dispatch` seguro; job dedicado para build/startup nos dois layouts; permissão `contents: read`. |
| PostgreSQL de teste | `.github/workflows/ci.yml`, `backend/tests/conftest.py`, `backend/tests/test_phase4i_ci_and_timezones.py` | As migrações continuam usando a conexão owner. A suíte de API agora usa a conexão runtime de menor privilégio; o guard permite somente os dois URLs locais sintéticos previamente validados. |
| Alembic | `backend/alembic/env.py`, `backend/app/db_base.py`, `backend/app/database_urls.py`, `backend/app/config.py`, `backend/app/database.py`, `backend/app/models.py`, `backend/tests/test_phase4x2e8_migration_config.py` | A configuração de migração de produção usa `HI_MIGRATION_DATABASE_URL` sem importar as configurações de runtime. A API continua falhando fechada quando `HI_RUNTIME_DATABASE_URL` está ausente. |
| Testes de layout | Removido `backend/tests/test_production_routing_startup.py`; adicionados `integration/replit-tests/README.md`, `integration/replit-tests/test_replit_artifact_routes.py` e `scripts/smoke_production_startup_layouts.py` | Verificações que dependem dos artefatos Replit não são mais coletadas no `pytest` backend do checkout GitHub plano. Os manifestos Replit continuam verificáveis separadamente; o smoke temporário testa build, frontend, rota de saúde e falha fechada do backend nos layouts plano e aninhado. |
| Standalone Next | `build-production.sh`, `start-production.sh` | Detectam a saída flat do GitHub ou a saída aninhada do Replit, mantendo `HI_NEXT_DIST_DIR=.next-production`; bind para loopback é configurável somente no smoke test e o padrão de produção permanece `0.0.0.0`. |
| Proteção de arquivos | `.gitignore`, `backend/tests/test_sensitive_gitignore.py` | Restaurados padrões para arquivos operacionais `.env`, dumps/backups e temporários; exemplos `.env.example` continuam permitidos. |
| Imagens | `docker-compose.yml`, `docker-compose.production.yml`, `backend/tests/test_phase4w_redis_live.py` | Postgres e Redis fixados por digest OCI em vez de tags mutáveis. |
| Contratos CI | `backend/tests/test_phase4i_ci_and_timezones.py` | Verifica os gatilhos, SHAs, imagens, URLs runtime, ordem dos E2Es e marcadores obrigatórios de execução. |

### Referências imutáveis verificadas

As referências abaixo foram confirmadas por tags dos repositórios oficiais do GitHub e metadados OCI do Docker Registry:

- `actions/checkout` v4.4.0 — `11d5960a326750d5838078e36cf38b85af677262`
- `actions/setup-python` v5.6.0 — `a26af69be951a213d495a4c3e4e4022e16d87065`
- `actions/upload-artifact` v4.6.2 — `ea165f8d65b6e75b540449e92b4886f43607fa02`
- `actions/setup-node` v4.4.0 — `49933ea5288caeca8642d1e84afbd3f7d6820020`
- `pnpm/action-setup` v4.4.0 — `fc06bc1257f339d1d5d8b3a19a8cae5388b55320`
- `postgres:16` — `sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d`
- `postgres:16-alpine` — `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`
- `redis:7-alpine` — `sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`

O Caddy do Compose de produção ainda usa `caddy:2-alpine`; não foi alterado porque o escopo solicitado para digest cobre PostgreSQL e Redis. É um risco residual de reprodutibilidade da imagem Caddy, não um bloqueio da CI nesta fase.

## Evidências de validação

| Verificação | Resultado comprovado |
|---|---|
| Instalação Python para o runner configurado | **PASS.** Python 3.12.12; `scripts/verify_ci_python_index.py` retornou `CI_PYPI_TLS_VERIFIED`. Instalação de `backend/requirements-ci.lock` com `--require-hashes --only-binary=:all:` via `https://pypi.org/simple`, validação TLS habilitada e sem `trusted-host`. |
| Dependências instaladas pelo lock Python | **PASS.** Incluiu FastAPI 0.128.2, Redis 6.4.0, OR-Tools 9.15.6755 e Playwright 1.64.0. Instalação limitada a um diretório temporário; nenhum arquivo de dependências foi alterado. |
| Frontend / lockfile | **PASS.** `pnpm install --frozen-lockfile --filter ./frontend` terminou com lockfile atualizado; `pnpm-lock.yaml` não foi alterado. |
| Python, YAML e shell | **PASS.** `compileall`, `bash -n` e parse YAML dos workflows e Compose passaram. `git diff --check` passou. |
| Contratos de CI e `.gitignore` | **PASS.** Quatro testes focados passaram, incluindo ações por SHA, imagens por digest, trigger manual, URL runtime e padrões de exclusão. |
| PostgreSQL e Redis reais | **PASS.** Suíte backend: **247 passed, 0 failed**, 7 warnings. PostgreSQL 17.5 descartável, migrações executadas, runtime `NOINHERIT` e RLS; verificadores registraram `CI_POSTGRES_GATES_PASS` para 5 gates críticos e `CI_REDIS_GATES_PASS` para 3 gates reais/autenticados. |
| Build e inicialização de produção | **PASS.** `scripts/smoke_production_startup_layouts.py` retornou `PRODUCTION_STARTUP_FLAT_PASSED`, `PRODUCTION_STARTUP_REPLIT_PASSED` e `PRODUCTION_STARTUP_LAYOUTS_PASSED`. Incluiu health check HTTP e falha fechada quando a API fica indisponível. |
| Manifestos dos artefatos Replit | **PASS.** A suíte isolada `integration/replit-tests` passou: **1 passed**, lendo os manifestos do workspace sem incorporá-los à coleta backend do GitHub. |
| GitHub Actions oficial / E2E Chromium 4H, 4J e 4K | **NOT TESTED.** O workflow estático exige os três scripts e seus marcadores; Chromium e Playwright estão configurados. Não houve push/PR, logo nenhum runner oficial executou esses E2Es. Nenhum marcador oficial de navegador foi afirmado nesta homologação local. |

## Falhas encontradas e resolução

1. A primeira verificação com Python 3.12 gerenciado por `uv` falhou na cadeia de certificados local. A causa foi o interpretador isolado não localizar automaticamente o bundle de CA do sistema. A execução foi repetida apontando `SSL_CERT_FILE`/`PIP_CERT` para o bundle confiável do sistema; a validação TLS passou. Nenhuma verificação foi desativada.
2. Uma tentativa diagnóstica com `docker exec` direto em um PostgreSQL descartável retornou erro OCI `setns`; o contêiner estava em estado running. Para a suíte PostgreSQL foi usado o binário PostgreSQL nativo descartável com socket em `/tmp`, loopback e cleanup. Os testes Redis reais e Compose passaram no gate da suíte.
3. A primeira suíte completa encontrou que a API de teste iniciava com a conexão owner, incompatível com a checagem de menor privilégio; o teste de migração offline também encontrou uma migration que consulta `connection.scalar`; e a checagem de exemplo no `.gitignore` estava usando o ponteiro Git incorreto da worktree. A CI foi ajustada para usar runtime após migrar com owner, a prova de Alembic passou para conexão online no PostgreSQL efêmero e o teste de ignore passou a aceitar o gitdir explícito da worktree. Reexecução final: **247/247 testes passaram**.

## Diferenças preservadas

- Estrutura Replit `horario-escolar/`, layout GitHub plano, `.replitignore`, `HI_NEXT_DIST_DIR=.next-production` e saída standalone foram preservados.
- O projeto não foi fundido entre históricos sem ancestral comum.
- O deployment público, seus Secrets e o Neon de produção permaneceram intocados.
- A branch candidata original e o conteúdo remoto não foram substituídos.
- Não foram usados mocks para substituir PostgreSQL ou Redis nos gates que exigem serviços reais.
- O relatório anterior `integration/FASE4X2E7_REVISAO_PRE_PUSH.md` foi mantido sem alterações.

## Bloqueadores e próximos gates

1. É necessária autorização explícita para enviar a branch local e abrir PR; isso não foi feito.
2. O CI oficial do GitHub ainda precisa executar em runner Ubuntu com Python 3.12, Node 22, Postgres 16, Redis e Chromium/Playwright. O teste local com PostgreSQL 17.5 não substitui esse gate.
3. A aprovação de 4K só pode ser registrada após execução bem-sucedida do script oficial no GitHub Actions.
4. Ainda não há decisão de merge ou publicação; ambas permanecem fora do escopo e exigem autorização própria.

**Resumo final:** a projeção isolada está tecnicamente preparada e passou nos testes locais disponíveis. O estado permanece **NO-GO para release** até os gates oficiais no GitHub e a revisão humana da PR.
