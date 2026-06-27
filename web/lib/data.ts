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

export function getScore() {
  return read<Payload<ScoreRow>>("score.json", { data: [] });
}
export function getFundamentos() {
  return read<Payload<Fundamento>>("fundamentos.json", { data: [] });
}
export function getFiis() {
  const p = read<Payload<FiiPrice>>("prices.json", { data: [] });
  return { meta: p.meta, data: p.data.filter((r) => r.tipo === "fii") };
}
