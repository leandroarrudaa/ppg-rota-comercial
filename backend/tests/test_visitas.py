"""Testes do fluxo bloqueante de visita: abrir, finalizar, relatório, promessas."""
from datetime import timedelta

import pytest

from app.services.tempo import hoje_brasil


@pytest.fixture
def token(cliente_http):
    r = cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    )
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _cliente_ouro(cliente_http, token):
    return cliente_http.get("/api/clientes?faixa=Ouro", headers=_auth(token)).json()[0]


def _cliente_bronze(cliente_http, token):
    return cliente_http.get("/api/clientes?faixa=Bronze", headers=_auth(token)).json()[0]


def test_abrir_e_finalizar_com_relatorio(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)

    r = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token))
    assert r.status_code == 200
    visita = r.json()
    assert visita["status"] == "aberta"
    assert visita["fim"] is None

    r2 = cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))
    assert r2.status_code == 200
    assert r2.json()["status"] == "aguardando_relatorio"
    assert r2.json()["fim"] is not None

    r3 = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "Cliente satisfeito, pediu retorno.", "retornoDias": 15, "promessas": ["Levar amostra de parafuso"]},
        headers=_auth(token),
    )
    assert r3.status_code == 200
    corpo = r3.json()
    assert corpo["status"] == "finalizada"
    assert corpo["retornoDias"] == 15
    # data de calendário em Brasília, não no fuso da máquina que roda o teste
    assert corpo["retornoData"] == str(hoje_brasil() + timedelta(days=15))
    assert len(corpo["promessas"]) == 1
    assert corpo["promessas"][0]["cumprida"] is False
    # padrão (sem mandar "sucesso" no corpo) é sucesso=true — histórico
    # antigo não pode virar "sem sucesso" sozinho
    assert corpo["sucesso"] is True
    assert corpo["motivoInsucesso"] is None


def test_relatorio_com_sucesso_false_grava_motivo(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "Ninguém no endereço.", "sucesso": False, "motivoInsucesso": "ausente"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["sucesso"] is False
    assert corpo["motivoInsucesso"] == "ausente"


def test_relatorio_com_sucesso_false_exige_motivo(cliente_http, token):
    """Sem motivo obrigatório, tudo que dava errado virava 'ausente' por ser
    o padrão do menu — mesmo quando a causa real era outra (endereço errado,
    por exemplo). Ver memória do relatório de comissão."""
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "Ninguém no endereço.", "sucesso": False},
        headers=_auth(token),
    )
    assert r.status_code == 400


def test_relatorio_com_sucesso_true_limpa_motivo_antigo(cliente_http, token, db):
    """Reabrir e salvar com sucesso=true não pode deixar um motivo velho
    'grudado' de uma edição anterior."""
    from app.models import StatusVisita, Visita

    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))
    cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "primeira tentativa", "sucesso": False, "motivoInsucesso": "ausente"},
        headers=_auth(token),
    )

    # reabre pra simular corrigir o relatório — não existe rota pra isso
    # ainda, então mexe direto no banco só pra montar o cenário do teste.
    registro = db.get(Visita, visita["id"])
    registro.status = StatusVisita.AGUARDANDO_RELATORIO
    db.commit()

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "consegui falar", "sucesso": True},
        headers=_auth(token),
    )
    corpo = r.json()
    assert corpo["sucesso"] is True
    assert corpo["motivoInsucesso"] is None


def test_relatorio_rejeita_motivo_insucesso_invalido(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "x", "sucesso": False, "motivoInsucesso": "nao-existe"},
        headers=_auth(token),
    )
    assert r.status_code == 422


def test_nao_pode_abrir_segunda_visita_enquanto_primeira_esta_aberta(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    outro = cliente_http.get("/api/clientes?faixa=Bronze", headers=_auth(token)).json()[0]

    cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token))
    r = cliente_http.post("/api/visitas", json={"clienteId": outro["id"]}, headers=_auth(token))
    assert r.status_code == 409


def test_nao_pode_abrir_visita_pra_cliente_que_nao_aceita_visita(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    cliente_http.patch(
        f"/api/clientes/{cliente['id']}",
        json={"aceitaVisita": False, "motivoRecusaVisita": "calote"},
        headers=_auth(token),
    )
    r = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token))
    assert r.status_code == 400


def test_visita_sem_tipo_abre_como_presencial(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    r = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token))
    assert r.json()["tipo"] == "presencial"


def test_contato_pode_ser_aberto_mesmo_sem_aceitar_visita_presencial(cliente_http, token):
    """O Plano de Contato existe justamente pra quem não aceita mais visita
    presencial (calote/sem-visita) — o contato por telefone não pode ficar
    bloqueado pela mesma regra."""
    cliente = _cliente_ouro(cliente_http, token)
    cliente_http.patch(
        f"/api/clientes/{cliente['id']}",
        json={"aceitaVisita": False, "motivoRecusaVisita": "sem-visita"},
        headers=_auth(token),
    )
    r = cliente_http.post(
        "/api/visitas", json={"clienteId": cliente["id"], "tipo": "contato"}, headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.json()["tipo"] == "contato"
    assert r.json()["status"] == "aberta"


def test_contato_finalizado_pode_inativar_cliente_pelo_relatorio(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post(
        "/api/visitas", json={"clienteId": cliente["id"], "tipo": "contato"}, headers=_auth(token)
    ).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "Empresa não existe mais no endereço.", "status": "inativo"},
        headers=_auth(token),
    )
    assert r.status_code == 200

    atualizado = cliente_http.get(f"/api/clientes/{cliente['id']}", headers=_auth(token)).json()
    assert atualizado["status"] == "inativo"


def test_visita_e_contato_nao_podem_ficar_abertos_ao_mesmo_tempo(cliente_http, token):
    """Mesma regra bloqueante de antes, agora valendo pros dois tipos juntos —
    um contato aberto também impede abrir uma visita presencial, e vice-versa."""
    cliente = _cliente_ouro(cliente_http, token)
    outro = _cliente_bronze(cliente_http, token)
    cliente_http.post("/api/visitas", json={"clienteId": cliente["id"], "tipo": "contato"}, headers=_auth(token))
    r = cliente_http.post("/api/visitas", json={"clienteId": outro["id"]}, headers=_auth(token))
    assert r.status_code == 409


def test_relatorio_exige_observacao_nao_vazia(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio", json={"observacao": ""}, headers=_auth(token)
    )
    assert r.status_code == 422


def test_nao_pode_salvar_relatorio_sem_finalizar_primeiro(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio", json={"observacao": "teste"}, headers=_auth(token)
    )
    assert r.status_code == 400


def test_visita_pendente_restaura_estado(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    assert cliente_http.get("/api/visitas/pendente", headers=_auth(token)).json() is None

    aberta = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    pendente = cliente_http.get("/api/visitas/pendente", headers=_auth(token)).json()
    assert pendente["id"] == aberta["id"]
    assert pendente["status"] == "aberta"

    cliente_http.patch(f"/api/visitas/{aberta['id']}/finalizar", headers=_auth(token))
    pendente2 = cliente_http.get("/api/visitas/pendente", headers=_auth(token)).json()
    assert pendente2["status"] == "aguardando_relatorio"


def test_promessa_pendente_e_pode_ser_cumprida(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))
    cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "ok", "promessas": ["Levar amostra"]},
        headers=_auth(token),
    )

    pendentes = cliente_http.get(f"/api/clientes/{cliente['id']}/promessas", headers=_auth(token)).json()
    assert len(pendentes) == 1
    promessa_id = pendentes[0]["id"]

    r = cliente_http.patch(f"/api/visitas/promessas/{promessa_id}/cumprir", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["cumprida"] is True

    pendentes_depois = cliente_http.get(f"/api/clientes/{cliente['id']}/promessas", headers=_auth(token)).json()
    assert len(pendentes_depois) == 0


def test_historico_de_visitas_so_mostra_finalizadas(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()

    # ainda aberta -> não aparece no histórico
    hist_antes = cliente_http.get(f"/api/clientes/{cliente['id']}/visitas", headers=_auth(token)).json()
    assert hist_antes == []

    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))
    cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio", json={"observacao": "concluída"}, headers=_auth(token)
    )
    hist_depois = cliente_http.get(f"/api/clientes/{cliente['id']}/visitas", headers=_auth(token)).json()
    assert len(hist_depois) == 1
    assert hist_depois[0]["status"] == "finalizada"


def test_relatorio_com_ajuste_de_status_invalido_nao_altera_nada(cliente_http, token):
    """aceitaVisita=false sem motivo deve falhar e não deixar a visita meio-salva."""
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    r = cliente_http.post(
        f"/api/visitas/{visita['id']}/relatorio",
        json={"observacao": "teste", "aceitaVisita": False},
        headers=_auth(token),
    )
    assert r.status_code == 400

    # a visita continua aguardando relatório, não foi finalizada pela metade
    pendente = cliente_http.get("/api/visitas/pendente", headers=_auth(token)).json()
    assert pendente["id"] == visita["id"]
    assert pendente["status"] == "aguardando_relatorio"


# ------------------------------------------------- cancelar visita esquecida
# Uma visita aberta bloqueia todas as outras. Sem saída, quem esqueceu de
# finalizar fica travado em campo — o problema real que motivou isso.

def test_cancelar_visita_aberta_libera_para_abrir_outra(cliente_http, token):
    primeira = cliente_http.post(
        "/api/visitas", json={"clienteId": _cliente_ouro(cliente_http, token)["id"]}, headers=_auth(token)
    ).json()

    # com a primeira aberta, abrir outra é recusado
    outro = _cliente_bronze(cliente_http, token)["id"]
    bloqueada = cliente_http.post("/api/visitas", json={"clienteId": outro}, headers=_auth(token))
    assert bloqueada.status_code == 409

    cancelada = cliente_http.delete(f"/api/visitas/{primeira['id']}", headers=_auth(token))
    assert cancelada.status_code == 200

    liberada = cliente_http.post("/api/visitas", json={"clienteId": outro}, headers=_auth(token))
    assert liberada.status_code == 200


def test_cancelar_some_com_a_visita_pendente(cliente_http, token):
    visita = cliente_http.post(
        "/api/visitas", json={"clienteId": _cliente_ouro(cliente_http, token)["id"]}, headers=_auth(token)
    ).json()
    assert cliente_http.get("/api/visitas/pendente", headers=_auth(token)).json() is not None

    cliente_http.delete(f"/api/visitas/{visita['id']}", headers=_auth(token))
    assert cliente_http.get("/api/visitas/pendente", headers=_auth(token)).json() is None


def test_nao_cancela_visita_que_ja_aconteceu(cliente_http, token):
    """Depois de finalizar, o relatório é obrigatório — cancelar seria uma
    porta de saída para não preencher."""
    visita = cliente_http.post(
        "/api/visitas", json={"clienteId": _cliente_ouro(cliente_http, token)["id"]}, headers=_auth(token)
    ).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))

    recusado = cliente_http.delete(f"/api/visitas/{visita['id']}", headers=_auth(token))
    assert recusado.status_code == 400
    assert "relatório" in recusado.json()["detail"]


def test_nao_cancela_visita_de_outro_vendedor(cliente_http, token):
    visita = cliente_http.post(
        "/api/visitas", json={"clienteId": _cliente_ouro(cliente_http, token)["id"]}, headers=_auth(token)
    ).json()

    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Outro", "usuario": "outro", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_outro = cliente_http.post(
        "/api/auth/login", json={"usuario": "outro", "senha": "123456"}
    ).json()["token"]

    recusado = cliente_http.delete(f"/api/visitas/{visita['id']}", headers=_auth(token_outro))
    assert recusado.status_code == 403


# ------------------------------------------------- corrigir resultado depois
# Corrige o "deu certo?" de uma visita já finalizada — pra quando o relatório
# em campo ficou errado e só se percebe na hora de apurar a comissão.

def _visita_finalizada_via_api(cliente_http, token, *, sucesso=True, motivo_insucesso=None):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()
    cliente_http.patch(f"/api/visitas/{visita['id']}/finalizar", headers=_auth(token))
    corpo = {"observacao": "relatório original", "sucesso": sucesso}
    if motivo_insucesso:
        corpo["motivoInsucesso"] = motivo_insucesso
    cliente_http.post(f"/api/visitas/{visita['id']}/relatorio", json=corpo, headers=_auth(token))
    return visita["id"]


def test_corrige_resultado_de_sucesso_para_insucesso(cliente_http, token):
    visita_id = _visita_finalizada_via_api(cliente_http, token, sucesso=True)

    r = cliente_http.patch(
        f"/api/visitas/{visita_id}/resultado",
        json={"sucesso": False, "motivoInsucesso": "endereco_nao_encontrado"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["sucesso"] is False
    assert corpo["motivoInsucesso"] == "endereco_nao_encontrado"


def test_corrigir_para_insucesso_exige_motivo(cliente_http, token):
    visita_id = _visita_finalizada_via_api(cliente_http, token, sucesso=True)

    r = cliente_http.patch(
        f"/api/visitas/{visita_id}/resultado", json={"sucesso": False}, headers=_auth(token)
    )
    assert r.status_code == 400


def test_corrigir_para_sucesso_limpa_o_motivo(cliente_http, token):
    visita_id = _visita_finalizada_via_api(cliente_http, token, sucesso=False, motivo_insucesso="ausente")

    r = cliente_http.patch(
        f"/api/visitas/{visita_id}/resultado", json={"sucesso": True}, headers=_auth(token)
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["sucesso"] is True
    assert corpo["motivoInsucesso"] is None


def test_nao_corrige_resultado_de_visita_ainda_nao_finalizada(cliente_http, token):
    cliente = _cliente_ouro(cliente_http, token)
    visita = cliente_http.post("/api/visitas", json={"clienteId": cliente["id"]}, headers=_auth(token)).json()

    r = cliente_http.patch(
        f"/api/visitas/{visita['id']}/resultado", json={"sucesso": True}, headers=_auth(token)
    )
    assert r.status_code == 400


def test_vendedor_nao_corrige_resultado_de_visita_de_outro(cliente_http, token):
    """Taborda pode corrigir o próprio erro, mas não o de outro vendedor."""
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_taborda = cliente_http.post(
        "/api/auth/login", json={"usuario": "taborda", "senha": "123456"}
    ).json()["token"]
    visita_id = _visita_finalizada_via_api(cliente_http, token_taborda, sucesso=True)

    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Outro Vendedor", "usuario": "outro-vend", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_outro = cliente_http.post(
        "/api/auth/login", json={"usuario": "outro-vend", "senha": "123456"}
    ).json()["token"]

    r = cliente_http.patch(
        f"/api/visitas/{visita_id}/resultado",
        json={"sucesso": False, "motivoInsucesso": "ausente"},
        headers=_auth(token_outro),
    )
    assert r.status_code == 403


def test_admin_corrige_resultado_de_qualquer_vendedor(cliente_http, token):
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda2", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_taborda = cliente_http.post(
        "/api/auth/login", json={"usuario": "taborda2", "senha": "123456"}
    ).json()["token"]
    visita_id = _visita_finalizada_via_api(cliente_http, token_taborda, sucesso=True)

    r = cliente_http.patch(
        f"/api/visitas/{visita_id}/resultado",
        json={"sucesso": False, "motivoInsucesso": "ausente"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["sucesso"] is False
