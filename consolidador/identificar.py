"""Etapa 1: listar a pasta de entrada e identificar cada arquivo.

- formato pela extensão (PDF, Excel ou Imagem);
- hash SHA-256 do conteúdo, para detectar arquivos duplicados
  mesmo quando o nome é diferente (ex.: "extrato (1).pdf").
"""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

FORMATOS = {
    ".pdf": "PDF",
    ".xlsx": "Excel", ".xlsm": "Excel", ".xls": "Excel",
    ".png": "Imagem", ".jpg": "Imagem", ".jpeg": "Imagem", ".webp": "Imagem",
}


@dataclass
class ArquivoEntrada:
    caminho: Path
    formato: str        # "PDF", "Excel", "Imagem" ou "Desconhecido"
    hash: str
    duplicado_de: str = ""  # nome do primeiro arquivo com o mesmo conteúdo


def calcular_hash(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


MARCA_DE_COPIA = re.compile(r"(\s*\(\d+\)|[\s_-]*(c[oó]pia|copy)(\s*\d+)?)$", re.IGNORECASE)


def parece_copia(caminho: Path) -> bool:
    """True para nomes como 'extrato (1).pdf', 'extrato - Cópia.pdf', 'extrato copy.pdf'."""
    return bool(MARCA_DE_COPIA.search(caminho.stem))


def listar_arquivos(pasta: Path) -> list[ArquivoEntrada]:
    """Lista os arquivos da pasta e marca os duplicados.

    Ignora arquivos ocultos e temporários do Office (~$...).
    Ordem: primeiro os nomes "limpos", depois os que parecem cópia, e em
    cada grupo ordem alfabética. Assim, entre 'extrato.pdf' e
    'extrato (1).pdf' com o mesmo conteúdo, o original é o primeiro.
    """
    arquivos = []
    vistos: dict[str, str] = {}
    ordem = lambda p: (parece_copia(p), p.name.lower())
    for caminho in sorted(pasta.iterdir(), key=ordem):
        if not caminho.is_file() or caminho.name.startswith((".", "~$")):
            continue
        formato = FORMATOS.get(caminho.suffix.lower(), "Desconhecido")
        h = calcular_hash(caminho)
        item = ArquivoEntrada(caminho, formato, h)
        if h in vistos:
            item.duplicado_de = vistos[h]
        else:
            vistos[h] = caminho.name
        arquivos.append(item)
    return arquivos
