"""Testes da listagem de clientes: filtros e exclusão de inativos por padrão."""
import pytest


@pytest.fixture
def token(cliente_http):
    r = cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    )
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_lista_exclui_inativos_por_padrao(cliente_http, token):
    r = cliente_http.get("/api/clientes", headers=_auth(token))
    nomes = [c["nome"] for c in r.json()]
    assert "Empresa Fechada LTDA" not in nomes
    assert "Empresa Ouro LTDA" in nomes


def test_incluir_inativos_reexibe(cliente_http, token):
    r = cliente_http.get("/api/clientes?incluirInativos=true", headers=_auth(token))
    nomes = [c["nome"] for c in r.json()]
    assert "Empresa Fechada LTDA" in nomes


def test_filtro_por_faixa(cliente_http, token):
    r = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token))
    corpo = r.json()
    assert len(corpo) == 1
    assert corpo[0]["nome"] == "Empresa Ouro LTDA"


def test_busca_por_nome(cliente_http, token):
    r = cliente_http.get("/api/clientes?busca=bronze", headers=_auth(token))
    corpo = r.json()
    assert len(corpo) == 1
    assert corpo[0]["faixa"] == "Bronze"


def test_ficha_de_cliente_inexistente_404(cliente_http, token):
    r = cliente_http.get("/api/clientes/9999", headers=_auth(token))
    assert r.status_code == 404


def test_historico_itens_vazio_quando_sem_dado(cliente_http, token):
    lista = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()
    cliente_id = lista[0]["id"]
    r = cliente_http.get(f"/api/clientes/{cliente_id}/historico-itens", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"total": 0, "pagina": 1, "tamanho": 20, "itens": []}


def test_patch_contato_editavel(cliente_http, token):
    lista = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()
    cliente_id = lista[0]["id"]
    r = cliente_http.patch(
        f"/api/clientes/{cliente_id}",
        json={"contatoNome": "Sr. João", "contatoCelular": "42999990000"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["contatoNome"] == "Sr. João"
    assert corpo["contatoCelular"] == "42999990000"
    # faixa/faturamento não foram tocados pelo PATCH
    assert corpo["faixa"] == "Ouro"


def test_patch_aceitaVisita_false_exige_motivo(cliente_http, token):
    lista = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()
    cliente_id = lista[0]["id"]
    r = cliente_http.patch(
        f"/api/clientes/{cliente_id}", json={"aceitaVisita": False}, headers=_auth(token)
    )
    assert r.status_code == 400


def test_patch_aceitaVisita_false_com_motivo_funciona_e_continua_na_lista(cliente_http, token):
    lista = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()
    cliente_id = lista[0]["id"]
    r = cliente_http.patch(
        f"/api/clientes/{cliente_id}",
        json={"aceitaVisita": False, "motivoRecusaVisita": "calote"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["aceitaVisita"] is False
    assert corpo["motivoRecusaVisita"] == "calote"

    # decisão de produto: calote continua no mapa/carteira geral (não é "inativo")
    lista_geral = cliente_http.get("/api/clientes", headers=_auth(token)).json()
    assert any(c["id"] == cliente_id for c in lista_geral)


def test_bbox_filtra_por_area_e_exclui_inativo_mesmo_dentro_da_caixa(cliente_http, token):
    # caixa cobre só Curitiba (-25.4,-49.2): pega Ouro, não pega Bronze (fora) nem Fechada (inativo)
    r = cliente_http.get(
        "/api/clientes?bbox=-25.5,-49.3,-25.3,-49.1", headers=_auth(token)
    )
    assert r.status_code == 200
    nomes = [c["nome"] for c in r.json()]
    assert nomes == ["Empresa Ouro LTDA"]


def test_bbox_exclui_aceitaVisita_false_mesmo_com_incluirInativos(cliente_http, token):
    cliente = cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]  # dentro da caixa de Curitiba
    cliente_http.patch(
        f"/api/clientes/{cliente['id']}",
        json={"aceitaVisita": False, "motivoRecusaVisita": "sem-visita"},
        headers=_auth(token),
    )
    r = cliente_http.get(
        "/api/clientes?bbox=-25.5,-49.3,-25.3,-49.1&incluirInativos=true", headers=_auth(token)
    )
    assert r.json() == []


def test_bbox_invalido_retorna_400(cliente_http, token):
    r = cliente_http.get("/api/clientes?bbox=abc", headers=_auth(token))
    assert r.status_code == 400


def test_patch_marcar_inativo_some_da_lista_padrao(cliente_http, token):
    lista = cliente_http.get("/api/clientes?faixa=Bronze", headers=_auth(token)).json()
    cliente_id = lista[0]["id"]
    r = cliente_http.patch(
        f"/api/clientes/{cliente_id}", json={"status": "inativo"}, headers=_auth(token)
    )
    assert r.status_code == 200

    lista_padrao = cliente_http.get("/api/clientes", headers=_auth(token)).json()
    assert not any(c["id"] == cliente_id for c in lista_padrao)

    lista_com_inativos = cliente_http.get("/api/clientes?incluirInativos=true", headers=_auth(token)).json()
    assert any(c["id"] == cliente_id for c in lista_com_inativos)

# --------------------------------------------- Ficha unificada (uma requisicao)

def test_ficha_unificada_traz_tudo_numa_resposta(cliente_http, token):
    """A ficha substitui as 4-5 chamadas que a tela fazia ao abrir."""
    lista = cliente_http.get("/api/clientes", headers=_auth(token)).json()
    alvo = next(c for c in lista if c["nome"] == "Empresa Ouro LTDA")

    r = cliente_http.get(f"/api/clientes/{alvo['id']}/ficha", headers=_auth(token))
    assert r.status_code == 200
    corpo = r.json()

    assert corpo["cliente"]["id"] == alvo["id"]
    assert corpo["cliente"]["nome"] == "Empresa Ouro LTDA"
    for chave in ("promessas", "visitas", "historico", "vinculo"):
        assert chave in corpo
    assert isinstance(corpo["promessas"], list)
    assert isinstance(corpo["visitas"], list)
    assert "itens" in corpo["historico"]


def test_ficha_unificada_de_cliente_inexistente_404(cliente_http, token):
    r = cliente_http.get("/api/clientes/9999/ficha", headers=_auth(token))
    assert r.status_code == 404


def test_ficha_unificada_exige_autenticacao(cliente_http):
    r = cliente_http.get("/api/clientes/1/ficha")
    assert r.status_code == 401
