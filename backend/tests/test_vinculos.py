"""Testes de vínculo de CNPJ: sugestão automática e criação/desfazimento manual."""
import pytest

from app.models import Cliente, OrigemCliente, StatusCliente


@pytest.fixture
def token(cliente_http):
    r = cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    )
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_par_mesmo_endereco(db):
    """Duas empresas com endereço (rua e número) idêntico, nomes diferentes —
    candidato por endereço exato, não por CEP (CEP cobre a rua inteira)."""
    a = Cliente(
        cnpj="44.444.444/0001-44", nome="Metalurgica Sul LTDA", cidade="Curitiba", uf="PR",
        endereco="Rua das Industrias, 500", cep="80000-000", lat=-25.4, lng=-49.2,
        faixa="Ouro", fat_total=40000,
        origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
    )
    b = Cliente(
        cnpj="55.555.555/0001-55", nome="Comercial Sul EIRELI", cidade="Curitiba", uf="PR",
        endereco="Rua das Industrias, 500", cep="80000-000", lat=-25.4, lng=-49.2,
        faixa="Prata", fat_total=8000,
        origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
    )
    db.add_all([a, b])
    db.commit()
    return a, b


def _seed_par_mesmo_cep_endereco_diferente(db):
    """Mesmo CEP, mesma cidade, mas endereço (rua e número) diferente e nomes
    sem nada em comum — CEP sozinho cobre a rua/quadra toda, não deve gerar
    sugestão de vínculo (critério exige endereço exato ou nome parecido)."""
    a = Cliente(
        cnpj="88.888.888/0001-88", nome="Distribuidora Norte LTDA", cidade="Curitiba", uf="PR",
        endereco="Rua das Industrias, 100", cep="80000-000", lat=-25.4, lng=-49.2,
        faixa="Ouro", fat_total=30000,
        origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
    )
    b = Cliente(
        cnpj="99.999.999/0001-99", nome="Papelaria Horizonte ME", cidade="Curitiba", uf="PR",
        endereco="Rua das Industrias, 900", cep="80000-000", lat=-25.4, lng=-49.2,
        faixa="Prata", fat_total=6000,
        origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
    )
    db.add_all([a, b])
    db.commit()
    return a, b


def _seed_par_nome_parecido(db):
    a = Cliente(
        cnpj="66.666.666/0001-66", nome="Parafusos Central LTDA", cidade="Ponta Grossa", uf="PR",
        lat=-25.1, lng=-50.1, faixa="Bronze", fat_total=2000,
        origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
    )
    b = Cliente(
        cnpj="77.777.777/0001-77", nome="Parafusos Central ME", cidade="Ponta Grossa", uf="PR",
        lat=-25.1, lng=-50.1, faixa="Bronze", fat_total=1500,
        origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
    )
    db.add_all([a, b])
    db.commit()
    return a, b


def test_gerar_sugestoes_por_mesmo_endereco(cliente_http, token, db):
    a, b = _seed_par_mesmo_endereco(db)
    r = cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["criadas"] >= 1

    sugestoes = cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json()
    pares = {(s["clienteA"]["id"], s["clienteB"]["id"]) for s in sugestoes}
    par_esperado = (min(a.id, b.id), max(a.id, b.id))
    assert par_esperado in pares
    encontrada = next(s for s in sugestoes if (s["clienteA"]["id"], s["clienteB"]["id"]) == par_esperado)
    assert encontrada["motivo"] == "mesmo endereço"
    # tela de revisão precisa mostrar CNPJ e endereço dos dois lados
    assert encontrada["clienteA"]["cnpj"] == a.cnpj
    assert encontrada["clienteA"]["endereco"] == a.endereco
    assert encontrada["clienteB"]["cnpj"] == b.cnpj
    assert encontrada["clienteB"]["endereco"] == b.endereco


def test_mesmo_cep_sozinho_nao_gera_sugestao(cliente_http, token, db):
    a, b = _seed_par_mesmo_cep_endereco_diferente(db)
    cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    sugestoes = cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json()
    pares = {(s["clienteA"]["id"], s["clienteB"]["id"]) for s in sugestoes}
    par = (min(a.id, b.id), max(a.id, b.id))
    assert par not in pares


def test_gerar_sugestoes_por_nome_parecido(cliente_http, token, db):
    a, b = _seed_par_nome_parecido(db)
    cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    sugestoes = cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json()
    pares = {(s["clienteA"]["id"], s["clienteB"]["id"]): s for s in sugestoes}
    par = (min(a.id, b.id), max(a.id, b.id))
    assert par in pares
    assert pares[par]["motivo"] == "nome parecido"


def test_gerar_sugestoes_nao_duplica_ao_rodar_duas_vezes(cliente_http, token, db):
    _seed_par_mesmo_endereco(db)
    cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    total_1 = len(cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json())
    cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    total_2 = len(cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json())
    assert total_1 == total_2


def test_aceitar_sugestao_cria_vinculo_e_consolida_rfm(cliente_http, token, db):
    a, b = _seed_par_mesmo_endereco(db)
    cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    sugestoes = cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json()
    par = (min(a.id, b.id), max(a.id, b.id))
    sug = next(s for s in sugestoes if (s["clienteA"]["id"], s["clienteB"]["id"]) == par)

    r = cliente_http.patch(f"/api/vinculos/sugestoes/{sug['id']}", json={"aceitar": True}, headers=_auth(token))
    assert r.status_code == 200

    cliente_a = cliente_http.get(f"/api/clientes/{a.id}", headers=_auth(token)).json()
    cliente_b = cliente_http.get(f"/api/clientes/{b.id}", headers=_auth(token)).json()
    assert cliente_a["clienteMestreId"] is not None
    assert cliente_a["clienteMestreId"] == cliente_b["clienteMestreId"]

    consolidado = cliente_http.get(f"/api/vinculos/{cliente_a['clienteMestreId']}", headers=_auth(token)).json()
    assert consolidado["fatTotal"] == 48000  # 40000 + 8000
    assert consolidado["faixa"] == "Ouro"  # melhor faixa entre os membros
    assert len(consolidado["membros"]) == 2

    # sugestão não aparece mais como pendente
    pendentes = cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json()
    assert sug["id"] not in [s["id"] for s in pendentes]


def test_recusar_sugestao_nao_cria_vinculo(cliente_http, token, db):
    a, b = _seed_par_mesmo_endereco(db)
    cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token))
    sugestoes = cliente_http.get("/api/vinculos/sugestoes", headers=_auth(token)).json()
    par = (min(a.id, b.id), max(a.id, b.id))
    sug = next(s for s in sugestoes if (s["clienteA"]["id"], s["clienteB"]["id"]) == par)

    r = cliente_http.patch(f"/api/vinculos/sugestoes/{sug['id']}", json={"aceitar": False}, headers=_auth(token))
    assert r.status_code == 200

    cliente_a = cliente_http.get(f"/api/clientes/{a.id}", headers=_auth(token)).json()
    assert cliente_a["clienteMestreId"] is None


def test_vinculo_manual_entre_clientes_sem_sugestao(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    bronze = cliente_http.get("/api/clientes?faixa=Bronze", headers=_auth(token)).json()[0]

    r = cliente_http.post(
        "/api/vinculos", json={"clienteIds": [ouro["id"], bronze["id"]]}, headers=_auth(token)
    )
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["membros"]) == 2


def test_busca_manual_para_vincular(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    r = cliente_http.get(f"/api/vinculos/buscar?q=Bronze&excluirId={ouro['id']}", headers=_auth(token))
    assert r.status_code == 200
    assert any("Bronze" in c["nome"] for c in r.json())


def test_desvincular_com_dois_membros_desfaz_grupo_inteiro(cliente_http, token):
    ouro = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]
    bronze = cliente_http.get("/api/clientes?faixa=Bronze", headers=_auth(token)).json()[0]
    vinculo = cliente_http.post(
        "/api/vinculos", json={"clienteIds": [ouro["id"], bronze["id"]]}, headers=_auth(token)
    ).json()

    r = cliente_http.delete(f"/api/vinculos/{vinculo['id']}/membros/{bronze['id']}", headers=_auth(token))
    assert r.status_code == 200

    cliente_ouro_depois = cliente_http.get(f"/api/clientes/{ouro['id']}", headers=_auth(token)).json()
    assert cliente_ouro_depois["clienteMestreId"] is None  # grupo de 1 não faz sentido, foi desfeito


def test_vendedor_nao_acessa_endpoints_de_vinculo(cliente_http, token):
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_vendedor = cliente_http.post(
        "/api/auth/login", json={"usuario": "taborda", "senha": "123456"}
    ).json()["token"]

    r = cliente_http.post("/api/vinculos/gerar-sugestoes", headers=_auth(token_vendedor))
    assert r.status_code == 403
