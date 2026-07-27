"""Testes das melhorias: promessa pendente na lista, busca elegível sem bbox,
visitas de hoje, histórico de item sem paginação."""
import pytest


@pytest.fixture
def token(cliente_http):
    r = cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    )
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _fazer_visita_completa(cliente_http, token, cliente_id, promessas=None):
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente_id}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))
    cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "ok", "promessas": promessas or []},
        headers=_auth(token),
    )
    return visita


def test_tem_promessa_pendente_aparece_na_listagem(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    bronze = cliente_http.get("/api/clientes?faixa=Bronze", headers=_auth(token)).json()[0]

    _fazer_visita_completa(cliente_http, token, ouro["id"], promessas=["Levar amostra"])

    lista = cliente_http.get("/api/clientes", headers=_auth(token)).json()
    por_id = {c["id"]: c for c in lista}
    assert por_id[ouro["id"]]["temPromessaPendente"] is True
    assert por_id[bronze["id"]]["temPromessaPendente"] is False


def test_promessa_cumprida_some_do_flag(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    _fazer_visita_completa(cliente_http, token, ouro["id"], promessas=["Levar amostra"])
    pendentes = cliente_http.get(f"/api/clientes/{ouro['id']}/promessas", headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/promessas/{pendentes[0]['id']}/cumprir", headers=_auth(token))

    cliente_atualizado = cliente_http.get(f"/api/clientes/{ouro['id']}", headers=_auth(token)).json()
    assert cliente_atualizado["temPromessaPendente"] is False


def test_busca_elegivel_visita_exclui_inativo_e_sem_aceita_visita(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    cliente_http.patch(
        f"/api/clientes/{ouro['id']}",
        json={"aceitaVisita": False, "motivoRecusaVisita": "calote"},
        headers=_auth(token),
    )
    # sem elegivelVisita, o calote aparece normalmente na busca geral
    r_normal = cliente_http.get("/api/clientes?busca=Ouro", headers=_auth(token)).json()
    assert any(c["id"] == ouro["id"] for c in r_normal)

    # com elegivelVisita=true (busca da Rota do Dia), ele some — não pode entrar em rota
    r_elegivel = cliente_http.get("/api/clientes?busca=Ouro&elegivelVisita=true", headers=_auth(token)).json()
    assert not any(c["id"] == ouro["id"] for c in r_elegivel)


def test_busca_elegivel_visita_funciona_sem_bbox_carteira_toda(cliente_http, token):
    r = cliente_http.get("/api/clientes?busca=Bronze&elegivelVisita=true", headers=_auth(token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_visitados_hoje_lista_cliente_com_visita_finalizada(cliente_http, token):
    assert cliente_http.get("/api/visitas/hoje", headers=_auth(token)).json() == []
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    _fazer_visita_completa(cliente_http, token, ouro["id"])
    hoje = cliente_http.get("/api/visitas/hoje", headers=_auth(token)).json()
    assert hoje == [ouro["id"]]


def test_historico_itens_todos_ignora_paginacao(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    r = cliente_http.get(f"/api/clientes/{ouro['id']}/historico-itens?todos=true", headers=_auth(token))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["pagina"] == 1
    assert corpo["tamanho"] == corpo["total"]
