# Estado do código (mapa vivo)

Atualizado em: 2026-06-26

## Pronto e testado (offline)
| Módulo | Função | Testes |
|---|---|---|
| `pipeline/normalize.py` | Leitura CVM (ISO-8859-1, `;`, vírgula decimal), ZIP/CSV, `to_numeric_ptbr` | `test_normalize.py` |
| `pipeline/columns.py` | Resolução config-driven de colunas (candidatos → coluna real) | `test_columns.py` |
| `pipeline/fii.py` | Parser INF_MENSAL → VP da cota (direto ou derivado PL/cotas) | `test_fii.py` |
| `pipeline/metrics.py` | DY TTM, DY histórico (média/mediana), payout, recorrência, growth, flag yield trap | `test_metrics.py` |
| `pipeline/prices.py` | `split_adjust`, `reconstruct_traded_from_adjusted`, preço médio anual, P/VP, `build_price_record` | `test_prices.py` |
| `pipeline/export.py` | Export JSON + Parquet com metadados/proveniência | `test_export.py` |
| `pipeline/cvm.py` | Downloader dos pacotes da CVM (rede isolada) | — (I/O de rede) |

Scripts: `scripts/inspect_zip.py` (valida colunas reais), `scripts/ingest_fii.py`
(ingestão FII), `scripts/fetch_prices.py` (Fase 1).
Workflows: `.github/workflows/ingest.yml` (mensal), `prices.yml` (diário).

`pytest`: 39 testes passando offline.

## Validado contra dados reais (2026-06-26)
- **Pipeline real rodado localmente** (rede aberta): `ingest_fii --download` →
  `data/fii_vp.json` com 1314 fundos; `fetch_prices` → `data/prices.json` com os 16
  tickers da watchlist. Primeiros artefatos reais commitados.
- **columns.yml validado**: os candidatos resolvem contra o arquivo real. Correções:
  (a) INF_MENSAL de FII é **ponto-decimal** (não vírgula) — `decimal: "."`; (b) VP/PL/cotas
  vivem no membro `complemento` (o ingest agora escolhe o membro pela resolução de colunas,
  não pelo 1º CSV); (c) `fii.py` threada `spec.decimal` (antes ignorava). Ver `CLAUDE.md`.
- **URLs da CVM validadas** contra o índice vivo (`inf_mensal_fii_2026.zip` presente, 200 OK).

## Pendências conhecidas / a validar
- **watchlist.yml**: tickers conferidos; `cnpj` dos FIIs está `null` → P/VP dos 8 FIIs sai
  `null`. Falta uma fonte autoritativa ticker→CNPJ (não está no INF_MENSAL, que só tem
  nome/ISIN). Preencher do cadastro CVM/B3, não inventar.
- **Série histórica de preços** vem do yfinance (`Close` auto_adjust=False = split-adj,
  div-unadj). brapi é o primário do PREÇO SPOT. Refinamento sobre o briefing (brapi
  primário p/ série) — feito por correção metodológica; sinalizado ao Felipe.
- Rede indisponível neste ambiente: `fetch_prices` degrada (lista indisponíveis, não
  inventa). Rodar localmente: `pip install -r requirements.txt && python scripts/fetch_prices.py`.

## Próximo (roadmap)
Fase 2: proventos com data-com (B3). Ver CLAUDE.md.
