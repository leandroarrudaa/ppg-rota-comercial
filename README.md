# PPG · Plataforma de Representação Comercial

Ferramenta de inteligência comercial para o time de representação da **PPG — Parafusos e Ferramentas**.
Transforma a carteira de clientes (matriz RFM) em decisão diária: onde estão os clientes,
quem são os melhores, e qual a rota/contato do dia.

## O que a plataforma faz

- **Mapa da carteira** — todos os clientes plotados, coloridos por faixa RFM (Ouro / Prata / Bronze),
  com filtros por faixa, risco, cidade e busca.
- **Plano da Semana** — 5 dias de rota presencial, cada um geograficamente compacto, equilibrando
  valor do cliente e quilometragem. **Não repete quem foi visitado há pouco**: respeita a data de
  retorno que o vendedor combinou ao fechar a última visita.
- **Rota do Dia** — seleção dos clientes da região, rota de estrada real (OSRM), e o fluxo de campo:
  abrir visita, finalizar, preencher o relatório (bloqueante) e registrar promessas.
- **Relatórios** — o que o time fez, por período e por vendedor.
- **Gestão** (admin) — lista completa da carteira, vínculo de CNPJs da mesma empresa, inativação,
  importação de dados e ajustes das regras do negócio.

## Atualização da carteira

Duas origens, com precedência clara: **o banco mestre sobrepõe o relatório diário**.

| Origem | Quando | Como |
|---|---|---|
| Pacote do banco mestre | 1× por mês | Gere o pacote no PC do escritório e envie em **Gestão → Importar** |
| Relatório de vendas do ERP | Todo dia | Exporte o CSV e envie em **Gestão → Importar** |

O **banco mestre** (gerado dos XMLs de NFe) é a fonte mais completa: tem o CNPJ real e o histórico
inteiro. Como o arquivo tem ~139 MB, um passo local extrai só o que interessa (~1 MB). No Windows,
duplo clique em **`Preparar Pacote do Banco Mestre.bat`** — ele gera o arquivo e abre a pasta nele.
Por linha de comando:

```bash
python backend/scripts/preparar_pacote.py
```

Dentro do Claude Code, a skill `pacote-banco-mestre` faz o mesmo e ainda confere se os números do
pacote batem com o esperado antes de mandar subir.

O **relatório do ERP** ("Pedidos com Produtos — Detalhado", em CSV) não traz CNPJ nenhum: o cliente
aparece como `729 - RAZÃO SOCIAL`, um código interno. Por isso o pacote do banco mestre também
carrega o de-para `código → CNPJ` — é ele que torna o arquivo diário aproveitável. A maior parte do
relatório é venda de balcão e pessoa física, que nunca fez parte da carteira de visitas e fica de fora.

Toda importação mostra **uma prévia antes de gravar** e enviar o mesmo arquivo duas vezes não conta
em dobro (cada pedido é registrado pelo número).

Alternativa por linha de comando, para atualizar direto do banco mestre:

```bash
python backend/scripts/recarregar_do_banco_mestre.py --simular   # só mostra o que mudaria
python backend/scripts/recarregar_do_banco_mestre.py --com-historico
```

No Windows há o atalho de um clique **`Atualizar Carteira.bat`**, que roda a simulação, mostra os
números e só grava depois de confirmação. Ele avisa em qual banco vai gravar — local ou produção,
conforme o `backend/.env`.

## Stack

- **Frontend**: React + Vite + Leaflet (mapa OpenStreetMap/CARTO)
- **Backend**: FastAPI + SQLAlchemy — SQLite no desenvolvimento, PostgreSQL (Supabase) em produção
- **Hospedagem**: Render (API + site estático)

## Como rodar localmente

Pré-requisitos: **Node.js 18+** e **Python 3.11+**.

```bash
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --port 8090
```

```bash
cd app && npm install && npm run dev
```

No Windows, **`PPG Rota Comercial.bat`** sobe os dois e abre o navegador.

## Testes

```bash
cd backend && pytest
```

## Estrutura

```
app/                      # aplicação React
  src/views/              # Mapa, Plano da Semana, Rota do Dia, Relatórios, Gestão
  src/lib/                # roteirização, recomendação, PDF, formatação
backend/
  app/models.py           # tabelas
  app/routers/            # rotas da API
  app/services/           # regras de negócio
  app/services/fontes/    # leitura do banco mestre, do relatório do ERP e do pacote
  scripts/                # carga e atualização por linha de comando
  tests/                  # pytest
scripts/                  # pipeline original da planilha (histórico)
```

## ⚠️ Dados sensíveis

A base contém **dados reais de clientes** (empresas, CNPJs, telefones, faturamento).
Mantenha este repositório **privado**. Cópias do banco (`*.db`) e pacotes de atualização
(`*.ppg`) estão no `.gitignore` e **não podem** ser commitados.
