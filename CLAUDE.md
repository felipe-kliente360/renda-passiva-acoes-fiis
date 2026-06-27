# divbr — contexto persistente do projeto

> Este arquivo é carregado automaticamente como contexto. Mantê-lo atualizado
> quando uma decisão mudar. Decisões TRAVADAS não se relitigam sem o Felipe sinalizar.

## Quem é o parceiro de engenharia nesta sessão
Parceiro de engenharia do Felipe (perfil técnico avançado, APIs e código). Rigor
metodológico > atalhos de conveniência. Decisões travadas e documentadas para não
relitigar. Antes de codar uma etapa nova: propor um plano curto e esperar o ok.
Escrever testes. Commits pequenos, escopo claro, mensagem imperativa.

## O produto
**divbr** — inteligência de renda passiva na B3 (ações, FIIs e FIAgros). Encontrar e
monitorar papéis sólidos, com histórico saudável e pagamentos recorrentes e relevantes
de dividendos/JCP/rendimentos. Pergunta-guia de todo cálculo: **isto paga, e vai
continuar pagando?** Não é caçar o maior yield do trimestre — é o fluxo que se sustenta.
Produto final: portal web alimentado por pipelines que rodam sozinhos, sem infra paga.

## Decisões TRAVADAS — não relitigar sem sinalização

### Metodologia de Dividend Yield
> **Revisado em 2026-06-26 (sinalizado pelo Felipe).** Antes atribuíamos por **data-com**
> (fonte B3/brapi/yfinance). Mudança: a tese é de **longo prazo**, não pontual, e as fontes
> de mercado não cravam o original. Passamos a usar o **dado oficial da CVM (ITR/DFP)**
> atribuído pela **competência do período**, fechando janelas (ano + TTM de 4 trimestres).

- Proventos atribuídos pela **competência do período da CVM** (não mais data-com).
- **Numerador (DY)** = dividendos + JCP **pagos no período** — linha de financiamento da
  **DFC** (`6.03.x`). Em R$, escala `MIL` (×1000). Base caixa, atribuição limpa por período.
- **Numerador (payout)** = proventos **declarados/propostos sobre o resultado do exercício**
  (DMPL), que casam com o lucro do mesmo ano. Sabor diferente do DY, de propósito.
- **Granularidade**: DY no **nível da empresa** = proventos totais ÷ valor de mercado
  (preço × ações de `composicao_capital`). Evita ratear provento entre ON/PN.
- Denominador = **preço negociado, ajustado só por split/grupamento, NUNCA por dividendo**
  (preço ajustado-por-provento infla o DY histórico). Vem do pipeline de preços (Fase 1).
- **DY corrente** = proventos TTM (4 últimos trimestres do ITR) ÷ valor de mercado atual.
- **DY histórico** = somas anuais ÷ preço médio do ano; reportar **média E mediana**
  (divergência grande = provento extraordinário).
- **Flag de yield trap**: DY corrente > 1,5× a mediana histórica do papel.

### Score composto (pesos equilibrados)
- Recorrência/segurança do pagamento — 40%
- Yield atual vs. baseline histórico — 30%
- Crescimento do dividendo — 30%
- Sustentabilidade: payout 30–80%; pagou em ≥8 dos últimos 10 anos; checagens de
  dívida líquida/EBITDA e ROE.

### Formato cru da CVM (sempre tratar)
- Encoding **ISO-8859-1**; separador `;`. **Separador decimal varia por dataset** —
  NÃO é universalmente vírgula. Validado: **INF_MENSAL de FII usa PONTO** (ex.: `92.21`,
  em 2020 e 2026). Decimal é config-driven por dataset em `config/columns.yml` e threadado
  via `spec.decimal`; o default vírgula é só fallback. Validar cada dataset novo.
- INF_MENSAL de FII tem 3 CSVs no ZIP (`ativo_passivo`, `complemento`, `geral`); o VP da
  cota / PL / cotas vivem no **`complemento`**. O ingest escolhe o membro pela resolução
  de colunas, não pelo 1º CSV.
- O ZIP do ano corrente é reescrito a cada atualização (não incremental).
- Nomes de coluna podem ter mudado após a Resolução 175 → **validar contra arquivo real,
  nunca fixar no código** (config-driven via `config/columns.yml`). Ex.: `CNPJ_Fundo`
  (2020) → `CNPJ_Fundo_Classe` (2026).

### Arquitetura
```
GitHub Actions (cron) → Python (pandas) ingestão+normalização
   → artefatos estáticos JSON/Parquet commitados no repo
   → Front (Next.js) lê os JSON com ISR
```
- Armazenamento: JSON/Parquet versionados no repo. Sem banco — estático é suficiente,
  auditável e grátis.
- Orquestração: GitHub Actions, cron mensal (fundamentos) + diário (preços) +
  `workflow_dispatch`.
- **Front: Next.js, deploy no Netlify free tier** (decisão vigente; o briefing original
  citava Vercel — Felipe optou por Netlify para o MVP).

### Fontes de dados
- **CVM dados abertos** — fonte de verdade e **autoritativa de proventos + fundamentos**
  (ITR/DFP para ações; INF_MENSAL/INF_TRIMESTRAL para FII/FIAgro). Proventos saem da DFC
  (pagos) e DMPL (declarados), não mais da B3.
- **brapi / yfinance** — só **preço de mercado** (a CVM dá o patrimonial). yfinance série
  split-adj/div-unadj; brapi spot.
- **B3 / IPE-RAD** — eventos corporativos e fatos relevantes (data-com exata, comunicados).
  Sem API decente → fica para a Fase de fatos relevantes, não é mais a fonte do DY.

## Convenções operacionais
- **Git: tudo em `main`.** MVP, deploy contínuo no Netlify. Sem branches, sem PR, até o
  Felipe dizer o contrário.
- Python **3.11**, `pandas`, `pyarrow`, `pyyaml`, `pytest`. Type hints.
- Estrutura: `pipeline/` (lógica pura), `scripts/` (entry points), `config/` (YAML),
  `tests/`, `data/` (artefatos), `.github/workflows/`, `docs/`.
- Toda lógica de cálculo é **pura e testável offline**; rede fica isolada nos módulos de
  download. Commits pequenos. Rodar os testes antes de propor commit. Nunca commitar segredos.

## Limitações a respeitar (não contornar)
- Carteira na B3 não tem API pública sancionada para varejo → importar CSV exportado da B3.
  **Não** implementar scraping de login / automação da área do investidor.
- FIAgro tem cobertura menos consolidada que FII na base aberta → tratar caso a caso, não
  assumir paridade de campos.
- Alarme de "oportunidade" sempre cruzado com o flag de yield trap.
- Não inventar dados nem cotações. Se não puder buscar online no ambiente, deixar a lógica
  testável offline e dizer o que rodar localmente.

## Roadmap
0. **Fundação** (normalize CVM, parser FII config-driven, métricas puras de DY). ✅ feito
1. **Pipeline de preços** (brapi + yfinance, série ajustada só por split, P/VP, preço médio
   anual, export, Action diária). ✅ feito
2. **Fundamentos + proventos via CVM ITR/DFP (ações)** — espinha da tese. ✅ feito
   (DFP 2015–2025): proventos pagos (DFC), lucro atribuível à controladora (DRE), ações
   (`composicao_capital`, escala por ano via âncora yfinance), DY histórico/corrente,
   payout, recorrência, CAGR e flag yield trap → `data/fundamentos.json`. Config-driven
   por `config/contas.yml`, tratando os dois planos (financeira × não-financeira). ✅ inclui
   refinamentos: **P/VP de ações** (book value do BPP, controladora) e **DY corrente por TTM
   via ITR** (ponte ano-cheio + YTD). (Funde as antigas Fases 2+3 — ver revisão da
   metodologia de DY.) Pendente: dívida líquida/EBITDA; DMPL (proventos declarados).
4. **Score composto** → short-list ranqueada. ✅ feito (`pipeline/score.py`,
   `data/score.json`): 40% recorrência + 30% yield-vs-baseline + 30% crescimento ×
   sustentabilidade (payout, ROE), corte por yield trap.
5. **Dashboard Next.js/Netlify**. ✅ feito (`web/`, static export → `web/out`,
   `netlify.toml`). Lê os JSON de `data/` no build; sem runtime. Falta o deploy efetivo
   no Netlify (conectar o repo).
6. Alertas (e-mail/Telegram pela Action) + import de carteira via CSV.
7. Fatos relevantes da watchlist (feed IPE/RAD da CVM).

## Estado atual do código
Ver `docs/STATUS.md` para o mapa vivo de módulos prontos / pendentes.
