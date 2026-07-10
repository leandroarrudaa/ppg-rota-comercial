#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01 - Processamento da base Fratelli Vicentim.
Filtra a carteira, normaliza dados e calcula RFM (Recencia/Frequencia/Valor)
com faixas Ouro/Prata/Bronze + flag de risco.

Entrada: dados/origem/clientes_fratelli_completo.xlsx
Saida:   saida/base_mestra.csv  e  saida/base_mestra.xlsx
"""
import os
import unicodedata
import pandas as pd

# Data de referencia para calculo de recencia (hoje)
HOJE = pd.Timestamp("2026-06-25")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEM = os.path.join(BASE_DIR, "dados", "origem", "clientes_fratelli_completo.xlsx")
SAIDA_DIR = os.path.join(BASE_DIR, "saida")


def title_inteligente(s):
    """Title case que preserva siglas curtas (LTDA, ME, S/A) em maiusculo."""
    if not isinstance(s, str) or not s.strip():
        return ""
    palavras = s.strip().split()
    siglas = {"LTDA", "ME", "EPP", "EIRELI", "S/A", "SA", "MEI"}
    conectores = {"de", "da", "do", "das", "dos", "e"}
    out = []
    for i, p in enumerate(palavras):
        up = p.upper()
        if up in siglas:
            out.append(up)
        elif p.lower() in conectores and i > 0:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def limpar_cidade(s):
    if not isinstance(s, str) or not s.strip():
        return ""
    return " ".join(w.capitalize() for w in s.strip().split())


def main():
    # header real esta na linha 3 (index 2): pulamos as 2 primeiras de titulo
    df = pd.read_excel(ORIGEM, sheet_name="CNPJs Clientes", skiprows=2)
    df.columns = [
        "no", "cnpj", "razao_social", "endereco", "bairro", "cep",
        "cidade", "uf", "status", "no_compras", "fat_total",
        "primeira_compra", "ultima_compra",
    ]
    print(f"Linhas brutas: {len(df)}")

    # --- FILTRO DE CARTEIRA: empresas com compras reais ---
    df["razao_norm"] = df["razao_social"].fillna("").str.upper().str.strip()
    genericos = df["razao_norm"].str.contains("CONSUMIDOR") | (df["razao_norm"] == "")
    df["no_compras"] = pd.to_numeric(df["no_compras"], errors="coerce").fillna(0)
    carteira = df[(df["no_compras"] > 0) & (~genericos)].copy()
    print(f"Carteira (empresas com compras): {len(carteira)}")

    # --- NORMALIZACAO ---
    carteira["razao_social"] = carteira["razao_social"].apply(title_inteligente)
    carteira["cidade"] = carteira["cidade"].apply(limpar_cidade)
    carteira["uf"] = carteira["uf"].fillna("").str.upper().str.strip()
    carteira["bairro"] = carteira["bairro"].apply(limpar_cidade)
    carteira["endereco"] = carteira["endereco"].fillna("").str.strip()
    carteira["cep"] = carteira["cep"].fillna("").astype(str).str.strip()
    carteira["fat_total"] = pd.to_numeric(carteira["fat_total"], errors="coerce").fillna(0)
    carteira["primeira_compra"] = pd.to_datetime(carteira["primeira_compra"], errors="coerce")
    carteira["ultima_compra"] = pd.to_datetime(carteira["ultima_compra"], errors="coerce")

    # --- METRICAS DERIVADAS ---
    carteira["recencia_dias"] = (HOJE - carteira["ultima_compra"]).dt.days
    carteira["ticket_medio"] = (carteira["fat_total"] / carteira["no_compras"]).round(2)
    carteira["dias_como_cliente"] = (HOJE - carteira["primeira_compra"]).dt.days

    # --- RFM (quintis 1-5) ---
    # rank antes do qcut para lidar com empates (muitos valores iguais)
    def quintil(serie, invertido=False):
        r = serie.rank(method="first")
        labels = [5, 4, 3, 2, 1] if invertido else [1, 2, 3, 4, 5]
        return pd.qcut(r, 5, labels=labels).astype(int)

    carteira["R"] = quintil(carteira["recencia_dias"], invertido=True)  # menos dias = nota maior
    carteira["F"] = quintil(carteira["no_compras"])
    carteira["M"] = quintil(carteira["fat_total"])
    carteira["rfm_score"] = carteira["R"] + carteira["F"] + carteira["M"]

    # --- CADENCIA: intervalo medio entre compras (dias) ---
    span = (carteira["ultima_compra"] - carteira["primeira_compra"]).dt.days
    carteira["cadencia_dias"] = (span / (carteira["no_compras"] - 1).clip(lower=1)).round(0)
    # quem so comprou 1x nao tem cadencia
    carteira.loc[carteira["no_compras"] <= 1, "cadencia_dias"] = pd.NA

    # --- FAIXAS (modelo de VALOR + LEALDADE) ---
    # Ouro = maiores contas (M alto) que compram RECENTE (R) e com FREQUENCIA (F).
    # Bronze = baixo faturamento. Prata = o meio (inclui contas grandes que esfriaram).
    R, F, M = carteira["R"], carteira["F"], carteira["M"]
    ouro = (M >= 4) & (R >= 4) & (F >= 4)
    bronze = (M <= 2) & ~ouro
    carteira["faixa"] = "Prata"
    carteira.loc[ouro, "faixa"] = "Ouro"
    carteira.loc[bronze, "faixa"] = "Bronze"

    # --- FLAG EM RISCO: conta GRANDE que esfriou (alerta maximo) ---
    carteira["em_risco"] = (M >= 4) & (R <= 2)

    # coluna geo (preenchida no proximo script)
    carteira["lat"] = pd.NA
    carteira["lng"] = pd.NA
    carteira["geo_status"] = pd.NA

    # ordena por valor para inspecao
    carteira = carteira.sort_values("rfm_score", ascending=False)

    cols = [
        "cnpj", "razao_social", "endereco", "bairro", "cep", "cidade", "uf",
        "status", "no_compras", "fat_total", "ticket_medio",
        "primeira_compra", "ultima_compra", "recencia_dias", "dias_como_cliente",
        "cadencia_dias", "R", "F", "M", "rfm_score", "faixa", "em_risco", "lat", "lng", "geo_status",
    ]
    out = carteira[cols].reset_index(drop=True)

    os.makedirs(SAIDA_DIR, exist_ok=True)
    out.to_csv(os.path.join(SAIDA_DIR, "base_mestra.csv"), index=False)
    out.to_excel(os.path.join(SAIDA_DIR, "base_mestra.xlsx"), index=False)

    # --- RELATORIO ---
    print("\n===== DISTRIBUICAO POR FAIXA =====")
    g = out.groupby("faixa").agg(
        clientes=("cnpj", "count"),
        faturamento=("fat_total", "sum"),
    )
    g["%_clientes"] = (100 * g["clientes"] / len(out)).round(1)
    g["%_faturamento"] = (100 * g["faturamento"] / out["fat_total"].sum()).round(1)
    g = g.reindex(["Ouro", "Prata", "Bronze"])
    print(g.to_string())

    print(f"\nClientes EM RISCO (bom historico, esfriaram): {int(out['em_risco'].sum())}")
    print("\n===== DISTRIBUICAO DO RFM SCORE =====")
    print(out["rfm_score"].value_counts().sort_index().to_string())
    print(f"\nSem endereco (geocodificar via CNPJ): {(out['endereco']=='').sum()}")
    print(f"\nArquivos gerados em: {SAIDA_DIR}")


if __name__ == "__main__":
    main()
