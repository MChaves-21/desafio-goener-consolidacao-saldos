"""Etapa 5: gerar a planilha consolidada a partir do modelo da Goener."""
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

from .modelo import Extrato

CORES = {"ok": "C6EFCE", "revisar": "FFEB9C", "falhou": "FFC7CE"}  # verde, amarelo, vermelho


def gerar_planilha(extratos: list[Extrato], modelo: Path, destino: Path) -> None:
    wb = openpyxl.load_workbook(modelo)
    aba = wb["Consolidado"]

    # Remove a linha de exemplo (e qualquer conteúdo abaixo do cabeçalho)
    if aba.max_row > 1:
        aba.delete_rows(2, aba.max_row - 1)

    for e in sorted(extratos, key=lambda x: x.arquivo.lower()):
        observacao = " | ".join(e.pendencias + e.observacoes)
        aba.append([e.arquivo, e.banco, e.conta, e.periodo, e.saldo_final,
                    e.formato, e.status, observacao])
        linha = aba.max_row
        aba.cell(linha, 5).number_format = "#,##0.00"
        aba.cell(linha, 7).fill = PatternFill("solid", fgColor=CORES.get(e.status, "FFFFFF"))

    larguras = {"A": 38, "B": 17, "C": 12, "D": 10, "E": 15, "F": 10, "G": 9, "H": 110}
    for col, largura in larguras.items():
        aba.column_dimensions[col].width = largura
    aba.freeze_panes = "A2"
    aba.auto_filter.ref = aba.dimensions

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
