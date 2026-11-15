"""Extratores de Excel. O layout é reconhecido pelo CONTEÚDO, não pelo nome do arquivo.

Layout "excel_dados_controle": abas 'dados' (lançamentos) e 'controle'
    (banco, agência, conta, período, saldo_inicial, saldo_final).
Layout "excel_extrato": uma aba com cabeçalho (Titular, CNPJ, Agência...)
    e lançamentos entre as linhas 'SALDO ANTERIOR' e 'SALDO FINAL'.
"""
import openpyxl

from ..identificar import ArquivoEntrada
from ..modelo import ArquivoNaoReconhecido, Extrato, Lancamento
from ..util import para_data, periodo_aaaa_mm, sem_acento, valor_br


def extrair_excel(entrada: ArquivoEntrada) -> Extrato:
    wb = openpyxl.load_workbook(entrada.caminho, data_only=True, read_only=True)
    abas = {sem_acento(nome): nome for nome in wb.sheetnames}
    extrato = Extrato(arquivo=entrada.caminho.name, hash=entrada.hash, formato="Excel")

    if "dados" in abas and "controle" in abas:
        _layout_dados_controle(wb[abas["dados"]], wb[abas["controle"]], extrato)
    else:
        for aba in wb.worksheets:
            linhas = [list(r) for r in aba.iter_rows(values_only=True)]
            if _tem_rotulo(linhas, "saldo final"):
                _layout_extrato(linhas, extrato)
                break
        else:
            raise ArquivoNaoReconhecido("planilha sem aba de controle nem linha 'SALDO FINAL'")
    wb.close()
    return extrato


def _tem_rotulo(linhas, rotulo: str) -> bool:
    return any(sem_acento(c) == rotulo for linha in linhas for c in linha if isinstance(c, str))


def _layout_dados_controle(aba_dados, aba_controle, extrato: Extrato) -> None:
    extrato.layout = "excel_dados_controle"

    # Aba controle: pares chave -> valor
    controle = {sem_acento(r[0]): r[1] for r in aba_controle.iter_rows(values_only=True) if r and r[0]}
    extrato.banco = str(controle.get("banco", "") or "")
    extrato.agencia = str(controle.get("agencia", "") or "")
    extrato.conta = str(controle.get("conta", "") or "")
    extrato.periodo = periodo_aaaa_mm(controle.get("periodo", ""))
    extrato.saldo_inicial = valor_br(controle.get("saldo_inicial"))
    extrato.saldo_final = valor_br(controle.get("saldo_final"))  # valor OFICIAL

    # Aba dados: lançamentos (tipo CREDITO/DEBITO + valor sempre positivo)
    linhas = list(aba_dados.iter_rows(values_only=True))
    cabecalho = [sem_acento(c) if c else "" for c in linhas[0]]
    col = {nome: i for i, nome in enumerate(cabecalho)}
    for r in linhas[1:]:
        if not r or r[col["valor"]] is None:
            continue
        valor = valor_br(r[col["valor"]])
        if sem_acento(r[col["tipo"]]).startswith("deb"):
            valor = -valor
        extrato.lancamentos.append(Lancamento(para_data(r[col["data"]]), str(r[col["descricao"]]), valor))
        if "saldo" in col:
            extrato.saldo_ultimo_lancamento = valor_br(r[col["saldo"]])
        extrato.titular = extrato.titular or str(r[col.get("ufv", 0)] or "")
        if "cnpj" in col:
            extrato.cnpj = extrato.cnpj or str(r[col["cnpj"]] or "")


def _layout_extrato(linhas, extrato: Extrato) -> None:
    extrato.layout = "excel_extrato"
    extrato.banco = str(linhas[0][0] or "")  # 1ª célula: nome do banco

    # Cabeçalho "rótulo | valor" nas primeiras linhas
    rotulos = {"titular": "titular", "cnpj": "cnpj", "agencia": "agencia", "conta": "conta"}
    i_cab = None
    for i, r in enumerate(linhas):
        chave = sem_acento(r[0]) if isinstance(r[0], str) else ""
        if chave in rotulos:
            setattr(extrato, rotulos[chave], str(r[1] or ""))
        elif chave == "periodo":
            extrato.periodo = periodo_aaaa_mm(r[1])
        elif chave == "data" and any(sem_acento(c) == "saldo (r$)" for c in r if isinstance(c, str)):
            i_cab = i
            break
    if i_cab is None:
        raise ArquivoNaoReconhecido("cabeçalho da tabela de lançamentos não encontrado")

    cab = [sem_acento(c) if c else "" for c in linhas[i_cab]]
    c_desc = next(i for i, c in enumerate(cab) if c.startswith("descri"))
    c_valor = next(i for i, c in enumerate(cab) if c.startswith("valor"))
    c_saldo = next(i for i, c in enumerate(cab) if c.startswith("saldo"))

    for r in linhas[i_cab + 1:]:
        desc = sem_acento(r[c_desc]) if r[c_desc] else ""
        if desc == "saldo anterior":
            extrato.saldo_inicial = valor_br(r[c_saldo])
        elif desc == "saldo final":
            extrato.saldo_final = valor_br(r[c_saldo])  # valor OFICIAL
        elif r[c_valor] is not None:
            extrato.lancamentos.append(Lancamento(para_data(r[0]), str(r[c_desc]), valor_br(r[c_valor])))
            extrato.saldo_ultimo_lancamento = valor_br(r[c_saldo])
