import { getScore, getFundamentos, getFiis, getFiiDy, type Fundamento } from "@/lib/data";

const pct = (v?: number | null, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v?: number | null, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d);

function scoreClass(s: number) {
  return s >= 75 ? "s-hi" : s >= 55 ? "s-mid" : "s-lo";
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

export default function Home() {
  const score = getScore();
  const fundamentos = getFundamentos();
  const fiis = getFiis();
  const fiiDy = getFiiDy();
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
        <h2>FIIs monitorados</h2>
        <p className="sub">
          Preço e P/VP (VP da cota do informe mensal da CVM) + DY 12m e mediana histórica
          (DY mensal oficial da CVM).
        </p>
        <div className="tablecard">
          <table>
            <thead>
              <tr>
                <th>Ativo</th>
                <th>Preço</th>
                <th>P/VP</th>
                <th>DY 12m</th>
                <th>DY mediana</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {fiis.data.map((r) => {
                const dy = fiiDy.get(r.ticker);
                return (
                  <tr key={r.ticker}>
                    <td>
                      <span className="tk">{r.ticker}</span>
                      <div className="name">{r.nome}</div>
                    </td>
                    <td>{num(r.current_price)}</td>
                    <td>{num(r.pvp)}</td>
                    <td>{pct(dy?.dy_ttm)}</td>
                    <td className="muted">{pct(dy?.dy_mediana)}</td>
                    <td>
                      {dy?.yield_trap ? (
                        <span className="chip trap">yield trap</span>
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

      <footer>
        Fonte: CVM (dados abertos) para proventos e fundamentos; yfinance/brapi para preço de
        mercado. Metodologia em <code>CLAUDE.md</code>. {generated ? `Gerado em ${generated}.` : ""}{" "}
        Conteúdo informativo, não é recomendação de investimento.
      </footer>
    </main>
  );
}
