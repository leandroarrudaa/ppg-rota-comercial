# PPG · Plataforma de Representação Comercial

Ferramenta de inteligência comercial para o time de representação da **PPG — Parafusos e Ferramentas**.
Transforma a carteira de clientes (matriz RFM) em decisão diária: onde estão os clientes,
quem são os melhores, e qual a rota/contato do dia.

## O que a plataforma faz

- **Mapa da carteira** — todos os clientes plotados, coloridos por faixa RFM (Ouro / Prata / Bronze),
  com filtros por faixa, risco, cidade e busca. Clique no pino abre nome, endereço e telefone.
- **Plano de Visitas** — clientes ativos, agrupados por proximidade e valor, com rota de estrada
  real (OSRM), ordem de visita otimizada, km/tempo e recomendação de ação por cliente.
- **Plano de Contato** — clientes adormecidos numa fila de ligações priorizada, com telefone e
  script de reativação (objetivo: reabrir relacionamento e agendar visita).
- **Relatórios em PDF** — rota do dia e lista de contatos, com a identidade visual da PPG.

## Stack

React + Vite + Leaflet (mapa OpenStreetMap/CARTO). Sem back-end: os dados ficam em
`app/public/clientes.json`, gerados a partir da planilha pelos scripts em `scripts/`.

## Como rodar localmente

Pré-requisito: **Node.js 18+** (recomendado 20 LTS) — https://nodejs.org

```bash
cd app
npm install
npm run dev
```

Abra o link que aparecer no terminal (ex.: http://localhost:5173).

## Estrutura

```
app/            # aplicação React (o que roda no navegador)
  src/views/    # Mapa, Plano de Visitas, Plano de Contato
  src/lib/      # RFM/rota, recomendação, PDF, formatação
  public/clientes.json   # base já processada que a plataforma consome
scripts/        # pipeline de dados (Python): limpeza, RFM, geocodificação, enriquecimento
dados/          # planilha de origem
saida/          # base mestra + caches de geocodificação/CNPJ
```

## Pipeline de dados (opcional, só se for reprocessar a base)

Requer Python 3 com `pandas`, `openpyxl`, `requests`.

```bash
python3 scripts/01_processar_base.py   # limpeza + RFM + faixas
python3 scripts/02_geocodificar.py     # endereços -> lat/lng (usa cache)
python3 scripts/04_enriquecer_cnpj.py  # porte/telefone via BrasilAPI (usa cache)
python3 scripts/03_gerar_dados.py       # gera app/public/clientes.json
```

## ⚠️ Dados sensíveis

A base contém **dados reais de clientes** (empresas, CNPJs, telefones, faturamento).
Mantenha este repositório **privado**. Não publique nem compartilhe fora dos colaboradores autorizados.
