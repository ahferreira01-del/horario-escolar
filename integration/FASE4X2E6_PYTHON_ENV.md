# Horário Inteligente — Fase 4X.2-E.6: recuperação do ambiente Python

**Data:** 14/10/2026
**Decisão:** **NO-GO** para homologação completa
**Projeção:** `integration/fase4x2-pr-draft`, base `08e4126`
**Candidata original:** `integration/fase4x2-candidate`, `a99c2ba`
**Referência GitHub:** `development/fase4i-homologacao`, `d9ddea0`

## Resumo

O bloqueio não é uma versão comprovadamente ausente: o índice configurado responde a consultas de metadados, mas usa HTTP e o ambiente exporta `PIP_TRUSTED_HOST` para o mesmo host. Isso permite confiar em tráfego sem TLS. Não instalei pacotes por essa rota, não usei a opção CLI `--trusted-host`, não desativei certificados e não usei PyPI público como atalho. A configuração precisa ser corrigida ou aprovada pelo responsável do índice antes de qualquer instalação.

Em paralelo, preparei na projeção uma instalação PNPM congelada para a raiz plana do GitHub, derivada do lockfile original sem alterar suas versões. O teste congelado offline de lockfile passou. Os builds TypeScript/Next standalone e a resposta HTTP 200 foram repetidos nas estruturas plana e Replit, usando dependências já instaladas em cópias temporárias.

Sem instalar `redis`, `ortools` e `playwright` por uma origem TLS aprovada, a suíte Python, a API e os E2Es 4H/4J/4K continuam bloqueados. `OFFICIAL_BROWSER_PASSED` **não foi emitido**.

## 1. Integridade e isolamento

| Item | Resultado |
|---|---|
| Projeção | `integration/fase4x2-pr-draft`, base `08e4126`; alterações desta fase restritas ao worktree |
| Candidata | `integration/fase4x2-candidate`, `a99c2ba`; sem alterações |
| Checkout principal | `main`; sem alterações feitas nesta fase |
| Worktree da projeção | O backlink `.git` estava ausente. O registro administrativo único foi validado e o backlink restaurado antes de usar o worktree. Raiz, branch e HEAD foram conferidos. |
| Instalação Python | Nenhuma dependência foi instalada; Python global permaneceu inalterado |
| Produção e dados | Sem acesso ou alteração a produção, Neon, bancos, migrations, Secrets ou dados reais |
| GitHub/deployment | Sem execução do workflow remoto, push, merge ou publicação |
| Workflows Replit | Permaneceram ativos; nenhum foi parado ou reiniciado |

Os testes de frontend foram executados em cópias temporárias sob `/tmp/hi-fase4x2e5.tU2RNu`. Os servidores standalone temporários usaram somente `127.0.0.1:3011` e `127.0.0.1:3012` e foram encerrados ao final dos testes.

## 2. Diagnóstico de `pip`, `uv`, rede e TLS

### Configuração efetiva observada

| Verificação | Evidência |
|---|---|
| Python padrão | `3.13.11`; o CI da referência usa Python `3.12` |
| CLI `pip` | Disponível, versão `25.0.1` |
| `python -m pip` | Falha: o módulo/distribuição `pip` não está instalado no Python padrão |
| CLI `uv` | Disponível |
| Índice efetivo de `pip` | Variável de ambiente configurada para `http://package-firewall.replit.internal`; usuário, senha, caminho e query não foram exibidos |
| `PIP_TRUSTED_HOST` | Variável presente; comparação em memória confirmou que corresponde ao host do índice |
| Configuração persistente de `pip` | `PIP_CONFIG_FILE` ausente; os arquivos padrão consultados não estavam presentes |
| Configuração de `uv` | `UV_INDEX_URL`, `UV_DEFAULT_INDEX`, `UV_INDEX`, `UV_CERT` e `UV_NATIVE_TLS` ausentes; nenhum `uv.toml`/`pyproject.toml` de configuração encontrado na projeção |
| Proxies | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, variantes minúsculas e `NO_PROXY` ausentes |
| Certificados | Nenhum `PIP_CERT`, `PIP_CLIENT_CERT`, `UV_CERT`, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `REQUESTS_CA_BUNDLE` ou `CURL_CA_BUNDLE` configurado; o arquivo CA padrão do sistema existe |
| HTTPS público | Requisição com verificação TLS padrão a `https://pypi.org/simple/` retornou HTTP 200; isso não autoriza baixar dependências diretamente desse índice |

### Causa raiz e segurança

- O host consegue resolver e acessar PyPI por HTTPS com o CA padrão. A falha DNS vista na Fase E.5 foi específica à rede bridge padrão do contêiner; no host e no teste anterior com rede host, DNS funcionou.
- O índice configurado do Replit usa HTTP. No ambiente atual, `PIP_TRUSTED_HOST` está exportado para esse mesmo host; por isso as consultas de metadados por nome (`fastapi`, `redis`, `ortools`, `playwright`) terminaram com sucesso. Essas consultas **não baixaram pacotes** e não constituem evidência de instalação segura.
- A tentativa de instalação anterior no contêiner não recebeu essa variável e o `pip` rejeitou o host HTTP como não confiável. O erro `No matching distribution found for fastapi==0.128.2` não prova que essa versão esteja ausente: o acesso seguro ao índice não foi estabelecido.
- Não usei `--trusted-host`, não alterei `PIP_TRUSTED_HOST`, não desliguei TLS e não instalei por PyPI público. O valor efetivo de `PIP_TRUSTED_HOST` foi mantido oculto; só foi comparado ao host do índice.
- A busca na documentação oficial do Replit não encontrou orientação relevante para esse endpoint específico. Não há integração de administração do índice disponível neste workspace; a configuração ou liberação de um endpoint TLS depende do responsável do serviço.

### Dependências requeridas

Os três `requirements.txt` da projeção, candidata e referência GitHub são idênticos (blob `99ee6ec6f9fa`). As especificações relevantes são:

| Pacote | Especificação declarada | Situação |
|---|---|---|
| FastAPI | `fastapi==0.128.2` | Metadados consultáveis pelo índice configurado; versão exata não verificada por canal TLS aprovado |
| Redis | `redis[hiredis]>=5.2,<7` | Metadados consultáveis pelo índice configurado; resolução segura não validada |
| OR-Tools | `ortools>=9.12,<10` | Metadados consultáveis pelo índice configurado; resolução segura não validada |
| Playwright | `playwright>=1.48,<2` (instalado pelo passo de CI) | Metadados consultáveis pelo índice configurado; resolução segura não validada |

Não há evidência de que esses pacotes ou versões estejam ausentes do índice. A lista acima é o conjunto exato de specs que precisa ser resolvido por uma fonte autorizada com TLS válido; nenhuma versão foi reduzida ou removida.

### Recuperação segura

- Não foi criado `venv`: o ambiente Replit não oferece suporte a ambientes virtuais. Uma alternativa isolada seria um destino temporário `pip --target`, mas somente após disponibilizar uma origem validada por TLS.
- Não reutilizei wheels: não houve wheel cuja procedência e integridade pudessem ser validadas para os pacotes bloqueadores.
- Não acionei a instalação gerenciada de pacotes do Replit: ela reiniciaria todos os workflows ativos.
- Nenhum pacote foi baixado, instalado ou alterado.

**Bloqueio para o administrador do índice:** fornecer ou habilitar uma origem HTTPS aprovada, com certificado verificável, para os requisitos listados acima; ou documentar um fluxo de instalação autorizado que preserve TLS. Não adicionar o host HTTP à lista de confiança.

## 3. Estratégia de lockfile e CI

| Alteração na projeção | Verificação |
|---|---|
| `pnpm-lock.yaml` derivado do original da candidata; única diferença em relação à origem: importer `horario-escolar/frontend` → `frontend` | Comparação byte a byte após normalizar esse caminho: **PASS** |
| `pnpm-workspace.yaml` preserva catálogos e overrides; o escopo de pacotes foi ajustado para `frontend` | Linhas não vazias coincidem com a configuração candidata, exceto o escopo plano: **PASS** |
| `.npmrc` alinhado à candidata (`auto-install-peers=false`, `strict-peer-dependencies=false`) | Igual à origem: **PASS** |
| CI usa `pnpm/action-setup@v4` com PNPM `10.26.1`, Node `22`, cache pelo lockfile e `pnpm install --frozen-lockfile --filter ./frontend` | YAML parseado localmente; o workflow remoto não foi executado |
| `pnpm install --lockfile-only --frozen-lockfile --offline --filter ./frontend` | **PASS**; o lockfile não mudou |

Diagnósticos adicionais em cópias temporárias:

- Workspace mínimo sem os catálogos originais falhou com `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`; o erro apontou divergência de `catalogs`.
- Tentar gerar lock do zero em modo offline falhou com `ERR_PNPM_NO_OFFLINE_META` ao resolver `@types/react-dom>=19.0.0`. Não houve re-resolução nem atualização de versões.
- O lockfile original da candidata permanece intacto. A projeção tem uma cópia derivada para a raiz plana. A instalação completa de dependências no ambiente Replit não foi executada; o cache offline não contém todos os tarballs e nenhuma instalação online foi feita nesta fase.
- O CI oficial do GitHub não foi executado; a validação local de lock/YAML não equivale a aprovação do Actions.

## 4. Builds e smoke tests frontend

Os testes usaram os módulos Node já presentes nas cópias temporárias; nenhuma dependência foi instalada nesta fase.

| Verificação | Resultado |
|---|---|
| `tsc --noEmit`, layout GitHub plano | **PASS** |
| `next build` com `HI_NEXT_DIST_DIR=.next-production`, layout plano incluindo o novo workspace root | **PASS**; `standalone/server.js` |
| `next build` com `HI_NEXT_DIST_DIR=.next-production`, layout Replit | **PASS**; `standalone/horario-escolar/frontend/server.js` |
| Standalone plano | **PASS**; HTTP 200 em `127.0.0.1:3011` |
| Standalone Replit | **PASS**; HTTP 200 em `127.0.0.1:3012` |

Os builds locais usaram Node `24.13.0`; o workflow GitHub usa Node `22`. O destino compilado da API permaneceu sintético (`127.0.0.1:8001`); não comprova disponibilidade nem funcionamento dos endpoints.

## 5. Gates ainda bloqueados

| Gate | Estado | Motivo |
|---|---|---|
| Suíte Python completa | **BLOCKED** | Dependências necessárias não foram instaladas por origem TLS aprovada |
| API `/api/health`, `/api/ready`, `/api/release` | **NOT TESTED** | API não inicializada nesta fase |
| E2E Chromium 4H, 4J e 4K | **NOT TESTED** | Playwright Python indisponível; nenhuma execução oficial do Actions |
| `OFFICIAL_BROWSER_PASSED` | **NOT EMITIDO** | 4K não foi executado com sucesso |
| Instalação PNPM completa nesta fase | **NOT TESTED** | Somente validação congelada do lockfile em modo offline; tarballs ausentes no cache |
| Homologação funcional completa | **NO-GO** | Gates Python/API/Chromium pendentes |

Os resultados de PostgreSQL, Redis e SMTP da Fase E.5 permanecem evidências daquela fase; não foram repetidos porque a suíte Python continua sem instalação segura.

## Pendências para retomar

1. Obter do responsável do índice uma origem HTTPS aprovada, certificado válido e resolução das versões declaradas, sem usar a variável de confiança HTTP atual.
2. Instalar as dependências em diretório temporário isolado; verificar hashes/proveniência das wheels e alinhar a versão Python de homologação com o CI (`3.12`).
3. Executar a suíte Python completa, PostgreSQL e Redis descartáveis, endpoints health/ready/release e E2Es 4H/4J/4K no Chromium.
4. Executar o workflow real do GitHub somente após autorização de push; não tratar a validação local como CI oficial.
5. Manter o deployment público, Neon, Secrets e checkout principal inalterados. Nenhuma publicação ou migração está autorizada por esta etapa.
