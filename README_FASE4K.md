# Horário Inteligente — Fase 4K: fluxo oficial no navegador

## Implementado
- `scripts/smoke_browser_publication_fase4k.py`: cenário isolado para duas identidades no Chromium, reaproveitando o cadastro da Fase 4J.
- Coordenador recebe convite, gera e envia proposta à revisão; não deve visualizar controles de aprovação/publicação nem conseguir publicar via API.
- Diretor, em sessão separada, aprova; seleciona a turma e a vigência, pré-valida e publica no PostgreSQL.
- Verificação de histórico, leitura dos arquivos oficiais CSV, PDF e XLSX com assinaturas e MIME e bloqueio de versão com vigência sobreposta.
- A Fase 4J foi ampliada com `after_preview` opcional, sem modificar o fluxo anterior.
- Texto do painel atualizado para não afirmar incorretamente que os testes PostgreSQL nunca foram executados.

## Evidência e limites
Os workflows de Fase 4I/4J continuam aprovados no GitHub. No commit de inclusão deste novo teste, os workflows **não executaram o script 4K**, porque o arquivo `.github/workflows/ci.yml` ainda não o referencia. A tentativa de inclusão foi bloqueada pela conexão do GitHub nesta sessão; não se deve declarar o teste 4K como aprovado sem execução.

## Integração requerida ao CI
Após revisão e autorização do fluxo de CI, no job `frontend_browser_postgres`, imediatamente depois do passo `Fluxo escolar de ponta a ponta no Chromium e PostgreSQL`, executar:

```yaml
- name: Aprovação segregada e publicação oficial no navegador
  env:
    HI_BROWSER_URL: http://127.0.0.1:3000
    HI_BROWSER_ADMIN_EMAIL: admin-e2e@example.com
    HI_BROWSER_ADMIN_PASSWORD: Senha-Teste-Homologacao-123!
  run: python scripts/smoke_browser_publication_fase4k.py
```

A execução deve ocorrer **apenas em PostgreSQL efêmero/RLS com dados de teste**. A mensagem `OFFICIAL_BROWSER_PASSED` é emitida somente após todos os passos concluírem.

## Critérios restantes
- Executar e depurar o smoke da Fase 4K no GitHub Actions.
- Validar exportações com outros perfis e cenários de publicação excepcional, vigências futuras, bloqueios de recursos e professores compartilhados.
- Realizar revisão de segurança, testes de carga, acessibilidade, privacidade/LGPD, backup e restauração.
- Adotar o gerador definitivo OR-Tools CP-SAT somente após validação funcional e métricas de desempenho.

**Não homologado para produção. Não realizar merge automático.**
