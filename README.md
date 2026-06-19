# divbr

Inteligência de renda passiva na B3 (ações, FIIs e FIAgros). Pipelines Python que rodam
em GitHub Actions, geram artefatos estáticos (JSON/Parquet) versionados, e alimentam um
portal Next.js. Sem banco, sem infra paga.

Visão de produto: [`PRODUCT.md`](PRODUCT.md) · Contexto/decisões: [`CLAUDE.md`](CLAUDE.md)
· Estado do código: [`docs/STATUS.md`](docs/STATUS.md)

## Setup

```bash
pip install -r requirements.txt   # runtime + dev
pytest                            # suíte offline
ruff check .                      # lint
```

## Pipelines

```bash
# Fundamentos de FII (VP da cota) — baixa o pacote da CVM e ingere
python scripts/ingest_fii.py --download --out data/fii_vp

# Validar colunas reais da CVM contra config/columns.yml antes de confiar
python scripts/inspect_zip.py data/raw/inf_mensal_fii_2026.zip

# Preços diários da watchlist (Fase 1) — brapi (spot) + yfinance (série)
python scripts/fetch_prices.py --fii-vp data/fii_vp.json --out data/prices
```

Sem rede, `fetch_prices` lista os tickers indisponíveis em vez de inventar cotação.

## Estrutura
- `pipeline/` — lógica pura e testável (rede isolada em `cvm.py`/`prices.py`)
- `scripts/` — entry points
- `config/` — YAML (colunas CVM, watchlist)
- `tests/` — suíte offline com amostras sintéticas
- `data/` — artefatos gerados (commitados pelas Actions)
- `.github/workflows/` — `ingest.yml` (mensal), `prices.yml` (diário)

## Metodologia
DY pela data-com, preço ajustado **só por split** (nunca por dividendo), DY histórico
com média e mediana, flag de yield trap. Detalhes em
[`docs/prices-methodology.md`](docs/prices-methodology.md). Decisões travadas em `CLAUDE.md`.
