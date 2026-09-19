"""Prospecção: importa a lista de empresas que ainda não são clientes e a consulta.

A importação segue o padrão do resto do app: roda tudo e devolve o resumo; quem
chama decide se dá commit ou rollback (é assim que a "prévia" não mente).
Reimportar o mesmo CNPJ atualiza os dados que vêm da lista e NUNCA mexe no que
a equipe decidiu (status, motivo, observação).
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import Integer, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as insert_pg
from sqlalchemy.dialects.sqlite import insert as insert_sqlite
from sqlalchemy.orm import Session

from ..models import Cliente, OrigemCliente, Prospecto, StatusCliente, StatusProspecto
from .cnpj import normalizar_cnpj
from .fontes.lista_prospectos import LinhaLista, ListaLida
from .potencial import nota_sql
from .ramos import TIPO_EMPRESA, TIPO_MEI, classificar_tipo, normalizar_porte, ramo_por_cnae

# Linhas por comando de gravação. Postgres aceita 65 mil parâmetros por comando (1.000 x ~19 colunas = 19 mil);
# o SQLite de desenvolvimento, em versões antigas, só 999 — fica com um bloco menor.
_BLOCO_POSTGRES = 1000
_BLOCO_SQLITE = 400

# Colunas que a listagem aceita para ordenar (nada vem direto da URL).
_ORDENAVEIS = {
    "razaoSocial": Prospecto.razao_social,
    "ramo": Prospecto.ramo,
    "tipo": Prospecto.tipo,
    "porte": Prospecto.porte,
    "capitalSocial": Prospecto.capital_social,
    "bairro": Prospecto.bairro,
    "cidade": Prospecto.cidade,
    "telefone": Prospecto.telefone,
    "situacaoLista": Prospecto.situacao_lista,
    "notaPotencial": nota_sql(Prospecto),
    "situacaoReceita": Prospecto.situacao_receita,
    "socios": Prospecto.socios,
    "status": Prospecto.status,
}


def _cnpjs_da_carteira(db: Session) -> set[str]:
    """CNPJs (só dígitos) de quem já é cliente — o cadastro os guarda formatados."""
    return {normalizar_cnpj(c) for (c,) in db.query(Cliente.cnpj).filter(Cliente.cnpj.isnot(None)) if c}


def _campos_da_lista(linha: LinhaLista, arquivo: str | None, clientes: set[str]) -> dict:
    """Só os campos que vêm da lista — nunca os "donos do app"."""
    return {
        "razao_social": linha.razao_social,
        "capital_social": linha.capital_social,
        "porte": normalizar_porte(linha.porte),
        "situacao_lista": linha.situacao or None,
        "cnae_codigo": linha.cnae or None,
        "ramo": ramo_por_cnae(linha.cnae),
        "tipo": classificar_tipo(linha.razao_social),
        "logradouro": linha.logradouro or None,
        "numero": linha.numero or None,
        "bairro": linha.bairro or None,
        "cep": linha.cep or None,
        "cidade": linha.cidade or None,
        "uf": linha.uf or None,
        "telefone": linha.telefone or None,
        "email": linha.email or None,
        "ja_cliente": linha.cnpj in clientes,
        "lote": arquivo,
    }


def _gravar_em_blocos(db: Session, linhas: list[dict]) -> None:
    """Grava as linhas com UPSERT (insere o CNPJ novo, atualiza o que já existe),
    em blocos (ver _BLOCO_*).

    Por que não `bulk_insert_mappings`: ele quebra as linhas em grupos pelas
    colunas que estão vazias, e uma lista real vira mais de mil comandos
    separados. Com o banco a centenas de milissegundos de distância isso leva
    minutos e o servidor derruba a requisição (visto em produção). Aqui todas
    as linhas têm as mesmas colunas, então são ~13 comandos para 12 mil linhas.

    No conflito, só as colunas que vêm da lista são atualizadas — status,
    motivo, observação e a conferência da Receita nunca são tocados.
    """
    if not linhas:
        return
    postgres = db.get_bind().dialect.name == "postgresql"
    inserir = insert_pg if postgres else insert_sqlite
    bloco = _BLOCO_POSTGRES if postgres else _BLOCO_SQLITE
    colunas_da_lista = [c for c in linhas[0] if c not in ("cnpj", "status")]
    for i in range(0, len(linhas), bloco):
        comando = inserir(Prospecto).values(linhas[i:i + bloco])
        atualizar = {c: comando.excluded[c] for c in colunas_da_lista}
        atualizar["atualizado_em"] = func.now()
        db.execute(comando.on_conflict_do_update(index_elements=["cnpj"], set_=atualizar))


def aplicar_lista(db: Session, lista: ListaLida, arquivo: str | None) -> dict:
    """Grava a lista (novos entram, existentes são atualizados) e devolve o resumo.

    Não dá commit: quem chama decide.
    """
    clientes = _cnpjs_da_carteira(db)
    existentes = {cnpj for (cnpj,) in db.query(Prospecto.cnpj)}

    novos, atualizados = [], []
    for linha in lista.linhas:
        campos = {"cnpj": linha.cnpj, "status": StatusProspecto.NOVO, **_campos_da_lista(linha, arquivo, clientes)}
        (atualizados if linha.cnpj in existentes else novos).append(campos)

    _gravar_em_blocos(db, novos + atualizados)

    todos = novos + atualizados
    tipos = Counter(c["tipo"] for c in todos)
    ramos: dict[str, dict] = {}
    for c in todos:
        r = ramos.setdefault(c["ramo"], {"ramo": c["ramo"], "total": 0, "empresas": 0})
        r["total"] += 1
        r["empresas"] += c["tipo"] == TIPO_EMPRESA
    return {
        "linhasNoArquivo": len(lista.linhas) + lista.invalidas + lista.repetidas,
        "invalidas": lista.invalidas,
        "repetidas": lista.repetidas,
        "novos": len(novos),
        "atualizados": len(atualizados),
        "jaClientes": sum(1 for c in todos if c["ja_cliente"]),
        "empresas": tipos[TIPO_EMPRESA],
        "meiAutonomos": tipos[TIPO_MEI],
        "situacaoNoArquivo": dict(Counter(c["situacao_lista"] or "sem dado" for c in todos)),
        "cidades": [{"cidade": k or "sem cidade", "total": v}
                    for k, v in Counter(c["cidade"] for c in todos).most_common(8)],
        "ramos": sorted(ramos.values(), key=lambda r: -r["total"]),
    }


# ------------------------------------------------------------------ consulta

def _cnpjs_clientes_sql():
    """Subconsulta com o CNPJ (só dígitos) de TODO cliente do cadastro, ativo ou
    inativo — o cadastro guarda formatado ("11.111.111/0001-11")."""
    limpo = func.replace(func.replace(func.replace(Cliente.cnpj, ".", ""), "/", ""), "-", "")
    return select(limpo).where(Cliente.cnpj.isnot(None))


def _condicao_situacao(situacao: str):
    """Filtro pela situação NA RECEITA (não a que vem escrita no arquivo).

    ""  (padrão)   ativas + ainda não conferidas — o que "vale mostrar"
    "ativa"        só as que a Receita confirmou como ativas
    "nao_conferida" ainda sem consulta
    "nao_ativa"    baixadas, inaptas, suspensas e não encontradas — o que fica escondido
    "todas"        sem filtro
    """
    sr = Prospecto.situacao_receita
    if situacao == "todas":
        return None
    if situacao == "ativa":
        return sr == "ATIVA"
    if situacao == "nao_conferida":
        return sr.is_(None)
    if situacao == "nao_ativa":
        return sr.isnot(None) & (sr != "ATIVA")
    return sr.is_(None) | (sr == "ATIVA")


def _base(db: Session, cidade: str | None, incluir_clientes: bool = False, situacao: str = ""):
    """Prospectos que valem ser mostrados.

    Fora, sempre: quem é cliente (inclusive o inativo — empresa que fechou não é
    alvo de prospecção) e o que a equipe descartou. A checagem é feita AGORA,
    contra o cadastro, e não pela marca `ja_cliente` gravada na importação:
    quem foi cadastrado ou inativado depois da importação sai da lista na hora,
    sem esperar uma nova importação. Por padrão também fica de fora quem a
    Receita já confirmou que NÃO está ativa (ver `_condicao_situacao`).
    """
    q = db.query(Prospecto).filter(Prospecto.status != StatusProspecto.DESCARTADO)
    if not incluir_clientes:
        q = q.filter(Prospecto.cnpj.not_in(_cnpjs_clientes_sql()))
    condicao = _condicao_situacao(situacao)
    if condicao is not None:
        q = q.filter(condicao)
    if cidade:
        q = q.filter(Prospecto.cidade == cidade.strip().upper())
    return q


def resumo(db: Session, cidade: str | None = None) -> dict:
    """Números para a tela: tamanho da lista, e o que sobra por ramo depois de
    tirar quem já é cliente e quem a Receita disse que fechou. Filtrar por
    cidade vale para tudo, menos para a lista de cidades (senão não dá para
    trocar de cidade)."""
    total_lista = db.query(func.count(Prospecto.id)).scalar() or 0
    ja_clientes = (
        db.query(func.count(Prospecto.id)).filter(Prospecto.cnpj.in_(_cnpjs_clientes_sql())).scalar() or 0
    )

    cidades = [
        {"cidade": c or "sem cidade", "total": n}
        for c, n in db.query(Prospecto.cidade, func.count(Prospecto.id))
        .filter(Prospecto.status != StatusProspecto.DESCARTADO)
        .filter(Prospecto.cnpj.not_in(_cnpjs_clientes_sql()))
        .filter(_condicao_situacao(""))
        .group_by(Prospecto.cidade).order_by(func.count(Prospecto.id).desc())
    ]

    def soma(condicao):
        return func.coalesce(func.sum(cast(case((condicao, 1), else_=0), Integer)), 0)

    linhas = (
        _base(db, cidade)
        .with_entities(
            Prospecto.ramo,
            func.count(Prospecto.id),
            soma(Prospecto.tipo == TIPO_EMPRESA),
            soma((Prospecto.tipo == TIPO_EMPRESA) & (Prospecto.porte == "Micro")),
            soma((Prospecto.tipo == TIPO_EMPRESA) & (Prospecto.porte == "Pequena")),
            soma((Prospecto.tipo == TIPO_EMPRESA) & (Prospecto.porte == "Demais")),
        )
        .group_by(Prospecto.ramo)
        .all()
    )
    ramos = [
        {"ramo": r or "Outros", "total": t, "empresas": e, "micro": mi, "pequena": pe, "demais": de}
        for r, t, e, mi, pe, de in linhas
    ]
    ramos.sort(key=lambda r: -r["empresas"])
    return {
        "totalNaLista": total_lista,
        "jaClientes": ja_clientes,
        "naCidade": sum(r["total"] for r in ramos),
        "empresasNaCidade": sum(r["empresas"] for r in ramos),
        # fechadas segundo a Receita: ficam escondidas, mas a conta aparece
        "escondidasNaoAtivas": _base(db, cidade, situacao="nao_ativa").count(),
        "confirmadasAtivas": _base(db, cidade, situacao="ativa").count(),
        "cidades": cidades,
        "ramos": ramos,
    }


def filtrar(
    db: Session, *, cidade=None, ramo=None, tipo=None, porte=None, status=None, busca=None, situacao="",
    nota_min=None,
):
    q = _base(db, cidade, situacao=situacao)
    if nota_min:
        q = q.filter(nota_sql(Prospecto) >= nota_min)
    if ramo:
        q = q.filter(Prospecto.ramo == ramo)
    if tipo:
        q = q.filter(Prospecto.tipo == tipo)
    if porte:
        q = q.filter(Prospecto.porte == porte)
    if status:
        q = q.filter(Prospecto.status == status)
    if busca and len(busca.strip()) >= 2:
        termo = f"%{busca.strip()}%"
        q = q.filter(or_(
            Prospecto.razao_social.ilike(termo),
            Prospecto.cnpj.ilike(f"%{normalizar_cnpj(busca) or busca.strip()}%"),
            Prospecto.bairro.ilike(termo),
        ))
    return q


def listar(
    db: Session, *, ordenar="razaoSocial", direcao="asc", pagina=1, tamanho=50, **filtros,
) -> tuple[list[Prospecto], int]:
    q = filtrar(db, **filtros)
    total = q.count()
    coluna = _ORDENAVEIS.get(ordenar, Prospecto.razao_social)
    ordem = coluna.desc() if direcao == "desc" else coluna.asc()
    # "nulos por último" nos dois sentidos, e o id de desempate mantém a
    # paginação estável quando muitas linhas têm o mesmo valor
    q = q.order_by(coluna.is_(None), ordem, Prospecto.id)
    itens = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
    return itens, total


def pendentes_de_conferencia(db: Session, limite: int | None = None, **filtros):
    """Os que o filtro mostra e a Receita ainda não conferiu — os de maior capital
    primeiro, que são os que mais interessam."""
    filtros["situacao"] = "nao_conferida"
    q = filtrar(db, **filtros)
    total = q.count()
    if limite is None:
        return total
    lista = q.order_by(Prospecto.capital_social.is_(None), Prospecto.capital_social.desc(), Prospecto.id).limit(limite).all()
    return lista, total


def para_saida(p: Prospecto) -> dict:
    from .potencial import calcular_nota, descricao_das_partes
    nota, partes = calcular_nota(ramo=p.ramo, tipo=p.tipo, capital=p.capital_social, porte=p.porte)
    return {
        "notaPotencial": nota,
        "potencialDetalhe": descricao_das_partes(partes),
        "id": p.id,
        "cnpj": p.cnpj,
        "razaoSocial": p.razao_social,
        "capitalSocial": p.capital_social,
        "porte": p.porte,
        "ramo": p.ramo,
        "tipo": p.tipo,
        "logradouro": p.logradouro,
        "numero": p.numero,
        "bairro": p.bairro,
        "cep": p.cep,
        "cidade": p.cidade,
        "uf": p.uf,
        "telefone": p.telefone,
        "email": p.email,
        "situacaoLista": p.situacao_lista,
        "situacaoReceita": p.situacao_receita,
        "verificadoEm": p.verificado_em.isoformat() if p.verificado_em else None,
        "socios": p.socios,
        "status": p.status.value if p.status else None,
        "lote": p.lote,
    }


# ------------------------------------------------------------------ levar para a carteira

LIMITE_POR_CHAMADA = 500


def _cnpj_formatado(digitos: str) -> str:
    """A carteira guarda o CNPJ formatado ("11.111.111/0001-11"); a lista, só dígitos."""
    d = normalizar_cnpj(digitos)
    if len(d) != 14:
        return digitos
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def levar_para_carteira(db: Session, prospectos: list[Prospecto]) -> dict:
    """Vira cliente novo (origem NOVO) cada prospecto recebido, com a nota de potencial.

    A localização no mapa é feita depois, em lotes (ver geocodificacao.py): sem
    coordenada o cliente existe, mas ainda não aparece no mapa nem na rota.
    Quem já é cliente é pulado — nunca cria duplicata pelo mesmo CNPJ.
    """
    ja = _cnpjs_da_carteira(db)
    criados = pulados = 0
    for p in prospectos[:LIMITE_POR_CHAMADA]:
        if p.cnpj in ja:
            pulados += 1
            continue
        endereco = ", ".join(x for x in (p.logradouro, p.numero) if x) or None
        db.add(Cliente(
            cnpj=_cnpj_formatado(p.cnpj),
            nome=p.razao_social,
            endereco=endereco,
            bairro=p.bairro,
            cep=p.cep,
            cidade=p.cidade,
            uf=p.uf,
            telefone=p.telefone,
            email=p.email,
            porte=p.porte,
            capital_social=p.capital_social,
            ramo=p.ramo,
            # quem provavelmente decide a compra, vindo da conferência na Receita
            contato_nome=(p.socios.split(";")[0].strip() if p.socios else None),
            origem=OrigemCliente.NOVO,
            status=StatusCliente.ATIVO,
            aceita_visita=True,
        ))
        p.status = StatusProspecto.VALE_VISITA
        ja.add(p.cnpj)
        criados += 1
    return {"criados": criados, "jaEramClientes": pulados, "acimaDoLimite": max(0, len(prospectos) - LIMITE_POR_CHAMADA)}
