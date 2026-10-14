# Homologação de versão publicada no Replit — Horário Inteligente

**Endereço informado pelo responsável:** https://horario-inteligente.replit.app

## Estado observado neste ciclo
O URL foi fornecido como publicado, mas as ferramentas externas deste ambiente
não conseguiram obter uma resposta HTTP verificável: a ferramenta web retornou
erro de acesso/cache e a tentativa de rede do contêiner falhou na resolução DNS.
**Isso NÃO comprova indisponibilidade da aplicação**, mas impede afirmar que
esta versão está online, saudável, idêntica ao GitHub ou homologada em produção.

O repositório GitHub está na branch `development/fase4i-homologacao`,
PR #2 (rascunho), e o CI não executa o smoke oficial 4K.
O fato de o URL ter sido publicado não significa que o Replit esteja
executando o SHA desta branch nem que o backend tenha PostgreSQL/RLS.

## Identificação determinística de release
O backend expõe, após implantar o código desta fase:

`GET /api/release`

Exemplo de resposta **com a variável HI_RELEASE_SHA corretamente configurada**:

```json
{
  "app": "horario-inteligente",
  "api_version": "0.4.9",
  "release_sha": "<40-caracteres-hexadecimais-do-commit-implantado>",
  "release_identified": true
}
```

Sem `HI_RELEASE_SHA` configurada, devolve
`release_sha: null` e `release_identified: false`. **Não existe
detecção automática do commit em plataformas que não o fornecem.**
Nunca inserir senha, URL privada, token do Replit ou chave SMTP na variável
`HI_RELEASE_SHA`. O valor tem de representar o commit **efetivamente
implantado**, não simplesmente o último commit visível no GitHub.

Se a rota devolver **404**, verificar se o Replit executa código anterior
ou outro projeto. Se `/api/release` não estiver disponível, NÃO afirmar
paridade entre Replit/GitHub.

## Smoke remoto não destrutivo
Após sincronizar e implantar o mesmo commit no Replit:

```bash
python scripts/verify_public_deployment.py \
  --url https://horario-inteligente.replit.app \
  --expected-sha SHA_COMPLETO_EFETIVAMENTE_IMPLANTADO
```

O script exige:
1. URL HTTPS sem credenciais ou caminhos adicionais.
2. `/api/release` identificando **exatamente** o SHA esperado.
3. `/api/health` retornando `{"status":"ok"}`.
4. `/api/ready` retornando `{"status":"ready"}`.

Toda saída diferente retorna código de erro e o marcador
`PUBLIC_DEPLOYMENT_NOT_VERIFIED`.
Quando todos passam, escreve `PUBLIC_DEPLOYMENT_READONLY_PASS`.
Mesmo nesse caso, só comprova **identidade/configuração básica,
não liberação operacional**.

Em projetos Replit cujo runtime use outras tecnologias, essa ferramenta
só funcionará quando as rotas equivalentes forem implementadas no
backend realmente publicado; não transformar um 404 em sucesso.

## Próximas ações na instalação Replit
- Conferir o projeto efetivamente associado ao domínio e seu histórico de
  deploys. Registrar SHA, data, ambiente e build atual.
- Configurar **segredos pelo gerenciador de Secrets/Deployment**, nunca no
  git, código frontend ou mensagem pública.
- Conferir armazenamento permanente PostgreSQL real, role do runtime
  **sem BYPASSRLS**, FORCE RLS e isolamento de tenant. Não considerar
  SQLite/local RAM como produção de escolas.
- Comprovar que o login tem proteção distribuída Redis, sessões HTTPS,
  e-mail de convite SMTP e que a API não divulga dados/erros internos.
- **Executar o smoke oficial 4K em PostgreSQL/Chromium descartável** por
  edição manual aprovada do workflow (Issue #4); não rodar esse fluxo
  destrutivo contra produção nem contornar bloqueio do GitHub.
- Verificar backup externo criptografado e restauração em ambiente
  isolado, LGPD, segurança independente e piloto com dados fictícios.
- Conferir DNS/TLS e tempos de resposta a partir de um navegador real,
  inclusive em mobile; registrar screenshot e logs sem segredos.
- Só liberar contas e dados de escolas após documentação dos gates.

## Bloqueio explícito
A existência do link Replit não prova que esta branch foi implantada.
Não fazer merge da PR #2 nem trocar para CP-SAT como padrão até
homologação e autorização.
