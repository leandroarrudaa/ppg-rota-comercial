"""Reimportação da carteira NÃO pode sobrescrever campos donos do app."""
from app.models import Cliente, MotivoRecusaVisita, OrigemCliente, StatusCliente
from app.services.importacao import upsert_clientes_antigos


def _registro(cnpj, faixa, fat_total):
    """Registro mínimo no formato que o pipeline produz (todas as chaves de CAMPOS_PIPELINE)."""
    return {
        "cnpj": cnpj, "nome": "Empresa Teste", "endereco": None, "bairro": None, "cep": None,
        "cidade": "Curitiba", "uf": "PR", "lat": -25.4, "lng": -49.2, "geo_status": "preciso",
        "faixa": faixa, "em_risco": False, "fat_total": fat_total, "no_compras": 10,
        "ticket_medio": fat_total / 10, "recencia_dias": 5, "cadencia_dias": 30,
        "ultima_compra": None, "r": 5, "f": 5, "m": 5, "rfm_score": 15,
        "porte": "Pequena", "capital_social": None, "cnae": "Comércio", "telefone": None,
        "email": None,
    }


def test_cria_cliente_novo(db):
    resultado = upsert_clientes_antigos(db, [_registro("44.444.444/0001-44", "Ouro", 60000)])
    db.commit()
    assert resultado == {"criados": 1, "atualizados": 0}
    cliente = db.query(Cliente).filter(Cliente.cnpj == "44.444.444/0001-44").one()
    assert cliente.faixa == "Ouro"
    assert cliente.origem == OrigemCliente.ANTIGO


def test_reimportacao_preserva_campos_do_app(db):
    # cliente já existe no banco, com dados "do app" preenchidos pelo uso real
    cliente = Cliente(
        cnpj="55.555.555/0001-55", nome="Empresa Antiga", origem=OrigemCliente.ANTIGO,
        faixa="Bronze", fat_total=1000, status=StatusCliente.INATIVO,
        aceita_visita=False, motivo_recusa_visita=MotivoRecusaVisita.CALOTE,
        contato_nome="Sr. João", contato_celular="42999990000",
    )
    db.add(cliente)
    db.commit()

    # reprocessamento do Excel: RFM mudou (agora Ouro, faturamento maior)
    resultado = upsert_clientes_antigos(
        db, [_registro("55.555.555/0001-55", "Ouro", 90000)]
    )
    db.commit()
    db.refresh(cliente)

    assert resultado == {"criados": 0, "atualizados": 1}
    # campos do pipeline foram atualizados
    assert cliente.faixa == "Ouro"
    assert cliente.fat_total == 90000
    # campos donos do app permanecem intocados
    assert cliente.status == StatusCliente.INATIVO
    assert cliente.aceita_visita is False
    assert cliente.motivo_recusa_visita == MotivoRecusaVisita.CALOTE
    assert cliente.contato_nome == "Sr. João"
    assert cliente.contato_celular == "42999990000"


def test_registro_sem_cnpj_e_ignorado(db):
    total_antes = db.query(Cliente).count()  # fixture já semeia 3 clientes
    resultado = upsert_clientes_antigos(db, [_registro("", "Ouro", 1000)])
    db.commit()
    assert resultado == {"criados": 0, "atualizados": 0}
    assert db.query(Cliente).count() == total_antes
