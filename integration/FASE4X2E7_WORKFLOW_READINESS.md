# Horário Inteligente — Fase 4X.2-E.7

**Data:** 14/10/2026
**Projeção local:** `integration/fase4x2-pr-draft`, base `1cc0ab9`
**Candidata original:** `integration/fase4x2-candidate`, `a99c2ba`
**Decisão:** **PRONTO PARA REVISÃO LOCAL; NO-GO para homologação final até executar GitHub Actions**

## Resumo

O workflow local foi preparado para o runner `ubuntu-24.04`, sem depender do Package Firewall Replit. Python usa Python 3.12, PyPI HTTPS com validação de certificado, lockfiles hashados e instalação somente de wheels. Node usa Node 22, PNPM 10.26.1, o lockfile validado em modo congelado e o registry HTTPS do npm.

PostgreSQL fica em serviço descartável do próprio job. Os gates Redis existentes iniciam contêineres Redis reais e efêmeros com credenciais exclusivas de teste; a execução falha se Docker/Compose ou os testes obrigatórios forem ignorados. Os E2Es 4H, 4J e 4K exigem os marcadores de conclusão emitidos pelos scripts.

Não executei GitHub Actions, E2Es, migrações nem serviços de banco nesta fase: isso exigiria enviar a branch. Como o pedido proíbe push, a branch remota e o PR não foram criados. **Não foi emitido `OFFICIAL_BROWSER_PASSED`.**

## Integridade e limites

| Item | Resultado |
|---|---|
| Projeção | Branch `integration/fase4x2-pr-draft`, base `1cc0ab9`; mudanças desta fase restritas a esse worktree |
| Candidata original | `integration/fase4x2-candidate`, `a99c2ba`; preservada sem alterações |
| Checkout principal | Nenhuma alteração feita por esta fase |
| GitHub remote | A referência local `github/development/fase4i-homologacao` existe em `d9ddea0`, mas `git remote -v` não lista um remote GitHub de publicação |
| Remoto/PR | Não criados: sem push autorizado e sem remote GitHub configurado |
| Produção | Nenhum acesso a Neon, banco público ou Secrets; nenhuma migration, alteração de deployment ou publicação |
| Workflow | Permissões limitadas a `contents: read`; nenhum `secrets.*` usado |

As URLs de banco definidas no workflow apontam somente para `localhost`/`127.0.0.1`, com dados e credenciais fictícios. O teste Chromium também restringe a URL à instância local.

## Configuração preparada

### Python e origem dos pacotes

- Runner explicitado como Ubuntu 24.04 e Python 3.12.
- `PIP_INDEX_URL` fixado em `https://pypi.org/simple`; `PIP_TRUSTED_HOST` e `PIP_EXTRA_INDEX_URL` vazios.
- `scripts/verify_ci_python_index.py` falha se o índice não for exatamente PyPI HTTPS, se houver host confiável/índice extra/link alternativo, se o certificado não puder ser validado ou se a resposta sair do host PyPI.
- Instalação usa `python -m pip`, `--require-hashes` e `--only-binary=:all:`; não usa o Package Firewall Replit nem aceita distribuições-fonte.
- `backend/requirements-ci.in` deriva dos requisitos do backend e acrescenta Playwright; `backend/requirements-ci.lock` fixa 58 distribuições com 1.747 hashes.
- O lock específico do solver fixa 7 distribuições com 137 hashes. Os requisitos de entrada originais continuam preservados.
- Versões diretas resolvidas do lock principal: `fastapi==0.128.2`, `redis==6.4.0`, `ortools==9.15.6755`, `playwright==1.64.0`, `numpy==2.5.4`, `scipy==1.18.1`, `pytest==9.1.1`.

### Node e navegador

- Node 22, PNPM 10.26.1 e `pnpm install --frozen-lockfile --filter ./frontend`.
- Registry fixado em `https://registry.npmjs.org/`, com validação SSL explicitamente habilitada.
- Mantidos `pnpm-lock.yaml`, `pnpm-workspace.yaml` e `.npmrc` da preparação E.6; o lock PNPM não foi alterado.
- O build CI usa `HI_NEXT_DIST_DIR=.next-production`, preserva o caminho standalone plano `frontend/.next-production/standalone/server.js` e inicia o app contra API/PostgreSQL locais.
- Chromium é instalado pela versão de Playwright travada e tem preflight headless obrigatório.

### PostgreSQL, Redis e E2Es

- PostgreSQL 16 é um serviço descartável por job, com papéis owner/runtime separados e migrações limitadas a esse serviço.
- Os testes Redis existentes iniciam Redis real via Docker, autenticado com credenciais sintéticas de teste. `HI_REQUIRE_REDIS_E2E=1` e `HI_REQUIRE_DOCKER_TESTS=1` transformam a ausência de Docker/Compose em falha, não em skip.
- Os verificadores JUnit exigem exatamente os testes PostgreSQL e Redis críticos e falham se estiverem ausentes, duplicados, ignorados ou com falha.
- 4H, 4J e 4K continuam como scripts Chromium end-to-end; cada etapa agora exige o marcador específico do script. `OFFICIAL_BROWSER_PASSED` só é registrado depois do marcador 4K e do sucesso da etapa.

## Evidências executadas nesta fase

| Verificação | Resultado |
|---|---|
| Integridade da projeção e da candidata antes da edição | **PASS**; projeção em `1cc0ab9`, candidata limpa em `a99c2ba` |
| Consulta HTTPS ao JSON do PyPI para FastAPI, Redis, OR-Tools e Playwright | **PASS**; respostas TLS verificadas e versões/requisitos disponíveis para resolução |
| Compilação do lock backend para Python 3.12/Linux com hashes via PyPI HTTPS | **PASS** |
| `pip download --require-hashes --only-binary=:all:` para wheels compatíveis com CPython 3.12/Linux x86_64 | **PASS**; 58/58 wheels do backend e 7/7 do solver |
| Guarda local do índice Python | **PASS**; aceita PyPI HTTPS e rejeita origem HTTP/host confiável |
| Validação dos gates JUnit | **PASS**; fixtures sintéticas passam e fixtures com teste obrigatório ignorado são rejeitadas |
| Lock PNPM congelado offline (`pnpm install --lockfile-only --frozen-lockfile --offline --filter ./frontend`) | **PASS**; hash do lock preservado |
| Parse YAML dos workflows e contratos estáticos | **PASS** |
| `actionlint` | **NOT AVAILABLE** neste ambiente |
| GitHub Actions no runner `ubuntu-24.04` | **NOT RUN**; nenhuma branch enviada |
| Instalação completa Node no runner e E2Es 4H/4J/4K | **NOT RUN** |
| `OFFICIAL_BROWSER_PASSED` | **NOT EMITIDO** |

### Diagnósticos encontrados

1. O primeiro download de wheels foi executado com um conjunto incompleto de tags de plataforma/ABI e não encontrou `argon2-cffi-bindings==26.1.0`. A inspeção dos artefatos oficiais mostrou wheels `abi3` para `manylinux_2_28`; após incluir essas tags, a validação compatível com Ubuntu passou para todos os 58 wheels. A falha inicial foi da simulação de tags, não evidência de pacote ausente.
2. O CLI `pip` local do Replit emitiu uma advertência de `sitecustomize` por não encontrar o módulo `pip`, embora o comando de download tenha concluído. O workflow evita essa inconsistência usando `actions/setup-python` e `python -m pip` do Python 3.12 configurado.
3. O parse YAML local passou, mas não substitui `actionlint` nem uma execução real do GitHub Actions.

## Alterações na projeção

- `.github/workflows/ci.yml`: Ubuntu 24.04, origem PyPI HTTPS, instalação Python com lock/hash e wheels, registry PNPM com SSL, saída Next `.next-production`, marcadores obrigatórios 4H/4J/4K.
- `backend/requirements-ci.in` e `backend/requirements-ci.lock`: entrada e lock de CI do backend/Playwright.
- `solver_poc_v0_2/requirements-ci.in` e `solver_poc_v0_2/requirements-ci.lock`: entrada e lock do solver legado.
- `scripts/verify_ci_python_index.py`: valida a origem PyPI e a verificação TLS antes de instalar.
- Este relatório.

## Preparação para PR — ainda não enviada

**Título sugerido:** `CI: travar dependências Python por hash e exigir E2Es 4H/4J/4K`
**Base sugerida:** `development/fase4i-homologacao` (confirmar branch/alvo no GitHub ao abrir).

**Resumo para a descrição do PR:**

> Prepara os jobs no Ubuntu 24.04 com Python 3.12 e Node 22, trava dependências Python com hashes da origem PyPI HTTPS, usa o lock PNPM congelado, mantém PostgreSQL e Redis efêmeros com dados fictícios e torna os E2Es Chromium 4H/4J/4K obrigatórios. Não inclui Secrets, Neon, banco público ou alterações de deployment. Os testes locais de resolução/lock e as verificações estáticas passaram; a execução oficial do Actions ainda precisa ocorrer no PR.

## Bloqueadores restantes

1. O remote GitHub de publicação não está configurado nesta projeção e push está explicitamente proibido; por isso ainda não há branch remota ou PR.
2. A instalação Node completa, os serviços PostgreSQL/Redis e os testes 4H/4J/4K precisam ser comprovados por uma execução real do Actions em Ubuntu 24.04.
3. A aprovação final depende de todos os jobs passarem sem skip. Em particular, `OFFICIAL_BROWSER_PASSED` só poderá ser considerado depois do sucesso real do 4K no GitHub Actions.

**Conclusão:** workflow preparado para revisão local; homologação final continua **NO-GO** até autorização para enviar a branch, abrir o PR e comprovar os gates no runner oficial.
