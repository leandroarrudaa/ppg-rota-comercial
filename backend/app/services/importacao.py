"""Upsert de clientes vindos do pipeline (carteira antiga).

Separado do script de carga pra ser testável sem precisar de CSV real: quem
chama passa uma lista de dicts já no formato de CAMPOS_PIPELINE + "cnpj".
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


def aplicar_vendas(db: Session, registros: list[dict]) -> RelatorioAtualizacao:
    """Atualiza SÓ os números de venda/RFM dos clientes que já existem.

    Não cria cliente e não altera nada fora de CAMPOS_VENDAS — um CNPJ que
    aparece nas vendas mas não está na carteira é DEVOLVIDO no relatório para
    decisão humana, nunca criado no escuro (cliente sem endereço não aparece no
    mapa e viraria lixo invisível na base).

    Não dá commit: quem chama decide, e é isso que torna a simulação possível
    (roda tudo, lê o relatório, desfaz).
    """
    relatorio = RelatorioAtualizacao()

    existentes = {}
    for cliente in db.query(Cliente).filter(Cliente.origem == OrigemCliente.ANTIGO).all():
        chave = normalizar_cnpj(cliente.cnpj)
        if chave:
            existentes[chave] = cliente

    vistos = set()
    for reg in registros:
        chave = normalizar_cnpj(reg.get("cnpj"))
        if not chave:
            continue
        cliente = existentes.get(chave)
        if cliente is None:
            relatorio.sem_cliente_na_carteira.append(reg.get("nome") or chave)
            continue
        vistos.add(chave)

        faixa_antes, risco_antes = cliente.faixa, cliente.em_risco
        ultima_antes = cliente.ultima_compra

        for campo in CAMPOS_VENDAS:
            if campo in reg:
                setattr(cliente, campo, reg[campo])

        if faixa_antes != cliente.faixa:
            relatorio.mudou_faixa.append((cliente.nome, faixa_antes or "—", cliente.faixa or "—"))
        if risco_antes and not cliente.em_risco:
            relatorio.saiu_de_risco.append(cliente.nome)
        elif not risco_antes and cliente.em_risco:
            relatorio.entrou_em_risco.append(cliente.nome)
        if ultima_antes and cliente.ultima_compra and cliente.ultima_compra > ultima_antes:
            relatorio.recencia_corrigida += 1
        relatorio.atualizados += 1

    relatorio.sem_venda_no_periodo = len(set(existentes) - vistos)
    return relatorio
