// Leitura dos artefatos estáticos da CVM/pipeline no BUILD (sem rede em runtime).
// Os JSON vivem na raiz do repo (../data); o static export embute o resultado no HTML.
import { readFileSync } from "node:fs";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "..", "data");

function read<T>(file: string, fallback: T): T {
  try {
    const raw = readFileSync(path.join(DATA_DIR, file), "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export type Meta = { generated_at?: string; [k: string]: unknown };
type Payload<T> = { meta?: Meta; data: T[] };

export type ScoreRow = {
  rank: number;
  ticker: string;
  nome?: string;
  score: number;
  recurrence: number;
  yield: number;
  growth: number;
  sustainability: number;
  yield_trap: boolean;
  dy_corrente?: number | null;
  dy_mediana_hist?: number | null;
  pvp?: number | null;
  roe_recente?: number | null;
  divida_liquida_ebitda?: number | null;
};

export type Fundamento = {
  ticker: string;
  nome?: string;
  proventos_pagos_por_ano: Record<string, number>;
  dy_historico_por_ano: Record<string, number>;
  dy_historico_mediana?: number | null;
  dy_corrente?: number | null;
  dy_corrente_base?: string;
  payout_por_ano: Record<string, number | null>;
  proventos_declarados_por_ano?: Record<string, number>;
  payout_declarado_por_ano?: Record<string, number | null>;
  pvp?: number | null;
  recorrencia?: { years_paid?: number; window?: number; passes?: boolean };
  crescimento_dps_cagr?: number | null;
  yield_trap?: boolean;
  notes?: string[];
};

export type FiiPrice = {
  ticker: string;
  tipo: string;
  nome?: string;
  current_price?: number | null;
  pvp?: number | null;
};

export type FiiDy = {
  ticker: string;
  dy_ttm?: number | null;
  dy_mediana?: number | null;
  meses_com_pagamento_12m?: number;
  yield_trap?: boolean;
};

// Score de FUNDOS (FII e FIAgro) — mesma metodologia 40/30/30 × sustentabilidade,
// adaptada a fundos (alavancagem/cota/taxa/recorrência). FII traz baseline histórico
// próprio (dy_mediana); FIAgro, baseline cross-sectional (dy_baseline_pares) e confiança.
export type FundScoreRow = {
  rank: number;
  ticker: string;
  nome?: string;
  score: number;
  recurrence: number;
  yield: number;
  growth: number;
  sustainability: number;
  yield_trap: boolean;
  confianca?: "alta" | "baixa";
  tipo?: string | null;
  inadimplencia?: number | null;
  diversificacao_hhi?: number | null;
  liquidez_pl?: number | null;
  num_cotistas?: number | null;
  spread_cdi?: number | null;
  volume_brapi?: number | null;
  dy_ttm?: number | null;
  dy_ttm_estimado?: boolean;
  dy_mediana?: number | null;
  dy_baseline_pares?: number | null;
  pvp?: number | null;
  alavancagem?: number | null;
  vp_cota_var?: number | null;
  meses_disponiveis?: number;
  crescimento?: number | null;
  crescimento_base?: string | null;
};

export type FatoRelevante = {
  cd_cvm: string;
  ticker?: string | null;
  nome?: string | null;
  data: string;
  categoria: string;
  tipo?: string | null;
  assunto?: string | null;
  link?: string | null;
  alerta_politica?: boolean;
};

export function getScore() {
  return read<Payload<ScoreRow>>("score.json", { data: [] });
}
export function getFatosRelevantes() {
  return read<Payload<FatoRelevante>>("fatos_relevantes.json", { data: [] });
}

export type Macro = {
  cdi_12m?: number | null;
  selic_meta?: number | null;
  ipca_12m?: number | null;
  as_of?: string | null;
};
export function getMacro(): Macro {
  const p = read<Payload<Macro>>("macro.json", { data: [] });
  return p.data[0] ?? {};
}
export function getFiiScore() {
  return read<Payload<FundScoreRow>>("fii_score.json", { data: [] });
}
export function getFiagroScore() {
  return read<Payload<FundScoreRow>>("fiagro_score.json", { data: [] });
}
export function getFundamentos() {
  return read<Payload<Fundamento>>("fundamentos.json", { data: [] });
}
export function getFiis() {
  const p = read<Payload<FiiPrice>>("prices.json", { data: [] });
  return { meta: p.meta, data: p.data.filter((r) => r.tipo === "fii") };
}
export function getFiiDy() {
  const p = read<Payload<FiiDy>>("fii_dy.json", { data: [] });
  return new Map(p.data.map((r) => [r.ticker, r]));
}
