"""Extratores de PDF. O layout é reconhecido pelo conteúdo do texto.

Layout "pdf_cd": linhas 'SALDO ANTERIOR' / 'SALDO FINAL' e valores com C/D.
Layout "pdf_resumo": colunas separadas de Crédito e Débito e um bloco
    'Resumo do período' com 'Saldo em DD/MM/AAAA'.
Qualquer outro PDF (ex.: comunicado do banco) -> ArquivoNaoReconhecido.
"""
import re
from datetime import datetime

import pdfplumber

from ..identificar import ArquivoEntrada
from ..modelo import ArquivoNaoReconhecido, Extrato, Lancamento
from ..util import para_data, periodo_aaaa_mm, valor_br

VALOR_CD = r"[\d.]+,\d{2} [CD]"
DATA = r"\d{2}/\d{2}/\d{4}"


def extrair_pdf(entrada: ArquivoEntrada) -> Extrato:
    with pdfplumber.open(entrada.caminho) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
        extrato = Extrato(arquivo=entrada.caminho.name, hash=entrada.hash, formato="PDF")

        if re.search(r"SALDO FINAL", texto):
            _layout_cd(texto, extrato)
        elif re.search(r"Resumo do per[ií]odo", texto, re.IGNORECASE):
            _layout_resumo(pdf, texto, extrato)
        elif not texto.strip():
            raise ArquivoNaoReconhecido("PDF sem texto (provável digitalização); precisa de OCR")
        else:
            raise ArquivoNaoReconhecido("PDF não contém extrato (sem saldo final nem resumo do período)")
    return extrato


def _buscar(padrao: str, texto: str) -> str:
    m = re.search(padrao, texto)
    return m.group(1).strip() if m else ""


def _layout_cd(texto: str, extrato: Extrato) -> None:
    extrato.layout = "pdf_cd"
    extrato.banco = _buscar(r"^(BANCO [A-ZÀ-Ú ]+?)\s+EXTRATO", texto).title()
    extrato.titular = _buscar(r"Titular:\s*(.+?)\s+CNPJ", texto)
    extrato.cnpj = _buscar(r"CNPJ:\s*([\d./-]+)", texto)
    extrato.agencia = _buscar(r"Ag[eê]ncia:\s*(\S+)", texto)
    extrato.conta = _buscar(r"Conta:\s*(\S+)", texto)
    extrato.periodo = periodo_aaaa_mm(_buscar(rf"Per[ií]odo:\s*({DATA} a {DATA})", texto))

    for linha in texto.splitlines():
        linha = linha.strip()
        m = re.match(rf"^{DATA}\s+SALDO (ANTERIOR|FINAL)\s+({VALOR_CD})$", linha)
        if m:
            if m.group(1) == "ANTERIOR":
                extrato.saldo_inicial = valor_br(m.group(2))
            else:
                extrato.saldo_final = valor_br(m.group(2))  # valor OFICIAL
            continue
        # data | histórico | documento (opcional) | valor C/D | saldo C/D
        m = re.match(rf"^({DATA})\s+(.+?)\s+(?:[A-Z]{{3}}\d+\s+)?({VALOR_CD})\s+({VALOR_CD})$", linha)
        if m:
            extrato.lancamentos.append(Lancamento(para_data(m.group(1)), m.group(2), valor_br(m.group(3))))
            extrato.saldo_ultimo_lancamento = valor_br(m.group(4))


def _layout_resumo(pdf, texto: str, extrato: Extrato) -> None:
    extrato.layout = "pdf_resumo"
    extrato.banco = texto.splitlines()[0].strip()
    extrato.titular = _buscar(r"Cliente:\s*(.+)", texto)
    extrato.cnpj = _buscar(r"CNPJ\s*([\d./-]+)", texto)
    extrato.agencia = _buscar(r"Ag\.\s*(\d+)", texto)
    extrato.conta = _buscar(r"Conta\s*([\d-]+)", texto)
    periodo_txt = _buscar(rf"Per[ií]odo consultado:\s*({DATA} a {DATA})", texto)
    extrato.periodo = periodo_aaaa_mm(periodo_txt)
    ano = periodo_txt[-4:] if periodo_txt else ""

    # Saldos do resumo: data mais antiga = inicial, mais recente = final (OFICIAL).
    saldos = [(datetime.strptime(d, "%d/%m/%Y"), valor_br(v))
              for d, v in re.findall(rf"Saldo em ({DATA})\s+(-?[\d.]+,\d{{2}})", texto)]
    if saldos:
        saldos.sort()
        extrato.saldo_inicial = saldos[0][1]
        extrato.saldo_final = saldos[-1][1]

    # Lançamentos: o texto puro não diz se o valor é crédito ou débito,
    # então usamos a POSIÇÃO horizontal do número na página,
    # comparando com as colunas "Crédito" e "Débito" do cabeçalho.
    for pagina in pdf.pages:
        palavras = pagina.extract_words(keep_blank_chars=False)
        col_credito = _borda_direita_coluna(palavras, "Crédito")
        col_debito = _borda_direita_coluna(palavras, "Débito")
        if col_credito is None or col_debito is None:
            continue
        for linha in _agrupar_linhas(palavras):
            if not re.fullmatch(r"\d{2}/\d{2}", linha[0]["text"]):
                continue
            numeros = [p for p in linha if re.fullmatch(r"-?[\d.]+,\d{2}", p["text"])]
            if len(numeros) < 2:
                continue
            valor_p, saldo_p = numeros[-2], numeros[-1]
            valor = valor_br(valor_p["text"])
            # números alinhados à direita: compara a borda direita com a de cada coluna
            if abs(valor_p["x1"] - col_debito) < abs(valor_p["x1"] - col_credito):
                valor = -valor
            descricao = " ".join(p["text"] for p in linha[1:] if p not in numeros)
            extrato.lancamentos.append(Lancamento(para_data(f"{linha[0]['text']}/{ano}"), descricao, valor))
            extrato.saldo_ultimo_lancamento = valor_br(saldo_p["text"])


def _borda_direita_coluna(palavras, titulo: str):
    """Borda direita do título da coluna (ex.: 'Crédito (R$)'), onde os valores se alinham."""
    for i, p in enumerate(palavras):
        if p["text"].startswith(titulo):
            prox = palavras[i + 1] if i + 1 < len(palavras) else None
            if prox and prox["text"] == "(R$)" and abs(prox["top"] - p["top"]) < 3:
                return prox["x1"]
            return p["x1"]
    return None


def _agrupar_linhas(palavras, tolerancia=3):
    """Agrupa palavras que estão na mesma altura da página em linhas."""
    linhas = []
    for p in sorted(palavras, key=lambda p: (round(p["top"]), p["x0"])):
        if linhas and abs(linhas[-1][0]["top"] - p["top"]) <= tolerancia:
            linhas[-1].append(p)
        else:
            linhas.append([p])
    return [sorted(l, key=lambda p: p["x0"]) for l in linhas]
