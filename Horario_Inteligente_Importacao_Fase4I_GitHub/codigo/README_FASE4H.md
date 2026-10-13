# Horário Inteligente — Aplicação Fase 4H

Continuação incremental da Fase 4G, preservando API, interfaces e gerador experimental. **Não instalar em produção.**

## Entrega

- RLS: políticas canônicas, bloqueio da role runtime quando possui memberships que permitem `SET ROLE`.
- Teste de publicação oficial integrada PostgreSQL: fluxo de proposta aprovada, lote transacional, vigência, exportações, isolamento.
- Smoke de navegador real com Chromium para login e cadastro de organização pelo Next.js.
- Pipeline CI que executa PostgreSQL e navegador separadamente; não considera testes PostgreSQL ignorados como sucesso.

Veja `RESULTADOS_VALIDACAO_FASE4H.md` para evidências reais e limites do ambiente.

## Executar testes locais (sem PostgreSQL)

```bash
cd backend
pytest -q
cd ..
python scripts/smoke_http_fase4g.py
```

## Homologar com PostgreSQL e navegador

Use o workflow `.github/workflows/ci.yml` sobre ambiente **efêmero** ou forneça um ambiente de integração com PostgreSQL 16, Node.js 22, npm, Chromium e Python 3.12. **Não execute scripts de homologação contra produção.**

O CI cria role de runtime sem `BYPASSRLS`, aplica Alembic, roda os testes críticos, compila o Next, abre Chromium e testa o cadastro administrativo via UI. Nenhuma etapa é considerada comprovada nesta entrega apenas por existir código de CI.

## O que continua pendente

- Rodar a integração real em infraestrutura com Postgres/Next; corrigir eventuais falhas observadas.
- OR-Tools CP-SAT definitivo, geração conjunta com efeitos de deslocamento, fluxos de substituição/versionamento em vigência, MFA, política de retenção e backup/recuperação.
