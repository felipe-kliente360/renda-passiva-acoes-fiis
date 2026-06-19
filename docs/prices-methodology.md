# Metodologia da série de preços (Fase 1)

> Decisão TRAVADA: o denominador do Dividend Yield é o **preço negociado, ajustado
> apenas por split/grupamento, NUNCA por dividendo**. Preço ajustado-por-provento
> infla o DY histórico (o denominador passado fica artificialmente menor), então é
> proibido como base de cálculo.

## O problema das fontes
A maioria das fontes de mercado entrega o *adjusted close* já corrigido por **split
E dividendo** (estilo Yahoo Finance "Adj Close"). Precisamos da série corrigida
**só por split**. Há dois caminhos, conforme o que a fonte entrega:

### Caminho A — a fonte dá o close não-ajustado-por-dividendo (preferido)
- **yfinance** com `auto_adjust=False`: a coluna `Close` já vem ajustada por split e
  **não** por dividendo. Usar diretamente como série negociada. (A coluna `Adj Close`
  é a ajustada por ambos — não usar para DY.)
- **brapi**: o campo `close` é o preço cru como negociado (não ajustado nem por split).
  Aplicar só o ajuste de split a partir dos eventos de desdobramento/grupamento.

`split_adjust` resolve o caminho A: dado o close cru e os eventos de split, devolve a
série contínua ajustada só por split.

```
split_adj[t] = raw_close[t] / Π_{s : data_s > t} R_s
```
onde `R_s` é a razão do evento (desdobramento 1→R tem R>1; grupamento tem R<1). Só
eventos **posteriores** à data t afetam o preço daquela data (back-adjust).

### Caminho B — a fonte só dá o adjusted close (split+dividendo): reconstruir
Quando só houver a série ajustada por ambos, **desfazemos o ajuste de dividendo** para
recuperar a série negociada (ajustada só por split). Usamos a definição padrão do fator
de dividendo (Yahoo/CRSP):

```
f_e = 1 - D_e / C_{e-1}
```
`D_e` = provento na data-com `e`; `C_{e-1}` = close (ajustado-só-por-split) do pregão
anterior à data-com. O *adjusted close* multiplica todos os preços até `e-1` pelo
produto cumulativo desses fatores:

```
CF[t] = Π_{e : data_e > t} f_e
adj_close[t] = split_adj[t] · CF[t]   ⇒   split_adj[t] = adj_close[t] / CF[t]
```

`f_e` depende de `C_{e-1}`, que é justamente o que queremos. Resolvendo a recursão (ver
dedução abaixo) e processando as data-com da **mais recente para a mais antiga**:

```
f_e = 1 / (1 + D_e · CF[e] / adj_close[e-1])
```
com `CF[e] = Π_{data-com posteriores a e} f_l` (conhecido ao varrer de trás pra frente)
e `adj_close[e-1]` vindo direto da fonte. Daí `split_adj[t] = adj_close[t] / CF[t]`.

`reconstruct_traded_from_adjusted` implementa o caminho B.

#### Dedução de `f_e`
Para `t = e-1`: `CF[e-1] = f_e · CF[e]`. Como `adj[e-1] = C_{e-1}·CF[e-1]`:
`f_e = 1 - D_e/C_{e-1} = 1 - D_e·CF[e-1]/adj[e-1] = 1 - D_e·f_e·CF[e]/adj[e-1]`.
Isolando: `f_e (1 + D_e·CF[e]/adj[e-1]) = 1`. ∎

## Verificação
`tests/test_prices.py` cobre, com séries **sintéticas** (nenhum dado real):
- ajuste de split puro (desdobramento e grupamento);
- round-trip do caminho B: gera `adj_close` a partir de uma série negociada conhecida +
  proventos, reconstrói e exige recuperar a série original;
- combinação split + provento na mesma série.

## Derivados
- **P/VP** = preço atual ÷ valor patrimonial da cota (VP vindo do informe CVM já ingerido,
  `pipeline/fii.py`). Não envolve ajuste de série.
- **Preço médio anual** = média dos closes (ajustados só por split) dentro do ano-calendário;
  insumo das funções de DY histórico em `pipeline/metrics.py`.
