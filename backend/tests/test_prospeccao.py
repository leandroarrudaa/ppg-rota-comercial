"""Prospecção: ramos por CNAE, tipo de cadastro, leitura da lista, importação e consulta.

Todos os nomes e CNPJs abaixo são inventados — dado de cliente real não entra
em teste, porque teste vai para o repositório.
"""
import io

import pytest
from openpyxl import Workbook

from app.models import Cliente, OrigemCliente, Prospecto, StatusCliente, StatusProspecto
from app.services import prospeccao as svc
from app.services.fontes import lista_prospectos as lp
from app.services.ramos import (
    RAMO_OUTROS, TIPO_EMPRESA, TIPO_MEI, classificar_tipo, normalizar_codigo_cnae,
    normalizar_porte, ramo_por_cnae,
)

CABECALHO = ["cnpj", "razao_social", "capital_social", "porte", "situacao_cadastral", "cnae_fiscal",
             "tipo_logradouro", "logradouro", "numero", "bairro", "cep", "uf", "ddd1",
             "telefone_completo", "correio_eletronico", "nome_municipio"]


def _linha(cnpj, nome, cnae=4399103, cidade="PONTA GROSSA", porte="MICRO EMPRESA", capital=5000):
    return [cnpj, nome, capital, porte, "ATIVA", cnae, "RUA", "DAS FLORES", 10, "CENTRO", "84010000",
            "PR", 42, "42999990000", "contato@exemplo.com", cidade]


def _xlsx(linhas, cabecalho=CABECALHO) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(cabecalho)
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


LISTA = [
    _linha(10000000000101, "Construtora Alfa LTDA", 4120400, porte="DEMAIS", capital=800000),  # CNPJ como número
    _linha("20.000.000/0001-02", "Serralheria Beta LTDA", 2512800),
    _linha("30000000000103", "JOAO DA SILVA 12345678901", 4399103),          # MEI (CPF no nome)
    _linha("40000000000104", "Oficina Gama LTDA", 4520001, cidade="CURITIBA"),
    _linha("11111111000111", "Empresa Ouro LTDA", 4744001),                  # já é cliente (semeado no conftest)
]


@pytest.fixture
def token(cliente_http):
    return cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    ).json()["token"]


@pytest.fixture
def token_vendedor(cliente_http, token):
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    return cliente_http.post("/api/auth/login", json={"usuario": "taborda", "senha": "123456"}).json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _enviar(cliente_http, token, conteudo, confirmar=False, nome="lista.xlsx"):
    return cliente_http.post(
        f"/api/prospectos/importar?confirmar={'true' if confirmar else 'false'}",
        files={"arquivo": (nome, conteudo, "application/octet-stream")},
        headers=_auth(token),
    )


# ------------------------------------------------------------------ ramos e tipo

def test_ramo_por_codigo_cnae():
    assert ramo_por_cnae("4120400") == "Construção civil / obras"
    assert ramo_por_cnae(4744001) == "Varejo de ferragens / construção / elétrico"
    assert ramo_por_cnae("2512800") == "Metalurgia / serralheria / esquadrias"
    assert ramo_por_cnae("3314710") == "Manutenção / montagem industrial"
    assert ramo_por_cnae("4321500") == "Elétrica (instalação/manutenção)"
    assert ramo_por_cnae("4110700") == "Condomínios / imobiliário"  # incorporação não é obra
    assert ramo_por_cnae("9602501") == RAMO_OUTROS  # cabeleireiro
    assert ramo_por_cnae("") == RAMO_OUTROS


def test_codigo_cnae_aceita_numero_e_texto_formatado():
    assert normalizar_codigo_cnae(4744001.0) == "4744001"
    assert normalizar_codigo_cnae("47.44-0-01") == "4744001"
    assert normalizar_codigo_cnae(112) == "0000112"  # zeros à esquerda que o Excel comeu


def test_tipo_documento_no_nome_e_mei():
    assert classificar_tipo("MARIA DE SOUZA 12345678901") == TIPO_MEI
    assert classificar_tipo("12.498.009 CARLOS PEREIRA") == TIPO_MEI
    assert classificar_tipo("CARLOS PEREIRA DOS SANTOS") == TIPO_MEI  # nome de pessoa, sem forma jurídica


def test_tipo_empresa_por_forma_juridica_ou_palavra_de_negocio():
    assert classificar_tipo("Construtora Alfa LTDA") == TIPO_EMPRESA
    assert classificar_tipo("J. L. ALVES - CONSTRUTORA") == TIPO_EMPRESA
    assert classificar_tipo("PEDRO LIMA SERVICOS ELETRICOS") == TIPO_EMPRESA
    assert classificar_tipo("Metalurgica Delta S/A") == TIPO_EMPRESA


def test_porte_normalizado():
    assert normalizar_porte("MICRO EMPRESA") == "Micro"
    assert normalizar_porte("EMPRESA DE PEQUENO PORTE") == "Pequena"
    assert normalizar_porte("DEMAIS") == "Demais"
    assert normalizar_porte(None) == "Sem dado"


# ------------------------------------------------------------------ leitura

def test_le_lista_e_recupera_zeros_do_cnpj():
    lista = lp.ler(_xlsx([_linha(72266000140, "Igreja Exemplo Ltda")]))
    assert lista.linhas[0].cnpj == "00072266000140"
    assert lista.linhas[0].telefone == "42999990000"  # não duplica o DDD
    assert lista.linhas[0].logradouro == "RUA DAS FLORES"


def test_cabecalho_tolerante_a_acento_e_maiuscula():
    cab = ["CNPJ", "Razão Social", "Município"]
    lista = lp.ler(_xlsx([["10000000000101", "Empresa X LTDA", "Ponta Grossa"]], cabecalho=cab))
    assert lista.linhas[0].razao_social == "Empresa X LTDA"
    assert lista.linhas[0].cidade == "PONTA GROSSA"


def test_falta_coluna_obrigatoria_da_erro_amigavel():
    with pytest.raises(lp.ListaInvalida, match="razao_social"):
        lp.ler(_xlsx([["10000000000101"]], cabecalho=["cnpj"]))


def test_conta_invalidas_e_repetidas():
    lista = lp.ler(_xlsx([
        _linha("10000000000101", "Empresa A LTDA"),
        _linha("10000000000101", "Empresa A LTDA (de novo)"),
        _linha("123", "CNPJ curto demais LTDA"),
        _linha("20000000000102", ""),
    ]))
    assert len(lista.linhas) == 1
    assert lista.repetidas == 1
    assert lista.invalidas == 2
    assert lista.linhas[0].razao_social == "Empresa A LTDA (de novo)"  # vale a última


def test_le_csv_com_ponto_e_virgula_em_latin1():
    csv = "cnpj;razao_social;nome_municipio\n10000000000101;Serralheria São João LTDA;PONTA GROSSA\n"
    lista = lp.ler(csv.encode("latin-1"))
    assert lista.linhas[0].razao_social == "Serralheria São João LTDA"


def test_arquivo_vazio_ou_sem_empresas():
    with pytest.raises(lp.ListaInvalida):
        lp.ler(_xlsx([]))


# ------------------------------------------------------------------ importação

def test_previa_nao_grava_nada(cliente_http, token, db):
    r = _enviar(cliente_http, token, _xlsx(LISTA))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["previa"] is True
    assert corpo["resumo"]["novos"] == 5
    assert db.query(Prospecto).count() == 0


def test_confirmar_grava_e_resume(cliente_http, token, db):
    r = _enviar(cliente_http, token, _xlsx(LISTA), confirmar=True)
    assert r.status_code == 200
    resumo = r.json()["resumo"]
    assert resumo["novos"] == 5 and resumo["atualizados"] == 0
    assert resumo["jaClientes"] == 1
    assert resumo["meiAutonomos"] == 1
    assert db.query(Prospecto).count() == 5
    p = db.query(Prospecto).filter_by(cnpj="10000000000101").one()
    assert p.ramo == "Construção civil / obras"
    assert p.porte == "Demais"
    assert p.status == StatusProspecto.NOVO
    assert p.cidade == "PONTA GROSSA"


def test_importacao_fica_no_historico(cliente_http, token):
    _enviar(cliente_http, token, _xlsx(LISTA), confirmar=True, nome="ddd42.xlsx")
    historico = cliente_http.get("/api/importacao/historico", headers=_auth(token)).json()
    assert historico[0]["tipo"] == "prospectos"
    assert historico[0]["arquivo"] == "ddd42.xlsx"


def test_reimportar_atualiza_mas_preserva_decisao_da_equipe(cliente_http, token, db):
    _enviar(cliente_http, token, _xlsx(LISTA), confirmar=True)
    p = db.query(Prospecto).filter_by(cnpj="10000000000101").one()
    p.status = StatusProspecto.DESCARTADO
    p.motivo_descarte = "fechou"
    db.commit()

    nova = [_linha(10000000000101, "Construtora Alfa Novo Nome LTDA", 4120400, capital=900000)]
    resumo = _enviar(cliente_http, token, _xlsx(nova), confirmar=True).json()["resumo"]
    assert resumo["novos"] == 0 and resumo["atualizados"] == 1

    db.expire_all()
    p = db.query(Prospecto).filter_by(cnpj="10000000000101").one()
    assert p.razao_social == "Construtora Alfa Novo Nome LTDA"  # dado da lista foi atualizado
    assert p.capital_social == 900000
    assert p.status == StatusProspecto.DESCARTADO                # decisão da equipe, não
    assert p.motivo_descarte == "fechou"
    assert db.query(Prospecto).count() == 5                      # os outros continuam lá


def test_quem_virou_cliente_deixa_de_aparecer_como_prospecto(cliente_http, token, db):
    _enviar(cliente_http, token, _xlsx(LISTA), confirmar=True)
    db.add(Cliente(cnpj="20.000.000/0001-02", nome="Serralheria Beta LTDA", origem=OrigemCliente.ANTIGO))
    db.commit()

    # qualquer nova importação refaz a marca em TODOS os prospectos
    _enviar(cliente_http, token, _xlsx([_linha("50000000000105", "Outra Empresa LTDA")]), confirmar=True)
    db.expire_all()
    assert db.query(Prospecto).filter_by(cnpj="20000000000102").one().ja_cliente is True
    itens, _ = svc.listar(db)
    assert "20000000000102" not in {p.cnpj for p in itens}


def test_arquivo_invalido_devolve_400_amigavel(cliente_http, token):
    r = _enviar(cliente_http, token, _xlsx([["10000000000101"]], cabecalho=["cnpj"]))
    assert r.status_code == 400
    assert "razao_social" in r.json()["detail"]


# ------------------------------------------------------------------ consulta

@pytest.fixture
def com_lista(cliente_http, token):
    _enviar(cliente_http, token, _xlsx(LISTA), confirmar=True)


def test_lista_esconde_quem_ja_e_cliente(cliente_http, token, com_lista):
    r = cliente_http.get("/api/prospectos", headers=_auth(token)).json()
    assert r["total"] == 4
    assert "11111111000111" not in {i["cnpj"] for i in r["itens"]}


def test_filtro_de_cidade(cliente_http, token, com_lista):
    r = cliente_http.get("/api/prospectos?cidade=curitiba", headers=_auth(token)).json()
    assert [i["razaoSocial"] for i in r["itens"]] == ["Oficina Gama LTDA"]


def test_filtro_por_ramo_e_tipo(cliente_http, token, com_lista):
    r = cliente_http.get("/api/prospectos?tipo=empresa", headers=_auth(token)).json()
    assert r["total"] == 3
    r = cliente_http.get("/api/prospectos?ramo=Construção civil / obras&tipo=mei_autonomo", headers=_auth(token)).json()
    assert r["total"] == 1


def test_ordenacao_por_capital_do_maior_para_o_menor(cliente_http, token, com_lista):
    r = cliente_http.get("/api/prospectos?ordenar=capitalSocial&direcao=desc", headers=_auth(token)).json()
    assert r["itens"][0]["razaoSocial"] == "Construtora Alfa LTDA"


def test_busca_por_nome(cliente_http, token, com_lista):
    r = cliente_http.get("/api/prospectos?busca=serralheria", headers=_auth(token)).json()
    assert [i["razaoSocial"] for i in r["itens"]] == ["Serralheria Beta LTDA"]


def test_resumo_por_ramo_na_cidade(cliente_http, token, com_lista):
    r = cliente_http.get("/api/prospectos/resumo?cidade=PONTA GROSSA", headers=_auth(token)).json()
    assert r["totalNaLista"] == 5
    assert r["jaClientes"] == 1
    assert r["naCidade"] == 3          # Alfa, Beta e o MEI; Curitiba e o cliente ficam fora
    assert r["empresasNaCidade"] == 2  # sem o MEI
    obras = next(x for x in r["ramos"] if x["ramo"] == "Construção civil / obras")
    assert obras["total"] == 2 and obras["empresas"] == 1 and obras["demais"] == 1
    assert {c["cidade"] for c in r["cidades"]} == {"PONTA GROSSA", "CURITIBA"}


# ------------------------------------------------------------------ inativas não aparecem

def test_cliente_inativo_nunca_aparece_como_prospecto(cliente_http, token, db):
    """Empresa que fechou (cliente marcado como inativo) não é alvo de prospecção."""
    # "Empresa Fechada LTDA" é cliente INATIVO no conftest (33.333.333/0001-33)
    lista = [_linha("33333333000133", "Empresa Fechada LTDA"), _linha("60000000000106", "Empresa Viva LTDA")]
    _enviar(cliente_http, token, _xlsx(lista), confirmar=True)
    r = cliente_http.get("/api/prospectos", headers=_auth(token)).json()
    assert [i["razaoSocial"] for i in r["itens"]] == ["Empresa Viva LTDA"]


def test_inativar_cliente_depois_da_importacao_tira_da_lista_na_hora(cliente_http, token, db):
    """A checagem é feita ao vivo: nem precisa importar a lista de novo."""
    _enviar(cliente_http, token, _xlsx([_linha("60000000000106", "Empresa Viva LTDA")]), confirmar=True)
    assert cliente_http.get("/api/prospectos", headers=_auth(token)).json()["total"] == 1

    db.add(Cliente(cnpj="60.000.000/0001-06", nome="Empresa Viva LTDA", origem=OrigemCliente.ANTIGO,
                   status=StatusCliente.INATIVO))
    db.commit()
    assert cliente_http.get("/api/prospectos", headers=_auth(token)).json()["total"] == 0
    resumo = cliente_http.get("/api/prospectos/resumo", headers=_auth(token)).json()
    assert resumo["naCidade"] == 0 and resumo["jaClientes"] == 1


def test_prospecto_descartado_nao_aparece(cliente_http, token, db):
    _enviar(cliente_http, token, _xlsx(LISTA), confirmar=True)
    db.query(Prospecto).filter_by(cnpj="20000000000102").update({"status": StatusProspecto.DESCARTADO})
    db.commit()
    r = cliente_http.get("/api/prospectos", headers=_auth(token)).json()
    assert "20000000000102" not in {i["cnpj"] for i in r["itens"]}
    resumo = cliente_http.get("/api/prospectos/resumo?cidade=PONTA GROSSA", headers=_auth(token)).json()
    assert resumo["naCidade"] == 2  # Alfa e o MEI; a Beta foi descartada


# ------------------------------------------------------------------ acesso

def test_exige_login(cliente_http):
    assert cliente_http.get("/api/prospectos").status_code == 401


def test_vendedor_nao_importa_nem_consulta(cliente_http, token_vendedor):
    assert cliente_http.get("/api/prospectos", headers=_auth(token_vendedor)).status_code == 403
    r = cliente_http.post(
        "/api/prospectos/importar",
        files={"arquivo": ("x.xlsx", _xlsx(LISTA), "application/octet-stream")},
        headers=_auth(token_vendedor),
    )
    assert r.status_code == 403
