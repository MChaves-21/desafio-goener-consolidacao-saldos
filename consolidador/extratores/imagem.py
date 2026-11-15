"""Extrator de imagens (prints de app bancário).

Principal: Gemini por API (chamada programática, sem interface de chat).
Reserva:   OCR local com Tesseract, se não houver chave ou a API falhar.

Regra: a IA só TRANSCREVE o que está na imagem (textos e valores como
aparecem). Toda conversão e toda conta são feitas aqui, em Python, para
que a validação cruzada seja independente da IA.
"""
import base64
import json
import re
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

import requests

from .. import config
from ..identificar import ArquivoEntrada
from ..modelo import ArquivoNaoReconhecido, Extrato, Lancamento
from ..util import periodo_aaaa_mm, sem_acento, valor_br

MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}

PROMPT = """Você é um transcritor de extratos bancários.
Transcreva EXATAMENTE o que aparece na imagem, sem calcular, somar, arredondar ou corrigir nada.
- Valores: copie como aparecem, com o sinal (+ ou -) e no formato brasileiro (ex.: "- R$ 1.234,56").
- Datas dos lançamentos: copie como aparecem (ex.: "05 out").
- "saldo_inicial_texto" e "saldo_final_texto": os valores rotulados como "Saldo inicial" e "Saldo final".
- Liste TODOS os lançamentos, na ordem em que aparecem, cada um com o saldo exibido logo abaixo dele.
- Se a imagem não for um extrato bancário, responda e_extrato = false e deixe o resto vazio.
- Se algum campo não estiver visível, deixe vazio. Não invente."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "e_extrato": {"type": "BOOLEAN"},
        "banco": {"type": "STRING"},
        "titular": {"type": "STRING"},
        "agencia": {"type": "STRING"},
        "conta": {"type": "STRING"},
        "periodo_texto": {"type": "STRING"},
        "saldo_inicial_texto": {"type": "STRING"},
        "saldo_final_texto": {"type": "STRING"},
        "lancamentos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "data_texto": {"type": "STRING"},
                    "descricao": {"type": "STRING"},
                    "valor_texto": {"type": "STRING"},
                    "saldo_texto": {"type": "STRING"},
                },
                "required": ["data_texto", "descricao", "valor_texto", "saldo_texto"],
            },
        },
    },
    "required": ["e_extrato", "banco", "titular", "agencia", "conta", "periodo_texto",
                 "saldo_inicial_texto", "saldo_final_texto", "lancamentos"],
}


class FalhaLeituraIA(Exception):
    pass


def extrair_imagem(entrada: ArquivoEntrada) -> Extrato:
    extrato = Extrato(arquivo=entrada.caminho.name, hash=entrada.hash, formato="Imagem")
    chave = config.gemini_api_key()
    motivo_reserva = "GEMINI_API_KEY não configurada"
    if chave:
        try:
            dados = _ler_com_gemini(entrada.caminho, chave, config.gemini_modelo())
            extrato.layout = f"imagem_ia ({config.gemini_modelo()})"
            _preencher(extrato, dados)
            _dupla_leitura(entrada.caminho, extrato)
            return extrato
        except FalhaLeituraIA as erro:
            motivo_reserva = f"Gemini indisponível: {erro}"

    # Reserva: OCR local
    dados = _ler_com_ocr(entrada.caminho)
    extrato.layout = "imagem_ocr"
    extrato.observacoes.append(f"Lido por OCR local ({motivo_reserva}).")
    _preencher(extrato, dados)
    return extrato


def _dupla_leitura(caminho: Path, extrato: Extrato) -> None:
    """Relê a imagem com OCR local e compara os saldos com a leitura da IA.

    Duas leituras independentes concordando = mais confiança.
    Discordando = pendência (status 'revisar'), sem escolher um lado.
    """
    try:
        ocr = _ler_com_ocr(caminho)
    except ArquivoNaoReconhecido:
        extrato.observacoes.append("Dupla leitura não realizada (Tesseract não instalado).")
        return
    for campo, rotulo, valor_ia in (("saldo_final_texto", "saldo final", extrato.saldo_final),
                                    ("saldo_inicial_texto", "saldo inicial", extrato.saldo_inicial)):
        valor_ocr = valor_br(ocr.get(campo))
        if valor_ocr is None:
            extrato.observacoes.append(f"Dupla leitura: OCR não leu o {rotulo}.")
        elif valor_ia is None or abs(valor_ocr - valor_ia) > 0.009:
            extrato.pendencias.append(
                f"Dupla leitura diverge no {rotulo}: IA={_fmt(valor_ia)} x OCR={_fmt(valor_ocr)}.")


def _fmt(v) -> str:
    return "—" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- Gemini
def _ler_com_gemini(caminho: Path, chave: str, modelo: str, tentativas: int = 3) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    mime = "image/png" if caminho.suffix.lower() == ".png" else "image/jpeg"
    corpo = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(caminho.read_bytes()).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": ESQUEMA},
    }
    espera = 5
    for tentativa in range(1, tentativas + 1):
        try:
            r = requests.post(url, json=corpo, headers={"x-goog-api-key": chave}, timeout=90)
        except requests.RequestException as e:
            erro = f"erro de rede ({e.__class__.__name__})"
        else:
            if r.status_code == 200:
                try:
                    texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(texto)
                except (KeyError, IndexError, json.JSONDecodeError):
                    raise FalhaLeituraIA("resposta da IA fora do formato esperado")
            if r.status_code not in (429, 500, 503):  # erro que não melhora tentando de novo
                raise FalhaLeituraIA(f"HTTP {r.status_code}: {r.text[:150]}")
            erro = f"HTTP {r.status_code} (limite ou instabilidade)"
        if tentativa < tentativas:
            time.sleep(espera)
            espera *= 2
    raise FalhaLeituraIA(f"{erro} após {tentativas} tentativas")


# ---------------------------------------------------------------- OCR
def _tesseract() -> str:
    caminho = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not Path(caminho).exists() and not shutil.which("tesseract"):
        raise ArquivoNaoReconhecido("sem chave do Gemini e Tesseract não instalado")
    return caminho


VALOR = r"R\$\s*([\d.]+,\d{2})"


def _ler_com_ocr(caminho: Path) -> dict:
    """OCR em modo 'bloco uniforme' (--psm 6): cada linha do app sai inteira, ex.:
         '05 out + R$ 66.589,11'
         'Liquidacao Cobranca - Boletos Ass... Saldo R$ 224.222,32'
    """
    texto = subprocess.run([_tesseract(), str(caminho), "-", "--psm", "6"], capture_output=True,
                           text=True, encoding="utf-8").stdout
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    m_conta = re.search(r"Ag\s*(\d+)\s*\W+\s*CC\s*([\d-]+)", texto)
    m_inicial = re.search(rf"Saldo inicial\s*{VALOR}", texto)
    # o saldo final é o primeiro valor em linha própria logo depois do rótulo "Saldo final"
    m_final = re.search(rf"Saldo final.*?\n\s*{VALOR}", texto)

    lancamentos = []
    for i, l in enumerate(linhas):
        m = re.match(rf"^(\d{{2}} [a-z]{{3}})\s+([+-])\s*{VALOR}", l)
        if not m:
            continue
        prox = linhas[i + 1] if i + 1 < len(linhas) else ""
        m_saldo = re.search(rf"Saldo\s*{VALOR}", prox)
        lancamentos.append({
            "data_texto": m.group(1),
            "descricao": re.split(r"\s+Saldo\b|\s+—", prox)[0],
            "valor_texto": f"{m.group(2)} R$ {m.group(3)}",
            "saldo_texto": f"R$ {m_saldo.group(1)}" if m_saldo else "",
        })
    return {
        "e_extrato": "saldo final" in sem_acento(texto),
        "banco": linhas[0] if linhas else "",
        "titular": next((l for l in linhas if "SPE" in l or "Ltda" in l), ""),
        "agencia": m_conta.group(1) if m_conta else "",
        "conta": m_conta.group(2) if m_conta else "",
        "periodo_texto": _buscar_periodo(texto),
        "saldo_inicial_texto": f"R$ {m_inicial.group(1)}" if m_inicial else "",
        "saldo_final_texto": f"R$ {m_final.group(1)}" if m_final else "",
        "lancamentos": lancamentos,
    }


def _buscar_periodo(texto: str) -> str:
    m = re.search(r"\d{2}/\d{2}/\d{4} a \d{2}/\d{2}/\d{4}", texto)
    return m.group(0) if m else ""


# ---------------------------------------------------------------- normalização
def _preencher(extrato: Extrato, dados: dict) -> None:
    """Converte a transcrição (da IA ou do OCR) para o registro padrão."""
    if not dados.get("e_extrato"):
        raise ArquivoNaoReconhecido("imagem não parece ser um extrato bancário")
    extrato.banco = dados.get("banco", "").strip()
    extrato.titular = dados.get("titular", "").strip()
    extrato.agencia = dados.get("agencia", "").strip()
    extrato.conta = dados.get("conta", "").strip()
    extrato.periodo = periodo_aaaa_mm(dados.get("periodo_texto", ""))
    extrato.saldo_inicial = valor_br(dados.get("saldo_inicial_texto"))
    extrato.saldo_final = valor_br(dados.get("saldo_final_texto"))  # valor OFICIAL
    ano = int(extrato.periodo[:4]) if extrato.periodo[:4].isdigit() else None
    for l in dados.get("lancamentos", []):
        valor = valor_br(l.get("valor_texto"))
        if valor is None:
            extrato.observacoes.append(f"Valor ilegível: '{l.get('valor_texto')}'.")
            continue
        extrato.lancamentos.append(Lancamento(_data_curta(l.get("data_texto", ""), ano),
                                              l.get("descricao", ""), valor))
        # None se o saldo da última linha estiver ilegível (a 2ª checagem fica sem dado)
        extrato.saldo_ultimo_lancamento = valor_br(l.get("saldo_texto"))


def _data_curta(texto: str, ano):
    """'05 out' -> date(ano, 10, 5)."""
    m = re.fullmatch(r"(\d{1,2})\s+([a-zç]{3})\w*", sem_acento(texto))
    if not (m and ano and m.group(2) in MESES):
        return None
    try:
        return date(ano, MESES[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
