# Fase 4I — Integração real preparada e validação da transição entre escolas

## Alterações no código

1. **Publicação/preflight:** viagens entre escolas exigem tempo cadastrado para o par origem→destino, mesmo quando as aulas ocorrem em dias civis diferentes. A verificação usa intervalos em UTC; quando o trajeto está cadastrado, o intervalo real deve comportar o tempo mínimo de viagem. Intervalos longos entre dias satisfazem naturalmente esse tempo. A falta de tempo configurado não é interpretada como zero.
2. **Teste de navegador em PostgreSQL:** o job `frontend_browser_postgres` do GitHub Actions foi configurado para criar PostgreSQL 16 efêmero, criar contas owner/runtime separadas, aplicar Alembic como owner, iniciar a API pela conta runtime com RLS, compilar o Next.js e executar Playwright Chromium no sistema integrado. O job anterior de navegador com SQLite foi substituído.
3. **Regressões automatizadas:** inclusão de testes que protegem o contrato do CI, a passagem pela meia-noite e a sobreposição global de aulas com fusos diferentes. A regressão antiga de aulas em dias distintos passou a configurar explicitamente o deslocamento, preservando o comportamento sem conflito quando há intervalo suficiente.
4. **Dependência de desenvolvimento:** `PyYAML` para validar o arquivo do workflow.

## Evidências locais — 13/10/2026

| Gate | Evidência | Estado |
|---|---|---|
| Backend | `cd backend && pytest -q -ra` → **70 passed, 5 skipped** | PASS apenas para testes executados |
| Gerador anterior SciPy/HiGHS | `cd solver_poc_v0_2 && pytest -q -ra` → **16 passed** | PASS experimental |
| API HTTP real + SQLite efêmero | `python scripts/smoke_http_fase4g.py` → PASS | PASS somente para API |
| Contrato CI e fusos | Quatro novos testes → PASS | PASS local |
| Sintaxe das fontes frontend | TypeScript global sem erros de parser | PASS sintático, NÃO é build |
| PostgreSQL/RLS/concorrência reais | Não disponíveis neste ambiente | **NÃO EXECUTADO** |
| Next.js build e browser integrado | Dependências de frontend/serviço indisponíveis neste ambiente | **NÃO EXECUTADO** |
| OR-Tools CP-SAT | Ainda não implementado | **PENDENTE** |

**Nunca confundir `pytest PASS` com homologação de produção**: os cinco testes ignorados exigem PostgreSQL real. O novo workflow foi validado estruturalmente, mas só será comprovado ao ser executado num runner com PostgreSQL, npm e Chromium.

## Homologação recomendada

1. Usar um repositório privado **autorizado pelo responsável pelo projeto**. Nenhum push foi feito por esta entrega.
2. Publicar o conteúdo deste ZIP na raiz do repositório e executar o workflow `.github/workflows/ci.yml` em PR/branch de homologação.
3. Exigir PASS de `backend_postgres`, `frontend_browser_postgres` e `solver_legacy`. O job `backend_postgres` reprova testes PostgreSQL ignorados.
4. Revisar migrações e as autorizações em ambiente **descartável**, nunca em banco de produção. Verificar logs e corrigir falhas reais, inclusive de instalação do frontend e de políticas RLS.
5. Só depois executar testes de carga, backup/restore, gestão de segredos, autenticação multifator, LGPD e aceite das escolas.

## Limitações em aberto

- Fluxo completo no PostgreSQL e Next.js **não comprovado** neste ambiente.
- Motor oficial ainda utiliza SciPy/HiGHS; CP-SAT não foi instalado nem integrado.
- A publicação em produção permanece proibida até homologação integrada.
- O compartilhamento entre tenants continua fora da implementação atual.
- Backups/restauração, rate limit, MFA e política de retenção exigem validação adicional.
