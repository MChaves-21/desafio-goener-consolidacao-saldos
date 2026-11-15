"""Funções de normalização usadas por todos os extratores."""
import re
import unicodedata
from datetime import date, datetime
from typing import Optional


def sem_acento(texto: str) -> str:
    """'Agência' -> 'agencia' (minúsculo e sem acento), para comparar rótulos."""
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()


def valor_br(texto) -> Optional[float]:
    """Converte valores no formato brasileiro para float.

    '1.234,56' -> 1234.56 | '1.234,56 D' -> -1234.56 | '- R$ 45,00' -> -45.0
    Se já vier número (Excel), apenas devolve como float.
    """
    if texto is None or texto == "":
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    s = str(texto).strip().upper().replace("R$", "").replace(" ", "")
    negativo = s.startswith("-") or s.endswith("D")
    s = s.strip("+-CD")
    if not re.fullmatch(r"[\d.]+(,\d{1,2})?", s):
        return None
    numero = float(s.replace(".", "").replace(",", "."))
    return -numero if negativo else numero


def para_data(valor) -> Optional[date]:
    """Aceita datetime do Excel, 'AAAA-MM-DD' ou 'DD/MM/AAAA'."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            pass
    return None


def periodo_aaaa_mm(texto: str) -> str:
    """'01/10/2026 a 31/10/2026' -> '2026-10'.

    Usa o mês da data final do período. Se o intervalo cobrir mais de um
    mês, devolve 'AAAA-MM a AAAA-MM' para a validação apontar.
    """
    datas = re.findall(r"(\d{2})/(\d{2})/(\d{4})", str(texto))
    if not datas:
        return ""
    meses = [f"{a}-{m}" for _, m, a in datas]
    if meses[0] != meses[-1]:
        return f"{meses[0]} a {meses[-1]}"
    return meses[-1]
