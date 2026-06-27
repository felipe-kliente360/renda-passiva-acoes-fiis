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

# DY de FII (rendimentos) via DY mensal oficial do INF_MENSAL
python scripts/ingest_fii_dy.py --start 2020 --end 2026 --out data/fii_dy

# Preços diários da watchlist (Fase 1) — brapi (spot) + yfinance (série)
python scripts/fetch_prices.py --fii-vp data/fii_vp.json --out data/prices

# Fundamentos de ações via CVM ITR/DFP — proventos, lucro, P/VP, DY, payout (Fase 2)
python scripts/ingest_fundamentos.py --start 2015 --end 2026 --out data/fundamentos

# Score composto → short-list ranqueada (Fase 4)
python scripts/build_score.py --out data/score
```

Sem rede, `fetch_prices` lista os tickers indisponíveis em vez de inventar cotação.

## Front (Fase 5)

```bash
cd web && npm install && npm run build   # static export -> web/out
```

Next.js com `output: export`: lê os JSON de `data/` no build e gera HTML estático. Deploy
no Netlify free tier via `netlify.toml` (base `web`, publish `web/out`).

## Estrutura
- `pipeline/` — lógica pura e testável (rede isolada em `cvm.py`/`prices.py`)
- `scripts/` — entry points
- `config/` — YAML (colunas CVM, contas ITR/DFP, watchlist)
- `tests/` — suíte offline com amostras sintéticas
- `data/` — artefatos gerados (commitados pelas Actions)
- `web/` — portal Next.js (static export)
- `.github/workflows/` — `ingest.yml` (FII mensal), `prices.yml` (diário), `fundamentos.yml` (trimestral)

## Metodologia
Proventos pela **competência da CVM** (ITR/DFP), preço ajustado **só por split** (nunca por
dividendo), DY histórico com média e mediana, flag de yield trap, score composto. Detalhes
em [`docs/prices-methodology.md`](docs/prices-methodology.md) e decisões travadas em `CLAUDE.md`.
