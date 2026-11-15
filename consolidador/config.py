"""Configuração lida de variáveis de ambiente ou do arquivo .env.

A chave da API NUNCA fica no código: fica no .env (fora do Git) ou no ambiente.
"""
import os
from pathlib import Path


def carregar_env(caminho: Path = Path(".env")) -> None:
    """Lê linhas CHAVE=valor do .env sem sobrescrever o que já está no ambiente."""
    if not caminho.exists():
        return
    # utf-8-sig: ignora o BOM que alguns editores do Windows colocam no início do arquivo
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def gemini_modelo() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
