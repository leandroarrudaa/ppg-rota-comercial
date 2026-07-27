"""Upsert de clientes vindos do pipeline (carteira antiga).

Separado do script de carga pra ser testável sem precisar de CSV real: quem
chama passa uma lista de dicts já no formato de CAMPOS_PIPELINE + "cnpj".
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Cliente, OrigemCliente
from .cnpj import normalizar_cnpj

# Campos que a reimportação PODE atualizar (dados do pipeline).
# Tudo que não está aqui (status, aceita_visita, motivo_recusa_visita,
# contato_nome, contato_celular, cliente_mestre_id) é preservado.
CAMPOS_PIPELINE = [
    "nome", "endereco", "bairro", "cep", "cidade", "uf",
    "lat", "lng", "geo_status",
    "faixa", "em_risco", "fat_total", "no_compras", "ticket_medio",
    "recencia_dias", "cadencia_dias", "ultima_compra",
    "r", "f", "m", "rfm_score",
    "porte", "capital_social", "cnae", "telefone", "email",
]


def upsert_clientes_antigos(db: Session, registros: list[dict]) -> dict:
    """Cria/atualiza clientes origem=ANTIGO a partir dos registros do pipeline.

    Cada registro precisa ter "cnpj" + todas as chaves de CAMPOS_PIPELINE.
    Devolve {"criados": N, "atualizados": N} sem dar commit (quem chama decide).
    """
    existentes = {
        normalizar_cnpj(c.cnpj): c
        for c in db.query(Cliente).filter(Cliente.origem == OrigemCliente.ANTIGO).all()
        if c.cnpj
    }
    criados = atualizados = 0
    for reg in registros:
        chave = normalizar_cnpj(reg.get("cnpj"))
        if not chave:
            continue
        existente = existentes.get(chave)
        if existente is None:
            dados = {k: reg[k] for k in CAMPOS_PIPELINE}
            db.add(Cliente(origem=OrigemCliente.ANTIGO, cnpj=reg["cnpj"], **dados))
            criados += 1
        else:
            for campo in CAMPOS_PIPELINE:
                setattr(existente, campo, reg[campo])
            atualizados += 1
    return {"criados": criados, "atualizados": atualizados}
