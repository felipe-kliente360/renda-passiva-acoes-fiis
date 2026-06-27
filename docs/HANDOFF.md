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
.venv/bin/python scripts/fetch_prices.py --fii-vp data/fii_vp.json --out data/prices # preços + P/VP FII
.venv/bin/python scripts/ingest_fundamentos.py --start 2015 --end 2026 --out data/fundamentos  # ações
.venv/bin/python scripts/build_score.py --out data/score                       # short-list
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

## 5. Pendente (com a especificação para retomar)
1. **Deploy Netlify** (ação do Felipe): conectar o repo; `netlify.toml` já configurado
   (base `web`, publish `out` — relativo ao base!, Node 20).
2. **FI-Agro** — dataset PRÓPRIO da CVM em `https://dados.cvm.gov.br/dados/FIAGRO/DOC/`
   (os "agro" no INF_MENSAL de FII são FIIs do setor, não FIAgros). Precisa de uma passada
   de inspeção própria (cobertura menos consolidada — validar campos, não assumir paridade
   com FII). Provável reuso do parser FII se o layout casar.
3. **DMPL — proventos declarados/propostos** (payout que casa com o lucro do exercício).
   A DMPL é matriz (linhas=movimentos, colunas=componentes do PL); o "Dividendos/JCP"
   aparece como movimento na coluna de Lucros Acumulados. Não iniciado. Sabor diferente do
   payout atual (que usa proventos PAGOS via DFC).
4. **DY histórico de ações** cobre só ~5 anos (série de preços yfinance `period=5y`);
   proventos/payout vão a 2015. Para aprofundar o DY, estender o período de preços.
5. **XPML11 DY de FII = 2,6% TTM** vs mediana 8,9% — outlier a investigar (provável mês
   faltante no INF_MENSAL 2026 daquele fundo).
6. **Fase 6** — alertas (e-mail/Telegram pela Action) + import de carteira via CSV da B3
   (sem scraping de login). **Fase 7** — feed de fatos relevantes IPE/RAD: dataset aberto
   `ipe_cia_aberta_AAAA.zip` (índice estruturado com data/empresa/categoria/link). **Sem
   infra nova** — só ingestão + JSON + front. Ler o corpo dos PDFs seria opcional/depois.

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
`prices.json` (16 tickers, P/VP dos FIIs) · `fundamentos.json` (8 ações) ·
`score.json` (short-list ranqueada). Gerados pelas Actions: `ingest.yml` (FII, mensal),
`prices.yml` (diário), `fundamentos.yml` (trimestral, fundamentos+score).
