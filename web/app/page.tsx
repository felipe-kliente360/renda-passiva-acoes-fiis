import {
  getScore,
  getFundamentos,
  getFiiScore,
  getFiagroScore,
  getFatosRelevantes,
  getMacro,
  type Fundamento,
  type FundScoreRow,
} from "@/lib/data";

const pct = (v?: number | null, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v?: number | null, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d);
const pctSigned = (v?: number | null, d = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)}%`;
const fmtVol = (v?: number | null) => {
  if (v === null || v === undefined || Number.isNaN(v) || v <= 0) return "—";
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
  return `${v}`;
};

function scoreClass(s: number) {
  return s >= 75 ? "s-hi" : s >= 55 ? "s-mid" : "s-lo";
}

// Valor do ano mais recente de um dicionário {ano: valor} (ex.: payout declarado).
function latestYearValue(d?: Record<string, number | null>): number | null {
  if (!d) return null;
  const years = Object.keys(d).filter((y) => d[y] !== null);
  if (!years.length) return null;
  const y = years.sort((a, b) => Number(b) - Number(a))[0];
  return d[y];
}

function Sparkline({ series }: { series: Record<string, number> }) {
  const entries = Object.entries(series).sort((a, b) => Number(a[0]) - Number(b[0]));
  const vals = entries.map(([, v]) => v);
  if (!vals.length) return <span className="muted">—</span>;
  const max = Math.max(...vals, 1e-9);
  return (
    <div className="spark" title={entries.map(([y, v]) => `${y}: ${(v / 1e9).toFixed(1)}bi`).join("  ")}>
      {vals.map((v, i) => (
        <i key={i} style={{ height: `${Math.max(2, (v / max) * 28)}px` }} />
      ))}
    </div>
  );
}

function FundShortlist({
  rows,
  baselineKey,
  baselineLabel,
  showConfianca = false,
  showCredito = false,
}: {
  rows: FundScoreRow[];
  baselineKey: "dy_mediana" | "dy_baseline_pares";
  baselineLabel: string;
  showConfianca?: boolean;
  showCredito?: boolean;
}) {
  return (
    <div className="tablecard">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Ativo</th>
            <th>Tipo</th>
            <th>Score</th>
            <th>DY 12m</th>
            <th>{baselineLabel}</th>
            <th>P/VP</th>
            <th title="DY 12m − CDI 12m (contexto, não score)">Spread CDI</th>
            <th>Cresc.</th>
            <th>Alav.</th>
            {showCredito && <th>Inadimpl.</th>}
            <th title="Volume diário negociado (brapi)">Liq.</th>
            {showConfianca && <th>Confiança</th>}
            <th>Flags</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker}>
              <td className="muted">{r.rank}</td>
              <td>
                <span className="tk">{r.ticker}</span>
                <div className="name">{r.nome}</div>
              </td>
              <td>{r.tipo ? <span className="chip">{r.tipo}</span> : "—"}</td>
              <td>
                <span className={`score-pill ${scoreClass(r.score)}`}>{r.score}</span>
              </td>
              <td>
                {pct(r.dy_ttm)}
                {r.dy_ttm_estimado ? <span className="muted"> est.</span> : ""}
              </td>
              <td className="muted">{pct(r[baselineKey])}</td>
              <td>{num(r.pvp)}</td>
              <td className="muted">{pctSigned(r.spread_cdi)}</td>
              <td>{r.crescimento === null || r.crescimento === undefined ? "—" : pctSigned(r.crescimento)}</td>
              <td className="muted">{r.alavancagem === null || r.alavancagem === undefined ? "—" : `${(r.alavancagem * 100).toFixed(0)}%`}</td>
              {showCredito && (
                <td className="muted">
                  {r.inadimplencia === null || r.inadimplencia === undefined
                    ? "—"
                    : pct(r.inadimplencia)}
                </td>
              )}
              <td className="muted">{fmtVol(r.volume_brapi)}</td>
              {showConfianca && (
                <td>
                  <span className={`chip ${r.confianca === "baixa" ? "trap" : "ok"}`}>
                    {r.confianca ?? "—"}
                  </span>
                </td>
              )}
              <td>
                {r.yield_trap ? (
                  <span className="chip trap">yield trap</span>
                ) : (
                  <span className="chip ok">recorrente</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Home() {
  const score = getScore();
  const fundamentos = getFundamentos();
  const fiiScore = getFiiScore();
  const fiagroScore = getFiagroScore();
  const fatos = getFatosRelevantes();
  const macro = getMacro();
  const fByTk = new Map<string, Fundamento>(fundamentos.data.map((f) => [f.ticker, f]));
  const generated =
    (score.meta?.generated_at as string) || (fundamentos.meta?.generated_at as string) || "";

  return (
    <main className="wrap">
      <header className="hero">
        <h1>
          div<span className="dot">br</span>
        </h1>
        <p>Renda passiva na B3 a partir de dados oficiais da CVM (ITR/DFP).</p>
      </header>

      <div className="guide">
        <strong>Isto paga, e vai continuar pagando?</strong> O score não premia o maior yield do
        trimestre — premia o fluxo que se sustenta: <strong>recorrência (40%)</strong>, yield vs.
        baseline histórico <strong>(30%)</strong> e crescimento do dividendo <strong>(30%)</strong>,
        ajustado por sustentabilidade (payout, ROE) e com corte de <em>yield trap</em>.
      </div>

      {(macro.cdi_12m ?? macro.selic_meta ?? macro.ipca_12m) != null && (
        <div className="macro">
          <span>Contexto (BCB):</span>
          <strong>CDI 12m {pct(macro.cdi_12m)}</strong>
          <strong>Selic {pct(macro.selic_meta)}</strong>
          <strong>IPCA 12m {pct(macro.ipca_12m)}</strong>
          <span className="muted">— base do spread sobre CDI dos fundos de crédito/papel</span>
        </div>
      )}

      <section>
        <h2>Short-list de ações</h2>
        <p className="sub">Ranqueada pelo score composto. Proventos por competência da CVM.</p>
        <div className="tablecard">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Ativo</th>
                <th>Score</th>
                <th>DY atual</th>
                <th>DY mediana</th>
                <th>P/VP</th>
                <th>ROE</th>
                <th>Payout decl.</th>
                <th>Dív.líq/EBITDA</th>
                <th>Recorr.</th>
                <th>Proventos pagos (10a)</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {score.data.map((r) => {
                const f = fByTk.get(r.ticker);
                const rec = f?.recorrencia;
                return (
                  <tr key={r.ticker}>
                    <td className="muted">{r.rank}</td>
                    <td>
                      <span className="tk">{r.ticker}</span>
                      <div className="name">{r.nome}</div>
                    </td>
                    <td>
                      <span className={`score-pill ${scoreClass(r.score)}`}>{r.score}</span>
                    </td>
                    <td>{pct(r.dy_corrente)}</td>
                    <td className="muted">{pct(r.dy_mediana_hist)}</td>
                    <td>{num(r.pvp)}</td>
                    <td>{pct(r.roe_recente)}</td>
                    <td className="muted" title="Proventos declarados (DMPL) ÷ lucro do exercício">
                      {pct(latestYearValue(f?.payout_declarado_por_ano))}
                    </td>
                    <td className="muted">
                      {r.divida_liquida_ebitda === null || r.divida_liquida_ebitda === undefined
                        ? "—"
                        : `${r.divida_liquida_ebitda.toFixed(2)}x`}
                    </td>
                    <td className="muted">
                      {rec ? `${rec.years_paid}/${rec.window}` : "—"}
                    </td>
                    <td>{f ? <Sparkline series={f.proventos_pagos_por_ano} /> : "—"}</td>
                    <td>
                      {r.yield_trap ? (
                        <span className="chip trap">yield trap</span>
                      ) : rec?.passes ? (
                        <span className="chip ok">recorrente</span>
                      ) : (
                        <span className="chip">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Short-list de FIIs</h2>
        <p className="sub">
          Mesma análise das ações, adaptada a fundos: DY oficial da CVM, crescimento (CAGR do
          DY), alavancagem (passivo/PL), preservação da cota e taxa de administração.{" "}
          <strong>Baseline = histórico do próprio fundo</strong> (~5 anos de DY mensal); o trap é
          per-fundo. <strong>Tipo</strong> (tijolo/papel/FoF) classificado pela composição do
          ativo no informe da CVM.
        </p>
        <FundShortlist
          rows={fiiScore.data}
          baselineKey="dy_mediana"
          baselineLabel="DY mediana"
        />
      </section>

      <section>
        <h2>Short-list de FIAgros</h2>
        <p className="sub">
          Universo <strong>auto-detectado</strong> (fi-agro negociados na B3 ∩ informe da CVM).
          O FIAgro só tem dado mensal desde <strong>2025-05 (~1 ano)</strong>: o DY 12m pode ser{" "}
          <em>anualizado</em> (est.) e o baseline é <strong>cross-sectional</strong> (mediana dos
          pares), não histórico. A coluna <em>confiança</em> rebaixa DY com cara de placeholder
          (constante) e histórico muito curto. <strong>Tipo</strong> (crédito/terras) e{" "}
          <strong>inadimplência</strong> (Vencidos/carteira) saem da composição do informe; o
          baseline de yield é por tipo.
        </p>
        <FundShortlist
          rows={fiagroScore.data}
          baselineKey="dy_baseline_pares"
          baselineLabel="DY pares"
          showConfianca
          showCredito
        />
      </section>

      {fatos.data.length > 0 && (
        <section>
          <h2>Fatos relevantes da watchlist</h2>
          <p className="sub">
            Avisos de proventos, fatos relevantes e relatórios de proventos das ações
            monitoradas (índice IPE-RAD da CVM). Link abre o documento original.
          </p>
          <div className="tablecard">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Ativo</th>
                  <th>Categoria</th>
                  <th>Assunto</th>
                  <th>Doc.</th>
                </tr>
              </thead>
              <tbody>
                {fatos.data.slice(0, 30).map((r, i) => (
                  <tr key={`${r.cd_cvm}-${r.data}-${i}`}>
                    <td className="muted">{r.data}</td>
                    <td>
                      <span className="tk">{r.ticker ?? r.cd_cvm}</span>
                    </td>
                    <td>{r.categoria}</td>
                    <td className="muted">{r.assunto || "—"}</td>
                    <td>
                      {r.link ? (
                        <a href={r.link} target="_blank" rel="noopener noreferrer">
                          abrir
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <footer>
        Fonte: CVM (dados abertos) para proventos e fundamentos; yfinance/brapi para preço de
        mercado. Metodologia em <code>CLAUDE.md</code>. {generated ? `Gerado em ${generated}.` : ""}{" "}
        Conteúdo informativo, não é recomendação de investimento.
      </footer>
    </main>
  );
}
