"""Leitura e normalização do formato cru da CVM.

Decisão TRAVADA do formato CVM: encoding ISO-8859-1, separador `;`, vírgula decimal.
Funções puras sobre arquivos/buffers locais — nenhum acesso a rede aqui.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

CVM_ENCODING = "ISO-8859-1"
CVM_SEP = ";"
CVM_DECIMAL = ","

# Sentinelas comuns de "vazio" nos arquivos da CVM.
NA_VALUES = ["", " ", "NA", "N/A", "nan", "null", "NULL"]


def read_cvm_csv(
    source: str | Path | io.IOBase | bytes,
    *,
    encoding: str = CVM_ENCODING,
    sep: str = CVM_SEP,
    decimal: str = CVM_DECIMAL,
    dtype: dict[str, str] | None = None,
    **read_kwargs: object,
) -> pd.DataFrame:
    """Lê um CSV cru da CVM aplicando encoding/sep/decimal corretos.

    Aceita caminho, buffer ou bytes. Tudo é lido como string por padrão (dtype=str),
    a menos que `dtype` seja informado — a conversão numérica é responsabilidade dos
    parsers de domínio, que sabem quais colunas converter (ver `to_numeric_ptbr`).
    `read_kwargs` é repassado ao pandas (ex.: nrows para inspeção).
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    return pd.read_csv(
        source,
        encoding=encoding,
        sep=sep,
        decimal=decimal,
        dtype=dtype if dtype is not None else str,
        na_values=NA_VALUES,
        keep_default_na=True,
        **read_kwargs,
    )


def read_cvm_csv_from_zip(
    zip_source: str | Path | bytes,
    member: str,
    **kwargs: object,
) -> pd.DataFrame:
    """Lê um CSV específico de dentro de um ZIP da CVM."""
    zf_source: object = io.BytesIO(zip_source) if isinstance(zip_source, bytes) else zip_source
    with zipfile.ZipFile(zf_source) as zf:  # type: ignore[arg-type]
        with zf.open(member) as fh:
            data = fh.read()
    return read_cvm_csv(data, **kwargs)  # type: ignore[arg-type]


def list_zip_members(zip_source: str | Path | bytes) -> list[str]:
    """Lista os arquivos dentro de um ZIP da CVM (ordenado)."""
    zf_source: object = io.BytesIO(zip_source) if isinstance(zip_source, bytes) else zip_source
    with zipfile.ZipFile(zf_source) as zf:  # type: ignore[arg-type]
        return sorted(zf.namelist())


def to_numeric_ptbr(series: pd.Series, *, decimal: str = CVM_DECIMAL) -> pd.Series:
    """Converte uma série de strings em número, tratando a vírgula decimal pt-BR.

    Idempotente para séries já numéricas. Remove separador de milhar `.` somente
    quando a vírgula é o decimal (formato CVM padrão).
    """
    if pd.api.types.is_numeric_dtype(series):
        return series
    cleaned = series.astype("string").str.strip()
    if decimal == ",":
        cleaned = cleaned.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")
