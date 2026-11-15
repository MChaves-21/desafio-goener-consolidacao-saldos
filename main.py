"""Consolidação de saldos bancários — execução de ponta a ponta.

Uso:
    python main.py                              # competência = mês anterior
    python main.py --competencia 2026-10
    python main.py --entrada pasta --saida pasta --competencia 2026-10

Fluxo: identificar -> extrair -> normalizar -> validar -> planilha -> log.
"""
import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from consolidador import config
from consolidador.extratores.excel import extrair_excel
from consolidador.extratores.imagem import extrair_imagem
from consolidador.extratores.pdf import extrair_pdf
from consolidador.identificar import listar_arquivos
from consolidador.modelo import ArquivoNaoReconhecido, Extrato
from consolidador.planilha import gerar_planilha
from consolidador.validar import brl, contas_repetidas, validar

EXTRATORES = {"PDF": extrair_pdf, "Excel": extrair_excel, "Imagem": extrair_imagem}
RAIZ = Path(__file__).parent


def mes_anterior(hoje: date) -> str:
    ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    return f"{ano}-{mes:02d}"


def configurar_log(pasta: Path, competencia: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"log_{competencia}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    formato = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    for h in (logging.FileHandler(arquivo, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(formato)
        raiz.addHandler(h)
    return arquivo


def main() -> int:
    ap = argparse.ArgumentParser(description="Consolida saldos de extratos bancários.")
    ap.add_argument("--entrada", type=Path, default=RAIZ / "entrada")
    ap.add_argument("--saida", type=Path, default=RAIZ / "saida")
    ap.add_argument("--competencia", default=mes_anterior(date.today()), help="AAAA-MM (padrão: mês anterior)")
    ap.add_argument("--modelo", type=Path, default=RAIZ / "modelo" / "modelo_consolidado_extratos.xlsx")
    args = ap.parse_args()

    config.carregar_env(RAIZ / ".env")
    caminho_log = configurar_log(args.saida, args.competencia)
    log = logging.getLogger("consolidador")
    inicio = time.perf_counter()

    log.info("=== Início | competência %s | entrada: %s", args.competencia, args.entrada)
    log.info("Leitura de imagens: %s", f"Gemini ({config.gemini_modelo()})" if config.gemini_api_key()
             else "OCR local (GEMINI_API_KEY não configurada)")
    if not args.entrada.is_dir():
        log.error("Pasta de entrada não encontrada: %s", args.entrada)
        return 2

    arquivos = listar_arquivos(args.entrada)
    log.info("%d arquivo(s) encontrado(s).", len(arquivos))

    extratos: list[Extrato] = []
    for item in arquivos:
        t0 = time.perf_counter()
        nome = item.caminho.name
        log.info("Lendo %s (%s)...", nome, item.formato)
        try:
            extrator = EXTRATORES.get(item.formato)
            if extrator is None:
                raise ArquivoNaoReconhecido(f"formato não suportado ({item.caminho.suffix})")
            extrato = extrator(item)
            validar(extrato, args.competencia, item.duplicado_de)
        except ArquivoNaoReconhecido as erro:
            extrato = Extrato(arquivo=nome, hash=item.hash, formato=item.formato, status="falhou",
                              observacoes=[f"Não processado: {erro}."])
        except Exception as erro:  # um arquivo com erro inesperado não derruba os demais
            log.exception("Erro inesperado em %s", nome)
            extrato = Extrato(arquivo=nome, hash=item.hash, formato=item.formato, status="falhou",
                              observacoes=[f"Erro inesperado: {erro.__class__.__name__}: {erro}."])
        extratos.append(extrato)

    contas_repetidas(extratos)

    for e in extratos:
        nivel = {"ok": logging.INFO, "revisar": logging.WARNING}.get(e.status, logging.ERROR)
        detalhe = " | ".join(e.pendencias + e.observacoes)
        log.log(nivel, "%-38s %-7s %-6s %-26s saldo %15s %s", e.arquivo, e.formato, e.status.upper(),
                e.layout, brl(e.saldo_final), f"| {detalhe}" if detalhe else "")

    destino = args.saida / f"consolidado_extratos_{args.competencia}.xlsx"
    gerar_planilha(extratos, args.modelo, destino)

    contagem = {s: sum(e.status == s for e in extratos) for s in ("ok", "revisar", "falhou")}
    total_ok = sum(e.saldo_final for e in extratos if e.status == "ok")
    log.info("=== Resumo: %d arquivos | ok %d | revisar %d | falhou %d",
             len(extratos), contagem["ok"], contagem["revisar"], contagem["falhou"])
    log.info("Soma dos saldos com status ok: %s (arquivos em revisar ficam fora até a conferência)", brl(total_ok))
    log.info("Planilha: %s", destino)
    log.info("Log: %s", caminho_log)
    log.info("=== Fim em %.1f s", time.perf_counter() - inicio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
