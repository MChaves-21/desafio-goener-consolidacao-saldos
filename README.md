# Consolidação de saldos bancários

Case técnico do processo seletivo da Goener (Analista de RPA).

Lê os extratos da pasta `entrada/` (PDF, Excel e imagens), extrai o saldo final de cada conta,
valida e gera a planilha consolidada e o log de execução em `saida/`. Tudo com um comando, sem
etapa manual.

## Entregáveis

| Item | Onde |
|---|---|
| Automação | este repositório (`main.py` + pacote `consolidador/`) |
| Planilha consolidada gerada pela automação | [`saida/consolidado_extratos_2026-10.xlsx`](saida/consolidado_extratos_2026-10.xlsx) |
| Log de execução | [`saida/log_2026-10_20261115_203120.txt`](saida/log_2026-10_20261115_203120.txt) |
| Documentação (1 página) | [`DOCUMENTACAO.md`](DOCUMENTACAO.md) · [PDF](docs/Documentacao_Consolidacao_Saldos_Goener.pdf) |

Resultado da rodada de outubro/2026 (17 arquivos, imagens lidas pelo Gemini 2.5 Flash, 77 s):
**13 ok, 3 revisar, 1 falhou**.

| Status | Arquivo | Motivo |
|---|---|---|
| revisar | `extrato_sol_do_sertao_I_out2026.pdf` | Saldo final declarado R$ 1.080,00 acima do calculado; o saldo da última linha confirma o cálculo |
| revisar | `print_serra_dourada_II.png` | Extrato de setembro (competência é outubro) |
| revisar | `EXT_102026_LagoaAzul (1).pdf` | Cópia idêntica de `EXT_102026_LagoaAzul.pdf` |
| falhou | `aviso_agencia_horizonte.pdf` | Comunicado da agência, não é extrato |

## Como rodar

```powershell
python -m venv .venv                                   # ambiente isolado do projeto
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env                                 # depois cole a GEMINI_API_KEY no .env
.\.venv\Scripts\python.exe main.py --competencia 2026-10
```

(Linux/macOS: `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `.venv/bin/python main.py`.)

Sem `--competencia`, o robô usa o mês anterior (o processo roda no início de cada mês).

**Opcional:** instale o [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki). Ele é usado
para a dupla leitura das imagens e como reserva se o Gemini estiver indisponível. Sem chave e sem
Tesseract, as imagens saem como `falhou` e os outros formatos seguem normalmente.

## Fluxo

```
entrada/ → identificar (formato, hash, duplicados)
         → extrair (1 extrator por layout; imagens via API do Gemini)
         → normalizar (registro padrão: modelo.py)
         → validar (saldo inicial + lançamentos = saldo final; saldo da última linha; competência)
         → planilha (modelo da Goener) + log
```

| Arquivo | Papel |
|---|---|
| `main.py` | Orquestra o fluxo de ponta a ponta |
| `consolidador/identificar.py` | Lista a pasta, formato, hash SHA-256 e duplicados |
| `consolidador/extratores/` | Um leitor por formato (`excel.py`, `pdf.py`, `imagem.py`) |
| `consolidador/modelo.py` | Registro padrão que todo extrator devolve |
| `consolidador/validar.py` | Regras de status (ok / revisar / falhou) |
| `consolidador/planilha.py` | Gera o `.xlsx` a partir do modelo |

## Regras de status

- **falhou**: não foi possível extrair (não é extrato, layout desconhecido, ilegível).
- **revisar**: extraiu, mas há pendência (saldo não fecha, período diferente da competência,
  arquivo duplicado, conta repetida, dupla leitura divergente).
- **ok**: todas as checagens passaram. Observações informativas (lançamento repetido, saldo
  negativo no mês) não mudam o status.

O robô **nunca altera o saldo declarado pelo banco**: o recálculo só serve para conferir.

## Novo banco ou layout

Basta criar um extrator que devolva um `Extrato` (ver `modelo.py`) e registrá-lo. Validação,
planilha e log não mudam.
