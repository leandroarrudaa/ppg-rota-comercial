#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02 - Enriquece os clientes sem endereco (via BrasilAPI/CNPJ) e geocodifica
toda a carteira (endereco -> lat/lng) via Nominatim/OpenStreetMap.

- Deduplica por endereco para reduzir requisicoes.
- Cache incremental em saida/geo_cache.json (permite retomar).
- Estrategia: endereco completo -> CEP -> cidade (aproximado).
- Respeita 1 req/s da politica do Nominatim.
"""
import os
import re
import json
import time
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(BASE_DIR, "saida")
CSV = os.path.join(SAIDA, "base_mestra.csv")
CACHE = os.path.join(SAIDA, "geo_cache.json")
LOG = os.path.join(SAIDA, "geo_log.txt")

UA = {"User-Agent": "fratelli-representacao-geo/1.0 (rudderassessoria@gmail.com)"}


def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(c):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


def so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def enriquecer_cnpj(cnpj):
    """Busca endereco na BrasilAPI a partir do CNPJ."""
    d = so_digitos(cnpj)
    if len(d) != 14:
        return None
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{d}", headers=UA, timeout=20)
        if r.status_code != 200:
            return None
        j = r.json()
        log_num = j.get("numero", "")
        endereco = f"{j.get('logradouro','').strip()}, {log_num}".strip(", ")
        return {
            "endereco": endereco,
            "bairro": (j.get("bairro") or "").title(),
            "cep": so_digitos(j.get("cep")),
            "cidade": (j.get("municipio") or "").title(),
            "uf": (j.get("uf") or "").upper(),
        }
    except Exception as e:
        log(f"  BrasilAPI erro {d}: {e}")
        return None


def nominatim(params):
    params = {**params, "format": "json", "limit": 1, "countrycodes": "br"}
    r = requests.get("https://nominatim.openstreetmap.org/search", params=params,
                     headers=UA, timeout=25)
    time.sleep(1.1)  # politica de uso: 1 req/s
    if r.status_code == 200 and r.json():
        j = r.json()[0]
        return float(j["lat"]), float(j["lon"])
    return None


def geocodificar(endereco, bairro, cep, cidade, uf):
    """Tenta endereco completo -> CEP -> cidade. Retorna (lat, lng, status)."""
    cep_fmt = so_digitos(cep)
    cep_fmt = f"{cep_fmt[:5]}-{cep_fmt[5:]}" if len(cep_fmt) == 8 else cep_fmt
    # 1) endereco estruturado
    if endereco and cidade:
        try:
            res = nominatim({"street": endereco, "city": cidade, "state": uf, "country": "Brazil"})
            if res:
                return res[0], res[1], "preciso"
        except Exception:
            pass
    # 2) por CEP
    if len(so_digitos(cep)) == 8:
        try:
            res = nominatim({"postalcode": cep_fmt, "country": "Brazil"})
            if res:
                return res[0], res[1], "cep"
        except Exception:
            pass
    # 3) cidade (aproximado)
    if cidade:
        try:
            res = nominatim({"city": cidade, "state": uf, "country": "Brazil"})
            if res:
                return res[0], res[1], "cidade"
        except Exception:
            pass
    return None, None, "falhou"


def main():
    df = pd.read_csv(CSV, dtype={"cep": str})
    df["cep"] = df["cep"].fillna("").astype(str)
    open(LOG, "w").close()
    log(f"Iniciando. {len(df)} clientes.")

    # --- ENRIQUECER SEM ENDERECO ---
    sem = df[df["endereco"].fillna("").str.strip() == ""]
    log(f"Sem endereco para enriquecer via CNPJ: {len(sem)}")
    for idx in sem.index:
        info = enriquecer_cnpj(df.at[idx, "cnpj"])
        time.sleep(0.5)
        if info and info["endereco"]:
            for k, v in info.items():
                df.at[idx, k] = v
            log(f"  enriquecido: {df.at[idx,'cnpj']} -> {info['cidade']}/{info['uf']}")

    # --- GEOCODIFICAR (dedupe por endereco) ---
    cache = load_cache()
    df["geo_key"] = (
        df["endereco"].fillna("").str.upper().str.strip() + "|" +
        df["cidade"].fillna("").str.upper().str.strip() + "|" +
        df["uf"].fillna("").str.upper().str.strip()
    )
    chaves = df["geo_key"].unique().tolist()
    novos = [k for k in chaves if k not in cache]
    log(f"Enderecos unicos: {len(chaves)} | ja em cache: {len(chaves)-len(novos)} | a geocodificar: {len(novos)}")
    log(f"Tempo estimado: ~{len(novos)*1.2/60:.0f} min")

    for i, key in enumerate(novos, 1):
        linha = df[df["geo_key"] == key].iloc[0]
        lat, lng, status = geocodificar(linha["endereco"], linha["bairro"],
                                        linha["cep"], linha["cidade"], linha["uf"])
        cache[key] = {"lat": lat, "lng": lng, "status": status}
        if i % 25 == 0:
            save_cache(cache)
            log(f"  progresso {i}/{len(novos)} ({100*i/len(novos):.0f}%)")
    save_cache(cache)

    # aplica cache
    df["lat"] = df["geo_key"].map(lambda k: cache.get(k, {}).get("lat"))
    df["lng"] = df["geo_key"].map(lambda k: cache.get(k, {}).get("lng"))
    df["geo_status"] = df["geo_key"].map(lambda k: cache.get(k, {}).get("status"))
    df = df.drop(columns=["geo_key"])

    df.to_csv(CSV, index=False)
    df.to_excel(os.path.join(SAIDA, "base_mestra.xlsx"), index=False)

    log("\n===== RESULTADO GEOCODIFICACAO =====")
    log(df["geo_status"].value_counts(dropna=False).to_string())
    ok = df["lat"].notna().sum()
    log(f"\nCom coordenadas: {ok}/{len(df)} ({100*ok/len(df):.1f}%)")
    log("CONCLUIDO.")


if __name__ == "__main__":
    main()
