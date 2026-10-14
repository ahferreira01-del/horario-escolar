# Horário Inteligente — Fase 4X.2-E.3: endurecimento do CI

**Data:** 14/10/2026
**Branch local de PR:** `integration/fase4x2-pr-draft`
**Base da projeção:** `d9ddea00c98dc8b1278f493963d24b1e9132018c`
**Commit de endurecimento:** `37d0d78b1762f4be7d7ea6ad8ac56cdbe1b80350`
**Decisão:** **NO-GO para solicitar autorização de envio neste momento**

## Resumo

O CI da projeção agora usa PostgreSQL descartável também como `DATABASE_URL` padrão do `pytest`, valida que os URLs owner/runtime apontem apenas para a instância local de teste, exige Docker/Compose e falha se os gates PostgreSQL ou Redis obrigatórios forem ignorados. O job de browser valida que Chromium inicia e executa 4H, 4J e 4K na mesma aplicação integrada ao PostgreSQL descartável. `OFFICIAL_BROWSER_PASSED` só é escrito no job quando o passo 4K conclui com sucesso e os passos anteriores também passaram.

SQLite permanece apenas em testes auxiliares explicitamente identificados: unidade com banco em memória e o smoke HTTP complementar com arquivo temporário. Não é usado como fallback do job de integração PostgreSQL.

Os testes possíveis passaram: migrações PostgreSQL descartáveis e 11 testes selecionados de segurança/RLS/role; também passou o teste Compose de Redis real autenticado. A execução local da suíte completa parou na coleta porque este ambiente não tem o módulo Python `redis`; os E2Es não puderam ser executados porque faltam Playwright e `frontend/node_modules`. O binário do Chromium está instalado, mas isso não substitui a biblioteca/harness de browser. Não instalei dependências nem reiniciei workflows ativos.

## Matriz de testes e serviços

| Grupo | Banco/serviço | Regra do CI | Evidência local nesta etapa |
|---|---|---|---|
| Migrações e configuração de schema | PostgreSQL 16 descartável | Serviço obrigatório; migration falha se indisponível | **PASS** — `alembic upgrade head` executou as migrações `0001`–`0003` num contêiner temporário. |
| RLS, isolamento entre organizações e role runtime | PostgreSQL 16 descartável | `HI_REQUIRE_TEST_POSTGRES=1`; URLs fixos de loopback; verificador rejeita ausentes, skips, falhas e duplicatas dos testes críticos | **PASS parcial** — 11 testes selecionados passaram, incluindo segurança dos URLs, RLS, policy insegura e role runtime. |
| Publicação concorrente e exportações com negação cruzada | PostgreSQL 16 descartável | Fazem parte dos casos críticos verificados no JUnit do CI | **BLOCKED local** — dois módulos não puderam ser coletados porque importam `redis`, ausente neste runtime. Não contam como aprovados. |
| Limite de login distribuído e falha fechada | Redis 7 real, descartável e autenticado via Docker | `HI_REQUIRE_REDIS_E2E=1`; testes reais incluídos no `pytest`; verificador exige exatamente os dois casos Redis, sem skip/falha | **BLOCKED local** — o runtime não tem o pacote Python `redis`; a suíte completa parou na coleta antes desses casos. O GitHub Actions instala `backend/requirements.txt`; somente a execução remota provará o gate completo. |
| Redis do Compose de produção, senha e healthcheck | Redis real via Docker Compose temporário | `HI_REQUIRE_DOCKER_TESTS=1`; sem Docker/Compose o job falha | **PASS** — 1 teste passou, incluindo `PONG` autenticado e `NOAUTH` sem autenticação. O Compose foi desmontado pelo teste. |
| Chromium 4H, 4J e 4K | Chromium real + frontend/API + PostgreSQL descartável | Preflight lança Chromium; scripts 4H → 4J → 4K executam em sequência, sem fallback para skip | **BLOCKED local** — falta Playwright e `frontend/node_modules`. |
| Smoke HTTP auxiliar | SQLite em arquivo temporário | Passo separado e identificado como “SQLite, complementar” | Mantido deliberadamente como auxiliar, sem prova de RLS. |
| Testes unitários de `test_app.py` | SQLite em memória | Identificados no módulo como unitários; não comprovam RLS/integração | Auxiliares; não são aceitos como evidência PostgreSQL. |
| Verificações de configuração que contêm URI SQLite como dado | Nenhuma conexão SQLite | Testam a validação de uma string, sem abrir banco | Auxiliares; não são prova de integração. |
| `solver_legacy` | Nenhum serviço PostgreSQL/Redis/browser | Job separado de solver legado | Fora da homologação funcional do app. |

### Política de skip e falha

- Os testes PostgreSQL podem continuar sendo executados em modo de desenvolvimento sem URLs e então reportar o motivo do skip. No CI, `HI_REQUIRE_TEST_POSTGRES=1` faz o `conftest` falhar antes da coleta se owner/runtime estiverem ausentes ou se `DATABASE_URL` não for exatamente o owner descartável. O verificador `verify_ci_pg_fase4h.py` rejeita skip, falha, ausência ou duplicidade nos casos críticos.
- Os testes Redis podem ser opcionais fora do gate CI. No workflow, `HI_REQUIRE_REDIS_E2E=1` e `HI_REQUIRE_DOCKER_TESTS=1` tornam a ausência do Docker, daemon ou Compose um erro explícito. O verificador `verify_ci_redis_fase4w.py` rejeita os três casos Redis obrigatórios ausentes, ignorados, falhos ou duplicados.
- O teste Compose da Fase 4U ainda tem uma condição de skip para uso local sem Docker. No job CI, o preflight da sessão exige Docker/Compose antes da coleta, portanto essa condição não pode produzir uma aprovação silenciosa.
- Os scripts 4H/4J/4K não têm modo skip. O preflight Chromium falha antes dos scripts se o browser real não puder iniciar.

## Alterações realizadas

Commit `37d0d78…`, filho direto do commit de projeção `944e62073ba498a5b49bd05928f280528f4b5ed3`:

- `.github/workflows/ci.yml`
  - `DATABASE_URL` do `pytest` alterada de SQLite para PostgreSQL owner descartável.
  - Adicionados flags obrigatórios de PostgreSQL, Docker/Compose e Redis.
  - Adicionado o gate JUnit Redis.
  - Adicionado preflight de inicialização Chromium e marcador 4K condicional ao sucesso.
- `backend/tests/conftest.py` e `backend/tests/postgres_test_safety.py`
  - Falha explícita para URLs PostgreSQL ausentes/inseguros no modo obrigatório.
  - Falha explícita se `DATABASE_URL` não for o PostgreSQL owner local.
  - Verificação do Docker CLI, daemon e Compose no modo CI obrigatório.
- `backend/tests/test_postgres_rls_integration.py`
  - Skip local condicionado ao modo opcional; gate CI não pode ignorar os testes.
- `backend/tests/test_phase4w_redis_live.py` e `backend/tests/test_phase4w_production_redis_compose.py`
  - A ausência do Docker falha no gate Redis obrigatório; o Compose deixa de ter skip automático no CI.
- `backend/tests/test_postgres_test_safety.py`
  - Testes para ausência de URLs no modo obrigatório e para impedir skip no CI.
- `backend/tests/test_app.py`
  - Identificação explícita do SQLite em memória como unidade auxiliar.
- `scripts/verify_ci_redis_fase4w.py` (novo)
  - Valida no JUnit a execução sem skips dos dois testes Redis live e do teste Redis Compose.

Não alterei lógica de runtime da aplicação, arquivos de dependências, Secrets, Neon, banco, deployment, workflow Replit, branch principal ou workflow remoto.

## Validações e resultados

**Passaram:**

- Parser YAML e verificações de presença das variáveis PostgreSQL locais, flags obrigatórias, ordem 4H → 4J → 4K e condição do marcador.
- Sintaxe Python dos arquivos modificados e `git diff --check`.
- `pytest tests/test_postgres_test_safety.py`: **8 passed**.
- PostgreSQL descartável `postgres:16-alpine`, roles owner/runtime e `alembic upgrade head`: **PASS**.
- PostgreSQL/RLS/role selecionados no contêiner temporário: **11 passed**.
- `pytest tests/test_phase4w_production_redis_compose.py`: **1 passed**.
- Preflight de sessão com `HI_REQUIRE_DOCKER_TESTS=1`: **8 passed**.
- Contêineres descartáveis removidos ao final dos comandos/testes.

**Bloqueios de execução local:**

- A tentativa de coletar os testes críticos de publicação e o Redis live terminou com `ModuleNotFoundError: No module named 'redis'`. O pacote consta em `backend/requirements.txt`, que o GitHub Actions instala, mas não está instalado neste runtime. Não instalei pacotes porque isso poderia reiniciar os workflows atualmente ativos.
- Playwright e `frontend/node_modules` não estão instalados neste workspace. Não executei 4H/4J/4K localmente nesta etapa.
- Não houve execução GitHub Actions; nenhum push foi autorizado. O marcador `OFFICIAL_BROWSER_PASSED` **não foi emitido**.

## Diferenças entre candidata e projeção

- A candidata `integration/fase4x2-candidate` permanece sem alterações em `a99c2baec90722255b3d13377e679759c70a5dd7`.
- A projeção local começou em `944e620…`; o endurecimento está em `37d0d78…`. A projeção segue baseada no commit GitHub `d9ddea00…` e não foi mesclada com o histórico independente da candidata.
- Em relação à subárvore `horario-escolar` da candidata, o endurecimento acrescentou **8 arquivos modificados e 1 arquivo novo** (`scripts/verify_ci_redis_fase4w.py`). Nenhum arquivo da candidata está ausente na projeção; os 16 arquivos exclusivos da referência GitHub continuam preservados.
- A projeção continua local e limpa após o commit. Não enviei commits, abri PR, fiz merge ou deploy.

## Decisão

**NO-GO para solicitar autorização de envio ao GitHub agora.** O workflow e os guardas foram endurecidos, mas a verificação completa ainda não foi comprovada neste ambiente: os testes Redis live e os casos críticos de publicação não foram coletados por falta do módulo `redis`, e os três E2E não foram executados por falta do Playwright e das dependências frontend. A execução oficial do Actions e do 4K continua pendente; só ela poderá gerar `OFFICIAL_BROWSER_PASSED`.
