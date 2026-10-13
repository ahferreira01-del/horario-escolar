# Horário Inteligente — Fase 4O: primeiro adaptador OR-Tools CP-SAT

## O que entrou no código
- `backend/app/solver_cpsat.py`: adaptador **experimental** OR-Tools CP-SAT,
  com variáveis binárias, restrições inteiras, tempos de execução limitados e
  resultado em formato compatível com o solver atual.
- `backend/app/solver_preview.py`: permite executar a mesma montagem de
  restrições com `all_grid(data, engine="cpsat")`; o padrão continua sendo
  `engine="milp"`. **A API NÃO usa CP-SAT nesta fase.**
- `backend/requirements.txt`: instala OR-Tools para que o CI execute os testes
  de paridade, em vez de ignorar a integração por pacote ausente.
- `backend/tests/test_phase4o_cpsat_parity.py`: verifica OR-Tools real,
  objetivos fracionários, disponibilidade exata, limites de recursos,
  deslocamento direcional, cargas semanais em minutos com pesos fracionários,
  manutenção do motor padrão e cenário de seis turmas
  em duas escolas com professores compartilhados e laboratório.
- `backend/tests/test_phase4l_multischool_fixture.py`: fixture de múltiplas
  unidades reutilizável por ambos os motores.
- `scripts/benchmark_solver_fase4o.py`: ferramenta **manual** e reproduzível
  para medir tempo, cobertura, pendências, estado de otimização e inconsistências
  no verificador independente com dados fictícios do repositório.

## Experimentar localmente
Instale as dependências do backend com Python 3.12 em ambiente isolado:

```bash
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest tests/test_phase4o_cpsat_parity.py -q
cd ..
python scripts/benchmark_solver_fase4o.py --time-limit 8 --output evidencias/benchmark-4o.json
```

**Avisos de interpretação:**
- `complete` significa somente que as cargas mínimas do cenário de teste foram
  atendidas sem violar regras validadas; não implica solução pedagógica ótima.
- `coverage_proven_optimal` só pode ser verdadeiro se a primeira etapa do
  solver provar otimalidade dentro do tempo previsto.
- `solver_status=FEASIBLE` ou `COVERAGE_ONLY` não prova ótima distribuição
  de dias, turnos e janelas.
- A conversão de pesos fracionários para números inteiros em CP-SAT usa escala
  de 1.000.000; a comparação de otimalidade exata contra MILP depende de
  investigação de tolerâncias e conjuntos de dados maiores.
- O benchmark não é prova de escalabilidade, disponibilidade 24/7 ou desempenho
  com centenas de turmas. Não conecta banco de dados nem usa informações reais.
- O protótipo legado permanece com SciPy/HiGHS; este novo adaptador está no
  backend, sem integração da interface ou dos endpoints.

## Condições para considerar ativação na API
1. Cobrir com testes reais de CP-SAT **todas** as regras duras e recursos em
   escolas de portes variados (incluindo carga por minutos, turnos, fusos e
   casos sem solução).
2. Comparar cobertura ótima, pendências, limites de tempo, consumo de memória,
   diferenças e reprodutibilidade em cenários extensos.
3. Adotar chave de ativação separada, telemetria, rollback e tratamento seguro
   de timeout sem nunca publicar um resultado não validado.
4. Executar novamente os testes integrados PostgreSQL/RLS, aprovação,
   publicação concorrente e exportação — inclusive o smoke 4K.
5. Revisão independente de segurança e aceite escolar antes da produção.

## Pendências preexistentes
O smoke da Fase 4K (duas identidades, publicação e exportações no Chromium)
continua implementado, mas **fora do workflow**, pois a tentativa de
alteração do CI foi bloqueada. O sucesso de CP-SAT não supre esse requisito.

**PR em rascunho. Sem merge nem deploy de produção.**
