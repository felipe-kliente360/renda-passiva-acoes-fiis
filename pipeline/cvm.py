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

DEFAULT_DEST = Path("data/raw")


def fii_inf_mensal_url(year: int) -> str:
    """URL do ZIP do informe mensal de FII para um ano."""
    return f"{FII_INF_MENSAL_BASE}/inf_mensal_fii_{year}.zip"


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
