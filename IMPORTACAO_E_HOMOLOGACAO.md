# Importação e homologação — Fase 4I

**Estado:** o código completo ainda precisa ser importado na branch `development/fase4i-homologacao`. Nenhuma aplicação está homologada nem publicada.

## Envio do código
1. Use o pacote `Horario_Inteligente_Fase4I_Importacao_GitHub.zip` entregue nesta conversa.
2. Extraia o ZIP em uma pasta local no Windows.
3. Execute o script `publicar-no-github.ps1` conforme o `LEIA-ME-IMPORTACAO.txt`.
4. O script clona a branch de desenvolvimento, copia os arquivos de `codigo/`, verifica alterações e pede confirmação antes de enviar.
5. **Nunca envie** arquivos `.env`, credenciais, dados pessoais, bancos locais, caches ou dependências instaladas.

## Homologação obrigatória após o envio
O workflow original em `.github/workflows/ci.yml` define os jobs `backend_postgres`, `frontend_browser_postgres` e `solver_legacy`. Exigir execução real de todos os jobs com resultado de sucesso; testes PostgreSQL ignorados, falhas de RLS, build Next.js ou testes do navegador impedem homologação.

Critérios mínimos:
- Migrações PostgreSQL 16 e políticas RLS ativas com contas separadas.
- Isolamento entre organizações e contas autorizadas.
- Geração, revisão, aprovação, publicação e exportação pelo navegador.
- Testes concorrentes de publicação entre escolas e proteção de versão/vigência.
- Sem artefatos secretos, dados reais ou chaves no histórico do Git.

**Não usar em produção** até as verificações de segurança, concorrência e aceitação funcional estarem comprovadas. O motor ainda é experimental com SciPy/HiGHS; OR-Tools CP-SAT permanece pendente.
