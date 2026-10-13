# Horário Inteligente

Sistema SaaS multiempresa para planejamento, geração e publicação de horários escolares.

## Situação atual

**Em desenvolvimento — não homologado para produção.** O código-fonte da Fase 4I será importado em uma branch de desenvolvimento e submetido a testes antes da integração à branch `main`.

O sistema foi projetado para cadastrar organizações, escolas, professores, turmas e disponibilidades exatas, gerar grades com restrições, revisar e aprovar propostas e exportar horários.

## Integração planejada

- API: Python / FastAPI
- Aplicação web: Next.js / TypeScript
- Banco de dados: PostgreSQL com isolamento multiempresa (RLS)
- Gerador atual: protótipo SciPy/HiGHS; OR-Tools CP-SAT ainda pendente
- CI: GitHub Actions para testes de API, PostgreSQL, frontend e navegador

**Atenção:** não cadastrar dados reais de escolas nem ativar publicação oficial antes de comprovar o isolamento de dados, concorrência e fluxo ponta a ponta.

## Próximo marco

Importar o pacote `Horario_Inteligente_Aplicacao_Fase4I.zip` mantendo sua estrutura de pastas, executar a homologação no GitHub Actions e corrigir eventuais falhas.

Não publicar arquivos `.env`, senhas, bancos locais, diretórios `node_modules` ou credenciais.
