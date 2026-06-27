import Workspace, { type Detail, type Row } from "./components/Workspace";
import {
  getScore,
  getFundamentos,
  getFiiScore,
  getFiiFundos,
  getFiagroScore,
  getFiagro,
  getFatosRelevantes,
  getMacro,
  type Fundamento,
  type FundScoreRow,
  type FundoDetalhe,
} from "@/lib/data";

const pct = (v?: number | null, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`;
const n2 = (v?: number | null) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(2);
const signed = (v?: number | null) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

function latest(d?: Record<string, number | null>): number | null {
  if (!d) return null;
  const ys = Object.keys(d).filter((y) => d[y] !== null);
  if (!ys.length) return null;
  return d[ys.sort((a, b) => Number(b) - Number(a))[0]];
}
function clean(d?: Record<string, number | null>): Record<string, number> {
  const o: Record<string, number> = {};
  for (const [k, v] of Object.entries(d ?? {})) if (typeof v === "number") o[k] = v;
  return o;
}

function veredito(score: number, trap?: boolean, confBaixa?: boolean): string {
  let base =
    score >= 85 ? "Paga forte e de forma constante."
    : score >= 70 ? "Pagador sólido."
    : score >= 55 ? "Razoável — vale checar os pontos fracos."
    : "Fraco para a tese de renda passiva.";
  if (trap) base = "⚠ Yield muito acima do histórico — possível armadilha. " + base;
  if (confBaixa) base = "Dado de baixa confiança (histórico curto / placeholder). " + base;
  return base;
}

export default function Home() {
  const score = getScore();
  const fundamentos = getFundamentos();
  const fByTk = new Map<string, Fundamento>(fundamentos.data.map((f) => [f.ticker, f]));
  const fatos = getFatosRelevantes();
  const fatosByTk = new Map<string, typeof fatos.data>();
  for (const f of fatos.data) {
    const tk = f.ticker ?? f.cd_cvm;
    if (!tk) continue;
    if (!fatosByTk.has(tk)) fatosByTk.set(tk, []);
    fatosByTk.get(tk)!.push(f);
  }

  // ----- Ações -----
  const acoes: Row[] = score.data.map((r) => {
    const f = fByTk.get(r.ticker);
    const rec = f?.recorrencia;
    const detail: Detail = {
      veredito: veredito(r.score, r.yield_trap),
      breakdown: { recurrence: r.recurrence, yield: r.yield, growth: r.growth, sustainability: r.sustainability },
      series: {
        dy: { label: "DY histórico (% a.a.)", data: clean(f?.dy_historico_por_ano) },
        prov: { label: "Proventos pagos (R$)", data: clean(f?.proventos_pagos_por_ano), money: true },
        payout: { label: "Payout declarado (DMPL)", data: clean(f?.payout_declarado_por_ano) },
      },
      fundamentos: [
        { label: "DY atual", value: pct(r.dy_corrente) },
        { label: "DY mediana (hist.)", value: pct(r.dy_mediana_hist) },
        { label: "P/VP", value: n2(r.pvp) },
        { label: "ROE", value: pct(r.roe_recente) },
        { label: "Dív. líq./EBITDA", value: typeof r.divida_liquida_ebitda === "number" ? `${r.divida_liquida_ebitda.toFixed(2)}x` : "—", warn: (r.divida_liquida_ebitda ?? 0) > 3 },
        { label: "Recorrência", value: rec ? `${rec.years_paid}/${rec.window} anos` : "—" },
        { label: "Payout declarado", value: pct(latest(f?.payout_declarado_por_ano)) },
        { label: "CAGR dividendo", value: signed(f?.crescimento_dps_cagr) },
      ],
      fatos: fatosByTk.get(r.ticker)?.slice(0, 6),
      notes: f?.notes,
    };
    return { ...r, classe: "acoes", ticker: r.ticker, nome: r.nome ?? undefined, score: r.score, detail };
  });

  // ----- Fundos (FII / FIAgro): junta score + detalhe (séries) -----
  const buildFundo = (
    rows: FundScoreRow[],
    detalhes: FundoDetalhe[],
    classe: "fiis" | "fiagros"
  ): Row[] => {
    const byTk = new Map(detalhes.map((d) => [d.ticker, d]));
    return rows.map((r) => {
      const dt = byTk.get(r.ticker);
      const comp = dt?.composicao
        ? Object.entries(dt.composicao).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k.toUpperCase()} ${(v * 100).toFixed(0)}%`).join(" · ")
        : null;
      const fundamentos: { label: string; value: string; warn?: boolean }[] = [
        { label: "DY 12m", value: pct(r.dy_ttm) + (r.dy_ttm_estimado ? " est." : "") },
        { label: classe === "fiis" ? "DY mediana" : "DY pares", value: pct(classe === "fiis" ? r.dy_mediana : r.dy_baseline_pares) },
        { label: "P/VP", value: n2(r.pvp) },
        { label: "Alavancagem", value: pct(r.alavancagem, 0) },
        { label: "Cresc. (cota não derrete)", value: signed(r.vp_cota_var) },
        { label: "Taxa adm (a.a.)", value: pct(dt?.taxa_admin_aa) },
        { label: "Spread sobre CDI", value: signed(r.spread_cdi) },
        { label: "Nº cotistas", value: r.num_cotistas ? r.num_cotistas.toLocaleString("pt-BR") : "—" },
        { label: "Liquidez (vol/dia)", value: r.volume_brapi ? r.volume_brapi.toLocaleString("pt-BR") : "—" },
        { label: "Meses de histórico", value: r.meses_disponiveis ? String(r.meses_disponiveis) : "—" },
      ];
      if (classe === "fiis") {
        fundamentos.splice(3, 0,
          { label: "Vacância", value: pct(r.vacancia) },
          { label: "Inadimpl. aluguel", value: pct(r.inadimplencia) });
      } else {
        fundamentos.splice(3, 0,
          { label: "Inadimplência", value: pct(r.inadimplencia), warn: (r.inadimplencia ?? 0) > 0.03 },
          { label: "Diversificação (HHI)", value: n2(r.diversificacao_hhi) });
        if (comp) fundamentos.push({ label: "Composição", value: comp });
      }
      const detail: Detail = {
        veredito: veredito(r.score, r.yield_trap, r.confianca === "baixa"),
        breakdown: { recurrence: r.recurrence, yield: r.yield, growth: r.growth, sustainability: r.sustainability },
        series: { dy: { label: "DY por ano", data: clean(dt?.dy_por_ano) } },
        fundamentos,
      };
      return { ...r, classe, ticker: r.ticker, nome: r.nome ?? undefined, score: r.score, tipo: r.tipo, detail };
    });
  };

  const fiis = buildFundo(getFiiScore().data, getFiiFundos().data, "fiis");
  const fiagros = buildFundo(getFiagroScore().data, getFiagro().data, "fiagros");
  const macro = getMacro();
  const generated = (score.meta?.generated_at as string) || "";

  return (
    <main className="wrap">
      <header className="hero">
        <h1>div<span className="dot">br</span></h1>
        <p>Renda passiva na B3 a partir de dados oficiais da CVM, B3 e BCB.</p>
      </header>

      <div className="guide">
        <strong>Isto paga, e vai continuar pagando?</strong> Ranqueamos pelo fluxo que se
        sustenta: <strong>recorrência (40%)</strong>, yield vs. baseline <strong>(30%)</strong> e
        crescimento <strong>(30%)</strong>, ajustado por sustentabilidade e com corte de yield trap.
        Clique numa linha para o dossiê completo (timelines, breakdown do score, fundamentos).
      </div>

      <Workspace acoes={acoes} fiis={fiis} fiagros={fiagros} fatos={fatos.data} macro={macro} />

      <footer>
        Fontes: CVM (proventos/fundamentos), B3/FNET (vacância, fatos relevantes), brapi/yfinance
        (preço/volume), BCB (macro). Metodologia em <code>README.md</code> / <code>CLAUDE.md</code>.
        {generated ? ` Gerado em ${generated}.` : ""} Conteúdo informativo, não é recomendação de
        investimento.
      </footer>
    </main>
  );
}
