---
name: pacote-banco-mestre
description: Gera o pacote mensal de atualização da carteira a partir do banco_mestre.db do PPG Rota Comercial. Use quando o Antonio disser que regerou/atualizou o banco mestre, ou pedir "prepara o pacote", "gera o arquivo do banco mestre", "quero atualizar a carteira pelo banco mestre", ou perguntar como fazer a atualização mensal. NÃO use para o CSV diário de vendas do ERP — esse vai direto na tela, sem passar por aqui.
---

# Pacote mensal do banco mestre

O `banco_mestre.db` tem ~139 MB e mora na máquina do escritório. O app não recebe
esse arquivo: um script local extrai só o que interessa e gera um pacote de
~1 MB, que o Antonio sobe pela tela. Assim ninguém lida com senha de banco e
nada pesado atravessa a internet.

## O que fazer

Rode o gerador:

```bash
./backend/.venv/Scripts/python.exe backend/scripts/preparar_pacote.py
```

Caminho diferente do padrão (o padrão é `../output/banco_mestre.db`):

```bash
./backend/.venv/Scripts/python.exe backend/scripts/preparar_pacote.py "D:/caminho/banco_mestre.db"
```

O arquivo sai em `pacote-atualizacao.ppg`, na raiz do projeto.

## Confira antes de entregar

O script imprime quatro números. Compare com a última vez — se algum despencar,
**diga isso ao Antonio antes de mandar ele subir**, porque o pacote alimenta a
carteira inteira:

| Número | Referência (agosto/2026) | O que significa se cair muito |
|---|---|---|
| empresas com compra | ~1.474 | banco mestre incompleto ou meio-regerado |
| linhas de histórico | ~36.000 | itens de nota faltando |
| códigos no de-para | ~1.563 | o cadastro de clientes não veio junto — o CSV diário para de reconhecer cliente |
| venda mais recente | deve avançar todo mês | o banco mestre não foi regerado de verdade |

A **venda mais recente** é a checagem mais reveladora: se continuar na mesma data
do mês passado, o banco mestre não mudou e não adianta subir.

## Depois de gerar

Diga ao Antonio, nesta ordem:

1. Abrir o app como administrador
2. **Gestão → Importar → Pacote do banco mestre**
3. Enviar o `pacote-atualizacao.ppg`
4. Ler a prévia e confirmar

Nada é gravado até ele confirmar na tela.

Na prévia, os dois números que dizem se está tudo certo:

- **Clientes atualizados** — tem que ficar perto do total da carteira
- **Recência corrigida** — quantos estavam com data de compra atrasada

Se aparecer muita coisa em "Empresas fora da carteira", peça para ele **não
confirmar** e investigue: são CNPJs que compram e não têm cadastro no app.

## Coisas que não são para fazer aqui

- **Não** mande o `banco_mestre.db` inteiro para o app — é o motivo de o pacote existir.
- **Não** rode `recarregar_do_banco_mestre.py` no lugar deste script sem avisar: aquele
  grava direto no banco (produção, se houver `backend/.env`), pulando a prévia da tela.
- **Não** commite o `.ppg`: tem CNPJ, razão social e faturamento de cliente real.
  O `.gitignore` já bloqueia — não force.

## Contexto que evita erro

O relatório diário do ERP **não tem CNPJ**: o cliente vem como `729 - RAZÃO SOCIAL`,
um código interno. O de-para `código → CNPJ` viaja dentro deste pacote e é ele que
faz a importação diária funcionar. Por isso: **se o Antonio disser que o CSV diário
parou de reconhecer clientes, o pacote está velho** — cliente cadastrado no ERP
depois do último pacote não tem de-para ainda. A solução é regerar o banco mestre
e refazer o pacote.
