#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importa clientes "orfaos": CNPJs que tem historico de venda (banco mestre
v2.1, apos o cruzamento com o cadastro do ERP) mas ainda nao estao na
carteira do app (base_mestra.csv e mais antigo que esse cruzamento).

So processa CNPJs que tem endereco completo em cadastro_clientes (o
cruzamento nao cobre todo mundo — os sem endereco ficam de fora, listados
separadamente pelo script de auditoria).

Uso:  python backend/scripts/importar_clientes_novos_cruzados.py
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date

import requests

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.database import Base, SessaoLocal, engine  # noqa: E402
from app.models import Cliente, OrigemCliente, StatusCliente  # noqa: E402
from app.services.cnpj import normalizar_cnpj  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(BACKEND_DIR))
BANCO_MESTRE = os.path.join(RAIZ, "output", "banco_mestre.db")
GEO_CACHE = os.path.join(RAIZ, "ppg-rota-comercial", "saida", "geo_cache.json")
HOJE = date(2026, 6, 25)  # mesma data de referencia do base_mestra.csv original — mantem R consistente
NOMES_GENERICOS = {"CONSUMIDOR", "CONSUMIDOR_NAO_IDENTIFICADO", "A VISTA", "CLIENTE A VISTA", "CLIENTE"}

UA = {"User-Agent": "fratelli-representacao-geo/1.0 (rudderassessoria@gmail.com)"}


def so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def title_inteligente(s):
    if not s:
        return ""
    siglas = {"LTDA", "ME", "EPP", "EIRELI", "S/A", "SA", "MEI"}
    conectores = {"de", "da", "do", "das", "dos", "e"}
    out = []
    for i, p in enumerate(s.strip().split()):
        up = p.upper()
        if up in siglas:
            out.append(up)
        elif p.lower() in conectores and i > 0:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def load_geo_cache():
    if os.path.exists(GEO_CACHE):
        with open(GEO_CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_geo_cache(c):
    with open(GEO_CACHE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


def geocodificar(endereco, cep, cidade, uf):
    cep_fmt = so_digitos(cep)
    cep_fmt = f"{cep_fmt[:5]}-{cep_fmt[5:]}" if len(cep_fmt) == 8 else cep_fmt
    for params in (
        {"street": endereco, "city": cidade, "state": uf, "country": "Brazil"} if endereco and cidade else None,
        {"postalcode": cep_fmt, "country": "Brazil"} if len(so_digitos(cep)) == 8 else None,
        {"city": cidade, "state": uf, "country": "Brazil"} if cidade else None,
    ):
        if not params:
            continue
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={**params, "format": "json", "limit": 1, "countrycodes": "br"},
                headers=UA, timeout=25,
            )
            time.sleep(1.1)
            if r.status_code == 200 and r.json():
                j = r.json()[0]
                status = "preciso" if "street" in params else ("cep" if "postalcode" in params else "cidade")
                return float(j["lat"]), float(j["lon"]), status
        except Exception:
            pass
    return None, None, "falhou"


def quintil_manual(valor, referencias, invertido=False):
    """Classifica um valor em 1-5 usando os limiares (quintis) ja observados
    na carteira existente — mantem a mesma régua sem recalcular tudo."""
    referencias = sorted(referencias)
    n = len(referencias)
    posicao = sum(1 for r in referencias if r <= valor) / n
    nivel = min(5, max(1, int(posicao * 5) + 1))
    return (6 - nivel) if invertido else nivel


def main():
    db = SessaoLocal()
    Base.metadata.create_all(bind=engine)

    existentes = {normalizar_cnpj(c.cnpj) for c in db.query(Cliente.cnpj).filter(Cliente.cnpj.isnot(None)).all()}
    print(f"Clientes ja na carteira: {len(existentes)}")

    conn = sqlite3.connect(f"file:{BANCO_MESTRE}?mode=ro", uri=True)
    historico_cnpjs = {
        normalizar_cnpj(row[0])
        for row in conn.execute(
            "SELECT DISTINCT cpf_cnpj_cliente FROM notas WHERE tipo_operacao='saida' AND LENGTH(cpf_cnpj_cliente)=14"
        )
    }
    orfaos = historico_cnpjs - existentes
    print(f"CNPJs com venda mas fora da carteira: {len(orfaos)}")

    cadastro = {}
    for row in conn.execute(
        "SELECT cpf_cnpj_digits, nome, cep, endereco, numero, bairro, cidade, uf FROM cadastro_clientes "
        "WHERE LENGTH(cpf_cnpj_digits)=14 AND endereco IS NOT NULL AND endereco != ''"
    ):
        cadastro[row[0]] = row

    alvo = [c for c in orfaos if c in cadastro]
    print(f"Desses, com endereco disponivel pra importar: {len(alvo)}")

    # limiares de R/F/M da carteira atual, pra classificar os novos na mesma régua
    ref_recencia = [c.recencia_dias for c in db.query(Cliente.recencia_dias).filter(Cliente.recencia_dias.isnot(None)).all()]
    ref_frequencia = [c.no_compras for c in db.query(Cliente.no_compras).filter(Cliente.no_compras.isnot(None)).all()]
    ref_valor = [c.fat_total for c in db.query(Cliente.fat_total).filter(Cliente.fat_total.isnot(None)).all()]

    geo_cache = load_geo_cache()
    criados = 0
    for i, cnpj in enumerate(alvo, 1):
        _, nome_cad, cep, endereco, numero, bairro, cidade, uf = cadastro[cnpj]
        info_banco = conn.execute(
            "SELECT nome, total_compras, faturamento_total, primeira_compra, ultima_compra FROM clientes WHERE cpf_cnpj = ?",
            (cnpj,),
        ).fetchone()
        if not info_banco:
            continue
        nome_banco, no_compras, fat_total, primeira, ultima = info_banco
        nome_final = nome_cad if (nome_cad and nome_cad.strip().upper() not in NOMES_GENERICOS) else nome_banco
        if not nome_final or nome_final.strip().upper() in NOMES_GENERICOS:
            continue  # sem nome utilizavel — pula (fica na lista de "sem endereco/dados" pro usuario revisar)

        endereco_completo = f"{endereco.strip()}, {numero}".strip(", ") if numero else endereco.strip()
        ultima_dt = date.fromisoformat(str(ultima)[:10]) if ultima else None
        primeira_dt = date.fromisoformat(str(primeira)[:10]) if primeira else None
        recencia_dias = (HOJE - ultima_dt).days if ultima_dt else None
        dias_como_cliente = (HOJE - primeira_dt).days if primeira_dt else None
        ticket_medio = round(fat_total / no_compras, 2) if no_compras else 0
        cadencia_dias = None
        if no_compras and no_compras > 1 and primeira_dt and ultima_dt:
            cadencia_dias = round((ultima_dt - primeira_dt).days / (no_compras - 1))

        r = quintil_manual(recencia_dias, ref_recencia, invertido=True) if recencia_dias is not None else 1
        f_ = quintil_manual(no_compras or 0, ref_frequencia)
        m = quintil_manual(fat_total or 0, ref_valor)
        rfm_score = r + f_ + m
        ouro = m >= 4 and r >= 4 and f_ >= 4
        bronze = m <= 2 and not ouro
        faixa = "Ouro" if ouro else ("Bronze" if bronze else "Prata")
        em_risco = m >= 4 and r <= 2

        chave_geo = f"{endereco_completo.upper()}|{(cidade or '').upper()}|{(uf or '').upper()}"
        cache_hit = geo_cache.get(chave_geo)
        if cache_hit:
            lat, lng, geo_status = cache_hit.get("lat"), cache_hit.get("lng"), cache_hit.get("status")
        else:
            lat, lng, geo_status = geocodificar(endereco_completo, cep, cidade, uf)
            geo_cache[chave_geo] = {"lat": lat, "lng": lng, "status": geo_status}

        cliente = Cliente(
            cnpj=f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
            nome=title_inteligente(nome_final),
            endereco=endereco_completo or None,
            bairro=title_inteligente(bairro) or None,
            cep=so_digitos(cep) or None,
            cidade=title_inteligente(cidade) or None,
            uf=(uf or "").upper() or None,
            lat=lat, lng=lng, geo_status=geo_status,
            faixa=faixa, em_risco=em_risco,
            fat_total=fat_total, no_compras=no_compras, ticket_medio=ticket_medio,
            recencia_dias=recencia_dias, cadencia_dias=cadencia_dias,
            ultima_compra=ultima_dt,
            r=r, f=f_, m=m, rfm_score=rfm_score,
            origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
        )
        db.add(cliente)
        criados += 1
        if i % 10 == 0:
            save_geo_cache(geo_cache)
            print(f"  {i}/{len(alvo)}...")

    save_geo_cache(geo_cache)
    db.commit()
    print(f"\nCriados: {criados}")
    total = db.query(Cliente).count()
    print(f"Total na carteira agora: {total}")
    conn.close()
    db.close()


if __name__ == "__main__":
    main()
