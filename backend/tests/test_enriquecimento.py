"""Busca de CNAE pendente via CNPJ (BrasilAPI) — sem tocar a rede de verdade."""
import pytest

from app.models import Cliente, OrigemCliente, StatusCliente
from app.services import enriquecimento as svc


@pytest.fixture
def token(cliente_http):
    return cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    ).json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _cliente(nome, cnpj, origem=OrigemCliente.ANTIGO):
    return Cliente(nome=nome, cnpj=cnpj, origem=origem, status=StatusCliente.ATIVO)


def _limpar(db):
    """Tira os 3 clientes de exemplo da fixture `db` — eles também têm CNPJ
    sem CNAE, o que inflaria a fila de pendentes nos testes deste arquivo."""
    db.query(Cliente).delete()
    db.commit()


# --------------------------------------------------- contar_pendentes

def test_conta_so_quem_tem_cnpj_e_nunca_foi_tentado(db):
    _limpar(db)
    db.add_all([
        _cliente("Nunca tentado", "44.444.444/0001-44"),
        _cliente("Ja tem ramo", "55.555.555/0001-55"),
        _cliente("Ja tentou e nao achou", "66.666.666/0001-66"),
        _cliente("Sem cnpj", None),
    ])
    db.commit()
    db.query(Cliente).filter(Cliente.nome == "Ja tem ramo").update({"cnae": "Comércio varejista"})
    db.query(Cliente).filter(Cliente.nome == "Ja tentou e nao achou").update({"cnae": ""})
    db.commit()

    assert svc.contar_pendentes(db) == 1
    assert [c.nome for c in svc._pendentes_query(db)] == ["Nunca tentado"]


# --------------------------------------------------- enriquecer_lote

def test_preenche_quem_a_api_encontrou_e_marca_quem_nao_achou(db, monkeypatch):
    _limpar(db)
    db.add_all([
        _cliente("Achou", "77.777.777/0001-77"),
        _cliente("Nao achou", "88.888.888/0001-88"),
    ])
    db.commit()
    monkeypatch.setattr(svc, "PAUSA_ENTRE_CHAMADAS", 0)

    def cnae_falso(cnpj):
        return "Comércio varejista de ferragens e ferramentas" if cnpj == "77777777000177" else None

    monkeypatch.setattr(svc, "_buscar_cnae", cnae_falso)

    resultado = svc.enriquecer_lote(db, limite=10)

    achou = db.query(Cliente).filter(Cliente.nome == "Achou").one()
    nao_achou = db.query(Cliente).filter(Cliente.nome == "Nao achou").one()
    assert achou.cnae == "Comércio varejista de ferragens e ferramentas"
    assert nao_achou.cnae == ""  # tentou, não achou — não fica None pra sempre
    assert resultado["encontrados"] == 1
    assert resultado["naoEncontrados"] == 1
    assert resultado["restam"] == 0


def test_cnpj_invalido_e_marcado_como_tentado_sem_chamar_api(db, monkeypatch):
    _limpar(db)
    db.add(_cliente("CNPJ mal formado", "123"))
    db.commit()
    monkeypatch.setattr(svc, "PAUSA_ENTRE_CHAMADAS", 0)
    chamou = []
    monkeypatch.setattr(svc, "_buscar_cnae", lambda cnpj: chamou.append(cnpj) or "não deveria chamar")

    resultado = svc.enriquecer_lote(db, limite=10)

    assert chamou == []  # a API nem foi chamada
    assert resultado["semCnpjValido"] == 1
    assert resultado["restam"] == 0


def test_respeita_o_orcamento_de_tempo_e_deixa_o_resto_pra_proxima_chamada(db, monkeypatch):
    _limpar(db)
    for i in range(5):
        db.add(_cliente(f"Cliente {i}", f"1{i}.111.111/0001-1{i}"))
    db.commit()
    monkeypatch.setattr(svc, "PAUSA_ENTRE_CHAMADAS", 0)
    monkeypatch.setattr(svc, "_buscar_cnae", lambda cnpj: "Ramo qualquer")

    # primeira leitura do relógio marca o início; a segunda (já lá na frente
    # no tempo) é checada antes de processar o 1º cliente do lote — estoura
    # o orçamento imediatamente, sem processar ninguém.
    relogio = iter([0, 100])
    monkeypatch.setattr(svc.time, "monotonic", lambda: next(relogio))

    resultado = svc.enriquecer_lote(db, limite=10)

    assert resultado["processados"] == 0
    assert resultado["restam"] == 5


# --------------------------------------------------- endpoint

def test_endpoint_exige_admin(cliente_http, db, token):
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Vendedor", "usuario": "vend", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_vendedor = cliente_http.post(
        "/api/auth/login", json={"usuario": "vend", "senha": "123456"}
    ).json()["token"]

    resposta = cliente_http.post("/api/clientes/enriquecer-cnae", headers=_auth(token_vendedor))
    assert resposta.status_code == 403


def test_endpoint_roda_o_lote_e_devolve_o_resumo(cliente_http, db, token, monkeypatch):
    _limpar(db)
    db.add(_cliente("Achou via endpoint", "99.999.999/0001-99"))
    db.commit()
    monkeypatch.setattr(svc, "PAUSA_ENTRE_CHAMADAS", 0)
    monkeypatch.setattr(svc, "_buscar_cnae", lambda cnpj: "Comércio atacadista de ferragens")

    r = cliente_http.post("/api/clientes/enriquecer-cnae", headers=_auth(token))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["encontrados"] == 1
    assert corpo["restam"] == 0

    r2 = cliente_http.get("/api/clientes/cnae-pendentes", headers=_auth(token))
    assert r2.json() == {"pendentes": 0}
