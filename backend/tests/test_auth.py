"""Testes do fluxo de autenticação: setup, login, token, permissão de admin."""


def test_setup_cria_primeiro_usuario_como_admin(cliente_http):
    r = cliente_http.post(
        "/api/auth/setup",
        json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["usuario"]["papel"] == "admin"
    assert corpo["token"]

    # setup não pode rodar de novo com o banco já povoado
    r2 = cliente_http.post(
        "/api/auth/setup",
        json={"nome": "Outro", "usuario": "outro", "senha": "123456"},
    )
    assert r2.status_code == 400


def test_login_com_senha_errada_falha(cliente_http):
    cliente_http.post("/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"})
    r = cliente_http.post("/api/auth/login", json={"usuario": "antonio", "senha": "errada"})
    assert r.status_code == 401


def test_endpoint_protegido_exige_token(cliente_http):
    r = cliente_http.get("/api/clientes")
    assert r.status_code == 401


def test_apenas_admin_cria_usuarios(cliente_http):
    setup = cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    ).json()
    token_admin = setup["token"]

    r = cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda", "senha": "123456", "papel": "vendedor"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert r.status_code == 200
    assert r.json()["papel"] == "vendedor"

    login_vendedor = cliente_http.post(
        "/api/auth/login", json={"usuario": "taborda", "senha": "123456"}
    ).json()
    token_vendedor = login_vendedor["token"]

    # vendedor não pode criar outro usuário
    r2 = cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Fulano", "usuario": "fulano", "senha": "123456"},
        headers={"Authorization": f"Bearer {token_vendedor}"},
    )
    assert r2.status_code == 403
