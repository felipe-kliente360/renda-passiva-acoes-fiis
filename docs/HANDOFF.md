# divbr — handoff para continuar em nova sessão

> Documento vivo de retomada. Resume **o que foi feito, o que está pendente, as ideias,
> as memórias de cálculo (gotchas validados no dado real) e as decisões**. Para o contexto
> permanente e as decisões TRAVADAS, ver `CLAUDE.md`; para o mapa de módulos, `docs/STATUS.md`.
> Última atualização: 2026-06-26.

## 1. Estado em uma frase
Pipelines Python (CVM oficial) geram artefatos JSON/Parquet em `data/`; um front Next.js
(static export) os mostra. **Fases 0–5 feitas + refinamentos (P/VP, TTM, dívida/EBITDA, DY
de FII).** Falta: deploy efetivo no Netlify (ação do Felipe), DMPL, FI-Agro, Fases 6–7.

## 2. Ambiente (importante para rodar)
- **Python 3.12** em `.venv/` (o sistema tinha só 3.9; o projeto exige 3.11+). Criar com
  `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- **Node 25 / npm 11** para o front (`web/`). `pandas 3.0`, `pyarrow 24`, `yfinance 1.4`.
- **60 testes** offline (`/.venv/bin/python -m pytest -q`), `ruff check .` limpo.
- A rede é aberta localmente (a sessão remota bloqueava `dados.cvm.gov.br`/`brapi`/`yahoo`).

## 3. Como rodar tudo (ordem)
```bash
.venv/bin/python scripts/ingest_fii.py --download --out data/fii_vp           # VP de FII
.venv/bin/python scripts/ingest_fii_dy.py --start 2020 --end 2026 --out data/fii_dy  # DY de FII
.venv/bin/python scripts/ingest_fii_fundos.py --start 2020 --end 2026 --out data/fii_fundos  # FII estilo-ações + score
.venv/bin/python scripts/ingest_fiagro.py --out data/fiagro                    # FIAgro auto-detectado + shortlist
.venv/bin/python scripts/fetch_prices.py --fii-vp data/fii_vp.json --out data/prices # preços + P/VP FII
.venv/bin/python scripts/ingest_fundamentos.py --start 2015 --end 2026 --out data/fundamentos  # ações
.venv/bin/python scripts/build_score.py --out data/score                       # short-list ações
cd web && npm install && npm run build                                         # front -> web/out
```
`--no-download` reusa os ZIPs em `data/raw/` (gitignored). `inspect_zip.py` valida colunas reais.

## 4. Feito (fases e refinamentos)
- **0 Fundação / 1 Preços** — normalize CVM, parser FII (VP), métricas puras, preços
  split-adj (yfinance série + brapi spot), P/VP de FII.
- **2 Fundamentos+proventos de ações (CVM ITR/DFP)** — espinha. `data/fundamentos.json`:
  proventos pagos, lucro (controladora), DY hist/corrente, payout, recorrência, CAGR,
  yield-trap, **P/VP** (book value do BPP), **DY corrente por TTM** (ITR), **dívida
  líquida/EBITDA**. Config `config/contas.yml`.
- **4 Score** — `pipeline/score.py` + `data/score.json` ranqueado.
- **5 Dashboard** — `web/` (Next.js static export), `netlify.toml`.
- **DY de FII** — `data/fii_dy.json` (TTM, histórico, mediana, trap) via DY mensal oficial.
- **Fundos estilo-ações (FII + FIAgro)** — `pipeline/fiagro.py` (`aggregate_fund` genérica),
  `pipeline/score.py` (`fund_composite_score`). FIAgro auto-detectado (brapi ∩ ISIN da CVM),
  histórico curto tratado com honestidade (DY anualizado, baseline cross-sectional,
  confiança). FII reusa `aggregate_fund` com baseline histórico próprio (~5 anos) + P/VP.
  Artefatos: `data/fiagro.json`/`fiagro_score.json`, `data/fii_fundos.json`/`fii_score.json`.
  Front com short-lists separadas. Roda no `ingest.yml` mensal.

## 5. Pendente (com a especificação para retomar)
Tudo da última leva FEITO — restam só HOLD e gaps de dado conhecidos:
- ✅ **Deploy Netlify**, **FI-Agro** (§4), **FII estilo-ações** (§4).
- ✅ **DMPL — payout declarado**: `proventos_declarados` (DMPL, colunas de lucros/reservas,
  config-driven) → `payout_declarado_por_ano`. Validado (PETR 2024 ≈ 100,6bi; 7/8 papéis).
- ✅ **DY histórico de ações**: yfinance estendido p/ `10y` (ativa no próximo `prices.yml`;
  yfinance não roda neste ambiente — curl_cffi × proxy TLS).
- ✅ **XPML11**: DY mensal negativo de 2026-01 (−5,9%) era anomalia/clawback → `aggregate_fund`
  descarta DY<0. TTM voltou a ~9,4%.
- ✅ **Fase 7 — fatos relevantes (IPE/RAD)**: `pipeline/ipe.py` + `scripts/ingest_ipe.py` →
  `data/fatos_relevantes.json`; front com a seção. Índice-only (sem corpo do PDF).

Gaps conhecidos (dado, não código): **Bradesco** N/A no payout declarado (DMPL filada fora
das colunas de lucros/reservas); **FIAgros de DY ambíguo** (≤0,05 "chapado", ex.: PLCA/LSAG)
marcados confiança baixa — validar fundo a fundo se quiser cravar.

**Fase 6 (HOLD, sinalizado)** — alertas (e-mail/Telegram) + import de carteira CSV da B3.

## 6. Memórias de cálculo (gotchas validados no dado REAL — não relitigar)
- **Decimal varia por dataset.** FII INF_MENSAL e DFP/ITR usam **PONTO** (não vírgula). O
  default vírgula é fallback; `spec.decimal` é threadado nos parsers (era bug latente).
- **DFP/ITR escala `MIL`** → multiplicar VL_CONTA por 1000 (campo ESCALA_MOEDA).
- **Seleção de membro do ZIP** por resolução de colunas, não pelo 1º CSV. FII: VP/PL/cotas/
  DY-mensal vivem no `complemento`. DFP: DFC_MI (proventos/D&A), DRE (lucro/EBIT), BPP
  (PL/dívida), BPA (caixa), composicao_capital (ações).
- **Conta por SEÇÃO+DS, não por código.** `CD_CONTA` difere entre plano financeiro e não-
  financeiro (lucro controladora = 3.11.01 não-fin, 3.09.01 banco). Casar por prefixo de
  seção + palavras na DS_CONTA e somar. `max_dots` limita à linha-mãe (dívida).
- **Controladora ≠ consolidado.** Lucro e PL: preferir "atribuído à controladora" (DS
  "socios da empresa controladora" — cuidado: BB usa "aos sócios"), fallback consolidado.
  Vale: controladora R$ 13,8bi vs consolidado 11,8 (minoritário negativo).
- **Proventos pagos** = DFC `6.03.x`, excluir "recebido" e "não controlador". B3 usa
  "**Pagamento de Proventos**" (não "Dividendos") → incluir "provento" nos candidatos.
- **Escala de ações da CVM é caótica:** mistura unidades×milhares **por empresa E por ano**
  (Bradesco: milhares até 2023, unidades depois), sem coluna que sinalize. Desambiguada
  **por ano** via âncora yfinance `sharesOutstanding` (`resolve_share_scale`: razão 0,2–5
  → ×1; 200–5000 → ×1000). CVM é a contagem; yfinance só decide a unidade.
- **TTM de proventos (ações)** = ano cheio(Y-1, DFP) − YTD(Y-1, ITR PENÚLTIMO) + YTD(Y,
  ITR ÚLTIMO). O DFC do ITR é **acumulado no exercício**; pegar o trimestre de maior dt_fim.
- **Dívida líq/EBITDA** só em **não-financeira**. Banco não tem linha de dívida nem EBIT
  operacional → N/A (e o score não penaliza). EBITDA = EBIT ("antes do resultado financeiro",
  DRE) + D&A (DFC `6.01`, "deprecia"). Validado: PETR4 1,51x, ABEV3 −0,50x (caixa líquido).
- **DY de FII** = `Percentual_Dividend_Yield_Mes` (fração decimal mensal, ex. MXRF 0,0101).
  TTM = soma dos 12 últimos; histórico = soma anual (só anos completos na mediana).
- **DY de FIAgro** = `Dividend_Yield_Mes` (≠ do FII!): 3 escalas no mesmo arquivo —
  percentual (~1,07 → ÷100), fração (≤0,05), R$ mal-arquivado (milhões → NaN), negativo →
  NaN. `clean_fiagro_dy` resolve. Histórico curto (2025-05+): TTM anualiza pela média
  quando <12 meses; baseline cross-sectional (mediana dos pares); DY constante (cv≈0) =
  placeholder → confiança baixa. Ticker reconstruído do ISIN (`[2:6]+11`), validado vs brapi.
- **`aggregate_fund` é genérica** (FII e FIAgro): DY, projeção (CAGR de anos completos OU
  tendência 6m), saúde (alavancagem=passivo/PL, `vp_cota_var`, taxa de adm). FII deriva
  passivo de `Valor_Ativo−PL` (não vem direto no complemento).
- **Preço**: yfinance `Close` (`auto_adjust=False`) = split-adj/div-unadj = denominador
  correto. brapi é spot; degrada sem inventar.

## 7. Decisões (resumo; detalhe e TRAVADAS em CLAUDE.md)
- **Proventos por COMPETÊNCIA da CVM** (não data-com) — revisão sinalizada pelo Felipe
  (tese de longo prazo, dado oficial > fontes de mercado que "não cravam").
- **DY no nível da empresa** (proventos ÷ valor de mercado), não por classe ON/PN.
- **CVM autoritativa** para proventos/fundamentos; yfinance/brapi só para preço e âncora
  de ações. B3/IPE ficam para a fase de fatos relevantes.
- **Tudo em `main`**, commits pequenos, testes antes do commit, lógica pura testável offline.
- **Front: Netlify free tier**, static export (sem runtime).
- **Score 40/30/30** (recorrência/yield-vs-baseline/crescimento) × sustentabilidade
  (payout 30–80%, ≥8/10 anos, ROE>0, dívida/EBITDA≤3x) × corte de yield-trap (×0,7).

## 8. Artefatos em `data/`
`fii_vp.json` (VP de 1314 FIIs) · `fii_dy.json` (DY dos FIIs da watchlist) ·
`fii_fundos.json` + `fii_score.json` (FII estilo-ações + short-list) ·
`fiagro.json` + `fiagro_score.json` (FIAgro auto-detectado + short-list) ·
`prices.json` (16 tickers, P/VP dos FIIs) · `fundamentos.json` (8 ações) ·
`score.json` (short-list de ações). Gerados pelas Actions: `ingest.yml` (FII + FIAgro,
mensal), `prices.yml` (diário), `fundamentos.yml` (trimestral, fundamentos+score de ações).

## 9. Split de rede dos runners (CVM × Yahoo) — validado 2026-06-27
**Descoberta**: o runner do GitHub **não alcança `dados.cvm.gov.br`** (`Errno 101 Network
is unreachable` — egress de nuvem bloqueado). O Yahoo (yfinance) é o inverso: só funciona
no GH, não neste ambiente. Um run de `fundamentos.yml` no GH gravou 20 ações vazias e
sobrescreveu `main` (restaurado em `26cbe53`).

**Tratamento (commits c789700, 4b1f5b1, 655b1fb)**:
- `scripts/fetch_anchors.py` + `.github/workflows/anchors.yml`: coletam `sharesOutstanding`
  da watchlist no GH (yfinance OK) e commitam `config/shares_anchor.yml` por MERGE.
- `ingest_fundamentos.py --no-yfinance`: gera aqui (CVM OK) lendo só o cache de âncora.
  Aplicado no `fundamentos.yml`. 18/20 ações com DY; CPLE6 (Yahoo sem sharesOutstanding da
  PNB) e SAPR11 (escala unit/ação) ficam N/A honesto.
- **Trava anti-clobber** em `ingest_fundamentos`, `ingest_fii`, `ingest_fii_dy`,
  `ingest_fii_fundos`, `ingest_fiagro`, `ingest_ipe`: se nenhum período da CVM baixa,
  abortam (exit 1) sem escrever → `bash -e` derruba o passo antes do commit.

**Onde rodar o quê**: GH = `prices.yml` + `anchors.yml` (yfinance, com cron). CVM
(fundamentos + ingest FII/FIAgro/IPE) = **gerar neste ambiente** (alcança a CVM) e commitar.
**TRAVADO 2026-06-27 (opção A do Felipe)**: `fundamentos.yml` e `ingest.yml` ficaram **só
com `workflow_dispatch`, sem cron** — não geram mais run vermelho à toa no GH.
