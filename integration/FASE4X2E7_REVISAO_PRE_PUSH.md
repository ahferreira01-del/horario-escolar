# Horário Inteligente — Revisão independente pré-push da Fase 4X.2-E.7

**Data:** 14/10/2026
**Projeção:** `integration/fase4x2-pr-draft`
**Commit auditado:** `9a8dae2e1807d278d252e4d6c4befc2330042639`
**Pai imediato:** `1cc0ab902cfd552281834ae73fff48b5593c54a5`
**Referência GitHub:** `ahferreira01-del/horario-escolar`, `development/fase4i-homologacao`
**HEAD remoto consultado:** `d9ddea00c98dc8b1278f493963d24b1e9132018c`
**Decisão:** **NO-GO para autorizar push e PR rascunho neste estado**

## Escopo e método

Revisão independente e somente leitura da projeção e da referência GitHub. A referência foi consultada por clone raso somente leitura em `/tmp`; nenhum ref remoto foi atualizado no worktree. A comparação foi feita entre as árvores completas dos dois commits, sem merge ou aplicação de alterações.

Não foram instaladas dependências, executados testes, alterados workflows, lidos Secrets, acessados Neon/banco de produção, enviados commits, criados PRs ou publicados artefatos. O único arquivo gravado nesta revisão é este relatório.

## 1. Integridade e inventário

| Verificação | Resultado |
|---|---|
| Branch e HEAD da projeção | `integration/fase4x2-pr-draft`, `9a8dae2e1807d278d252e4d6c4befc2330042639` |
| Pai imediato | `1cc0ab902cfd552281834ae73fff48b5593c54a5` |
| Estado inicial da projeção | Limpo; zero arquivos modificados ou não rastreados |
| Relação com a referência | O commit remoto `d9ddea00c98dc8b1278f493963d24b1e9132018c` é ancestral da projeção |
| Candidata original | `integration/fase4x2-candidate`, `a99c2baec90722255b3d13377e679759c70a5dd7`, limpa e preservada |
| Contagem das árvores | Projeção: 165 arquivos rastreados; referência: 144 |
| Diferenças de caminho/conteúdo | 14 caminhos modificados, 21 exclusivos da projeção, zero exclusivos da referência |
| Arquivos da referência removidos | Nenhum |

### Arquivos modificados em relação à referência

1. `.github/workflows/ci.yml`
2. `.gitignore`
3. `README.md`
4. `backend/alembic/env.py`
5. `backend/app/config.py`
6. `backend/tests/test_app.py`
7. `backend/tests/test_phase4w_production_redis_compose.py`
8. `backend/tests/test_phase4w_redis_live.py`
9. `backend/tests/test_postgres_rls_integration.py`
10. `frontend/next.config.ts`
11. `ops/preflight_production.py`
12. `scripts/smoke_browser_fase4h.py`
13. `scripts/smoke_browser_publication_fase4k.py`
14. `scripts/smoke_browser_school_fase4j.py`

### Arquivos exclusivos da projeção

1. `.npmrc`
2. `backend/requirements-ci.in`
3. `backend/requirements-ci.lock`
4. `backend/tests/conftest.py`
5. `backend/tests/postgres_test_safety.py`
6. `backend/tests/test_postgres_test_safety.py`
7. `backend/tests/test_production_routing_startup.py`
8. `build-production.sh`
9. `integration/FASE4X2E3_CI_HARDENING.md`
10. `integration/FASE4X2E4_VALIDACAO_COMPLETA.md`
11. `integration/FASE4X2E5_DEPENDENCIAS.md`
12. `integration/FASE4X2E6_PYTHON_ENV.md`
13. `integration/FASE4X2E7_WORKFLOW_READINESS.md`
14. `pnpm-lock.yaml`
15. `pnpm-workspace.yaml`
16. `scripts/phase4x2d_test_support.py`
17. `scripts/verify_ci_python_index.py`
18. `scripts/verify_ci_redis_fase4w.py`
19. `solver_poc_v0_2/requirements-ci.in`
20. `solver_poc_v0_2/requirements-ci.lock`
21. `start-production.sh`

Não há arquivo que existia somente na referência e tenha sido removido da projeção. Os arquivos funcionais, de configuração e documentação da referência continuam presentes; os 14 itens modificados acima foram revisados por diff.

### Diffs funcionais e de configuração

- **CI:** substitui a instalação Python não travada por PyPI HTTPS, locks com hashes e wheels; usa Node 22/PNPM 10.26.1 e lockfile congelado; mantém o build Next em `.next-production`; troca SQLite por PostgreSQL efêmero nos testes de integração; torna os testes Redis reais obrigatórios no job; executa 4H, 4J e 4K em sequência no Chromium e verifica marcadores explícitos.
- **E2E 4H/4J/4K:** limita a URL da candidata a loopback ou host `.invalid` autorizado; lê convites de SMTP sink local quando configurado; 4K faz chamadas autenticadas dentro do contexto do navegador, incluindo CSRF, e verifica publicação/exportações. Não identifiquei remoção de asserções de autorização no diff revisado.
- **PostgreSQL/RLS e Redis:** as alterações em testes passam a falhar, em vez de ignorar os gates, quando o CI define as variáveis obrigatórias. Foram adicionadas guardas para rejeitar URLs PostgreSQL remotas nos testes.
- **Configuração de produção:** separa `HI_RUNTIME_DATABASE_URL` da URL de migração `HI_MIGRATION_DATABASE_URL`; exige runtime PostgreSQL, configuração de sessão/cookies, Redis autenticado e SMTP no arranque. Há, porém, a dependência operacional descrita no achado P1-2.
- **Next.js/Replit:** adiciona `HI_NEXT_DIST_DIR` e detecção da estrutura de workspace para manter `.next-production` e o standalone apropriados ao layout. O teste de startup adicionado não está isolado do layout Replit, conforme P1-1.
- **Preflight operacional:** a diferença é essencialmente formatação; não identifiquei alteração de regra funcional nesse arquivo.
- **README:** documenta os novos papéis runtime/migrator e a separação das URLs. A instrução de execução da migration não corresponde integralmente ao requisito de configuração de `app.config`, conforme P1-2.
- **Solver:** não há alteração no código do solver nem no seletor de algoritmo; o diff inclui somente locks/requisitos de CI do solver legado. A implementação padrão MILP/HiGHS permanece igual à referência.

## 2. Workflows, permissões e gates

### Triggers e permissões

- `.github/workflows/ci.yml`: `push` e `pull_request`; não define `workflow_dispatch`.
- `.github/workflows/source-check.yml`: `push` limitado à branch `development/fase4i-homologacao`, `pull_request` para `main` e `workflow_dispatch`. Esse workflow apenas verifica presença de arquivos; não substitui os testes completos.
- Ambos declaram `permissions: contents: read`. Não há `pull_request_target`, permissões de escrita, job de deploy ou merge automático.
- Não encontrei referências a `secrets.*` no workflow. As credenciais presentes são valores sintéticos de teste, associados aos serviços locais do job.

### Execução dos gates

- PostgreSQL: serviço efêmero `postgres:16`, com papéis de teste separados; as URLs do teste são restritas a loopback.
- Redis: os testes iniciam Redis real via Docker com autenticação; a ausência de Docker/Compose deve falhar quando os gates obrigatórios estão habilitados. A verificação JUnit exige os casos Redis críticos e rejeita casos ausentes, duplicados, ignorados ou falhos.
- 4H → 4J → 4K: passos sequenciais no mesmo job Chromium/PostgreSQL. Cada script deve emitir seu marcador para o passo passar.
- `OFFICIAL_BROWSER_PASSED`: o workflow só imprime o marcador agregado se o passo 4K terminar com sucesso e seu marcador específico for encontrado. Isso é uma condição configurada, não evidência de execução.
- Imagens de serviço usam tags (`postgres:16`, `redis:7-alpine`), não digest imutável.

### Ações e integridade

Referências encontradas: `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`, `pnpm/action-setup@v4` e `actions/setup-node@v4`. São tags principais, não SHAs completos imutáveis; a origem é conhecida, mas a integridade do código da Action não fica fixada ao commit exato.

## 3. Dependências e reprodutibilidade

- Python do workflow: 3.12 em `ubuntu-24.04`; o índice é fixado em `https://pypi.org/simple`, com validação TLS e bloqueio de `trusted-host`, índice extra e `find-links`.
- Os locks Python usam versões e hashes; a evidência registrada na Fase E.7 é de 58 distribuições/1.747 hashes para backend e 7/137 para solver. A validação anterior baixou wheels compatíveis com CPython 3.12/Linux via PyPI HTTPS. Esta revisão não repetiu downloads.
- Node do workflow: 22; PNPM 10.26.1; `pnpm-lock.yaml` tem formato v9 e 524 entradas de integridade. `package.json` usa faixas semver, enquanto o lockfile fixa resoluções.
- A evidência E.7 registra `pnpm install --lockfile-only --frozen-lockfile --offline` sem alteração do lock. Isso não equivale a executar `pnpm install --frozen-lockfile` completo no runner Ubuntu.
- Não executei instalação completa, build, Chromium, testes, `actionlint` ou GitHub Actions nesta auditoria somente leitura. A execução oficial e os E2Es continuam sem comprovação.

## 4. Segurança funcional e arquivos sensíveis

- Não há alterações de implementação nos módulos de autenticação, cookies/CSRF, publicação, auditoria/histórico ou regras do solver em relação à referência. O teste 4K revisado continua verificando autorização segregada antes da publicação.
- O startup mantém verificações PostgreSQL/RLS e Redis; o diff dos testes aumenta a exigência de execução em CI.
- A busca por caminhos rastreados identificou `.env.example`, sem `.env` real, dumps, backups ou arquivos de chave rastreados. A verificação de padrões comuns de chave privada/tokens não encontrou correspondências. O estado inicial do worktree estava limpo. Isto não é uma verificação dos Secrets da plataforma — eles não foram acessados.
- A alteração de `.gitignore`, entretanto, removeu as regras para `ops/*.env`, `ops/*.env.*`, exceção de exemplos, `*.backup`, `*.dump` e `*.sql.gz`. Verificações de `git check-ignore` confirmaram que exemplos de caminhos operacionais e de backup agora não são ignorados.
- As URLs e serviços do workflow apontam para loopback ou serviços efêmeros do job. Não encontrei referência a Neon ou banco público no workflow.

## 5. Achados e riscos

### P1-1 — Teste de startup Replit incompatível com o job e a árvore GitHub

`backend/tests/test_production_routing_startup.py` é coletado pelo `pytest -q` do job `backend_postgres`. Seu teste de rotas tenta abrir `artifacts/horario-inteligente/.replit-artifact/artifact.toml` e `artifacts/api-server/...`; a árvore GitHub consultada contém zero caminhos `artifacts/`. O teste de startup também invoca `build-production.sh`, que chama `pnpm run build` e exige a saída aninhada `standalone/horario-escolar/frontend/server.js`. O job `backend_postgres` não configura Node/PNPM nem instala dependências frontend; no checkout GitHub plano, `frontend/next.config.ts` seleciona `outputFileTracingRoot` do próprio app, não a raiz Replit, então a saída esperada pelo script/teste não corresponde ao layout.

**Impacto:** a suíte do job backend tende a falhar antes de completar, impedindo o CI de chegar a um resultado verde. A ausência dos artefatos torna o teste de presença de configuração incompatível com o checkout GitHub.

### P1-2 — Migração em produção acoplada à URL de runtime

`backend/alembic/env.py` importa `app.config` antes de ler `HI_MIGRATION_DATABASE_URL`. Em `ENVIRONMENT=production`, `app.config` exige `HI_RUNTIME_DATABASE_URL` durante a importação. Assim, executar Alembic com somente a credencial do papel migrator — como a instrução de `README.md` descreve — falha antes de usar a URL de migração.

**Impacto:** a separação operacional entre runtime e migrator não funciona em um job de migration que receba somente a credencial de menor escopo necessária. Nenhuma migração foi executada.

### P1-3 — Proteções de `.gitignore` para segredos/backups removidas

As regras da referência para arquivos de operação e backups desapareceram. Os caminhos `ops/production.env`, `ops/production.env.local`, `ops/backup.dump` e `ops/snapshot.sql.gz` não são ignorados agora.

**Impacto:** aumenta o risco de incluir acidentalmente credenciais ou cópias de banco em commits futuros. Não encontrei tais arquivos rastreados nesta projeção.

### P2-1 — Actions e imagens sem pinagem imutável

Actions estão referenciadas por tags `v4`/`v5`; PostgreSQL e Redis usam tags de imagem, não digests. Isso reduz a reprodutibilidade e permite que a referência de uma dependência externa mude com o tempo.

### P2-2 — CI principal sem disparo manual

`ci.yml` não oferece `workflow_dispatch`; somente o workflow de verificação estrutural tem disparo manual. A execução completa dependerá de push ou PR.

## 6. Correções propostas — não aplicadas

1. Isolar o teste `test_production_routing_startup.py` do `pytest` backend no GitHub, ou adaptá-lo ao layout do checkout e executar build/startup em job próprio com Node, PNPM e instalação congelada. Remover a dependência de arquivos `artifacts/` que não fazem parte da árvore remota ou fornecer uma validação Replit separada.
2. Corrigir o carregamento de configuração do Alembic para usar a credencial de migration sem exigir a credencial runtime no processo de migração; adicionar teste de configuração sem conexão a banco. Alternativamente, documentar explicitamente a necessidade de ambas as URLs e avaliar se isso mantém a separação de privilégio planejada.
3. Restaurar no `.gitignore` as proteções de arquivos operacionais e backups e adicionar uma verificação automática de `git check-ignore` para esses padrões.
4. Fixar Actions a SHAs completos verificados e imagens PostgreSQL/Redis a versões/digests imutáveis; decidir se o CI principal também deve ter `workflow_dispatch`.
5. Após essas correções, executar novamente a revisão local e então obter autorização separada para push/PR. Só considerar o gate oficial aprovado após a execução real do workflow.

## 7. Decisão

**NO-GO para autorizar push e PR rascunho nesta revisão.** Os achados P1-1 a P1-3 precisam ser resolvidos ou formalmente aceitos antes de usar o PR como gate de homologação. Não foram aplicadas correções.

O GitHub Actions, a instalação completa no runner e os E2Es 4H/4J/4K não foram executados. **`OFFICIAL_BROWSER_PASSED` não foi comprovado nem registrado como resultado.** Esta decisão não autoriza merge, alteração de banco/Secrets, migration, deployment ou publicação.
