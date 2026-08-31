"""Leitura do banco mestre: filtros de CNPJ, nome genérico e de-para do ERP."""
import sqlite3

import pytest

from app.services.fontes import banco_mestre

CNPJ_A = "11111111000111"
CNPJ_B = "22222222000122"
CNPJ_GENERICO = "33333333000133"
CPF = "12345678901"


@pytest.fixture
def mestre(tmp_path):
    """Banco mestre mínimo, com só o que os leitores consultam."""
    caminho = tmp_path / "banco_mestre.db"
    con = sqlite3.connect(caminho)
    con.executescript(
        """
        CREATE TABLE notas (
            chave_nota TEXT, data_emissao TEXT, valor_total REAL,
            cpf_cnpj_cliente TEXT, nome_cliente TEXT, tipo_operacao TEXT
        );
        CREATE TABLE itens (
            chave_nota TEXT, codigo_produto TEXT, codigo_limpo TEXT,
            descricao_produto TEXT, quantidade REAL, valor_total_item REAL
        );
        CREATE TABLE cadastro_clientes (codigo TEXT, cpf_cnpj TEXT, cpf_cnpj_digits TEXT);
        """
    )
    notas = [
        ("n1", "2026-01-10", 1000.0, CNPJ_A, "EMPRESA A LTDA", "saida"),
        ("n2", "2026-06-20", 500.0, CNPJ_A, "EMPRESA A LTDA", "saida"),
        ("n3", "2026-03-05", 700.0, CNPJ_B, "EMPRESA B LTDA", "saida"),
        # venda de balcão: CNPJ real, nome não preenchido na nota
        ("n4", "2022-04-01", 120.0, CNPJ_GENERICO, "CONSUMIDOR", "saida"),
        # pessoa física e entrada não entram na carteira
        ("n5", "2026-05-01", 90.0, CPF, "FULANO DE TAL", "saida"),
        ("n6", "2026-05-02", 80.0, CNPJ_A, "EMPRESA A LTDA", "entrada"),
        # auto-emissão da própria PPG
        ("n7", "2026-05-03", 60.0, banco_mestre.CNPJ_EMPRESA, "PPG", "saida"),
    ]
    con.executemany("INSERT INTO notas VALUES (?,?,?,?,?,?)", notas)
    con.executemany(
        "INSERT INTO itens VALUES (?,?,?,?,?,?)",
        [("n1", "P1", "P1", "PARAFUSO", 10, 1000.0), ("n2", "P1", "", "PARAFUSO", 5, 500.0)],
    )
    con.executemany(
        "INSERT INTO cadastro_clientes VALUES (?,?,?)",
        [("729", "11.111.111/0001-11", CNPJ_A), ("800", "123.456.789-01", CPF), ("900", "", "")],
    )
    con.commit()
    con.close()
    return str(caminho)


def _por_cnpj(registros):
    return {r["cnpj"]: r for r in registros}


def test_agrega_por_cnpj_contando_notas_distintas(mestre):
    carteira = _por_cnpj(banco_mestre.ler_carteira(mestre))
    a = carteira[CNPJ_A]
    assert a["no_compras"] == 2
    assert a["fat_total"] == 1500.0
    assert a["primeira_compra"].isoformat() == "2026-01-10"
    assert a["ultima_compra"].isoformat() == "2026-06-20"


def test_ignora_cpf_entrada_e_auto_emissao(mestre):
    carteira = _por_cnpj(banco_mestre.ler_carteira(mestre))
    assert CPF not in carteira
    assert banco_mestre.CNPJ_EMPRESA not in carteira
    # a nota de entrada não pode ter entrado no faturamento da empresa A
    assert carteira[CNPJ_A]["fat_total"] == 1500.0


def test_venda_de_balcao_sem_nome_fica_de_fora_da_carteira(mestre):
    """Esses CNPJs genéricos são centenas de compras avulsas minúsculas; se
    entrarem, baixam o corte dos quintis e promovem de faixa quem não mudou."""
    carteira = _por_cnpj(banco_mestre.ler_carteira(mestre))
    assert CNPJ_GENERICO not in carteira


def test_mas_entra_se_ja_for_cliente_conhecido_da_carteira(mestre):
    """Regressão: o filtro de nome genérico, sozinho, derrubava 58 clientes
    reais do app cujas notas saíram sem o nome preenchido."""
    carteira = _por_cnpj(
        banco_mestre.ler_carteira(mestre, cnpjs_conhecidos={CNPJ_GENERICO})
    )
    assert CNPJ_GENERICO in carteira
    assert carteira[CNPJ_GENERICO]["no_compras"] == 1


def test_depara_traz_so_codigo_de_empresa(mestre):
    mapa = banco_mestre.ler_depara_codigo_cnpj(mestre)
    assert mapa == {"729": CNPJ_A}, "CPF e cadastro sem documento não podem entrar"


def test_historico_por_produto_usa_codigo_limpo_quando_existe(mestre):
    historico = banco_mestre.ler_historico_itens(mestre)
    assert len(historico) == 1
    item = historico[0]
    assert item["cnpj_normalizado"] == CNPJ_A
    assert item["codigo_produto"] == "P1"
    assert item["quantidade_total"] == 15
    assert item["valor_total"] == 1500.0
    assert item["numero_compras"] == 2


def test_arquivo_inexistente_da_erro_amigavel(tmp_path):
    with pytest.raises(banco_mestre.BancoMestreInvalido) as erro:
        banco_mestre.ler_carteira(str(tmp_path / "nao_existe.db"))
    assert "não encontrado" in str(erro.value)


def test_arquivo_que_nao_e_banco_mestre_da_erro_amigavel(tmp_path):
    """O gerente vai subir arquivo errado uma hora — a mensagem precisa dizer
    o que houve, sem stack trace."""
    outro = tmp_path / "qualquer.db"
    con = sqlite3.connect(outro)
    con.execute("CREATE TABLE coisa (x INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(banco_mestre.BancoMestreInvalido) as erro:
        banco_mestre.ler_carteira(str(outro))
    assert "banco mestre válido" in str(erro.value)
