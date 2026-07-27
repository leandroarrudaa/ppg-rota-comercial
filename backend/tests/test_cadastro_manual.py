"""Testes do cadastro manual de cliente novo (lead cadastrado em campo)."""
import pytest


@pytest.fixture
def token(cliente_http):
    r = cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    )
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_cadastro_manual_minimo(cliente_http, token):
    r = cliente_http.post(
        "/api/clientes/manual",
        json={"nome": "Empresa Nova Encontrada em Campo", "lat": -25.09, "lng": -50.16},
        headers=_auth(token),
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["origem"] == "novo"
    assert corpo["geo"] == "manual"
    assert corpo["status"] == "ativo"
    assert corpo["aceitaVisita"] is True
    assert corpo["faixa"] is None  # lead não tem RFM


def test_cadastro_manual_completo(cliente_http, token):
    r = cliente_http.post(
        "/api/clientes/manual",
        json={
            "nome": "Ferragens do Bairro", "lat": -25.1, "lng": -50.1,
            "endereco": "Rua das Flores, 123", "bairro": "Centro", "cidade": "Ponta Grossa", "uf": "PR",
            "cnpj": "99.999.999/0001-99", "contatoNome": "Sr. Pedro", "contatoCelular": "42988887777",
        },
        headers=_auth(token),
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["endereco"] == "Rua das Flores, 123"
    assert corpo["contatoNome"] == "Sr. Pedro"
    assert corpo["cnpj"] == "99.999.999/0001-99"


def test_cadastro_manual_aparece_na_listagem_como_novo(cliente_http, token):
    cliente_http.post(
        "/api/clientes/manual",
        json={"nome": "Lead De Teste", "lat": -25.09, "lng": -50.16},
        headers=_auth(token),
    )
    r = cliente_http.get("/api/clientes?origem=novo", headers=_auth(token))
    nomes = [c["nome"] for c in r.json()]
    assert "Lead De Teste" in nomes


def test_cadastro_manual_sem_nome_falha(cliente_http, token):
    r = cliente_http.post(
        "/api/clientes/manual", json={"nome": "", "lat": -25.09, "lng": -50.16}, headers=_auth(token)
    )
    assert r.status_code == 422
