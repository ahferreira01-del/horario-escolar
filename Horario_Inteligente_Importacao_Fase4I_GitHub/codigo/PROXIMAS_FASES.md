# Horário Inteligente — Próximos passos após a Fase 4I

**Prioridade de bloqueio:** rodar o workflow integrado em repositório/runner autorizado com PostgreSQL 16 + Next.js + Chromium. Investigar as falhas reais sem enfraquecer RLS, autorização ou publicação transacional. Não publicar com contas privilegiadas.

**Depois de homologar:** executar teste simultâneo entre duas escolas, testes de visibilidade entre tenants, publicação parcial excepcional, leitura do PDF/Excel, backup e restauração em base descartável.

**Motor:** migrar progressivamente de SciPy/HiGHS para OR-Tools CP-SAT e demonstrar equivalência funcional nos cenários de horários completos e parciais, inclusive professores compartilhados, janelas, sequências após recreio, cargas por minutos e recursos. A versão anterior continua experimental.

**Fora de produção:** cronograma de retenção/LGPD, MFA, rate limit e testes de desempenho ainda exigem aceite e evidência.
