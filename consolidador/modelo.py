"""Registro padrão: todo extrator (Excel, PDF ou imagem) devolve um Extrato.

Depois da extração, validação, planilha e log só conhecem este formato,
sem saber de onde o dado veio.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Tolerância para comparar valores em reais (arredondamento de centavos).
TOLERANCIA = 0.01


@dataclass
class Lancamento:
    data: Optional[date]
    descricao: str
    valor: float  # positivo = crédito, negativo = débito


@dataclass
class Extrato:
    # Origem do arquivo
    arquivo: str
    hash: str
    formato: str               # "PDF", "Imagem" ou "Excel" (como o modelo pede)
    layout: str = ""           # qual extrator leu (ex.: "pdf_resumo")

    # Identificação da conta
    banco: str = ""
    titular: str = ""
    cnpj: str = ""
    agencia: str = ""
    conta: str = ""
    periodo: str = ""          # AAAA-MM

    # Saldos e movimentos
    saldo_inicial: Optional[float] = None
    saldo_final: Optional[float] = None
    lancamentos: list[Lancamento] = field(default_factory=list)
    saldo_ultimo_lancamento: Optional[float] = None  # saldo corrido após a última linha (2ª checagem)

    # Resultado da validação
    status: str = ""           # "ok", "revisar" ou "falhou"
    pendencias: list[str] = field(default_factory=list)   # problemas que FORÇAM "revisar"
    observacoes: list[str] = field(default_factory=list)  # informativas (status pode seguir "ok")

    @property
    def saldo_calculado(self) -> Optional[float]:
        """Saldo inicial + soma dos lançamentos (base da validação cruzada)."""
        if self.saldo_inicial is None:
            return None
        return round(self.saldo_inicial + sum(l.valor for l in self.lancamentos), 2)


class ArquivoNaoReconhecido(Exception):
    """O arquivo não corresponde a nenhum layout de extrato conhecido."""
