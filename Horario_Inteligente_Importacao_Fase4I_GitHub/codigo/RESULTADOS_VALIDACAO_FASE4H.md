# Horário Inteligente — Validação da Fase 4H

Estado: **desenvolvimento, NÃO homologado para produção**.

## Executado neste ambiente

- Backend: `pytest -q` — **66 passaram, 5 ignorados**. Os cinco ignorados exigem PostgreSQL efêmero real. Outros testes SQLite verificam o contrato de RLS de forma determinística, mas não constituem certificação do banco PostgreSQL.
- HTTP real da API: `python scripts/smoke_http_fase4g.py` — **PASS**, com backend Uvicorn, SQLite temporário, login, convites, CSRF e isolamento pela API entre organizações.
- Gerador legado: 4 testes selecionados aprovados nesta rodada; a suíte completa não foi concluída nesta execução.
- Parser TypeScript: verificadas as fontes `.ts`/`.tsx` via compilador TypeScript global; **sem erros sintáticos**. Não representa typecheck ou build do Next.js.
- PostgreSQL, migrações nele, RLS runtime e publicação concorrente: **NÃO EXECUTADOS** por ausência de servidor PostgreSQL e de binários de banco.
- Next.js completo: **NÃO EXECUTADO**, o registro npm está inacessível a partir do ambiente atual e as dependências Next/React não estão em cache.
- Browser real: **NÃO EXECUTADO**, pois depende do Next compilado e servidor iniciado.
- OR-Tools CP-SAT: **NÃO IMPLEMENTADO** nesta fase. O gerador experimental permanece como antes.

## Entregas verificáveis adicionadas

- Guarda RLS passou a exigir expressões canônicas para escopo `tenant_id`/`user_id`, rejeitando expressões com predicados alternativos não revisados.
- Guarda rejeita membership PostgreSQL que permita à role da API executar `SET ROLE` mesmo com `NOINHERIT`.
- Testes unitários adicionais para RLS malformado, contagem de permissões e falha segura do gate de homologação.
- Teste preparado para PostgreSQL real: gerar proposta, aprovar, publicar, recusar vigência duplicada, exportar CSV/PDF/XLSX e negar consulta de outra organização.
- Pipeline GitHub Actions com dois gates independentes: PostgreSQL real e navegador Chromium real. O gate PostgreSQL reprova se algum teste crítico for ignorado. O browser exercita login e criação de organização por meio da interface e do proxy Next.js.

## Como executar a homologação real

1. Publicar este código em um repositório GitHub autorizado e habilitar Actions (somente após revisão das políticas e segredos da organização), ou executar em um ambiente de integração descartável com PostgreSQL 16, Node.js 22 e Python 3.12.
2. Acompanhar o workflow `.github/workflows/ci.yml`: `backend_postgres`, `frontend_browser` e `solver_legacy`.
3. Não aprovar produção sem evidência PASS dos testes PostgreSQL, do build completo, do browser e de teste de backup/restore, somados a requisitos pendentes (MFA, limites de taxa, carga, observabilidade, retenção etc.).
4. Nenhum destes testes deve usar banco de produção. Eles criam organizações, perfis e grades fictícias em banco efêmero.

A Fase 4H **não substitui** as fases anteriores nem libera publicação oficial para uso real. Seu ganho é segurança reforçada + infraestrutura de validação integrada reproduzível.
