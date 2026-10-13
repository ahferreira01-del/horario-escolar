# Horário Inteligente — Fase 4P: ensaios de escala e seleção controlada de motor

## Objetivo e estado
Comparar SciPy/HiGHS MILP (motor atual) e OR-Tools CP-SAT (experimental),
sem ativar CP-SAT nos endpoints existentes, sem dados reais e sem afirmar
que o produto já suporta centenas de turmas em produção.

## Implementação

- `backend/app/solver_controlled.py`:
  `controlled_preview(data, engine="milp", enable_experimental=False,
  fallback_on_unsolved=False)`.
  - MILP continua **padrão**.
  - CP-SAT exige `engine="cpsat"` **e**
    `enable_experimental=True`.
  - Rollback para MILP exige `fallback_on_unsolved=True` e só acontece
    se a execução CP-SAT declarar `result="unsolved"`.
  - Se as aulas forem inválidas, o estado for desconhecido, a entrada
    estiver incorreta ou o solver lançar exceção, a chamada **falha
    fechada**, sem fallback silencioso.
  - Saída inclui `engine_control` com motor solicitado/executado,
    indicação de fallback, justificativa padronizada e durações.
  - Sem ativação por variável de ambiente e **sem qualquer chamada da API**
    a esse módulo. Não contém integração com publicação oficial.
- `backend/app/solver_scenarios_4p.py`:
  gerador sintético determinístico para 2 a 100 turmas (quantidades
  pares), em duas escolas, com docentes compartilhados, limites e
  laboratórios. Cada turma exige duas aulas semanais. Nenhum dado real.
- `backend/tests/test_phase4p_controlled_engine.py`:
  opt-in, política de rollback, contratos inválidos, verificação
  independente e não reexecutar entradas inseguras.
- `backend/tests/test_phase4p_scale_fixture.py`:
  integridade dos datasets e cenário de **12 turmas/24 aulas** com
  paridade dos dois motores. É um teste funcional, **não um benchmark**.
- `scripts/benchmark_solver_fase4p.py`:
  mede os dois motores com tamanhos configuráveis, registra cobertura,
  status de otimalidade e tempos observados, verifica cada resultado
  com o validador independente e grava JSON.

## Reprodução manual

Após instalar as dependências de `backend/requirements.txt`:

```bash
cd backend
python -m pytest -q tests/test_phase4p_controlled_engine.py tests/test_phase4p_scale_fixture.py
cd ..
python scripts/benchmark_solver_fase4p.py --sizes 8,12,24 --time-limit 5 --output evidencias/fase4p.json
```

`--sizes` aceita até cinco tamanhos distintos e pares, de 2 a 100.
`--time-limit` define de 1 a 15 segundos por etapa de otimização.
A execução pode levar mais do que `time-limit` (montagem, duas
etapas e verificação), e medições variam de hardware para hardware.

Os resultados de comparação NÃO devem ser interpretados como um SLA.
Divergências de cobertura em tamanhos maiores podem resultar de limite
de tempo e precisam de análise; não são automaticamente equivalência
de qualidade. Falha de verificação independente termina com erro.

## Critérios antes de ativar CP-SAT na aplicação

1. Validar recursos, docentes e deslocamentos em modelos complexos,
   inclusive minuto, turno, recursos compartilhados e grade inviável.
2. Medir p50/p95 de tempo e pico de memória com carga gradativa
   representativa (por exemplo 24, 48, 100+ turmas), em runner fixo.
3. Definir limites reais, cancelamento, isolamento do processamento,
   métricas, rollback e observabilidade sem dados pessoais nos logs.
4. Habilitação gradual por configuração versionada, auditoria de
   decisões e testes integrados completos antes de qualquer rollout.
5. Finalizar o smoke 4K da publicação por dois usuários e exportações
   no Chromium. O script existe, mas **não consta no CI atual** por
   bloqueio prévio de alteração de workflow.
6. Revisão independente de LGPD/segurança, backups e aceite escolar.

**A Fase 4P não promove motor, não implanta em produção e não faz merge.**
