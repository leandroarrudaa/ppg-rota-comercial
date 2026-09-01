"""Upsert de clientes vindos do pipeline (carteira antiga).

Separado do script de carga pra ser testável sem precisar de CSV real: quem
chama passa uma lista de dicts já no formato de CAMPOS_PIPELINE + "cnpj".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from ..models import Cliente, OrigemCliente
from .cnpj import normalizar_cnpj

# Campos que a reimportação PODE atualizar (dados do pipeline).
# Tudo que não está aqui (status, aceita_visita, motivo_recusa_visita,
# contato_nome, contato_celular, cliente_mestre_id) é preservado.
CAMPOS_PIPELINE = [
    "nome", "endereco", "bairro", "cep", "cidade", "uf",
    "lat", "lng", "geo_status",
    "faixa", "em_risco", "fat_total", "no_compras", "ticket_medio",
    "recencia_dias", "cadencia_dias", "ultima_compra",
    "r", "f", "m", "rfm_score",
    "porte", "capital_social", "cnae", "telefone", "email",
]


def upsert_clientes_antigos(db: Session, registros: list[dict]) -> dict:
    """Cria/atualiza clientes origem=ANTIGO a partir dos registros do pipeline.

    Cada registro precisa ter "cnpj" + todas as chaves de CAMPOS_PIPELINE.
    Devolve {"criados": N, "atualizados": N} sem dar commit (quem chama decide).
    """
    existentes = {
        normalizar_cnpj(c.cnpj): c
        for c in db.query(Cliente).filter(Cliente.origem == OrigemCliente.ANTIGO).all()
        if c.cnpj
    }
    criados = atualizados = 0
    for reg in registros:
        chave = normalizar_cnpj(reg.get("cnpj"))
        if not chave:
            continue
        existente = existentes.get(chave)
        if existente is None:
            dados = {k: reg[k] for k in CAMPOS_PIPELINE}
            db.add(Cliente(origem=OrigemCliente.ANTIGO, cnpj=reg["cnpj"], **dados))
            criados += 1
        else:
            for campo in CAMPOS_PIPELINE:
                setattr(existente, campo, reg[campo])
            atualizados += 1
    return {"criados": criados, "atualizados": atualizados}


# Colunas que uma atualização de VENDAS pode tocar. É um conjunto bem menor que
# CAMPOS_PIPELINE de propósito: o banco mestre e o relatório do ERP só sabem
# sobre compras. Endereço, coordenada, telefone e porte vêm de outras origens
# (geocodificação e BrasilAPI) e seriam APAGADOS se entrassem aqui — foi o que
# motivou separar os dois caminhos em vez de reaproveitar o upsert do pipeline.
CAMPOS_VENDAS = [
    "no_compras", "fat_total", "ticket_medio", "ultima_compra",
    "recencia_dias", "cadencia_dias",
    "r", "f", "m", "rfm_score", "faixa", "em_risco",
]


@dataclass
class RelatorioAtualizacao:
    """O que uma atualização de vendas fez (ou faria, em simulação).

    Serve tanto para o resumo impresso no terminal quanto para a prévia que o
    gerente confirma antes de gravar.
    """
    atualizados: int = 0
    sem_cliente_na_carteira: list[str] = field(default_factory=list)
    sem_venda_no_periodo: int = 0
    mudou_faixa: list[tuple[str, str, str]] = field(default_factory=list)
    saiu_de_risco: list[str] = field(default_factory=list)
    entrou_em_risco: list[str] = field(default_factory=list)
    recencia_corrigida: int = 0

    def resumo(self) -> dict:
        return {
            "atualizados": self.atualizados,
            "semClienteNaCarteira": len(self.sem_cliente_na_carteira),
            "semVendaNoPeriodo": self.sem_venda_no_periodo,
            "mudouFaixa": len(self.mudou_faixa),
            "saiuDeRisco": len(self.saiu_de_risco),
            "entrouEmRisco": len(self.entrou_em_risco),
            "recenciaCorrigida": self.recencia_corrigida,
        }


# Quantas linhas por comando nas gravações em massa. Ver TAMANHO_BLOCO em
# services/atualizacao.py — mesma razão.
TAMANHO_BLOCO = 2_000


def gravar_clientes_em_lote(db: Session, atualizacoes: list[dict]) -> None:
    """Grava as alterações de cliente em poucos comandos, não um por cliente.

    O ORM emite um UPDATE por objeto alterado. Com 1.257 clientes mudando, isso
    virava 426 comandos — e o banco fica a ~330ms do servidor, então dava 149
    segundos só de ida e volta, acima do limite de uma requisição HTTP. Era por
    isso que o "confirmar" da tela caía enquanto a prévia passava: a prévia não
    escreve nada.

    Todas as linhas carregam as MESMAS chaves de propósito: assim o SQLAlchemy
    agrupa tudo em poucos comandos em vez de um por combinação de colunas.
    """
    if not atualizacoes:
        return
    for inicio in range(0, len(atualizacoes), TAMANHO_BLOCO):
        db.bulk_update_mappings(Cliente, atualizacoes[inicio:inicio + TAMANHO_BLOCO])


def _carregar_carteira(db: Session) -> dict[str, dict]:
    """Clientes da carteira antiga como dicionários leves, indexados por CNPJ.

    Só as colunas usadas — carregar objetos completos do ORM para depois
    alterá-los é o que gerava a enxurrada de UPDATEs individuais.
    """
    colunas = ("id", "nome", "faixa", "em_risco", "ultima_compra",
               "primeira_compra", "no_compras", "fat_total")
    carteira = {}
    for linha in db.query(Cliente.cnpj, *(getattr(Cliente, c) for c in colunas)).filter(
        Cliente.origem == OrigemCliente.ANTIGO
    ):
        chave = normalizar_cnpj(linha[0])
        if chave:
            carteira[chave] = dict(zip(colunas, linha[1:]))
    return carteira


def aplicar_vendas(db: Session, registros: list[dict]) -> RelatorioAtualizacao:
    """Atualiza SÓ os números de venda/RFM dos clientes que já existem.

    Não cria cliente e não altera nada fora de CAMPOS_VENDAS — um CNPJ que
    aparece nas vendas mas não está na carteira é DEVOLVIDO no relatório para
    decisão humana, nunca criado no escuro (cliente sem endereço não aparece no
    mapa e viraria lixo invisível na base).

    Não dá commit: quem chama decide, e é isso que torna a prévia possível
    (roda tudo, lê o relatório, desfaz).
    """
    relatorio = RelatorioAtualizacao()
    carteira = _carregar_carteira(db)

    vistos = set()
    atualizacoes = []
    for reg in registros:
        chave = normalizar_cnpj(reg.get("cnpj"))
        if not chave:
            continue
        atual = carteira.get(chave)
        if atual is None:
            relatorio.sem_cliente_na_carteira.append(reg.get("nome") or chave)
            continue
        vistos.add(chave)

        novos_valores = {campo: reg[campo] for campo in CAMPOS_VENDAS if campo in reg}
        # a primeira compra só o banco mestre conhece; o relatório diário não
        if reg.get("primeira_compra"):
            novos_valores["primeira_compra"] = reg["primeira_compra"]

        if reg.get("faixa") != atual["faixa"]:
            relatorio.mudou_faixa.append(
                (atual["nome"], atual["faixa"] or "—", reg.get("faixa") or "—")
            )
        if atual["em_risco"] and not reg.get("em_risco"):
            relatorio.saiu_de_risco.append(atual["nome"])
        elif not atual["em_risco"] and reg.get("em_risco"):
            relatorio.entrou_em_risco.append(atual["nome"])
        if (atual["ultima_compra"] and reg.get("ultima_compra")
                and reg["ultima_compra"] > atual["ultima_compra"]):
            relatorio.recencia_corrigida += 1

        atualizacoes.append({"id": atual["id"], **novos_valores})
        relatorio.atualizados += 1

    gravar_clientes_em_lote(db, atualizacoes)
    relatorio.sem_venda_no_periodo = len(set(carteira) - vistos)
    return relatorio


@dataclass
class RelatorioVendasDiario:
    """Efeito de um relatório de vendas do ERP sobre a carteira."""
    pedidos_no_arquivo: int = 0
    pedidos_ja_importados: int = 0
    pedidos_novos: int = 0
    pedidos_sem_data: int = 0
    sem_depara: int = 0            # código do ERP sem CNPJ conhecido (CPF/balcão)
    cnpj_fora_da_carteira: int = 0
    clientes_atualizados: int = 0
    faturamento: float = 0.0
    periodo: tuple[date | None, date | None] = (None, None)
    mudou_faixa: list[tuple[str, str, str]] = field(default_factory=list)
    saiu_de_risco: list[str] = field(default_factory=list)
    entrou_em_risco: list[str] = field(default_factory=list)
    nomes_fora_da_carteira: list[str] = field(default_factory=list)

    def resumo(self) -> dict:
        inicio, fim = self.periodo
        return {
            "pedidosNoArquivo": self.pedidos_no_arquivo,
            "pedidosJaImportados": self.pedidos_ja_importados,
            "pedidosNovos": self.pedidos_novos,
            "pedidosSemData": self.pedidos_sem_data,
            "semDepara": self.sem_depara,
            "cnpjForaDaCarteira": self.cnpj_fora_da_carteira,
            "clientesAtualizados": self.clientes_atualizados,
            "faturamento": round(self.faturamento, 2),
            "periodoInicio": inicio.isoformat() if inicio else None,
            "periodoFim": fim.isoformat() if fim else None,
            "mudouFaixa": len(self.mudou_faixa),
            "saiuDeRisco": len(self.saiu_de_risco),
            "entrouEmRisco": len(self.entrou_em_risco),
            "nomesForaDaCarteira": self.nomes_fora_da_carteira[:20],
        }


def aplicar_relatorio_vendas(
    db: Session, pedidos: list, faturamento_minimo_risco: float = 0
) -> RelatorioVendasDiario:
    """Soma os pedidos novos no acumulado dos clientes e recalcula o RFM.

    É INCREMENTAL: acrescenta ao que o cliente já tinha, porque o relatório
    traz um período, não o histórico. Por isso a proteção contra duplicidade é
    obrigatória — reenviar o arquivo do mesmo mês dobraria o faturamento de
    todo mundo. Pedido já registrado é simplesmente pulado.

    Pedido cujo código do ERP não tem CNPJ conhecido também é registrado como
    importado: ele é venda de balcão/pessoa física (85% do arquivo), não vai
    virar cliente de carteira nunca, e registrar evita reprocessar de graça.

    Não dá commit — quem chama decide, e é isso que permite a prévia.
    """
    from ..models import MapaCodigoErp, PedidoImportado

    relatorio = RelatorioVendasDiario(pedidos_no_arquivo=len(pedidos))
    datas = [p.data for p in pedidos if p.data]
    relatorio.periodo = (min(datas), max(datas)) if datas else (None, None)
    relatorio.pedidos_sem_data = sum(1 for p in pedidos if not p.data)

    depara = {m.codigo: m.cnpj for m in db.query(MapaCodigoErp).all()}
    ja_importados = {n for (n,) in db.query(PedidoImportado.numero_pedido).all()}

    clientes = {}
    for c in db.query(Cliente).filter(Cliente.origem == OrigemCliente.ANTIGO).all():
        chave = normalizar_cnpj(c.cnpj)
        if chave:
            clientes[chave] = c

    estado_antes = {c.id: (c.faixa, c.em_risco) for c in clientes.values()}
    tocados: set[int] = set()
    fora_da_carteira: set[str] = set()

    for pedido in pedidos:
        if pedido.numero in ja_importados:
            relatorio.pedidos_ja_importados += 1
            continue
        relatorio.pedidos_novos += 1

        cnpj = depara.get(pedido.codigo_cliente)
        db.add(PedidoImportado(
            numero_pedido=pedido.numero, cnpj=cnpj,
            data_pedido=pedido.data, valor=pedido.total,
        ))
        ja_importados.add(pedido.numero)

        if not cnpj:
            relatorio.sem_depara += 1
            continue

        cliente = clientes.get(cnpj)
        if cliente is None:
            fora_da_carteira.add(cnpj)
            if pedido.nome_cliente and pedido.nome_cliente not in relatorio.nomes_fora_da_carteira:
                relatorio.nomes_fora_da_carteira.append(pedido.nome_cliente)
            continue

        cliente.no_compras = (cliente.no_compras or 0) + 1
        cliente.fat_total = round((cliente.fat_total or 0) + pedido.total, 2)
        relatorio.faturamento += pedido.total
        if pedido.data:
            if cliente.ultima_compra is None or pedido.data > cliente.ultima_compra:
                cliente.ultima_compra = pedido.data
            if cliente.primeira_compra is None or pedido.data < cliente.primeira_compra:
                cliente.primeira_compra = pedido.data
        tocados.add(cliente.id)

    relatorio.cnpj_fora_da_carteira = len(fora_da_carteira)
    relatorio.clientes_atualizados = len(tocados)

    # O RFM é por quintil, então mexer em 196 clientes muda a posição relativa
    # de TODOS. Recalcular só os tocados daria notas incoerentes entre si.
    _recalcular_rfm_da_carteira(db, clientes.values(), faturamento_minimo_risco)

    for cliente in clientes.values():
        faixa_antes, risco_antes = estado_antes[cliente.id]
        if faixa_antes != cliente.faixa:
            relatorio.mudou_faixa.append((cliente.nome, faixa_antes or "—", cliente.faixa or "—"))
        if risco_antes and not cliente.em_risco:
            relatorio.saiu_de_risco.append(cliente.nome)
        elif not risco_antes and cliente.em_risco:
            relatorio.entrou_em_risco.append(cliente.nome)

    return relatorio


def _recalcular_rfm_da_carteira(db: Session, clientes, faturamento_minimo_risco: float) -> None:
    """Recalcula notas, faixa e risco de toda a carteira e grava em lote.

    Precisa ser em lote pelo mesmo motivo de gravar_clientes_em_lote: o RFM é
    por quintil, então uma importação diária mexe na nota de quase todo mundo,
    e um UPDATE por cliente não caberia no tempo de uma requisição.
    """
    from . import rfm

    registros = [
        {
            "id": c.id,
            "no_compras": c.no_compras,
            "fat_total": c.fat_total,
            "primeira_compra": c.primeira_compra,
            "ultima_compra": c.ultima_compra,
        }
        for c in clientes
    ]
    rfm.calcular(registros, faturamento_minimo_risco=faturamento_minimo_risco)
    gravar_clientes_em_lote(db, [
        {"id": reg["id"], **{campo: reg[campo] for campo in CAMPOS_VENDAS if campo in reg}}
        for reg in registros
    ])
