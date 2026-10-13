# Horário Inteligente — Fase 4V: endurecimento do login e redes de produção

**Estado:** implementação no Pull Request em rascunho. Não é autorização para produção.
O CI valida contratos e simulações Redis, mas **não comprova proteção
fim a fim contra Redis real e tráfego externo**.

## Entregas
- `backend/app/login_throttle.py`: contador atômico Redis via script Lua
  `INCR` + `EXPIRE`, com **8 tentativas por e-mail normalizado em
  300 segundos**. A nona tentativa responde HTTP 429 com `Retry-After`.
- As chaves usam HMAC-SHA256 do e-mail com o segredo de sessão do servidor;
  não revelam o e-mail em claro no Redis. O mesmo Redis atende múltiplos
  workers/processos da aplicação. Uma autenticação bem-sucedida limpa
  o contador daquela identidade.
- Redis indisponível, sem URL ou falha na exclusão do contador após login:
  **HTTP 503** em produção. Não há `fail-open`. `GET /api/ready`
  também verifica Redis quando `ENVIRONMENT=production`.
- Usuários inexistentes ou desativados passam por Argon2 de referência
  antes de receber a mesma mensagem de falha. Isso reduz diferença
  óbvia de custo de verificação; não garante tempo constante exato.
- `backend/app/config.py` exige URL Redis autenticada em produção;
  `ops/preflight_production.py` exige chave própria, distinta de DB
  e sessão, e URL coerente com a instância interna.
- `docker-compose.production.yml` inclui Redis 7 **sem portas
  públicas** e healthcheck autenticado. As redes foram separadas:
  - `data_net`: PostgreSQL, Redis, migração e API.
  - `service_net`: API e Next.js.
  - `edge_net`: Next.js e Caddy.
  O proxy público **não tem rede compartilhada diretamente com PostgreSQL
  nem Redis**.
- `backend/tests/test_phase4v_login_throttle.py`: HTTP 401 e 429,
  normalização de contas, HMAC, reset após sucesso, falha fechada
  em conexão e limpeza de Redis, e preservação do desenvolvimento.
  `backend/tests/test_phase4u_compose_production.py` foi ampliado
  para conferir as três redes e ausência de portas públicas.
- A API continua usando MILP por padrão, CP-SAT permanece experimental.

## Como validar em homologação (AINDA PENDENTE)
1. Provisionar servidor com DNS/HTTPS, SMTP e Redis autenticado,
   estritamente sem portas públicas de DB e Redis.
2. Subir um ambiente **fictício**, usando `ops/production.env`
   privado e passar em `ops/preflight_production.py`.
3. Tentar login com conta fictícia, oito senhas incorretas e conferir
   bloqueio temporário na nona tentativa. Validar o retorno do login
   após a janela e após senha correta em um contador não bloqueado.
4. Repetir alternando duas réplicas/instâncias da API com a mesma
   configuração de Redis. Confirmar que os limites são compartilhados.
5. Derrubar Redis temporariamente e confirmar `/api/ready` e
   `/api/auth/login` indisponíveis (503), sem aceitar sessões novas.
6. Testar a rede no Docker: Caddy deve alcançar somente Next.js, Next.js
   deve alcançar a API, API deve alcançar PostgreSQL/Redis. Sem rotas
   publicadas para 5432/6379/8000/3000.
7. Confirmar E2E **4K de publicação oficial pelo Chromium** em CI
   efêmero, ainda **fora do workflow** por restrição anterior de edição.

## Limites e riscos conhecidos
- O limite por identidade pode ser abusado para bloquear uma conta
  durante cinco minutos; não substitui WAF na borda, medidas por IP
  devidamente validado, detecção de password spraying, MFA, alertas,
  auditoria externa e política de recuperação de acesso.
- A implementação Redis usa contador com TTL de janela fixa. Reiniciar
  Redis sem persistência apaga contadores; usuários/sessões não são
  armazenados nele. Não representa isolamento de segredos em cofre.
- Testes atuais do backend usam cliente Redis simulado (sem servidor
  Redis real), e o teste Compose é estático. A integração de produção
  precisa ser demonstrada, não presumida.
- Os scripts de backup/restore permanecem não comprovados em hardware
  de recuperação. Não há RPO/RTO acordados, infraestrutura efetiva,
  SMTP/DNS reais, auditoria independente ou aceite escolar.
- **O sistema NÃO está em produção e não deve usar dados reais.**
