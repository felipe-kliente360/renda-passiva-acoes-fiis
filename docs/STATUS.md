# Estado do código (mapa vivo)

Atualizado em: 2026-06-19

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

`pytest`: 36 testes passando offline.

## Pendências conhecidas / a validar
- **columns.yml** lista CANDIDATOS de nome de coluna por suposição. Validar contra o ZIP
  REAL da CVM com `scripts/inspect_zip.py` e ajustar (nomes pós-Resolução 175).
- **URLs da CVM** em `cvm.py` precisam de validação contra o índice vivo.
- **watchlist.yml**: tickers conferidos; `cnpj` dos FIIs está `null` (necessário para o
  JOIN do P/VP — preencher do cadastro CVM, não inventar).
- **Série histórica de preços** vem do yfinance (`Close` auto_adjust=False = split-adj,
  div-unadj). brapi é o primário do PREÇO SPOT. Refinamento sobre o briefing (brapi
  primário p/ série) — feito por correção metodológica; sinalizado ao Felipe.
- Rede indisponível neste ambiente: `fetch_prices` degrada (lista indisponíveis, não
  inventa). Rodar localmente: `pip install -r requirements.txt && python scripts/fetch_prices.py`.

## Próximo (roadmap)
Fase 2: proventos com data-com (B3). Ver CLAUDE.md.
