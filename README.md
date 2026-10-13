# Horário Inteligente — Aplicação Fase 4I

**Estado:** em desenvolvimento, **não homologado para produção**.

Esta fase continua a Fase 4H, reforçando a validação de deslocamento entre escolas e preparando um **teste de navegador usando a API ligada a PostgreSQL real**, com RLS obrigatório. Nenhum repositório remoto foi criado ou alterado nesta entrega.

# Horário Inteligente — Aplicação Fase 4G

Esta entrega parte integralmente da Fase 4F, adicionando testes HTTP reais e guarda de RLS reforçada. **Ainda não está homologada para produção.**

Leia [`RESULTADOS_VALIDACAO_FASE4G.md`](RESULTADOS_VALIDACAO_FASE4G.md) para conhecer exatamente o que foi ou não testado. Para demonstrar o backend, execute `python scripts/smoke_http_fase4g.py` na raiz após instalar as dependências Python. Esse smoke usa SQLite temporário e jamais substitui os testes de RLS com PostgreSQL.

---

# HORÁRIO INTELIGENTE — FASE 4F (HARDENING DA PRÉ-PUBLICAÇÃO)

**Estado: desenvolvimento, NÃO homologado para produção.** Esta versão preserva o código da Fase 4E e corrige validações independentes: cobertura semanal incompleta não pode ser declarada como completa, pendências parciais devem refletir o déficit real e o limite de **uma aula consecutiva** por disciplina/turma agora é conferido no preflight. Foram adicionados três testes de regressão e um verificador de homologação com saída JSON (`scripts/homologacao_fase4f.py`).

**Verificado neste ambiente:** 51 testes do backend aprovados, 2 testes PostgreSQL não executados; 16 testes do solver experimental aprovados; parser TS/TSX sem erros em 10 arquivos. **Não comprovado:** PostgreSQL/RLS/concorrência reais, build Next.js, testes ponta a ponta no navegador e OR-Tools CP-SAT. Ver `RESULTADOS_VALIDACAO_FASE4F.md` e `RESULTADO_AMBIENTE_FASE4F.json`. Use `python scripts/homologacao_fase4f.py --strict` em um ambiente de integração preparado; a ausência de PostgreSQL ou frontend instalado deve reprovar o gate.

---
# FASE 4E — exportação XLSX implementada; homologação PostgreSQL/Next.js pendente.

A Fase 4E adiciona exportação oficial em **Excel (.xlsx)** com uma aba Resumo, quadros gerais em grupos de até seis turmas e uma aba por turma; reutiliza a autorização `grades.read` e exporta exclusivamente registros de uma publicação oficial. O quadro geral contém horários reais em cada célula, pois a mesma posição de aula pode ter horários distintos entre turmas. Os campos são armazenados como texto, sem executar fórmulas fornecidas por usuários. A interface dispõe de novo link Excel no histórico de grades. A pré-validação na tela é invalidada sempre que mudar a vigência ou justificativa.

**Validação 4E no ambiente de construção:** 48 testes de backend aprovados, 2 testes PostgreSQL ignorados; 16 testes de solver experimental aprovados; arquivo XLSX de demonstração importado e lido; análise sintática TS/TSX passou. Não comprova build completo, PostgreSQL, RLS, concorrência ou solver CP-SAT. Consulte `RESULTADOS_VALIDACAO_FASE4E.md`.

---

# AVISO: FASE 4D — desenvolvimento, ainda não homologado para produção

**Entregas 4D:** verificação de limites semanais entre versões com vigências distintas, ajuste de deslocamentos entre dias, testes de regressão, teste de concorrência preparado para PostgreSQL e exportação de grade oficial em PDF A4. Leia `RESULTADOS_VALIDACAO_FASE4D.md` antes de tentar utilizar o sistema. **A publicação oficial continua NÃO certificada**, pois o PostgreSQL real e o build Next.js não puderam ser executados neste ambiente.

# Horário Inteligente — Aplicação Fase 4D

**Estado: desenvolvimento experimental. Não utilizar com dados reais de escolas nem expor na internet.** A Fase 4D preserva Fases 1–4C e acrescenta um módulo de **pré-validação e publicação controlada por vigência**, que **somente aceita gravação oficial se a execução ocorrer em PostgreSQL com verificação RLS válida**. A transação final ainda não foi ensaiada em PostgreSQL neste ambiente: **publicação não certificada para produção**.

## Novidades desta versão

- `backend/app/publication.py`: publicação por lote contendo uma ou mais partes (escola + proposta aprovada + conjunto de turmas), com intervalo de vigência. O lote é transacional e utiliza um **advisory lock PostgreSQL por organização** antes de revalidar e inserir registros.
- `POST /api/tenants/{tenant_id}/publications/preflight`: checagem sem gravação de vigência, escolas autorizadas, aprovação, cargas/slots, disponibilidade, conflitos docentes, deslocamento obrigatório entre unidades, lotação e capacidade de recursos, limites e grades oficiais existentes. **Uma pré-validação NÃO reserva horários.**
- `POST /api/tenants/{tenant_id}/publications/publish`: exige token CSRF, permissões específicas, PostgreSQL/RLS e revalidação **dentro** da transação e do lock; recusa SQLite com HTTP 503.
- `PUT /api/tenants/{tenant_id}/publications/travel/{from_school_id}`: configuração de deslocamento direcional, com autorização de escrita nas duas unidades e auditoria.
- `GET /api/tenants/{tenant_id}/publications?school_id=...`, `GET /api/tenants/{tenant_id}/publications/{id}` e `/export.csv`: consulta autorizada e exportação CSV das versões publicadas. As versões registradas são append-only para a conta runtime e as vigências sobrepostas da mesma turma são recusadas.
- `backend/alembic/versions/0003_official_publications.py`: novas tabelas `school_travel_times`, `published_grades`, `published_lessons` e `published_classes`; RLS e permissões PostgreSQL, inclusive atualização restrita de perfis-padrão já existentes.
- Interface `frontend/app/publication-panel.tsx`: pré-validação, seleção de turmas e data de vigência, confirmação explícita e consulta do histórico de publicações.

## Limites e NÃO implementado

**Esta entrega não libera uso comercial/produção.** Persistem como pendências de segurança e regra funcional:

- Ensaio real das migrações 0003, RLS, transação e **publicações concorrentes** em PostgreSQL; sem Docker/PostgreSQL no ambiente de construção, esse ensaio **não foi realizado**.
- Build e execução integral do Next.js, indisponíveis no ambiente porque o cache npm não contém todas as dependências.
- Comparação independente com OR-Tools CP-SAT; o gerador ainda utiliza o adaptador experimental SciPy/HiGHS.
- Calendários de exceção (feriados, eventos pontuais, aulas eventuais), substituição/revogação controlada de uma versão já vigente, exceções intertenant, regras de bloqueios fixos e otimização conjunta em um único job de múltiplas escolas.
- A geração de propostas ainda ocorre **por escola**; lotes de publicação multiescolas passam por validação conjunta e exigem propostas já aprovadas individualmente por escola.
- Exportação oficial em **XLSX** e revisão do layout PDF com dados reais, política de retenção, MFA, rate limiting, monitoramento, ensaio de backup/restauração, testes de carga e revisão jurídica.

**Proteção adicional:** o módulo não substitui versões já publicadas automaticamente; se houver vigência sobreposta para a mesma turma, recusa o lote e solicita definição explícita de nova política. A falta de tempo de deslocamento para professor que transita entre unidades também é impedimento, não é interpretada como zero. A publicação parcial exige permissão específica, proposta aprovada e justificativa excepcional.

## Como rodar (nova instalação de desenvolvimento)

São necessários Docker Engine/Compose, acesso a PyPI/npm e credenciais fortes.

```bash
cp .env.example .env
# Alterar POSTGRES_PASSWORD, RUNTIME_DB_PASSWORD e SESSION_SECRET
# Credenciais owner e runtime devem ser diferentes.
docker compose up --build -d
# Após serviço API ficar saudável:
docker compose exec api python -m app.cli bootstrap-platform \
  --email admin@exemplo.com --name "Administrador" \
  --password "SENHA-FORTE-DE-TESTE-COM-MAIS-DE-12-CARACTERES"
```

Previsto: interface `http://localhost:3000`, API `http://localhost:8000`. A conta `horario_owner` executa as migrações; `horario_runtime` opera a API sujeita a RLS. **Não reaproveitar volume de Fase 4A/4B sem backup e ensaio de migração**. `POSTGRES_USER` não altera automaticamente o usuário dono de um volume existente. Nunca apagar um volume existente para resolver falhas de migração.

Para testes sem Docker:

```bash
cd backend
pip install -r requirements.txt
pytest -q
cd ../solver_poc_v0_2
pip install -r requirements.txt
pytest -q
```

Para prova de RLS real, configurar `HI_TEST_PG_OWNER_URL` e `HI_TEST_PG_RUNTIME_URL` em **PostgreSQL de testes exclusivo**, aplicar Alembic `upgrade head` e executar `pytest` no backend. O workflow `.github/workflows/ci.yml` descreve uma tentativa de integração; só resultados efetivos do CI comprovam o funcionamento.

## Exemplo de pré-validação (requisição autenticada)

```json
{
  "parts": [
    {
      "school_id": "ID-DA-UNIDADE",
      "proposal_id": "ID-DA-PROPOSTA-APROVADA",
      "class_ids": ["ID-DA-TURMA"]
    }
  ],
  "valid_from": "2027-02-01",
  "valid_to": "2027-06-30",
  "exceptional_justification": null
}
```

O endpoint `preflight` usa o corpo acima. O endpoint `publish` usa o mesmo corpo, requer CSRF e revalida inteiramente antes de efetivar.

## Testes observados nesta construção

- Backend: **46 passaram**, **2 testes PostgreSQL ignorados** (sem servidor).
- Arquivos TypeScript/TSX relevantes: **parser OK** via compilador TypeScript global. Não corresponde a typecheck/build Next.js completo.
- Gerador legado: suíte preservada. Seu tempo de execução integral deve ser confirmado em CI; este pacote não contém alterações no gerador original.

Veja `PROXIMAS_FASES.md` para as prioridades após esta entrega.
