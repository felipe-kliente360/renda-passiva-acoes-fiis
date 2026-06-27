# divbr — produto

**Inteligência de renda passiva na B3** (ações, FIIs e FIAgros). Encontrar e monitorar
papéis sólidos, com histórico saudável e pagamentos recorrentes e relevantes de
dividendos/JCP/rendimentos.

> Pergunta-guia de todo cálculo: **isto paga, e vai continuar pagando?**
> Não é caçar o maior yield do trimestre — é o fluxo que se sustenta.

## Como o produto pensa

### Dividend Yield (metodologia)
- Proventos pela **competência da CVM** (ITR/DFP; revisado — antes era data-com).
- Denominador = preço negociado **ajustado só por split, nunca por dividendo**.
- **DY corrente** = proventos 12m (TTM) ÷ valor de mercado atual; **DY no nível da empresa**.
- **DY histórico** = soma anual ÷ preço médio do ano; reporta média **e** mediana.
- **Yield trap**: DY corrente > 1,5× a mediana histórica → sinal de alerta. Toda
  "oportunidade" é cruzada com esse flag.

> Explicação completa (conceitos, análises, lógica de decisão) no [`README.md`](README.md).

### Score composto (short-list)
- Recorrência/segurança do pagamento — 40%
- Yield atual vs. baseline histórico — 30%
- Crescimento do dividendo — 30%
- Sustentabilidade: payout 30–80%; pagou em ≥8 dos últimos 10 anos; dívida
  líquida/EBITDA e ROE.

## Como funciona (sem infra paga)
GitHub Actions (cron) roda o pipeline Python → artefatos estáticos JSON/Parquet
versionados no repo → front Next.js (deploy Netlify) lê com ISR. Sem banco.

Fontes: **CVM** (proventos + fundamentos, autoritativa), **brapi/yfinance** (preço/volume de
mercado), **BCB/SGS** (macro: CDI/Selic/IPCA). Detalhes vivos em `docs/STATUS.md`, metodologia
de preços em `docs/prices-methodology.md`, e o guia completo no [`README.md`](README.md).

## Roadmap
Fundação → Preços → Fundamentos ITR/DFP (+DMPL) → Score → Dashboard (no ar) → Fundos
estilo-ações (FII + FIAgro, por tipo + crédito) → Macro/spread + liquidez → Fatos relevantes
(IPE/RAD) **✅ tudo feito**. Pendente: alertas + import de carteira CSV (**HOLD**); vacância
de FII via FNET (futuro).
