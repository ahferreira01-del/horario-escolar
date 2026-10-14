# Horário Inteligente — Fase 4X.2-E.5: dependências e estrutura frontend

**Data:** 14/10/2026
**Decisão:** **NO-GO** para envio da projeção ao GitHub
**Projeção:** `integration/fase4x2-pr-draft`, HEAD de entrada `816668819102a86d79f148f097a410eccc0eabd9`
**Candidata original:** `integration/fase4x2-candidate`, `a99c2baec90722255b3d13377e679759c70a5dd7`
**Referência GitHub local:** `github/development/fase4i-homologacao`, `d9ddea0`

## Resumo executivo

Foi possível recuperar e usar o lockfile aprovado da candidata em uma cópia temporária com a estrutura de diretórios original. A instalação congelada do frontend, o TypeScript e o build standalone passaram. O build revelou um caminho de inicialização incompatível entre a estrutura plana da projeção GitHub e a estrutura monorepo Replit; a configuração de tracing foi ajustada **somente na projeção** e validada nos dois formatos. Os dois servidores standalone responderam HTTP 200.

A instalação Python segue bloqueada pelo índice de pacotes configurado. A falha inicial foi reproduzida: DNS falha na rede bridge padrão do Docker; DNS e HTTPS ao PyPI funcionam pelo host e pela rede host do contêiner. Ao reutilizar o índice configurado, o `pip` marcou o host interno do firewall como inseguro e não encontrou `fastapi==0.128.2`. As consultas do `pip` do host ao índice também falharam para FastAPI, Redis e OR-Tools. Não foi usado `--trusted-host`, não foi contornado o firewall e nenhum pacote foi instalado no Python global.

Sem as dependências Python `redis`, `ortools` e `playwright`, a coleta da suíte completa termina com 19 erros de importação. A API não importa, os endpoints não podem ser verificados e os E2Es 4H/4J/4K no Chromium não foram executados. `OFFICIAL_BROWSER_PASSED` **não foi emitido**.

## 1. Integridade, raízes e isolamento

| Checkout | Caminho absoluto | Branch/HEAD confirmado | Estado |
|---|---|---|---|
| Projeção | `/home/runner/workspace/.local/worktrees/horario-inteligente-fase4x2-pr-draft` | `integration/fase4x2-pr-draft`, entrada `8166688…` | Limpo antes da correção desta fase |
| Candidata | `/home/runner/workspace/.local/worktrees/horario-inteligente-fase4x2d` | `integration/fase4x2-candidate`, `a99c2ba…` | Limpa e preservada |
| Checkout principal | `/home/runner/workspace` | `main`, `c7d1cdd` no início desta fase | Não alterado |

Os arquivos `.git` e os registros administrativos correspondentes foram verificados; `git rev-parse --show-toplevel` confirmou as raízes reais da projeção e da candidata. A candidata não recebeu alterações. Os testes e builds foram feitos em cópias sob `/tmp/hi-fase4x2e5.tU2RNu`, não no checkout principal.

Não houve acesso ao Neon, banco de produção ou Secrets; não foram usados dados reais, migrations de produção, publicação, push ou merge. Os workflows ativos permaneceram intocados e não foram reiniciados ou parados.

## 2. Diagnóstico e instalação Python

### Causa da falha

- Python do host: 3.13.11; o CI da branch usa Python 3.12.
- `pypi.org` resolve no host; a requisição HTTPS a `https://pypi.org/simple/` retornou HTTP 200.
- Um contêiner Python na rede bridge padrão falhou em resolver `pypi.org` (`Temporary failure in name resolution`); o mesmo teste de DNS no contêiner com `--network host` passou.
- O host tem `PIP_INDEX_URL` configurado. O nome e o valor não foram registrados neste relatório. `HTTP_PROXY` e `HTTPS_PROXY` estavam ausentes.
- Ao passar o índice configurado ao contêiner pela rede host, o `pip` avisou que o host interno do package firewall não era confiável/seguro e encerrou com `No matching distribution found for fastapi==0.128.2`.
- Consultas de disponibilidade via configuração de `pip` do host falharam para `fastapi`, `redis` e `ortools`. A consulta pública HTTPS apenas confirmou que o artefato FastAPI indicado existe; não foi usada para instalar ou contornar o firewall.
- O cache `pip` não apresentou artefatos correspondentes a `redis`, `ortools` ou `playwright`. O diretório temporário de destino Python permaneceu vazio.
- `backend/requirements.txt` da projeção e `horario-escolar/backend/requirements.txt` da candidata são o mesmo blob Git (`99ee6ec6f9fa…`); não há divergência de requirements entre essas duas fontes.

Não foi usado `--trusted-host` nem um índice alternativo para contornar a política. A instalação continuou bloqueada sem alterar versões, remover dependências ou modificar o Python global. A instalação sancionada de pacotes do Replit não foi acionada porque reiniciaria os workflows ativos, o que está fora das condições desta fase.

**Procedimento necessário para desbloquear:** disponibilizar um caminho de instalação aprovado e seguro para o índice configurado (ou a correção do firewall/índice pelo mecanismo de pacotes do ambiente). Em seguida instalar as versões declaradas somente em ambiente descartável e repetir a coleta. Não tornar o host interno confiável manualmente nem usar PyPI direto como atalho.

## 3. Estrutura frontend e origem do lockfile

| Fonte | Estrutura e arquivos observados |
|---|---|
| Projeção `8166688…` | `frontend/package.json` e `frontend/next.config.ts`; sem lockfile ou `pnpm-workspace.yaml`. |
| GitHub `d9ddea0` | Estrutura plana `frontend/`; sem `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock` ou `pnpm-workspace.yaml`. |
| Candidata `a99c2ba…` | `horario-escolar/frontend/`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` v9 e `.npmrc` no workspace raiz. O lockfile contém o importer `horario-escolar/frontend`. |

O `package.json` da projeção e o da candidata têm o mesmo blob (`0e230eb414b3…`), e os specifiers de `dependencies`, `devDependencies` e `optionalDependencies` do importer da candidata coincidem exatamente com o manifesto. Portanto, há lockfile original compatível com as dependências, mas sua ausência na projeção **não foi uma falha de cópia**: a referência GitHub também não o possui e usa outra estrutura de diretórios. O caminho do importer no lockfile original não corresponde diretamente ao caminho plano `frontend/`.

Para testar sem gerar ou deformar um lockfile, foi montada uma cópia temporária da candidata com:

1. `pnpm-lock.yaml`, `pnpm-workspace.yaml` e `.npmrc` originais da candidata;
2. o código frontend da projeção em `horario-escolar/frontend`, mantendo o caminho do importer;
3. `pnpm install --frozen-lockfile` filtrado para esse frontend.

A tentativa offline não passou porque faltava um tarball no cache PNPM (780 MiB disponíveis). A instalação online congelada passou usando o registry oficial npm HTTPS e o lockfile original; o arquivo de lock permaneceu byte a byte igual ao original. A cópia temporária e seu store ficaram sob `/tmp`; nenhum manifesto ou lockfile foi alterado na projeção. O `.npmrc` da candidata foi verificado apenas quanto aos nomes de configuração e não continha chaves de autenticação/token/senha.

**Pendente para a branch GitHub:** decidir e revisar a forma de fornecer um lockfile compatível com a estrutura plana e trocar o passo atual de `npm install` por instalação congelada. O CI da referência ainda executa `npm install --no-audit --no-fund`, sem lockfile. O lockfile Replit não foi copiado diretamente para a raiz plana, pois seu importer aponta a outro caminho.

## 4. Next standalone e correção estrutural

O build inicial na estrutura plana colocou o servidor em `standalone/projection-root/frontend/server.js`, mas o CI inicia `standalone/server.js`. Na estrutura Replit original, o caminho aninhado `standalone/horario-escolar/frontend/server.js` é o esperado. A causa era `outputFileTracingRoot` fixo em dois níveis acima do frontend.

Foi alterado somente `frontend/next.config.ts` na projeção. A configuração agora detecta a estrutura Replit pela presença de `pnpm-workspace.yaml` e `horario-escolar/frontend/package.json` no workspace; nessa estrutura preserva o tracing root do monorepo. Na estrutura plana GitHub, usa o diretório do projeto como root de tracing e produz `standalone/server.js`.

| Verificação | Resultado |
|---|---|
| Instalação PNPM congelada com o lock original | **PASS** |
| `tsc --noEmit` na estrutura plana | **PASS** |
| `next build` com `HI_NEXT_DIST_DIR=.next-production`, estrutura plana | **PASS**; `standalone/server.js` presente |
| `next build` com `HI_NEXT_DIST_DIR=.next-production`, estrutura Replit `horario-escolar/frontend` | **PASS**; `standalone/horario-escolar/frontend/server.js` presente |
| Rewrites no build manifest | **PASS**; em ambos os builds, `/api/:path*` aponta para `http://127.0.0.1:8001/api/:path*` (destino sintético de teste) |
| Inicialização do standalone plano | **PASS**; HTTP 200 em `127.0.0.1:3001` |
| Inicialização do standalone Replit | **PASS**; HTTP 200 em `127.0.0.1:3002` |

Os builds usaram Node 24.13.0, enquanto o job GitHub configura Node 22; isso é uma diferença de versão do ambiente local, não uma aprovação do CI remoto.

## 5. Testes e matriz de gates

| Gate | Estado | Evidência |
|---|---|---|
| PostgreSQL efêmero, conexão autenticada e papel runtime | **PASS** | `postgres:16-alpine`, somente em `127.0.0.1:5432`; role sintético criado. |
| Alembic no PostgreSQL efêmero | **PASS** | `alembic upgrade head` concluiu na instância descartável. |
| Segurança PostgreSQL, RLS e troca de papel | **PASS** | 11 testes passaram em 0,91 s. |
| Redis real via Compose | **PASS** | 1 teste passou em 12,24 s. É validação do serviço Compose, não integração Redis da API. |
| SMTP/TLS | **PASS parcial** | 3 testes passaram em 0,15 s usando stub; não houve entrega em relay SMTP real. |
| Contrato estático do CI | **PASS** | 1 teste passou em 0,20 s. |
| Suíte Python completa | **BLOCKED** | `pytest --collect-only` saiu com código 2: 19 erros de importação (15 `redis`, 4 `ortools`); a execução integral não começou. |
| Importação/inicialização da API | **BLOCKED** | `app.main` falha com `ModuleNotFoundError: redis`. |
| `/api/health`, `/api/ready`, `/api/release` | **NOT TESTED** | API não pôde iniciar com as dependências disponíveis. |
| E2E Chromium 4H, 4J e 4K | **NOT TESTED** | A suíte CI usa `playwright` Python; o módulo não está instalado e a instalação Python está bloqueada. |
| Convites/SMTP real, geração, aprovação segregada, publicação e exportações pela interface | **NOT TESTED nesta fase** | Dependem da API e dos E2Es Chromium; não foram simulados. |
| `OFFICIAL_BROWSER_PASSED` | **NÃO EMITIDO** | O script 4K não concluiu; não foi declarado sucesso oficial ou local. |

### Recursos e limpeza

No preflight, as portas 3000 e 8000 estavam em uso pelos workflows existentes; 3001, 3002, 5432, 6379, 1025 e 8025 estavam livres. Os dois testes standalone usaram apenas 3001 e 3002 e encerraram seus próprios processos. O PostgreSQL de teste foi removido após os testes; o teste Compose do Redis encerrou sua própria instância. Não restaram contêineres identificados como pertencentes a esta fase.

Os workflows que estavam ativos permaneceram ativos. Nenhum foi parado, reiniciado ou consultado por logs nesta fase.

## 6. Arquivos alterados e decisão

- `frontend/next.config.ts` — ajuste do root de tracing para suportar tanto a estrutura plana GitHub quanto a estrutura monorepo Replit.
- `integration/FASE4X2E5_DEPENDENCIAS.md` — este diagnóstico e os resultados.
- Nenhum `package.json`, lockfile, `requirements.txt` ou workflow do GitHub foi alterado.
- A candidata original e o checkout principal permaneceram sem alterações desta fase. Nenhum push, merge ou publicação foi feito.

**Decisão final: NO-GO.** O frontend foi instalado, compilado e inicializado em ambos os layouts usando o lockfile original em uma cópia temporária. Ainda faltam uma origem Python aprovada acessível, a suíte backend integral, a API, os endpoints de health/release, os E2Es 4H/4J/4K no Chromium e uma decisão revisada de lockfile/CI para a estrutura plana. Não iniciar a Fase F nem enviar a projeção até esses gates terem evidência positiva.
