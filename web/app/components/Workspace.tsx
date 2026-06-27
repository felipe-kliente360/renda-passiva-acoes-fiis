"use client";

import { useMemo, useState } from "react";

// --------------------------------------------------------------------------- #
// Tipos (frouxos de propósito — as linhas carregam métricas heterogêneas por classe)
// --------------------------------------------------------------------------- #
export type Row = Record<string, unknown> & {
  ticker: string;
  nome?: string;
  classe: "acoes" | "fiis" | "fiagros";
  score: number;
  tipo?: string | null;
  detail: Detail;
};
export type Detail = Record<string, unknown> & {
  series?: Record<string, { label: string; data: Record<string, number>; money?: boolean }>;
  fundamentos?: { label: string; value: string; warn?: boolean }[];
  fatos?: { data: string; categoria: string; assunto?: string | null; link?: string | null; alerta_politica?: boolean }[];
  notes?: string[];
  breakdown?: { recurrence?: number; yield?: number; growth?: number; sustainability?: number };
  veredito?: string;
};
type Macro = { cdi_12m?: number | null; selic_meta?: number | null; ipca_12m?: number | null; as_of?: string | null };
type Col = { key: string; label: string; title?: string; num?: boolean; fmt?: (r: Row) => React.ReactNode };

// --------------------------------------------------------------------------- #
// Formatadores
// --------------------------------------------------------------------------- #
const n2 = (v: unknown, d = 2) =>
  typeof v === "number" && !Number.isNaN(v) ? v.toFixed(d) : "—";
const pct = (v: unknown, d = 1) =>
  typeof v === "number" && !Number.isNaN(v) ? `${(v * 100).toFixed(d)}%` : "—";
const signed = (v: unknown, d = 1) =>
  typeof v === "number" && !Number.isNaN(v) ? `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)}%` : "—";
const vol = (v: unknown) => {
  if (typeof v !== "number" || v <= 0) return "—";
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
  return `${v}`;
};
const scoreClass = (s: number) => (s >= 75 ? "s-hi" : s >= 55 ? "s-mid" : "s-lo");

function Pill({ s }: { s: number }) {
  return <span className={`score-pill ${scoreClass(s)}`}>{s}</span>;
}
function Chip({ children, kind }: { children: React.ReactNode; kind?: "ok" | "trap" }) {
  return <span className={`chip ${kind ?? ""}`}>{children}</span>;
}

// --------------------------------------------------------------------------- #
// Colunas por classe
// --------------------------------------------------------------------------- #
const COLS: Record<Row["classe"], Col[]> = {
  acoes: [
    { key: "score", label: "Score", num: true, fmt: (r) => <Pill s={r.score} /> },
    { key: "dy_corrente", label: "DY atual", num: true, fmt: (r) => pct(r.dy_corrente) },
    { key: "dy_mediana_hist", label: "DY mediana", num: true, fmt: (r) => pct(r.dy_mediana_hist) },
    { key: "pvp", label: "P/VP", num: true, fmt: (r) => n2(r.pvp) },
    { key: "roe_recente", label: "ROE", num: true, fmt: (r) => pct(r.roe_recente) },
    { key: "divida_liquida_ebitda", label: "Dív/EBITDA", num: true, title: "Dívida líquida / EBITDA", fmt: (r) => (typeof r.divida_liquida_ebitda === "number" ? `${(r.divida_liquida_ebitda as number).toFixed(2)}x` : "—") },
  ],
  fiis: [
    { key: "score", label: "Score", num: true, fmt: (r) => <Pill s={r.score} /> },
    { key: "dy_ttm", label: "DY 12m", num: true, fmt: (r) => pct(r.dy_ttm) },
    { key: "dy_mediana", label: "DY mediana", num: true, fmt: (r) => pct(r.dy_mediana) },
    { key: "pvp", label: "P/VP", num: true, fmt: (r) => n2(r.pvp) },
    { key: "vacancia", label: "Vacância", num: true, title: "Vacância dos imóveis (FNET)", fmt: (r) => pct(r.vacancia) },
    { key: "alavancagem", label: "Alav.", num: true, fmt: (r) => pct(r.alavancagem, 0) },
    { key: "spread_cdi", label: "Spread CDI", num: true, fmt: (r) => signed(r.spread_cdi) },
    { key: "volume_brapi", label: "Liq.", num: true, fmt: (r) => vol(r.volume_brapi) },
  ],
  fiagros: [
    { key: "score", label: "Score", num: true, fmt: (r) => <Pill s={r.score} /> },
    { key: "dy_ttm", label: "DY 12m", num: true, fmt: (r) => pct(r.dy_ttm) },
    { key: "dy_baseline_pares", label: "DY pares", num: true, fmt: (r) => pct(r.dy_baseline_pares) },
    { key: "pvp", label: "P/VP", num: true, fmt: (r) => n2(r.pvp) },
    { key: "inadimplencia", label: "Inadimpl.", num: true, fmt: (r) => pct(r.inadimplencia) },
    { key: "alavancagem", label: "Alav.", num: true, fmt: (r) => pct(r.alavancagem, 0) },
    { key: "spread_cdi", label: "Spread CDI", num: true, fmt: (r) => signed(r.spread_cdi) },
    { key: "volume_brapi", label: "Liq.", num: true, fmt: (r) => vol(r.volume_brapi) },
  ],
};

const dyKey: Record<Row["classe"], string> = { acoes: "dy_corrente", fiis: "dy_ttm", fiagros: "dy_ttm" };

// --------------------------------------------------------------------------- #
// Gráficos SVG (sem libs externas)
// --------------------------------------------------------------------------- #
function Bars({ data, money }: { data: Record<string, number>; money?: boolean }) {
  const entries = Object.entries(data).sort((a, b) => Number(a[0]) - Number(b[0]));
  if (!entries.length) return <span className="muted">sem dados</span>;
  const max = Math.max(...entries.map(([, v]) => Math.abs(v)), 1e-9);
  const W = 280, H = 70, bw = (W / entries.length) * 0.7, gap = (W / entries.length) * 0.3;
  const lbl = (v: number) => (money ? `${(v / 1e9).toFixed(1)}bi` : `${(v * 100).toFixed(1)}%`);
  return (
    <svg className="bars" viewBox={`0 0 ${W} ${H + 18}`} width="100%" preserveAspectRatio="none">
      {entries.map(([k, v], i) => {
        const h = Math.max(2, (Math.abs(v) / max) * H);
        const x = i * (bw + gap) + gap / 2;
        return (
          <g key={k}>
            <rect x={x} y={H - h} width={bw} height={h} rx="1.5" fill={v < 0 ? "var(--bad)" : "var(--accent)"}>
              <title>{`${k}: ${lbl(v)}`}</title>
            </rect>
            <text x={x + bw / 2} y={H + 12} textAnchor="middle" className="bars-x">{k.slice(-2)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function ScoreBreakdown({ b }: { b: Detail["breakdown"] }) {
  if (!b) return null;
  const rows: [string, number | undefined][] = [
    ["Recorrência (40%)", b.recurrence],
    ["Yield vs baseline (30%)", b.yield],
    ["Crescimento (30%)", b.growth],
    ["Sustentabilidade (×)", b.sustainability],
  ];
  return (
    <div className="brk">
      {rows.map(([label, v]) => (
        <div key={label} className="brk-row">
          <span className="brk-label">{label}</span>
          <span className="brk-track"><i style={{ width: `${Math.round((v ?? 0) * 100)}%` }} /></span>
          <span className="brk-val">{v === undefined ? "—" : v.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- #
// Tabela (sort + filtros)
// --------------------------------------------------------------------------- #
function Table({ rows, classe, onPick }: { rows: Row[]; classe: Row["classe"]; onPick: (r: Row) => void }) {
  const cols = COLS[classe];
  const [sortKey, setSortKey] = useState("score");
  const [asc, setAsc] = useState(false);
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<string | null>(null);
  const [hideTrap, setHideTrap] = useState(false);
  const [minScore, setMinScore] = useState(0);

  const tipos = useMemo(
    () => Array.from(new Set(rows.map((r) => r.tipo).filter(Boolean))) as string[],
    [rows]
  );

  const view = useMemo(() => {
    let v = rows.filter((r) => {
      if (q && !`${r.ticker} ${r.nome ?? ""}`.toLowerCase().includes(q.toLowerCase())) return false;
      if (tipo && r.tipo !== tipo) return false;
      if (hideTrap && r.yield_trap) return false;
      if (r.score < minScore) return false;
      return true;
    });
    v = [...v].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      const an = typeof av === "number" ? av : -Infinity;
      const bn = typeof bv === "number" ? bv : -Infinity;
      return asc ? an - bn : bn - an;
    });
    return v;
  }, [rows, q, tipo, hideTrap, minScore, sortKey, asc]);

  const clickSort = (k: string) => {
    if (k === sortKey) setAsc(!asc);
    else { setSortKey(k); setAsc(false); }
  };

  return (
    <div>
      <div className="filters">
        <input className="search" placeholder="buscar ticker ou nome…" value={q} onChange={(e) => setQ(e.target.value)} />
        {tipos.length > 1 && (
          <div className="tipo-chips">
            <button className={`fchip ${tipo === null ? "on" : ""}`} onClick={() => setTipo(null)}>todos</button>
            {tipos.map((t) => (
              <button key={t} className={`fchip ${tipo === t ? "on" : ""}`} onClick={() => setTipo(t)}>{t}</button>
            ))}
          </div>
        )}
        <label className="toggle"><input type="checkbox" checked={hideTrap} onChange={(e) => setHideTrap(e.target.checked)} /> esconder yield trap</label>
        <label className="slider">score ≥ {minScore}
          <input type="range" min={0} max={100} step={5} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
        </label>
        <span className="count">{view.length} de {rows.length}</span>
      </div>
      <div className="tablecard">
        <table>
          <thead>
            <tr>
              <th className="rk">#</th>
              <th className="sortable" onClick={() => clickSort("ticker")}>Ativo</th>
              {classe !== "acoes" && <th>Tipo</th>}
              {cols.map((c) => (
                <th key={c.key} className="sortable num" title={c.title} onClick={() => clickSort(c.key)}>
                  {c.label}{sortKey === c.key ? (asc ? " ▲" : " ▼") : ""}
                </th>
              ))}
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => (
              <tr key={r.ticker} className="clickable" onClick={() => onPick(r)}>
                <td className="muted rk">{i + 1}</td>
                <td><span className="tk">{r.ticker}</span><div className="name">{r.nome}</div></td>
                {classe !== "acoes" && <td>{r.tipo ? <Chip>{r.tipo}</Chip> : "—"}</td>}
                {cols.map((c) => <td key={c.key} className="num">{c.fmt ? c.fmt(r) : String(r[c.key] ?? "—")}</td>)}
                <td className="flags">
                  {r.alerta_politica ? <Chip kind="trap">⚠ política</Chip> : null}
                  {r.confianca === "baixa" ? <Chip kind="trap">conf. baixa</Chip> : null}
                  {r.yield_trap ? <Chip kind="trap">yield trap</Chip> : <Chip kind="ok">recorrente</Chip>}
                </td>
              </tr>
            ))}
            {!view.length && <tr><td colSpan={cols.length + 4} className="muted empty">nada com esses filtros.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// Drawer (dossiê)
// --------------------------------------------------------------------------- #
function Drawer({ row, onClose }: { row: Row | null; onClose: () => void }) {
  if (!row) return null;
  const d = row.detail;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`Dossiê ${row.ticker}`}>
        <button className="drawer-x" onClick={onClose} aria-label="Fechar">×</button>
        <div className="drawer-head">
          <div>
            <span className="tk big">{row.ticker}</span>
            {row.tipo ? <Chip>{row.tipo}</Chip> : null}
            <div className="name">{row.nome}</div>
          </div>
          <Pill s={row.score} />
        </div>
        {d.veredito && <p className="veredito">{d.veredito}</p>}

        <h4>Composição do score</h4>
        <ScoreBreakdown b={d.breakdown} />

        {d.series && Object.entries(d.series).map(([k, s]) => (
          <div key={k} className="chart-block">
            <h4>{s.label}</h4>
            <Bars data={s.data} money={s.money} />
          </div>
        ))}

        {d.fundamentos && d.fundamentos.length > 0 && (
          <>
            <h4>Fundamentos</h4>
            <div className="fgrid">
              {d.fundamentos.map((f) => (
                <div key={f.label} className="fcell">
                  <span className="fk">{f.label}</span>
                  <span className={`fv ${f.warn ? "warn" : ""}`}>{f.value}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {d.fatos && d.fatos.length > 0 && (
          <>
            <h4>Fatos relevantes</h4>
            <ul className="fatos">
              {d.fatos.map((f, i) => (
                <li key={i}>
                  <span className="muted">{f.data}</span> {f.categoria}
                  {f.alerta_politica ? <Chip kind="trap">⚠ política</Chip> : null}
                  {f.assunto ? <div className="fato-assunto">{f.assunto}</div> : null}
                  {f.link ? <a href={f.link} target="_blank" rel="noopener noreferrer">abrir documento</a> : null}
                </li>
              ))}
            </ul>
          </>
        )}

        {d.notes && d.notes.length > 0 && (
          <p className="caveat">⚠ {d.notes.join(" · ")}</p>
        )}
      </aside>
    </>
  );
}

// --------------------------------------------------------------------------- #
// Workspace (abas)
// --------------------------------------------------------------------------- #
const TABS: { id: Row["classe"]; label: string }[] = [
  { id: "acoes", label: "Ações" },
  { id: "fiis", label: "FIIs" },
  { id: "fiagros", label: "FIAgros" },
];

const SUB: Record<string, string> = {
  acoes: "Proventos por competência da CVM (DFP); DY no nível da empresa; payout pago (DFC) e declarado (DMPL). Clique para o dossiê (timelines + fatos relevantes).",
  fiis: "DY oficial da CVM; baseline = histórico do próprio fundo; tipo e vacância (tijolo, via FNET) quando disponível.",
  fiagros: "Universo auto-detectado (brapi ∩ CVM); histórico curto (~1 ano) — DY anualizado, baseline por tipo, confiança.",
};

export default function Workspace({
  acoes, fiis, fiagros, macro,
}: {
  acoes: Row[]; fiis: Row[]; fiagros: Row[];
  macro: Macro;
}) {
  const [tab, setTab] = useState<Row["classe"]>("acoes");
  const [sel, setSel] = useState<Row | null>(null);
  const byTab: Record<Row["classe"], Row[]> = { acoes, fiis, fiagros };

  return (
    <>
      {(macro.cdi_12m ?? macro.selic_meta ?? macro.ipca_12m) != null && (
        <div className="macro">
          <span>Contexto (BCB):</span>
          <strong>CDI 12m {pct(macro.cdi_12m)}</strong>
          <strong>Selic {pct(macro.selic_meta)}</strong>
          <strong>IPCA 12m {pct(macro.ipca_12m)}</strong>
          <span className="muted">— base do spread sobre CDI dos fundos de crédito/papel</span>
        </div>
      )}

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
            <span className="tab-n">{byTab[t.id]?.length ?? 0}</span>
          </button>
        ))}
      </nav>
      <p className="sub">{SUB[tab]}</p>

      <Table rows={byTab[tab]} classe={tab} onPick={setSel} />

      <Drawer row={sel} onClose={() => setSel(null)} />
    </>
  );
}
