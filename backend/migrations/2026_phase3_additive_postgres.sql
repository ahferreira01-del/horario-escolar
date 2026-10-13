-- Horário Inteligente / Fase 3. REVISAO OPERACIONAL NECESSARIA.
-- Executar em ambiente de testes com backup e janela exclusiva de manutenção.
-- Esta migração é incremental sobre o schema da Fase 2 no PostgreSQL.
-- Em seguida executar 'python -m app.cli init-db' para criar as novas tabelas e habilitar RLS.
BEGIN;
ALTER TABLE teaching_assignments ADD COLUMN IF NOT EXISTS load_mode varchar(10) NOT NULL DEFAULT 'lessons';
ALTER TABLE teaching_assignments ADD COLUMN IF NOT EXISTS target_minutes integer;
ALTER TABLE teaching_assignments ADD COLUMN IF NOT EXISTS min_minutes integer;
ALTER TABLE teaching_assignments ADD COLUMN IF NOT EXISTS max_minutes integer;
ALTER TABLE teaching_assignments ADD COLUMN IF NOT EXISTS resource_id varchar(36);
-- Sem mudanças nas atribuições anteriores: permanecem modo lessons.
COMMIT;
