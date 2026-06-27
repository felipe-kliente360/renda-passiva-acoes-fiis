# divbr — inteligência de renda passiva na B3

Encontrar e monitorar **ações, FIIs e FIAgros** sólidos, com histórico saudável e
pagamentos recorrentes e relevantes de dividendos/JCP/rendimentos. Pipelines Python rodam
em GitHub Actions, geram artefatos estáticos (JSON/Parquet) versionados no repo, e
alimentam um portal Next.js. **Sem banco, sem infra paga.**

> **Pergunta-guia de todo cálculo: isto paga, e vai continuar pagando?**
> Não é caçar o maior yield do trimestre — é o fluxo que se sustenta.

🌐 No ar: **https://renda-passiva-acoes-fiis.netlify.app/**

Este README é o guia explicativo (conceitos, análises, lógica de decisão). Os demais docs:
- [`CLAUDE.md`](CLAUDE.md) — decisões **travadas** e contexto persistente (a fonte da verdade das escolhas).
- [`docs/STATUS.md`](docs/STATUS.md) — mapa vivo de módulos prontos/pendentes.
- [`docs/HANDOFF.md`](docs/HANDOFF.md) — retomada completa (feito, pendente, gotchas validados).
- [`docs/prices-methodology.md`](docs/prices-methodology.md) — detalhe do ajuste de preço.

---

## 1. O que está coberto

| Universo | Análise | Artefato |
|---|---|---|
| **Ações** (blue chips pagadoras) | DY (competência CVM), payout pago **e** declarado, ROE, dívida líq./EBITDA, P/VP, recorrência, CAGR, yield trap → score | `fundamentos.json`, `score.json` |
| **FIIs** | DY oficial, crescimento, saúde (alavancagem/cota/taxa), **tipo** tijolo/papel/FoF, P/VP, nº cotistas → score | `fii_fundos.json`, `fii_score.json`, `fii_dy.json`, `fii_vp.json` |
| **FIAgros** | DY oficial, **camada de crédito** (inadimplência, diversificação, liquidez), **tipo** crédito/terras, confiança → score | `fiagro.json`, `fiagro_score.json` |
| **Preços** | spot (brapi) + série split-adj (yfinance), P/VP, preço médio anual | `prices.json` |
| **Macro** | CDI 12m, Selic, IPCA (BCB) — base do *spread sobre CDI* | `macro.json` |
| **Fatos relevantes** | feed IPE-RAD da watchlist + flag de mudança de política de proventos | `fatos_relevantes.json` |

As três short-lists (ações, FIIs, FIAgros) são **separadas e não comparáveis entre si** —
ver [§5](#5-como-ler-as-short-lists-lógica-de-decisão).

---

## 2. Arquitetura

```
GitHub Actions (cron) → Python (pandas) ingestão + normalização + métricas puras
   → artefatos estáticos JSON/Parquet commitados no repo
   → Front Next.js (static export) lê os JSON no build → Netlify (free tier)
```

- **Lógica de cálculo é pura e testável offline**; o acesso a rede fica isolado nos módulos
  de download (`pipeline/cvm.py`, `pipeline/prices.py`, `pipeline/macro.py`).
- **Sem banco**: JSON/Parquet versionados são suficientes, auditáveis e grátis.
- **Config-driven**: nomes de coluna da CVM não ficam fixos no código — vivem em
  `config/columns.yml` (informes) e `config/contas.yml` (ITR/DFP), resolvidos contra o
  arquivo real (a CVM muda nomes, ex.: pós-Resolução 175).

---

## 3. Conceitos e metodologia

### 3.1 Dividend Yield — a espinha da tese

- **Proventos pela competência da CVM** (não data-com). A tese é de **longo prazo**, e o dado
  oficial (ITR/DFP para ações; INF_MENSAL para fundos) é mais confiável que as fontes de
  mercado, que não cravam o provento original.
- **Denominador = preço negociado, ajustado SÓ por split/grupamento, NUNCA por dividendo.**
  Preço ajustado por provento infla o DY histórico. A série vem do yfinance (`Close`,
  `auto_adjust=False`); o spot, da brapi. Ver [`docs/prices-methodology.md`](docs/prices-methodology.md).
- **DY no nível da empresa** (proventos totais ÷ valor de mercado), não rateado por classe ON/PN.
- **DY corrente** = proventos TTM (12 meses) ÷ valor de mercado atual.
- **DY histórico** = soma anual ÷ preço médio do ano; reporta **média E mediana** (divergência
  grande = provento extraordinário).
- **Flag de yield trap**: DY corrente > **1,5× a mediana histórica** → provável armadilha.
  Toda "oportunidade" é cruzada com esse flag.

### 3.2 Ações (CVM ITR/DFP)

- **Proventos pagos** (numerador do DY) = dividendos + JCP **pagos** no período, da DFC
  (linha de financiamento `6.03.x`, base caixa).
- **Proventos declarados** (numerador do *payout*) = dividendos + JCP **propostos sobre o
  resultado**, da **DMPL** (somando as colunas de lucros/reservas, atribuível à controladora).
  São sabores diferentes de propósito: o DY mede o que pingou no bolso; o payout, o que casa
  com o lucro do exercício.
- **Lucro e PL**: preferir o **atribuível à controladora** (não o consolidado, que inclui
  minoritários). **ROE** = lucro ÷ PL.
- **Dívida líquida/EBITDA** ≤ 3x na sustentabilidade (N/A em banco — não tem dívida/EBIT
  operacional, e o score não penaliza).
- **P/VP de ações** via book value do BPP (controladora).
- **Escala de ações** (`composicao_capital`) é caótica na CVM (mistura unidades × milhares,
  às vezes trocando no meio do histórico) — desambiguada **por ano** via âncora do yfinance
  (`sharesOutstanding`). Sem âncora, sinaliza baixa confiança, não inventa.

### 3.3 Fundos (FII e FIAgro)

Elevados ao mesmo rigor das ações, com **listas separadas**:

- **DY mensal oficial** do INF_MENSAL. FII: TTM = soma dos 12 últimos meses. FIAgro
  (histórico curto, ~1 ano desde 2025-05): TTM **anualizado** pela média quando < 12 meses.
- **Baseline do yield**:
  - **FII** (~5 anos): o **próprio histórico** do fundo (mediana dos anos completos); trap per-fundo.
  - **FIAgro** (~1 ano): **cross-sectional por tipo** (mediana dos pares de crédito × terras) —
    com 1 ano, baseline per-fundo seria circular. É contexto peer-relativo, documentado.
- **Tipo** (classificação data-driven pela composição do ativo):
  - **FII**: *tijolo* (imóveis de renda), *papel* (CRI/recebíveis), *FoF* (cotas de fundos),
    *híbrido*. Risco e benchmark mudam por tipo — por isso classificamos.
  - **FIAgro**: *crédito* (CRA/CRI/CPR — a maioria) × *terras* (imóveis rurais).
- **Saúde financeira no tempo** (substitui payout/ROE/dívida das ações):
  alavancagem = passivo/PL · preservação da cota (VP não derrete) · taxa de administração ·
  recorrência do pagamento.
- **Camada de crédito (FIAgro)** — núcleo fundamentalista dos fundos de recebíveis:
  - **inadimplência** = Vencidos ÷ (A_Vencer + Vencidos);
  - **diversificação** = HHI dos instrumentos (1 = um só papel; →0 diversificado);
  - **liquidez** = Necessidades de Liquidez ÷ PL.
- **Confiança (FIAgro)**: DY positivo perfeitamente constante (cv≈0) cheira a placeholder do
  administrador → rebaixado; também o histórico muito curto. Não inventa, sinaliza.
- **Amortização ≠ rendimento** (FII): `Amortizacao_Cotas_Mes` é devolução de capital, separada
  do DY. **Nº de cotistas** = dispersão/liquidez.

### 3.4 Macro (BCB/SGS) — camada de contexto

CDI 12m (composto), Selic meta e IPCA 12m da API pública do Banco Central. Geram o **spread
sobre CDI** (`DY TTM − CDI 12m`) dos fundos — leitura natural dos fundos de crédito/papel,
que são produtos *CDI+*. **É contexto aditivo: não entra no score nem altera a metodologia
de DY.** (Lembra também que o "crescimento" de DY de FII de papel acompanha o ciclo de juros,
não é crescimento fundamental.)

### 3.5 Fatos relevantes (IPE-RAD) — early warning

Índice dos documentos protocolados na CVM pela watchlist de ações (fato relevante, aviso aos
acionistas, relatório de proventos), com link pro documento original. A flag **⚠ política**
marca, por heurística conservadora sobre o *assunto*, comunicados que mexem na **política de
proventos** (corte/suspensão/revisão) — sinal precoce do "vai continuar pagando?". Não lê o
corpo do PDF; marca o doc para você **abrir**, não afirma o corte.

---

## 4. Score composto

Metodologia **travada** (pesos equilibrados), igual para ações e fundos:

```
score = (0,40·recorrência + 0,30·yield_vs_baseline + 0,30·crescimento) × sustentabilidade
        × (0,70 se yield trap)
```

- **Recorrência** — anos pagando (ações) ou meses pagando ÷ **janela disponível** (fundos:
  um fundo novo que pagou todo mês marca 1,0, sem ser punido por "não ter existido" 12 meses).
- **Yield vs baseline** — premia a faixa saudável (corrente ≈ até 1,5× baseline) e decai na
  zona de trap.
- **Crescimento** — CAGR do dividendo (ações / FII com anos completos) ou tendência de 6m
  (FIAgro de histórico curto); sem base utilizável fica neutro (0,5), não pune.
- **Sustentabilidade** (multiplicador 0,5–1,0):
  - **Ações**: payout 30–80%, ≥8/10 anos pagando, ROE > 0, dívida líq./EBITDA ≤ 3x.
  - **Fundos**: alavancagem baixa, cota preservada, taxa de adm razoável, recorrência.
- **FIAgro** ainda aplica um **amortecedor de confiança** (×0,6) sobre DY-placeholder
  constante — dado suspeito não lidera a short-list.

---

## 5. Como ler as short-lists (lógica de decisão)

1. **As três listas não são comparáveis entre si.** Um FIAgro com score 70 não é "pior" que
   um FII com 90 — eles são medidos sobre dados de profundidades diferentes. Em particular o
   **crescimento** (30%): ações/FIIs têm anos de histórico e pontuam CAGR; o FIAgro (~1 ano)
   fica neutro. Compare **dentro** de cada lista.
2. **Score alto ≠ compra.** É um *ranking de quem paga de forma sustentável*, não recomendação.
3. **Sempre olhe os flags**: `yield trap` (corrente muito acima do histórico), `⚠ política`
   (comunicado mexendo na política de proventos), `confiança baixa` (FIAgro com dado fraco).
4. **Spread sobre CDI**: para fundos de **papel/crédito**, DY ≈ ou acima do CDI é o esperado
   (são CDI+); para **tijolo**, o DY costuma ficar abaixo do CDI (são plays de inflação/renda
   real) — não é defeito.
5. **Inadimplência (FIAgro de crédito)**: o número mais importante depois do DY — yield alto
   com inadimplência subindo é alerta.

---

## 6. Fontes de dados

| Fonte | O que dá | Por quê |
|---|---|---|
| **CVM dados abertos** | Proventos, fundamentos, informes de fundos, fatos relevantes (IPE) | **Autoritativa** — dado oficial por competência |
| **brapi** | Preço spot, **volume** (liquidez), universo negociado (lista fi-agro/fii) | Cotação corrente e liquidez |
| **yfinance** | Série histórica split-adj/div-unadj; âncora de nº de ações | Denominador correto do DY histórico |
| **BCB / SGS** | CDI, Selic, IPCA | Contexto macro / spread sobre CDI; API pública sem auth |

**Evitado de propósito**: scrapers de agregadores (Status Invest, Funds Explorer) — frágeis,
questões de ToS, e contra a decisão "CVM autoritativa". Carteira da B3 e scraping da área do
investidor **não** são automatizados (importar CSV exportado, quando houver — Fase 6, em HOLD).

---

## 7. Gotchas do dado real (não relitigar — detalhe em `CLAUDE.md`)

- **Decimal varia por dataset** da CVM. INF_MENSAL de FII/FIAgro e DFP/ITR usam **ponto**
  (não vírgula). Config-driven por dataset; default vírgula é só fallback.
- **`Dividend_Yield_Mes` do FIAgro ≠ do FII** apesar do nome: convive com 3 escalas no mesmo
  arquivo (percentual ÷100; fração ≤0,05; R$ mal-arquivado → NaN; negativo → NaN). Tratado em
  `pipeline/fiagro.clean_fiagro_dy`.
- **Conta da CVM por SEÇÃO + descrição, não por código** — `CD_CONTA` difere entre o plano
  financeiro (banco) e o não-financeiro.
- **DMPL é long-format por componente do PL** — somar só as colunas de lucros/reservas para
  não duplicar o provento.
- **Controladora ≠ consolidado** no lucro/PL — preferir o atribuível à controladora.
- **DY mensal negativo** (ex.: clawback) é anomalia → descartado, não afunda o TTM.
- **Seleção de membro do ZIP** por resolução de colunas, não pelo 1º CSV (FII tem 3 membros).

---

## 8. Limitações honestas

- **Vacância, contratos e inquilinos de FII de tijolo** — o indicador nº 1 do tijolo **não**
  está na base aberta da CVM (vive nos relatórios gerenciais do FNET). Não coberto.
- **FIAgro tem ~1 ano de histórico** (dataset começa em 2025-05): crescimento e baseline são
  rasos por construção — reportados com honestidade (TTM estimado, baseline por pares, confiança).
- **Bradesco** fica N/A no payout declarado (filou a DMPL fora das colunas de lucros/reservas).
- **Fatos relevantes / flag de política**: só ações (FII/FIAgro publicam no FNET) e só o
  *assunto* (não o corpo do PDF) — a flag aponta para ler, não conclui.
- **yfinance** não roda em alguns ambientes (TLS via proxy); a série de preços se atualiza no
  workflow `prices.yml`, onde funciona.
- **Nada disto é recomendação de investimento.** É informação a partir de dado público.

---

## 9. Como rodar

```bash
pip install -r requirements.txt     # runtime + dev
pytest                              # suíte offline (amostras sintéticas)
ruff check .                        # lint
```

Pipelines (ordem usual; `--no-download` reusa ZIPs em `data/raw/`):

```bash
python scripts/fetch_macro.py                                              # macro (CDI/Selic/IPCA)
python scripts/ingest_fii.py --download --out data/fii_vp                  # VP da cota de FII
python scripts/ingest_fii_dy.py --start 2020 --end 2026 --out data/fii_dy  # DY de FII
python scripts/ingest_fii_fundos.py --start 2020 --end 2026 --out data/fii_fundos  # FII estilo-ações + score
python scripts/ingest_fiagro.py --out data/fiagro                          # FIAgro + shortlist
python scripts/fetch_prices.py --fii-vp data/fii_vp.json --out data/prices # preços + P/VP
python scripts/ingest_fundamentos.py --start 2015 --end 2026 --out data/fundamentos  # ações
python scripts/build_score.py --out data/score                             # short-list de ações
python scripts/ingest_ipe.py --start 2025 --end 2026 --out data/fatos_relevantes  # fatos relevantes
python scripts/inspect_zip.py data/raw/<arquivo>.zip                       # validar colunas reais
```

Front:

```bash
cd web && npm install && npm run build   # static export -> web/out
```

---

## 10. Estrutura do repo

- `pipeline/` — lógica pura e testável. Rede isolada em `cvm.py` / `prices.py` / `macro.py`.
  Domínios: `normalize`, `columns` (resolução config-driven), `fii`, `fiagro` (+ `aggregate_fund`
  genérica e `credit_profile`), `fundamentos`, `metrics`, `score`, `prices`, `ipe`, `macro`, `export`.
- `scripts/` — entry points (um por artefato).
- `config/` — `columns.yml` (informes), `contas.yml` (ITR/DFP), `watchlist.yml`.
- `tests/` — suíte offline com amostras sintéticas.
- `data/` — artefatos gerados, versionados (commitados pelas Actions). `data/raw/` é gitignored.
- `web/` — portal Next.js (static export → Netlify).
- `.github/workflows/` — `ingest.yml` (FII + FIAgro + IPE + macro, mensal), `prices.yml`
  (diário), `fundamentos.yml` (ações, trimestral).

---

*Conteúdo informativo, não é recomendação de investimento.*
