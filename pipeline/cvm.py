"""Downloader dos pacotes de dados abertos da CVM (acesso a REDE isolado aqui).

Decisão TRAVADA: o ZIP do ano corrente é reescrito a cada atualização (não incremental)
— sempre rebaixar o ano corrente inteiro. Nada de parsing aqui; só I/O de rede para
disco. O parsing fica em normalize/fii (puros, testáveis offline).

ATENÇÃO (honestidade sobre incerteza): os caminhos exatos do portal de dados abertos
podem mudar. Antes de confiar em produção, validar a URL contra o índice vivo:
  https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# Base dos informes mensais de FII. Validar contra o índice da CVM.
FII_INF_MENSAL_BASE = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS"
# Demonstrações de companhias abertas (ações): DFP (anual) e ITR (trimestral). Validados
# contra o índice vivo em 2026-06-26 (dfp_cia_aberta_AAAA.zip / itr_cia_aberta_AAAA.zip).
DFP_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS"
ITR_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS"
# Informe mensal de FIAgro — DATASET PRÓPRIO, arquivos MENSAIS (inf_mensal_fiagro_AAAAMM.zip).
# Validado contra o índice vivo em 2026-06-27: cobertura começa em 202505. Difere do FII
# (que é anual): aqui cada ZIP é um mês.
FIAGRO_INF_MENSAL_BASE = "https://dados.cvm.gov.br/dados/FIAGRO/DOC/INF_MENSAL/DADOS"
# Primeiro mês disponível no portal (AAAAMM). Antes disso não há arquivo (404).
FIAGRO_FIRST_PERIOD = (2025, 5)

# Fatos relevantes / comunicados (IPE-RAD). Arquivos ANUAIS. Cobertura 2021+.
IPE_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS"

DEFAULT_DEST = Path("data/raw")


def fii_inf_mensal_url(year: int) -> str:
    """URL do ZIP do informe mensal de FII para um ano."""
    return f"{FII_INF_MENSAL_BASE}/inf_mensal_fii_{year}.zip"


def dfp_url(year: int) -> str:
    """URL do ZIP das DFP (demonstrações anuais) de companhias abertas."""
    return f"{DFP_BASE}/dfp_cia_aberta_{year}.zip"


def itr_url(year: int) -> str:
    """URL do ZIP das ITR (demonstrações trimestrais) de companhias abertas."""
    return f"{ITR_BASE}/itr_cia_aberta_{year}.zip"


def ipe_url(year: int) -> str:
    """URL do ZIP do índice IPE (fatos relevantes/comunicados) de um ano."""
    return f"{IPE_BASE}/ipe_cia_aberta_{year}.zip"


def download_ipe(year: int | None = None, dest_dir: str | Path = DEFAULT_DEST) -> Path:
    """Baixa o ZIP do índice IPE do ano (default: ano corrente)."""
    year = year or date.today().year
    dest = Path(dest_dir) / f"ipe_cia_aberta_{year}.zip"
    return download(ipe_url(year), dest)


def download(url: str, dest: str | Path, *, timeout: int = 60) -> Path:
    """Baixa `url` para `dest` (cria diretórios). Retorna o caminho local.

    Levanta exceção em falha — o chamador (Action/entry point) decide o retry.
    """
    import requests  # import tardio: rede isolada

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
    return dest


def download_fii_inf_mensal(
    year: int | None = None, dest_dir: str | Path = DEFAULT_DEST
) -> Path:
    """Baixa o ZIP do informe mensal de FII do ano (default: ano corrente)."""
    year = year or date.today().year
    dest = Path(dest_dir) / f"inf_mensal_fii_{year}.zip"
    return download(fii_inf_mensal_url(year), dest)


def fiagro_inf_mensal_url(year: int, month: int) -> str:
    """URL do ZIP do informe mensal de FIAgro de um mês (AAAAMM)."""
    return f"{FIAGRO_INF_MENSAL_BASE}/inf_mensal_fiagro_{year}{month:02d}.zip"


def iter_fiagro_periods(
    start: tuple[int, int] = FIAGRO_FIRST_PERIOD,
    end: tuple[int, int] | None = None,
) -> list[tuple[int, int]]:
    """Lista os (ano, mês) de start até end inclusive (default end = mês corrente)."""
    end = end or (date.today().year, date.today().month)
    periods: list[tuple[int, int]] = []
    y, m = start
    while (y, m) <= end:
        periods.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return periods


def download_fiagro_inf_mensal(
    year: int, month: int, dest_dir: str | Path = DEFAULT_DEST
) -> Path:
    """Baixa o ZIP do informe mensal de FIAgro de um mês (AAAAMM)."""
    dest = Path(dest_dir) / f"inf_mensal_fiagro_{year}{month:02d}.zip"
    return download(fiagro_inf_mensal_url(year, month), dest)


def download_dfp(year: int | None = None, dest_dir: str | Path = DEFAULT_DEST) -> Path:
    """Baixa o ZIP das DFP (anuais) do ano (default: ano corrente)."""
    year = year or date.today().year
    dest = Path(dest_dir) / f"dfp_cia_aberta_{year}.zip"
    return download(dfp_url(year), dest)


def download_itr(year: int | None = None, dest_dir: str | Path = DEFAULT_DEST) -> Path:
    """Baixa o ZIP das ITR (trimestrais) do ano (default: ano corrente)."""
    year = year or date.today().year
    dest = Path(dest_dir) / f"itr_cia_aberta_{year}.zip"
    return download(itr_url(year), dest)
