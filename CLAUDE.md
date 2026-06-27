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
- **INF_MENSAL de FIAgro** é dataset PRÓPRIO (`dados.cvm.gov.br/dados/FIAGRO/DOC/`), com
  arquivos **MENSAIS** (`inf_mensal_fiagro_AAAAMM.zip`, não anual), cobertura só de
  **2025-05+**, CSV único (sem membro `complemento`), identidade por `CNPJ_Classe`.
- **GOTCHA do `Dividend_Yield_Mes` do FIAgro** (≠ do FII apesar do nome): convive com 3
  convenções no mesmo arquivo — valores ~0,9–1,5 (que VARIAM) em **percentual** (÷100);
  ≤0,05 já em **fração** (0,01 = 1%/mês, mas costumam vir "chapados" = placeholder, baixa
  confiança); absurdos (milhões) são **R$ distribuído mal-arquivado** → NaN; negativos →
  NaN. Tratado em `pipeline/fiagro.clean_fiagro_dy`. Validado em 2025-05..2026-05.

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
- **GOTCHA de rede dos runners (validado 2026-06-27)**: o runner do GitHub **NÃO alcança
  `dados.cvm.gov.br`** (`[Errno 101] Network is unreachable` — bloqueio de egress p/ IPs de
  nuvem). O Yahoo (yfinance), ao contrário, **só** funciona no GH (não neste ambiente).
  Consequência: pipelines da CVM (fundamentos, ingest FII/FIAgro, IPE) **só geram dado bom
  ONDE A CVM É ALCANÇÁVEL — este ambiente**, não o GH. A âncora yfinance é coletada no GH
  (`anchors.yml` → `config/shares_anchor.yml`) e os fundamentos são gerados aqui com
  `--no-yfinance` lendo esse cache. **Trava anti-clobber** em todos os scripts da CVM:
  se nenhum período baixa, abortam (exit 1) sem escrever — `bash -e` derruba o passo antes
  do commit, então um run sem CVM (caso do GH) nunca sobrescreve artefato bom.
  - No GH funcionam (com cron): `prices.yml` (diário, yfinance) e `anchors.yml` (trimestral,
    yfinance). **TRAVADO 2026-06-27 (opção A do Felipe)**: `fundamentos.yml` e `ingest.yml`
    ficaram **só com `workflow_dispatch` (sem cron)** — gerariam só vermelho no GH. A geração
    da CVM (fundamentos + ingest FII/FIAgro/IPE) roda **neste ambiente** e commita o artefato.

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
3. **DY de FII (rendimentos)** ✅ feito — `Percentual_Dividend_Yield_Mes` do INF_MENSAL
   (DY mensal oficial). `scripts/ingest_fii_dy.py` → `data/fii_dy.json`: TTM (soma dos 12
   meses), histórico anual, mediana/média, recorrência e flag yield trap.
4. **Score composto** → short-list ranqueada. ✅ feito (`pipeline/score.py`,
   `data/score.json`): 40% recorrência + 30% yield-vs-baseline + 30% crescimento ×
   sustentabilidade (payout, ROE, **dívida líq./EBITDA ≤ 3x** — N/A em banco), corte por
   yield trap.
5. **Dashboard Next.js/Netlify**. ✅ feito e **NO AR** em
   https://renda-passiva-acoes-fiis.netlify.app/ (static export → `web/out`, `netlify.toml`).
   Lê os JSON de `data/` no build; sem runtime.
6. Alertas (e-mail/Telegram pela Action) + import de carteira via CSV. **HOLD** (sinalizado).
7. Fatos relevantes da watchlist (feed IPE/RAD da CVM — dataset aberto `ipe_cia_aberta`).
   ✅ feito — `scripts/ingest_ipe.py` → `data/fatos_relevantes.json`: índice dos
   documentos (fato relevante, aviso aos acionistas, relatório de proventos) das ações,
   mais recentes com link pro RAD. `pipeline/ipe.py`. Front com a seção. Não lê o corpo
   dos PDFs (opcional/depois). Roda no `ingest.yml` mensal.

### Fundos estilo-ações (FII + FIAgro) ✅ feito
A análise de fundos foi elevada ao mesmo rigor das ações (DY de longo prazo + constância +
saúde financeira no tempo + projeção), com **listas separadas** (decisão do Felipe):
- **FIAgro** — `scripts/ingest_fiagro.py` → `data/fiagro.json` + `data/fiagro_score.json`.
  Universo **auto-detectado**: fi-agro negociados da brapi (volume/spot) ∩ ticker
  reconstruído do ISIN da cota (mnemônico `[2:6]+11`). Histórico curto (~1 ano): DY 12m
  anualizado quando <12 meses, baseline **cross-sectional** (mediana dos pares), e flag de
  **confiança** que rebaixa DY-placeholder constante. Ver gotcha do `Dividend_Yield_Mes`.
- **FII** — `scripts/ingest_fii_fundos.py` → `data/fii_fundos.json` + `data/fii_score.json`.
  Reusa `pipeline.fiagro.aggregate_fund`: DY + CAGR do DY + saúde (alavancagem = passivo/PL
  via `Valor_Ativo−PL`, preservação da cota, taxa de adm) + P/VP. Baseline = histórico do
  **próprio fundo** (~5 anos), trap per-fundo.
- Score em `pipeline.score.fund_composite_score` (+ `fund_sustainability_multiplier`):
  mesmos 40/30/30, sustentabilidade adaptada (alavancagem/cota/taxa/recorrência no lugar de
  payout/ROE/dívida). Recorrência escala pela **janela disponível** (fundo novo que pagou
  todo mês = 1,0). Roda no workflow mensal `ingest.yml`. Front com as duas short-lists.
- **Classificação por TIPO** (decisão do Felipe — não comparar peras com maçãs):
  FII tijolo/papel/FoF via composição do ativo (`fii.classify_fii_tipo`, membro
  `ativo_passivo`); FIAgro crédito/terras via `Imoveis_Rurais` × instrumentos de crédito
  (`fiagro.credit_profile`). Baseline cross-sectional do FIAgro é **por tipo**.
- **Camada de crédito do FIAgro** (núcleo fundamentalista dos fundos de recebíveis):
  inadimplência (`Vencidos/(A_Vencer+Vencidos)`), diversificação (HHI de CRA/CRI/CPR/deb),
  liquidez (`Necessidades_Liquidez/PL`), composição. **FII** ganhou nº de cotistas e
  separação de amortização (`Amortizacao_Cotas_Mes` = devolução de capital, não yield).
- **Vacância de FII de tijolo (FNET)** — `pipeline/fnet.py` + `scripts/ingest_fii_vacancia.py`
  → `data/fii_vacancia.json`. A CVM aberta não traz vacância; vem do **Informe Trimestral
  Estruturado** (ANEXO 39-II) do FNET. Vacância + inadimplência de aluguel do fundo,
  ponderadas pela receita dos imóveis. Cobertura **parcial e honesta**: FNET é lento/instável
  (retry/backoff) e o layout varia por administrador — papel não tem; XPML preenche a coluna
  de vacância com ocupação (100%) → trava de sanidade (>40% = N/A). Parser por PADRÃO
  ("Área (m" + 3 percentuais), não pelo cabeçalho (que aparece 1×). Validado: HGLG 3,65%/37
  imóveis, HGRU 0,52%/100, VISC 5,46%.
- **Camada macro (BCB/SGS)** — `pipeline/macro.py` + `scripts/fetch_macro.py` →
  `data/macro.json` (CDI 12m composto, Selic meta, IPCA 12m; API pública sem auth). Gera o
  **spread sobre CDI** (`DY TTM − CDI 12m`) dos fundos — é **contexto aditivo**, NÃO entra
  no score nem altera a metodologia travada de DY. **Liquidez de mercado** (volume diário
  da brapi) exibida nas duas short-lists. Fontes de mercado ficam em brapi/BCB; aggregators
  (Status Invest etc.) são evitados por fragilidade/ToS e pela decisão "CVM autoritativa".

**Refinamentos** (todos ✅ nesta leva): DMPL (payout declarado via mutações do PL,
`proventos_declarados`/`payout_declarado_por_ano`; Bradesco N/A — DMPL anômala); DY
histórico de ações estendido p/ 10y (alcança ~2015); XPML11 resolvido (DY mensal negativo
de 2026-01 era anomalia → descartado). Pendente só o que está em HOLD (Fase 6). Detalhe em
`docs/HANDOFF.md`.

## Estado atual do código
Ver `docs/STATUS.md` para o mapa vivo de módulos prontos / pendentes, e
`docs/HANDOFF.md` para a retomada completa (feito, pendente, memórias de cálculo/gotchas
validados no dado real, decisões e como rodar tudo).
