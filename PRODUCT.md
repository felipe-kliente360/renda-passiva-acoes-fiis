# divbr — produto

**Inteligência de renda passiva na B3** (ações, FIIs e FIAgros). Encontrar e monitorar
papéis sólidos, com histórico saudável e pagamentos recorrentes e relevantes de
dividendos/JCP/rendimentos.

> Pergunta-guia de todo cálculo: **isto paga, e vai continuar pagando?**
> Não é caçar o maior yield do trimestre — é o fluxo que se sustenta.

## Como o produto pensa

### Dividend Yield (metodologia)
- Proventos atribuídos pela **data-com**.
- Denominador = preço negociado **ajustado só por split, nunca por dividendo**.
- **DY corrente** = proventos 12m ÷ preço atual.
- **DY histórico** = soma anual ÷ preço médio do ano; reporta média **e** mediana.
- **Yield trap**: DY corrente > 1,5× a mediana histórica → sinal de alerta. Toda
  "oportunidade" é cruzada com esse flag.

### Score composto (short-list)
- Recorrência/segurança do pagamento — 40%
- Yield atual vs. baseline histórico — 30%
- Crescimento do dividendo — 30%
- Sustentabilidade: payout 30–80%; pagou em ≥8 dos últimos 10 anos; dívida
  líquida/EBITDA e ROE.

## Como funciona (sem infra paga)
GitHub Actions (cron) roda o pipeline Python → artefatos estáticos JSON/Parquet
versionados no repo → front Next.js (deploy Netlify) lê com ISR. Sem banco.

Fontes: **CVM** (fundamentos, autoritativa), **B3** (proventos/data-com), **brapi/yfinance**
(preço de mercado). Detalhes vivos em `docs/STATUS.md` e metodologia de preços em
`docs/prices-methodology.md`.

## Roadmap
Fundação ✅ → Preços (Fase 1) ✅ → Proventos B3 → Fundamentos ITR/DFP → Score →
Dashboard → Alertas + import de carteira (CSV) → Fatos relevantes (IPE/RAD).
