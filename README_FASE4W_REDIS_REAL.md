# Horário Inteligente — Fase 4W: Redis real e autenticação da stack de produção

## Resumo técnico
A Fase 4V introduziu rate limiting por Redis com testes usando
um cliente simulado. A Fase 4W valida o **Redis 7 real** em contêiner
descartável e identifica/corrige um problema de interpolação de senha
no Compose de produção. Esta etapa **não equivale a uma instalação
pública nem autoriza dados reais de escolas**.

## Correção de implantação

Em `docker-compose.production.yml`, o comando Redis e o healthcheck
usavam `$REDIS_PASSWORD`. O parser do Docker Compose interpreta
variáveis do host, antes da execução do shell dentro do contêiner.
Agora usam `$$REDIS_PASSWORD` na definição YAML; a expansão acontece
no shell **dentro do contêiner**. Não se imprime a senha em log.

`backend/tests/test_phase4u_compose_production.py` confere o
resultado de `docker compose config --format json` e rejeita
substituição indevida pelo host.

## Novos testes automatizados

1. `backend/tests/test_phase4w_redis_live.py`: inicia Redis real
   `redis:7-alpine` com porta associada **somente a 127.0.0.1 do
   runner**. Executa 16 tentativas simultâneas contra o contador
   compartilhado via script Lua. Espera exatamente 8 autorizações e
   8 bloqueios HTTP 429; confere TTL positivo, contador lido de outra
   conexão, limpeza após sucesso e HTTP 503 diante de senha incorreta.
   O contêiner de teste é removido no final.
2. `backend/tests/test_phase4w_production_redis_compose.py`: utiliza
   **a mesma definição Redis do Compose de produção**, mas com
   valores fictícios em arquivo temporário e nome de projeto isolado.
   Inicia apenas o serviço Redis com `--wait`; comprova healthcheck
   e PONG autenticado; verifica que PING sem senha resulta em NOAUTH;
   remove projeto/contêiner ao terminar.
3. Em máquinas sem Docker, os testes reais podem ser ignorados
   explicitamente. A evidência CI abaixo, no runner GitHub com Docker,
   **não apresentou skips**.

## Evidência de GitHub Actions

- [Run 38457855736 — SUCCESS, 3/3 jobs](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38457855736):
  **223 testes backend PASS**, cinco gates PostgreSQL/RLS reais,
  testes de Redis real, 21 testes do solver legado, Next.js/Chromium
  4H/4J PASS. Commit `0d8387295e9cc261979c3f81cb4c47f31813a389`.
- [Run 38458280764 — SUCCESS, 3/3 jobs](https://github.com/ahferreira01-del/horario-escolar/actions/runs/38458280764):
  **224 testes backend PASS**, zero skips, inclui o teste do Redis
  definido na stack de produção; cinco gates PostgreSQL/RLS,
  solver legado e Chromium integrado PASS. Commit
  `e271d52e2716dc7ced65bad43b34ae4f612098a8`.
- O commit `9f2fe098aa9b95e38300edef27fd7e81b4d11c3f`
  torna o parser do teste compatível com JSON array ou NDJSON
  de versões diferentes do Docker Compose; obter evidência final
  de CI após a revisão.

## Limitações e próximos gates

- **Servidor, DNS/TLS público, SMTP real, backup offsite/restore e
  monitoramento NÃO estão configurados nem testados** nesta etapa.
  Não declarar `/api/ready` de uma infraestrutura pública.
- O limitador por e-mail é suscetível a bloqueio temporário abusivo da
  conta por terceiro; faltam mecanismos na borda/WAF e revisão externa
  de autenticação e rate limiting multiworker em tráfego real.
- As redes e o Docker Compose passam em testes de configuração, mas
  a stack inteira (migrations, DB, Redis, API, web e TLS) ainda precisa
  de teste real de implantação com dados artificiais em host isolado.
- **Bloqueio 4K**: o roteiro Playwright de duas identidades, aprovação,
  publicação e exportações está no repositório, mas NÃO está no workflow.
  Não há evidência `OFFICIAL_BROWSER_PASSED`. A atualização do workflow
  exige edição/revisão manual autorizada; ver issue #4.
- Revisão independente de segurança/LGPD, política de retenção,
  testes de restore, carga/acessibilidade e piloto escolar continuam
  pendentes. Não inventar prazos.
- CP-SAT não foi ativado na API; SciPy/HiGHS MILP continua padrão.

**Estado: segurança e infraestrutura mais verificáveis, sem merge na
`main`, sem deploy ou autorização de escolas reais.**
