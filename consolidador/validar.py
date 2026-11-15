"""Etapa 4: validar cada extrato e definir o status.

Status:
  falhou  -> não foi possível extrair (não é extrato, ilegível, layout desconhecido)
  revisar -> extraiu, mas há pendência (saldo não fecha, mês errado, duplicado...)
  ok      -> extraiu e todas as checagens passaram (pode ter observações informativas)

O robô NUNCA altera o saldo final declarado pelo banco: o recálculo só serve
para conferir e para apontar a diferença a quem vai revisar.
"""
from collections import Counter

from .modelo import TOLERANCIA, Extrato


def brl(v) -> str:
    """1234.5 -> 'R$ 1.234,50' (para mensagens)."""
    if v is None:
        return "—"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def validar(extrato: Extrato, competencia: str, duplicado_de: str = "") -> None:
    p, o = extrato.pendencias, extrato.observacoes

    # 1. Campos essenciais
    if extrato.saldo_final is None:
        extrato.status = "falhou"
        o.insert(0, "Saldo final não encontrado no arquivo.")
        return
    for campo in ("banco", "conta", "periodo"):
        if not getattr(extrato, campo):
            p.append(f"Campo '{campo}' não identificado.")

    # 2. Arquivo duplicado (mesmo conteúdo de outro arquivo da pasta)
    if duplicado_de:
        p.append(f"Arquivo duplicado de '{duplicado_de}' (conteúdo idêntico); não somar duas vezes.")

    # 3. Competência
    if extrato.periodo and extrato.periodo != competencia:
        p.append(f"Período {extrato.periodo} diferente da competência {competencia}.")

    # 4. Validação cruzada 1: saldo inicial + lançamentos = saldo final declarado
    calc = extrato.saldo_calculado
    if calc is None:
        p.append("Sem saldo inicial: não foi possível conferir o saldo final.")
    elif abs(calc - extrato.saldo_final) > TOLERANCIA:
        p.append(f"Saldo final declarado ({brl(extrato.saldo_final)}) difere do calculado "
                 f"pelo saldo inicial + lançamentos ({brl(calc)}); diferença {brl(extrato.saldo_final - calc)}.")

    # 5. Validação cruzada 2: saldo após o último lançamento = saldo final declarado
    ult = extrato.saldo_ultimo_lancamento
    if ult is not None and abs(ult - extrato.saldo_final) > TOLERANCIA:
        if calc is not None and abs(ult - calc) <= TOLERANCIA:
            p.append(f"O saldo após o último lançamento ({brl(ult)}) confirma o valor calculado; "
                     "a divergência está na linha de saldo final do extrato.")
        else:
            p.append(f"Saldo após o último lançamento ({brl(ult)}) difere do saldo final declarado.")

    # 6. Observações informativas (não mudam o status)
    _lancamentos_repetidos(extrato)
    _saldo_negativo(extrato)

    extrato.status = "revisar" if p else "ok"


def _lancamentos_repetidos(extrato: Extrato) -> None:
    chaves = Counter((l.data, l.descricao.strip().upper(), l.valor) for l in extrato.lancamentos)
    for (data, desc, valor), n in chaves.items():
        if n > 1:
            dia = data.strftime("%d/%m") if data else "?"
            extrato.observacoes.append(
                f"Lançamento repetido {n}x em {dia}: {desc} {brl(valor)} (conta fecha; confirmar se não é duplicidade do banco).")


def _saldo_negativo(extrato: Extrato) -> None:
    if extrato.saldo_final < 0:
        extrato.observacoes.append("Conta no vermelho no fim do período.")
    if extrato.saldo_inicial is None:
        return
    saldo, minimo, dia_min = extrato.saldo_inicial, extrato.saldo_inicial, None
    for l in extrato.lancamentos:
        saldo += l.valor
        if saldo < minimo:
            minimo, dia_min = saldo, l.data
    if minimo < 0 and extrato.saldo_final >= 0:
        dia = dia_min.strftime("%d/%m") if dia_min else "?"
        extrato.observacoes.append(f"Saldo ficou negativo durante o mês (mínimo {brl(round(minimo, 2))} em {dia}).")


def contas_repetidas(extratos: list[Extrato]) -> None:
    """Mesma agência/conta em arquivos DIFERENTES (não idênticos) -> revisar ambos."""
    por_conta: dict[tuple, list[Extrato]] = {}
    for e in extratos:
        if e.conta and e.status != "falhou" and not any("duplicado de" in x for x in e.pendencias):
            por_conta.setdefault((e.banco.lower(), e.agencia, e.conta), []).append(e)
    for (_, ag, cc), grupo in por_conta.items():
        if len(grupo) > 1:
            nomes = ", ".join(e.arquivo for e in grupo)
            for e in grupo:
                e.pendencias.append(f"Conta {ag}/{cc} aparece em mais de um arquivo: {nomes}.")
                e.status = "revisar"
