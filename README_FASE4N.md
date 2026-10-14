# Horário Inteligente — Fase 4N: propostas e deslocamento interunidades

## Problema corrigido
A assinatura (`source_fingerprint`) protege propostas de alterações
posteriores em turmas, horários, cargas, docentes e disponibilidades, mas
não incluía a matriz de **deslocamento direcional** entre escolas.

Uma alteração do trajeto de um professor compartilhado poderia deixar
uma proposta antiga marcada como "atualizada", embora as restrições
de deslocamento usadas para gerá-la tivessem mudado.

## Solução
- A assinatura agora inclui os registros de `SchoolTravelTime` do
  mesmo tenant, limitados às escolas às quais estão vinculados os
  professores com atribuições no ano/turma em análise.
- Alterações de minutos, inclusão e exclusão de direção relevante
  passam a invalidar propostas já geradas.
- Deslocamentos de escolas sem vínculo com os professores dessa proposta
  não invalidam indevidamente a grade.
- As validações de backend existentes (revisão, aprovação e pré-publicação)
  usam a mesma assinatura e seguem exigindo recálculo após alteração.

## Testes
`backend/tests/test_phase4n_travel_fingerprint.py`:

1. Cria escola de origem e destino, professor compartilhado e tempos
   direcionais válidos, gera proposta; modifica um tempo e verifica
   rejeição de submissão da proposta antiga com HTTP 409.
2. Configura deslocamento entre escolas não relacionadas aos docentes
   da proposta e comprova que a assinatura permanece igual.

## Limites
Não há declaração de prontidão para produção. O teste completo de
aprovação/publicação pelo navegador (Fase 4K) continua sem execução no
CI porque a alteração do workflow está bloqueada; ver `README_FASE4K.md`.
Faltam CP-SAT, carga/benchmark, auditoria de segurança/LGPD e piloto
com dados fictícios.
