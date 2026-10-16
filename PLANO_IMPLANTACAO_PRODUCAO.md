# Horário Inteligente — Release Candidate: plano de implantação e gates

**Status: infraestrutura preparada no código, implantação NÃO executada e uso com dados reais NÃO autorizado.** Este documento não dispensa validações de segurança, LGPD e aceite escolar.

## 1. O que existe
- `docker-compose.production.yml`: stack **separada** do Compose de desenvolvimento; PostgreSQL 16 persistente sem publicação de porta; migração Alembic como serviço `maintenance` executado explicitamente; backend com credencial `horario_runtime` exclusiva e RLS `FORCE` obrigatório; frontend Next.js interno; Caddy como única borda exposta em **80/443** com HTTPS.
- `ops/Caddyfile`: TLS automático e reverse proxy same-origin para Next.js; Next.js encaminha `/api/*` ao backend pela rede Docker.
- `ops/production.env.example`: apenas placeholders. Copiar para `ops/production.env` (protegido no `.gitignore`). Nunca versionar segredos, dumps, backups ou arquivos de acesso.
- `ops/preflight_production.py`: checagem **offline** de placeholders, URLs, usuários owner/runtime diferentes, segredos e hostname sem revelar valores; SMTP só é exigido quando `HI_USER_PROVISIONING_MODE=email`.
- `backend/app/config.py`: em `ENVIRONMENT=production`, recusa banco SQLite/superuser/owner, cookie não seguro, HTTP, URL local, segredo fraco, SMTP incompleto e sessão fora de limites.
- `GET /api/ready`: verifica banco e contrato PostgreSQL/RLS, retorna **503 sem detalhes internos** se inseguro/indisponível. `/api/health` é apenas liveness; não substituir readiness por health na decisão de liberação.
- `backend/app/cli.py`: aceita `--password-stdin` para bootstrap do primeiro admin, evitando senha em argumentos de processo.

### Proteção de autenticação (Fase 4V)
- A versão de produção usa Redis 7 autenticado, **sem portas públicas**, na rede do Compose. Redis armazena apenas contadores de 5 minutos, não sessões nem dados de alunos.
- O login contabiliza tentativas por HMAC-SHA256 do e-mail normalizado, com segredo do servidor (e-mail não é salvo como chave em claro). Após **8 tentativas em 5 minutos**, as demais recebem HTTP **429**, com `Retry-After`. A autenticação bem-sucedida limpa o contador.
- Redis indisponível ou não configurado gera **HTTP 503**, não liberação silenciosa. A prontidão da API valida também o serviço de limitação. Usuários inexistentes/inativos passam por comparação Argon2 fictícia para reduzir enumeração por tempo.
- O limitador por conta é apenas uma camada: permite negação temporária de acesso contra um e-mail conhecido e não substitui **WAF, controle por IP confiável na borda, detecção de abuso, captcha adaptativo, MFA, monitoramento e testes de segurança**. Ainda falta teste integrado contra servidor Redis real em uma instância de homologação.
- Configure `HI_REDIS_PASSWORD` (segredo **diferente** das senhas PostgreSQL e da sessão) e `HI_AUTH_REDIS_URL=redis://:senha@redis:6379/0` no arquivo privado `ops/production.env`. Evite caracteres especiais não codificados em URLs. O preflight de release exige coerência entre os dois.
- A instância Redis não usa persistência (contadores reiniciam após perda do container); isso não é banco de dados de usuários nem controle antifraude completo. O deploy deve bloquear login se a instância estiver indisponível.

## 2. Informações e infraestrutura pendentes
É preciso decidir e provisionar um **servidor/VPS ou serviço equivalente**, domínio DNS público, TLS/portas 80 e 443, SMTP com STARTTLS, serviço de backup criptografado fora do servidor, Redis de autenticação, monitoramento, alertas, política de retenção/exclusão LGPD e responsáveis pela operação. **Nenhum provedor, domínio real, servidor SSH, e-mail de produção ou ambiente ativo foi fornecido/certificado nesta etapa.**

Este exemplo usa Docker Compose em **um único servidor** e PostgreSQL 16 local. Para alta disponibilidade, gestão de chaves, autoscaling e recuperação regional, será necessário avaliar infraestrutura gerenciada. O Compose não implementa HA, backups automáticos ou recuperação sozinho.

## 3. Pré-requisitos de release obrigatórios (todos exigidos)
1. **E2E 4K**: executar o script `scripts/smoke_browser_publication_fase4k.py` via GitHub Actions no job Chromium/PostgreSQL efêmero e comprovar `OFFICIAL_BROWSER_PASSED`. Ainda BLOQUEADO por edição do workflow; instruções em `README_FASE4K.md`. NÃO contornar bloqueio do conector.
2. Confirmar RLS em PostgreSQL runtime com owner distinto, migração aprovada, testes de autorização de **duas escolas/organizações** e publicação concorrente, inclusive no navegador.
3. Revisão independente de autenticação, CSRF, senhas, Rate Limit no login, mensagens de erro, dependências, cookies, headers, URLs de convite e exposição de dados, corrigindo P0/P1 antes da liberação.
4. Validar segurança e contrato de tratamento de dados/LGPD, localização de dados, responsáveis, bases legais, **prazos de retenção e exclusão** e operações de titular. Prazos ainda não aprovados.
5. Backup automático criptografado em destino **externo**, controle de acesso à chave e **restauração comprovada em instância separada** com RPO/RTO acordados. O volume local não equivale a backup.
6. Testes de acessibilidade, carga concorrente e fluxos completos de escola com dados fictícios, além de piloto e aceite formal. Registrar incidentes/monitoramento e política de rollback.
7. Aprovar domínio/provedor, definir política de deploy (tag SHA imutável), proteção de branches e autorização explícita para merge/deploy.

**Falhar qualquer um desses itens impede a promoção para produção.**

## 4. Procedimento operacional após aprovação dos gates

### Preparar domínio e segredos
- Criar DNS A/AAAA de `HI_PUBLIC_HOST` apontando para IP público do host e liberar inbound TCP 80/443 e UDP 443. Manter **5432/8000/3000 fechadas externamente**. Configurar firewall, SSH por chave e atualizações de segurança.
- Provisionar armazenamento externo e criptografado de backups/segredos. Não depender apenas de volume Docker ou snapshots locais.
- Copiar `ops/production.env.example` para `ops/production.env` **somente no servidor** e definir `chmod 600 ops/production.env`.
- Gerar **três segredos diferentes**, aleatórios, de pelo menos 40 caracteres; evitar caracteres especiais ou aplicar URL-encoding nas conexões PostgreSQL. Configurar SMTP real e e-mail remetente. Os campos `HI_DB_OWNER_URL` e `HI_DB_RUNTIME_URL` precisam corresponder às duas senhas, sem trocar papéis.
- Não copiar variáveis fictícias de CI nem reutilizar senha do ambiente de homologação.

### Verificação offline e infraestrutura
```bash
python3 ops/preflight_production.py --env-file ops/production.env
docker compose --env-file ops/production.env -f docker-compose.production.yml --profile maintenance config --quiet
```
O PASS do preflight é só **consistência de configuração**, não certificação da infraestrutura.

### Migração (apenas quando aprovada)
**Antes de qualquer migração em base existente, efetuar backup e teste de restauração.** A inicialização do role `horario_runtime` em `docker/db-init` só funciona em volume PostgreSQL **novo**; nunca reutilizar volume existente supondo que a função rodará novamente.

```bash
docker compose --env-file ops/production.env -f docker-compose.production.yml up -d db
docker compose --env-file ops/production.env -f docker-compose.production.yml --profile maintenance run --rm migrate alembic upgrade head
```

Para criar o primeiro administrador, **não digitar senha nos parâmetros da linha de comando**. Exemplo interativo:
```bash
read -r -s -p "Senha inicial do administrador: " HI_INITIAL_PASSWORD
printf '\n'
printf '%s\n' "$HI_INITIAL_PASSWORD" | docker compose --env-file ops/production.env -f docker-compose.production.yml --profile maintenance run --rm -T migrate python -m app.cli bootstrap-platform --email ADMIN@EXEMPLO.COM --name "Administrador" --password-stdin
unset HI_INITIAL_PASSWORD
```
Substituir o e-mail fictício por uma conta real de administração de plataforma, de acesso restrito. Confirmar que o usuário não existe antes do bootstrap, pois o comando recusa sobrescrever.

### Subida e validação
```bash
docker compose --env-file ops/production.env -f docker-compose.production.yml up -d --build api web edge
docker compose --env-file ops/production.env -f docker-compose.production.yml ps
curl --fail --silent --show-error https://SEU-DOMINIO/api/ready
```
**Exigir** `{"status":"ready"}`, certificado HTTPS válido, login, convite SMTP, criação de escola fictícia, fluxo de aprovação com dois usuários, pré-validação, publicação oficial, exportações CSV/PDF/XLSX, isolamento, logs e backup/restore antes de liberar cadastro de escolas reais. Nunca usar o endpoint `/health` sozinho como prova de prontidão.

## 5. Operação, backup, rollback e recuperação
- **Backups não estão automatizados no pacote.** Antes de abrir a aplicação ao público, definir rotina diária ou frequência aprovada, usando `pg_dump -Fc`/backups gerenciados, **criptografia em trânsito e repouso**, retenção aprovada e cópia offsite. Testar restauração em outro banco/host com políticas RLS e migrações íntegras. Não copiar arquivos de backup em repositório Git.
- Monitoração mínima: latência HTTP, taxa 5xx, `/api/ready`, conexão DB, espaço em disco, renovação de certificado, backups realizados, último teste de restauração, falhas SMTP e auditoria de segurança. Logs não devem conter senhas, token, convite ou dados escolares desnecessários.
- Rollback **somente do código** por tag/imagem assinada e aprovada. Migrações destrutivas exigem plano de recuperação específico; trocar uma imagem não reverte schema. Verificar compatibilidade da versão antiga com dados/DDL novos antes da operação.
- Definir e registrar RPO/RTO e plano de resposta a incidentes, revogação de credenciais e troca de chave JWT em caso de vazamento.

### Ferramentas manuais de backup e restauração (não são agenda automática)

Foram acrescentados dois scripts operacionais para acelerar a preparação do
plano de recuperação. **Eles não foram executados contra um ambiente real
e não significam backup operacional.**

- `ops/backup_encrypted.sh`: exige `age`, Docker Compose e um
  `HI_BACKUP_DIR` absoluto, existente e **fora do repositório**, destinado
  a armazenamento montado/replicado fora do servidor. Transmite `pg_dump`
  diretamente ao criptografador `age` via pipe, sem gravar dump legível no
  host. Grava arquivo cifrado com permissões 600 e checksum.
- `ops/restore_drill.sh`: exige chave privada de recuperação e confirmação
  `HI_RESTORE_DRILL_CONFIRM=ISOLATED_HOST_ONLY`. Restaura **somente** em
  um banco extra `horario_restore_drill`, que não pode existir antes da
  operação, verifica migração 0003 e FORCE RLS nas tabelas críticas, e
  remove esse banco temporário apenas se a checagem passar.

Uso ilustrativo após preparar infraestrutura e chaves age **fora do servidor
de aplicação, por equipe autorizada**:

```bash
# Backup manual em destino cifrado/offsite — no host da instância fonte
HI_AGE_RECIPIENT="age1CHAVE_PUBLICA_DO_DESTINATARIO" \
HI_BACKUP_DIR="/mnt/backup-externo" bash ops/backup_encrypted.sh

# Drill em OUTRO host de recuperação isolado, com acesso ao arquivo e chave
HI_RESTORE_DRILL_CONFIRM=ISOLATED_HOST_ONLY \
HI_AGE_IDENTITY_FILE="/srv/secrets/age-identity.txt" \
HI_BACKUP_FILE="/mnt/backup-externo/ARQUIVO.pgdump.age" \
bash ops/restore_drill.sh
```

**Atenção:** o teste de sintaxe automatizado não faz recuperação real; a
restauração precisa ser comprovada manualmente, com prova documentada de
acesso pela conta runtime, políticas RLS, aplicação e métricas RPO/RTO.
É proibido guardar a chave privada no repositório, no próprio arquivo
de backup ou no CI público. Não agendar backups antes de validar a
retenção, a cópia externa e o tratamento de dados sob a LGPD.

## 6. Limitações importantes
- A infraestrutura acima **não foi implantada**, nem foi conferido DNS/SSL/SMTP real, política de backup, restore, portas/firewall ou capacidade do servidor.
- CP-SAT experimental continua DESATIVADO na API; SciPy/HiGHS é o motor operacional.
- O CI atual valida os smokes Chromium 4H/4J, **não** a Fase 4K. Não declarar publicação oficial certificada.
- Não há requisito de SLA, LGPD, retenção, piloto ou segurança independentes formalmente concluídos.
- **Somente liberar após preencher a checklist e comprovar os gates com evidências reais.**
