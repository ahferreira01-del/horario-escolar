# Horário Inteligente — Fase 4F: validação e limites

**Estado:** código de desenvolvimento, não homologado para produção.

## Alterações efetivamente implementadas

1. **Validação independente da cobertura semanal na pré-publicação.** Cada atribuição é comparada à carga exigida em aulas ou ao mínimo em minutos. Em publicação parcial, o déficit deve corresponder exatamente à pendência registrada no snapshot; uma proposta que se autodeclara completa não pode omitir aulas silenciosamente. Permanece a proibição de exceder a carga máxima.
2. **Máximo consecutivo igual a 1.** Além de proibir três aulas da mesma disciplina seguidas, o preflight agora recusa duas seguidas quando a disciplina/turma está limitada a uma. Se há dois professores da mesma disciplina/turma, prevalece o limite mais restritivo. Recreios não interrompem a contagem pedagógica.
3. **Testes de regressão.** Três novos cenários reproduzem cobertura falsamente completa, pendência inconsistente e violação de máximo consecutivo de uma aula.
4. **Comando de homologação reproduzível.** `python scripts/homologacao_fase4f.py --out relatorio.json` executa suítes disponíveis e registra, sem fingir sucesso, verificações não executadas; `--strict` impede aprovação na ausência de gates de integração.

## Gates obrigatórios antes de publicar com escolas reais

- Executar migrações Alembic e verificar RLS sob usuário PostgreSQL runtime sem privilégios de owner, com banco efêmero. **Não realizado neste ambiente.**
- Executar concorrência de publicação com múltiplas transações, simulando acesso de unidades autorizadas. **Não realizado neste ambiente.**
- Instalar dependências npm e executar `npm run lint:types` e `npm run build`, em seguida validar fluxo completo no navegador. **Não realizado neste ambiente.**
- Migrar e provar equivalência do motor para OR-Tools CP-SAT: **não implementado**. O protótipo continua SciPy/HiGHS.
- Revisar requisitos ainda não implementados e executar testes de segurança e carga antes de disponibilizar em produção.

## Execução sugerida em ambiente preparado

```bash
# Use um PostgreSQL EFÊMERO, exclusivo para testes, com owner/runtime separados.
# Defina HI_TEST_PG_OWNER_URL e HI_TEST_PG_RUNTIME_URL apenas para esse banco.
cd backend && python -m pytest -q && cd ..
cd solver_poc_v0_2 && python -m pytest -q && cd ..
cd frontend && npm install --no-audit --no-fund && npm run lint:types && npm run build && cd ..
python scripts/homologacao_fase4f.py --strict --out relatorio_homologacao.json
```

O workflow `.github/workflows/ci.yml` mantém os testes PostgreSQL. Nenhum resultado local em SQLite comprova RLS ou transações PostgreSQL. A função de publicação deve permanecer indisponível operacionalmente até a comprovação dos gates necessários.
