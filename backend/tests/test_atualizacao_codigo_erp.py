"""Código do ERP no cadastro do cliente: propagação a partir do de-para
(MapaCodigoErp) e preenchimento retroativo/auto-cura na subida do app."""
from app.models import Cliente, MapaCodigoErp
from app.services.atualizacao import _propagar_codigo_erp, preencher_codigo_erp_pendente


def test_preenche_pendente_casando_cnpj_normalizado(db):
    """Cliente.cnpj vem formatado (com pontuação); MapaCodigoErp.cnpj vem só
    dígitos — o casamento tem que normalizar, não comparar direto."""
    db.add(MapaCodigoErp(codigo="729", cnpj="11111111000111"))
    db.commit()

    atualizados = preencher_codigo_erp_pendente(db)
    assert atualizados == 1

    cliente = db.query(Cliente).filter(Cliente.cnpj == "11.111.111/0001-11").one()
    assert cliente.codigo_erp == "729"


def test_preencher_pendente_e_idempotente(db):
    db.add(MapaCodigoErp(codigo="729", cnpj="11111111000111"))
    db.commit()

    preencher_codigo_erp_pendente(db)
    # segunda chamada: não tem mais ninguém pendente (codigo_erp já setado),
    # não deve tentar mexer de novo nem quebrar
    atualizados = preencher_codigo_erp_pendente(db)
    assert atualizados == 0


def test_preencher_pendente_nao_toca_cliente_sem_correspondencia(db):
    """CNPJ que não está no de-para fica sem código — não inventa nada."""
    db.add(MapaCodigoErp(codigo="729", cnpj="11111111000111"))
    db.commit()

    preencher_codigo_erp_pendente(db)

    sem_match = db.query(Cliente).filter(Cliente.cnpj == "22.222.222/0001-22").one()
    assert sem_match.codigo_erp is None


def test_preencher_pendente_sem_mapa_nao_quebra(db):
    assert preencher_codigo_erp_pendente(db) == 0


def test_propagar_codigo_erp_atualiza_quem_ja_tinha_codigo_diferente(db):
    """Cenário da atualização mensal: o de-para mudou (empresa trocou de
    código no ERP) e o cadastro do cliente precisa acompanhar."""
    cliente = db.query(Cliente).filter(Cliente.cnpj == "11.111.111/0001-11").one()
    cliente.codigo_erp = "111"  # código antigo, de uma atualização anterior
    db.commit()

    atualizados = _propagar_codigo_erp(db, {"729": "11111111000111"})
    assert atualizados == 1

    db.refresh(cliente)
    assert cliente.codigo_erp == "729"


def test_propagar_codigo_erp_nao_reconta_quem_ja_esta_certo(db):
    cliente = db.query(Cliente).filter(Cliente.cnpj == "11.111.111/0001-11").one()
    cliente.codigo_erp = "729"
    db.commit()

    atualizados = _propagar_codigo_erp(db, {"729": "11111111000111"})
    assert atualizados == 0
