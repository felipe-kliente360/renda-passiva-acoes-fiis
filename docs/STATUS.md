# Estado do código (mapa vivo)

Atualizado em: 2026-06-27

## Pronto e testado (offline)
| Módulo | Função | Testes |
|---|---|---|
| `pipeline/normalize.py` | Leitura CVM (ISO-8859-1, `;`, decimal por-dataset), ZIP/CSV, `to_numeric_ptbr` | `test_normalize.py` |
| `pipeline/columns.py` | Resolução config-driven de colunas + escolha de membro do ZIP | `test_columns.py` |
| `pipeline/fii.py` | INF_MENSAL → VP + DY + `parse_fii_enriched` (DY+PL+passivo+taxa+amortização+cotistas) + `classify_fii_tipo` (tijolo/papel/FoF) | `test_fii.py` |
| `pipeline/fiagro.py` | INF_MENSAL FIAgro: parser + `ticker_from_isin` + `clean_fiagro_dy` (gotcha) + `aggregate_fund` (genérica FII/FIAgro) + `credit_profile` (tipo crédito/terras, inadimplência, diversificação HHI, liquidez) | `test_fiagro.py` |
| `pipeline/fundamentos.py` | ITR/DFP: proventos pagos, lucro+PL (controladora), ações, escala, TTM | `test_fundamentos.py` |
| `pipeline/metrics.py` | DY TTM, DY histórico (média/mediana), payout, recorrência, growth, flag yield trap | `test_metrics.py` |
| `pipeline/score.py` | Score composto 40/30/30 × sustentabilidade, corte por yield trap, rank + `fund_composite_score`/`fund_sustainability_multiplier` (fundos) | `test_score.py` |
| `pipeline/ipe.py` | Índice IPE-RAD: parser + `fatos_relevantes` (filtra watchlist + categorias de proventos/materialidade) | `test_ipe.py` |
| `pipeline/macro.py` | BCB/SGS: `fetch_macro_snapshot` (CDI 12m composto, Selic, IPCA) + `accumulate_daily` (puro). Base do spread sobre CDI | `test_macro.py` |
| `pipeline/prices.py` | `split_adjust`, `reconstruct_*`, preço médio anual, P/VP, `fetch_shares_outstanding` | `test_prices.py` |
| `pipeline/export.py` | Export JSON + Parquet com metadados/proveniência | `test_export.py` |
| `pipeline/cvm.py` | Downloaders CVM (FII INF_MENSAL, DFP, ITR; rede isolada) | — (I/O de rede) |

Scripts: `inspect_zip.py`, `ingest_fii.py` (VP), `ingest_fii_dy.py` (DY de FII),
`ingest_fii_fundos.py` (FII estilo-ações: DY/projeção/saúde/score), `ingest_fiagro.py`
(FIAgro auto-detectado + shortlist), `fetch_prices.py`, `ingest_fundamentos.py`
(DY/payout/P/VP/TTM/alavancagem + payout declarado via DMPL), `build_score.py` (short-list
de ações), `ingest_ipe.py` (fatos relevantes IPE-RAD da watchlist).
Workflows: `ingest.yml` (FII VP+DY+score **e FIAgro**, mensal), `prices.yml` (diário),
`fundamentos.yml` (trimestral, gera fundamentos + score de ações).
Front: `web/` (Next.js static export → Netlify; **no ar**) — short-lists separadas de
ações, FIIs e FIAgros.

`pytest`: **86 testes** passando offline. Retomada completa em `docs/HANDOFF.md`.

## Validado contra dados reais (2026-06-27)
- **FIAgro rodado de verdade** (rede aberta): 37 fi-agro da brapi ∩ informe CVM →
  28 com dados, 26 ranqueados. Topo: RZAG/KNCA/XPCA/SNAG/VCRA (~11–13% DY, variam). Gotcha
  de escala do `Dividend_Yield_Mes` (3 convenções) tratado e validado em 2025-05..2026-05.
- **FII estilo-ações rodado**: short-list KNCR/VISC/BTLG no topo; XPML11 expõe o outlier
  conhecido (2,6% TTM vs 8,9% mediana). Front buildado (static export) com as 3 short-lists.

## Validado contra dados reais (2026-06-26)
- **Pipeline real rodado localmente** (rede aberta): `ingest_fii --download` →
  `data/fii_vp.json` com 1314 fundos; `fetch_prices` → `data/prices.json` com os 16
  tickers da watchlist. Primeiros artefatos reais commitados.
- **columns.yml validado**: os candidatos resolvem contra o arquivo real. Correções:
  (a) INF_MENSAL de FII é **ponto-decimal** (não vírgula) — `decimal: "."`; (b) VP/PL/cotas
  vivem no membro `complemento` (o ingest agora escolhe o membro pela resolução de colunas,
  não pelo 1º CSV); (c) `fii.py` threada `spec.decimal` (antes ignorava). Ver `CLAUDE.md`.
- **URLs da CVM validadas** contra o índice vivo (FII INF_MENSAL + DFP/ITR, 200 OK).
- **P/VP dos FIIs preenchido**: `cnpj` resolvido por ticker→ISIN→CNPJ (membro `geral`),
  cruzado com o cadastro de VP. P/VP dos 8 FIIs em 0,90–1,05.
- **Fase 2 (fundamentos de ações) rodada de verdade**: `ingest_fundamentos.py` sobre DFP
  2015–2025 → `data/fundamentos.json` com proventos pagos, lucro (controladora), DY
  histórico/corrente, payout, recorrência, CAGR e flag yield trap das 8 ações. Proventos
  por **competência CVM** (DFC); validado: Petrobras 45,2bi, Itaú 48,3bi, BB 13,7bi (lucro).

## Pendências conhecidas / a validar
- **Escala de ações da CVM** (`composicao_capital`) mistura unidades×milhares, às vezes
  trocando no meio do histórico (Bradesco). Resolvida por ano via âncora yfinance
  `sharesOutstanding`. Sem âncora → assume ×1 e sinaliza baixa confiança (não inventa).
- **DY histórico limitado a ~5 anos**: a série de preços (yfinance, `period=5y`) cobre
  2021+, então o DY/ano só existe nesse intervalo; proventos/payout/recorrência vão a 2015.
  Para DY mais fundo, estender o período de preços.
- **DY corrente usa o último ano fiscal** (DFP), não TTM de ITR (DFC trimestral é
  acumulado no exercício — exige tratamento). Refinamento previsto.
- **Série histórica de preços** vem do yfinance (`Close` auto_adjust=False = split-adj,
  div-unadj). brapi é o primário do PREÇO SPOT. Sinalizado ao Felipe.

## Próximo (roadmap)
Fases 0–5 feitas + refinamentos (P/VP, TTM, dívida/EBITDA, **DY de FII**). Pendente:
**deploy no Netlify** (ação do Felipe), **DMPL** (proventos declarados), **FI-Agro**
(dataset próprio FIAGRO), Fase 6 (alertas + carteira CSV), Fase 7 (IPE/RAD, sem infra
nova). Detalhe e specs de retomada em `docs/HANDOFF.md`; decisões em `CLAUDE.md`.
