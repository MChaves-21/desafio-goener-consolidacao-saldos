# Consolidação de saldos bancários — Documentação

Murilo Chaves · 15/11/2026

## Fluxo

Um comando (`python main.py --competencia 2026-10`) lê a pasta de entrada e gera a planilha consolidada e o log, sem etapa manual. Na pasta de outubro (17 arquivos), a execução levou cerca de 77 segundos, quase todo esse tempo nas 5 imagens lidas pelo Gemini, e terminou com 13 ok, 3 revisar e 1 falhou.

1. **Identificar**: formato pela extensão, impressão digital (hash SHA-256) do conteúdo e arquivos duplicados.
2. **Extrair**: um leitor por layout, reconhecido pelo conteúdo e não pelo nome. São 2 layouts de Excel, 2 de PDF e 1 de imagem. As imagens são lidas pela API do Gemini, com OCR local (Tesseract) como reserva.
3. **Normalizar**: todo leitor devolve o mesmo registro (banco, conta, período, saldos e lançamentos). Para incluir um banco novo, basta criar um leitor.
4. **Validar**: o saldo inicial somado aos lançamentos precisa dar o saldo final, o saldo da última linha precisa bater, o período precisa ser o da competência e o arquivo não pode ser duplicado.
5. **Consolidar**: a planilha sai no modelo da Goener, uma linha por arquivo, com Status e Observação. O log registra cada arquivo, o tempo de execução e o total dos saldos com status ok.

## Premissas

- **O saldo oficial é o declarado pelo banco.** O recálculo só confere e nunca corrige. Se não bater, o status vai para *revisar* com a diferença escrita.
- **Status:** *falhou* quando não foi possível extrair (não é extrato ou o layout é desconhecido); *revisar* quando há pendência (saldo não fecha, mês errado, duplicado, conta repetida); *ok* quando tudo confere. Lançamento repetido e saldo negativo no meio do mês viram observação, sem mudar o status.
- **A competência é um parâmetro**, não é deduzida dos arquivos. O padrão é o mês anterior, porque o processo roda no início de cada mês.
- **A IA só transcreve.** O Gemini devolve JSON com esquema fixo e as contas são feitas em Python, então a IA não valida o próprio trabalho. Nas imagens há dupla leitura (IA e OCR), e se as duas diferirem o status vai para *revisar*.
- **A chave fica no `.env`**, fora do código e do Git. A camada gratuita do Gemini pode usar os dados para treinar o modelo, o que não é problema com extratos fictícios. Com dados reais, a opção é o plano pago ou só o OCR local.
- **Um arquivo com erro não interrompe os demais**, e o total do log soma apenas os saldos com status *ok*.

## Estimativa de ganho

A automação economiza de **55 a 120 minutos por mês** (de 1 a 2 horas, ou 11 a 24 horas por ano) com o volume atual de 17 arquivos.

A premissa é que cada extrato leva de 5 a 10 minutos no processo manual: abrir o arquivo, achar o saldo final, digitar na planilha e conferir. O tempo depende do tamanho e do formato do arquivo e da agilidade de quem faz: uma planilha curta fica perto de 5 minutos, e um PDF ou print longo, que exige leitura e digitação cuidadosas, perto de 10. Depois da automação, só as exceções continuam manuais (4 arquivos em *revisar* ou *falhou*), mais 10 minutos para conferir a planilha e o log.

|  | Conservador (5 min/arquivo) | Base (10 min/arquivo) |
| --- | --- | --- |
| Manual hoje: 17 arquivos × tempo | 85 min | 170 min |
| Automatizado: 4 exceções × tempo + 10 min de conferência | 30 min | 50 min |
| **Ganho por mês** | **55 min** | **120 min** |

O ganho cresce com o número de contas, porque cada conta nova soma de 5 a 10 minutos ao processo manual e quase nada ao automatizado. O tempo de execução (cerca de 77 segundos, sem ninguém acompanhando) não entra na conta. Fica de fora também o ganho em qualidade: nesta rodada, o robô apontou um saldo divergente em R$ 1.080,00, um extrato do mês errado e um arquivo duplicado, erros fáceis de passar despercebidos na digitação manual.

## Próximos passos

1. **Cadastro de contas esperadas** (prioridade alta). Hoje o robô não tem como saber se o extrato de uma conta deixou de chegar. Com uma lista de contas ativas, ele marca *falhou* para cada extrato ausente e confere se o saldo inicial do mês é igual ao saldo final consolidado no mês anterior.
2. **Execução agendada e entrada automática** (prioridade média). A ideia é rodar todo dia 1 pelo Agendador de Tarefas ou pelo n8n, buscar os extratos no e-mail ou numa pasta compartilhada e enviar ao financeiro um resumo com os itens em *revisar*.
3. **Testes de regressão por layout** (prioridade média). Cada layout teria um extrato de referência com o resultado esperado. Quando um banco mudar o formato do arquivo, o teste falha antes da rodada do mês.
