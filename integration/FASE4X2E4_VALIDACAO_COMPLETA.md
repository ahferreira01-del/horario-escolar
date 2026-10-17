# Horário Inteligente — Fase 4X.2-E.4: Certificação local

**Data:** 14/10/2026
**Decisão:** **NO-GO** para solicitar autorização de envio da projeção ao GitHub
**Projeção:** `integration/fase4x2-pr-draft`, commit de entrada `058eb814800bb96423fbddaca9db0ec7cba9341a`
**Candidata preservada:** `integration/fase4x2-candidate`, `a99c2baec90722255b3d13377e679759c70a5dd7`

## Resumo

Foram executados gates independentes com PostgreSQL descartável, Redis real via Docker Compose, testes locais de SMTP/TLS e o contrato estático do CI. Os testes selecionados passaram.

A suíte Python completa não pôde iniciar os testes: a coleta terminou com 19 erros de importação (15 por falta do pacote `redis` e 4 por falta de `ortools`). A tentativa de instalar as dependências em diretório temporário falhou porque o contêiner não conseguiu resolver o endereço do índice de pacotes. O frontend não tem lockfile nem `node_modules`; portanto não foi possível realizar a instalação congelada, o build standalone ou os E2Es 4H/4J/4K sem inventar uma resolução de dependências.

`OFFICIAL_BROWSER_PASSED` **não foi emitido**. O E2E 4K não foi executado.

## Integridade e isolamento

- As branches e commits foram confirmados antes dos testes: projeção `058eb81…`; candidata `a99c2ba…`.
- Os worktrees da projeção e da candidata estavam sem o arquivo `.git` de backlink. Os registros administrativos únicos apontavam para as duas pastas esperadas. Os backlinks foram reconstruídos apontando para seus diretórios administrativos correspondentes; raiz, branch, HEAD e status foram novamente conferidos.
- A candidata permaneceu no commit `a99c2ba…`, limpa e sem alterações de código.
- A projeção permaneceu no commit `058eb81…`, limpa após os testes; este relatório é o único arquivo novo da Fase 4X.2-E.4.
- O checkout principal não foi editado nesta fase. No preflight estava em `main` (`045e74c`), com o arquivo de instruções anexado pelo usuário ainda não rastreado.
- PostgreSQL de teste: contêiner `postgres:16-alpine`, database sintético, publicado somente em `127.0.0.1:5432`, com papéis owner/runtime descartáveis. Migrações executadas somente nessa instância.
- Redis Compose: projeto temporário e credenciais sintéticas; o teste não publicou portas.
- O contêiner PostgreSQL e sua rede temporária foram removidos ao final. Não restaram contêineres de teste ativos.
- Não houve acesso ao Neon, alteração de Secrets, dados escolares reais, publicação, push ou merge. Nenhum workflow do Replit foi parado ou reiniciado.

## Inventário relevante

| Componente | Estado observado |
|---|---|
| Backend | `backend/requirements.txt`, `backend/pytest.ini`, Alembic e testes disponíveis na projeção. |
| Frontend | `frontend/package.json` e `frontend/next.config.ts`; Next standalone configurado e aceita `HI_NEXT_DIST_DIR`. |
| Lockfile frontend | **Ausente**: não há `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml` ou `yarn.lock` na projeção. |
| Dependências frontend instaladas | **Ausentes**: `frontend/node_modules` não existe. |
| CI | Usa Python 3.12 e Node 22. A instalação frontend atual é `npm install`, não `npm ci` com lockfile congelado. |
| Runtime local | Python 3.13.11, Node 24.13.0, pnpm 10.26.1, Docker 27.5.1 e Docker Compose 2.36.0. |
| Recursos | 4 CPUs, aproximadamente 4.2 GiB de memória disponível e 32 GiB livres em `/tmp`. |
| Portas no preflight | 3000 e 8000 já estavam atendidas pelos workflows existentes. 5432, 6379, 1025 e 8025 estavam sem listener. A verificação foi feita por conexão TCP; `ss` não está instalado. |

O diretório temporário de evidências foi `/tmp/hi-fase4x2e4.gajoQY`, com subpastas para Python, frontend, Playwright, logs e artefatos. O frontend foi copiado para esse espaço; nenhuma instalação ou alteração de manifest foi feita no worktree.

## Matriz de validação

| Gate | Resultado | Evidência |
|---|---|---|
| Integridade dos worktrees e commits | **PASS** | Identidade confirmada e ambos limpos após reconstrução dos backlinks administrativos. |
| PostgreSQL descartável e migrações | **PASS** | Conexão TCP/autenticada à instância local; `alembic upgrade head` concluiu. |
| Testes PostgreSQL, RLS e troca de papel | **PASS** | 11 testes passaram em 1,03 s, com `HI_REQUIRE_TEST_POSTGRES=1` e Docker obrigatório. JUnit: `logs/postgres-critical.xml`. |
| Redis de produção via Compose | **PASS** | 1 teste passou em 13,70 s; verificou estado healthy/running, `PONG` autenticado e `NOAUTH` sem autenticação. JUnit: `logs/redis-compose.xml`. |
| SMTP/TLS unitário | **PASS** | 3 testes passaram em 0,15 s; validaram o contexto TLS com verificação de certificado e o comportamento sem SMTP. O transporte foi substituído por stub: não prova entrega por um servidor SMTP real. |
| Contrato estático do CI | **PASS** | `test_phase4h_ci_gate.py`: 1 passou em 0,04 s. |
| Instalação temporária das dependências Python | **BLOCKED** | A imagem Python 3.13 foi obtida, mas `pip` não conseguiu resolver o índice (`Temporary failure in name resolution`) e encerrou sem instalar as dependências requeridas. Nenhuma instalação global foi feita. |
| Suíte Python completa | **FAIL na coleta / BLOCKED** | `pytest -q` terminou com código 2 e 19 erros de coleta: 15 imports de `redis` e 4 de `ortools`. A coleta separada identificou 123 testes, mas a execução integral foi interrompida antes de executá-los. Log: `logs/full-pytest.log`; coleta: `logs/full-collect.log`. |
| Gate Redis da aplicação (limite de tentativas/login) | **BLOCKED** | O teste real da aplicação depende do pacote Python `redis`, ausente. Não foi substituído por mock. O teste Compose de serviço acima não é evidência de integração Redis da aplicação. |
| Instalação frontend congelada | **BLOCKED** | Não existe lockfile aprovado para `npm ci`/instalação congelada. Não foi criado lockfile no projeto nem instalada uma resolução arbitrária. |
| Build standalone e TypeScript | **NOT TESTED** | Dependências frontend não instaladas. |
| Chromium 4H, 4J e 4K | **NOT TESTED** | Playwright não está instalado; o frontend não pode ser instalado de forma congelada a partir da projeção atual. |
| `/api/health`, `/api/ready` e `/api/release` | **NOT TESTED** | O backend candidato não foi iniciado: imports da suíte mostram que a dependência `redis` requerida está indisponível. |
| `OFFICIAL_BROWSER_PASSED` | **NOT EMITIDO** | 4K não terminou com sucesso; nenhum marcador local ou oficial foi declarado. |
| SMTP real/entrega de convite | **NOT TESTED** | Os testes aprovados verificaram a política TLS com stub; não houve relay SMTP sintético ativo nem relay externo de homologação. |

### Erro operacional observado

O primeiro probe de readiness por `docker exec pg_isready` retornou erro OCI de `setns`. O contêiner permaneceu ativo; a conexão PostgreSQL autenticada via TCP e as migrações foram bem-sucedidas, confirmando a disponibilidade pelo caminho usado pelos testes. O contêiner descartável foi removido após a execução.

## Arquivos e commits

- Arquivo novo nesta fase: `integration/FASE4X2E4_VALIDACAO_COMPLETA.md`.
- Não foram alterados código da aplicação, manifests, lockfiles, configurações de CI ou arquivos da candidata.
- A projeção já continha o endurecimento CI da Fase 4X.2-E.3 no commit `37d0d78…`; esta fase não criou novo commit de aplicação.
- Este relatório está registrado em commit **local da projeção**, sem push.

## Pendências para fechar a certificação local

1. Disponibilizar uma fonte de pacotes acessível ao ambiente isolado sem reiniciar os workflows ativos; instalar requirements e Playwright somente em diretórios temporários.
2. Resolver a ausência de lockfile frontend em uma etapa autorizada e separada; então instalar de modo congelado, executar TypeScript e o build standalone com `HI_NEXT_DIST_DIR=.next-production`.
3. Reexecutar a suíte Python completa sob a versão alinhada ao CI, com PostgreSQL efêmero e Redis autenticado real, e validar os verificadores JUnit sem skips dos gates obrigatórios.
4. Inicializar a candidata isolada com serviços sintéticos, verificar `/api/health`, `/api/ready` e `/api/release`, e executar 4H, 4J e 4K no Chromium.
5. Emitir `OFFICIAL_BROWSER_PASSED` somente se 4K local terminar com sucesso. Isso continua sendo evidência local; o gate oficial do GitHub Actions permanece pendente.
6. Fazer uma prova SMTP/TLS com relay sintético ativo se a Fase F exigir comprovação de entrega; os testes stub atuais só atestam a configuração TLS do cliente.

**Conclusão:** os gates independentes comprovados passaram, mas a certificação integral não foi concluída. A projeção não está autorizada para envio ao GitHub nesta fase (**NO-GO**).
