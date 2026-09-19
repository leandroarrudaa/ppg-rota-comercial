"""Agrupamento de atividades (CNAE) em "ramos" e classificação do tipo de cadastro.

Os ramos são os mesmos grupos usados na análise do perfil dos clientes ouro.
A lista de prospectos (extração da Receita) traz o CNAE só como CÓDIGO
(ex.: 4744001), sem descrição — por isso o agrupamento aqui é por prefixo de
código, do mais específico para o mais geral: a primeira regra que casar vence.

Este agrupamento é uma primeira proposta. A prioridade de cada ramo (alta,
média, baixa, fora) é decisão de negócio e fica para ser editada na tela.
"""
from __future__ import annotations

import re
import unicodedata

RAMO_OUTROS = "Outros"

# (ramo, prefixos de código CNAE). Ordem importa: específico antes do geral.
_REGRAS: list[tuple[str, tuple[str, ...]]] = [
    ("Ar-condicionado / refrigeração", ("4322302", "2825", "2823")),
    ("Elétrica (instalação/manutenção)", ("4321500",)),
    # incorporação imobiliária cai em "Condomínios / imobiliário", não em obras
    ("Condomínios / imobiliário", ("4110700", "68", "8112", "8111")),
    ("Construção civil / obras", ("41", "42", "43", "7112")),
    ("Metalurgia / serralheria / esquadrias", ("24", "25", "3250")),
    ("Manutenção / montagem industrial", ("33",)),
    ("Fabricação de máquinas / equipamentos", ("27", "28")),
    ("Móveis / madeira", ("16", "31")),
    ("Comércio de peças/veículos", ("4530", "4541", "4511", "4512", "4513", "4731")),
    ("Oficina / serviço de veículos", ("4520", "9529")),
    ("Varejo de ferragens / construção / elétrico", ("4744", "4742", "4741", "4743")),
    ("Varejo (outros)", ("47",)),
    ("Atacado", ("46",)),
    ("Transporte", ("49", "52")),
    ("Religioso / associações / clubes", ("94", "9312", "9313")),
]

RAMOS = [r for r, _ in _REGRAS] + [RAMO_OUTROS]


def normalizar_codigo_cnae(valor) -> str:
    """Devolve só os dígitos do código, com 7 posições ("4744001").

    O Excel costuma guardar o código como número (perdendo zeros à esquerda)
    ou como texto "47.44-0-01"; os dois casos viram a mesma coisa.
    """
    if isinstance(valor, float):
        valor = int(valor)
    digitos = re.sub(r"\D", "", str(valor if valor is not None else ""))
    return digitos.zfill(7)[:7] if digitos else ""


def ramo_por_cnae(codigo) -> str:
    cod = normalizar_codigo_cnae(codigo)
    if not cod:
        return RAMO_OUTROS
    for ramo, prefixos in _REGRAS:
        if cod.startswith(prefixos):
            return ramo
    return RAMO_OUTROS


# A carteira antiga guarda o CNAE como DESCRIÇÃO ("Instalação e manutenção elétrica"),
# não como código. Mesmos ramos, casados por palavras-chave da descrição (a primeira
# que casar vence). Foi a regra usada na análise do perfil dos clientes ouro.
_REGRAS_DESCRICAO: list[tuple[str, str]] = [
    ("Religioso / associações / clubes", r"religios|associa|clubes|defesa|sindic"),
    ("Condomínios / imobiliário", r"condominio|imobiliari|incorporacao"),
    ("Elétrica (instalação/manutenção)", r"instalacao e manutencao eletrica|instalacoes eletricas"),
    ("Oficina / serviço de veículos",
     r"(manutencao|reparacao|lanternagem|acessorios).*(veiculos|motocicletas)|veiculos automotores$"),
    ("Comércio de peças/veículos", r"comercio.*(pecas e acessorios|automoveis|motocicletas)|combustiveis"),
    ("Construção civil / obras",
     r"construcao|obras|engenharia|terraplenagem|fundacoes|pintura de edificios|acabamento|alvenaria"),
    ("Metalurgia / serralheria / esquadrias",
     r"serralheria|estruturas metalicas|esquadrias|produtos de metal|movel.*metal|usinagem|letreiros"),
    ("Manutenção / montagem industrial",
     r"montagem industrial|usos industriais|instalacao de maquinas|manutencao e reparacao de maquinas|"
     r"manutencao e reparacao de (aparelhos|equipamentos|veiculos ferro)|aluguel de outras maquinas"),
    ("Fabricação de máquinas / equipamentos", r"fabricacao de (outras )?(maquinas|aparelhos)"),
    ("Móveis / madeira", r"moveis|madeira|serrarias"),
    ("Ar-condicionado / refrigeração", r"ar condicionado|refrigeracao"),
    ("Varejo de ferragens / construção / elétrico", r"ferragens|materiais de construcao|material eletrico|vidros"),
    ("Atacado", r"atacadista"),
    ("Transporte", r"transporte"),
    ("Varejo (outros)", r"comercio varejista"),
]


def ramo_por_descricao(descricao) -> str:
    """Ramo a partir da descrição do CNAE (o formato guardado na carteira)."""
    texto = _sem_acento_maiusculo(descricao).lower()
    if not texto.strip():
        return RAMO_OUTROS
    for ramo, regra in _REGRAS_DESCRICAO:
        if re.search(regra, texto):
            return ramo
    return RAMO_OUTROS


# ------------------------------------------------------------------ tipo de cadastro

TIPO_EMPRESA = "empresa"
TIPO_MEI = "mei_autonomo"

# Sufixos e palavras que só aparecem em razão social de empresa de verdade.
_FORMA_JURIDICA = re.compile(
    r"\b(LTDA|LTDA\.|EIRELI|EIRELE|S/A|S\.A\.?|SA|SLU|EPP|SOCIEDADE|ASSOCIACAO|COOPERATIVA|"
    r"CONDOMINIO|FUNDACAO|SINDICATO|IGREJA|PAROQUIA|COMPANHIA|CIA|& CIA|E CIA)\b"
)
_PALAVRA_DE_EMPRESA = re.compile(
    r"\b(COMERCIO|COMERCIAL|INDUSTRIA|INDUSTRIAL|SERVICOS|SERVICO|CONSTRUCAO|CONSTRUCOES|"
    r"CONSTRUTORA|ENGENHARIA|MATERIAIS|MAQUINAS|EQUIPAMENTOS|SOLUCOES|EMPREENDIMENTOS|"
    r"INCORPORADORA|TRANSPORTES|DISTRIBUIDORA|IMPORTACAO|EXPORTACAO|MANUTENCAO|"
    r"METALURGICA|MECANICA|ELETRICA|AUTO PECAS|MOVEIS|MADEIRAS|ESTRUTURAS|"
    r"INSTALACOES|MONTAGENS|REPRESENTACOES|ASSESSORIA|CONSULTORIA|TECNOLOGIA)\b"
)
# CPF (11 dígitos) ou raiz do CNPJ escrita no nome: "JOAO DA SILVA 12345678901",
# "12.498.009 CATARINA ..." — é como a Receita nomeia o MEI.
_DOCUMENTO_NO_NOME = re.compile(r"\b\d{11}\b|^\d{2}\.?\d{3}\.?\d{3}\s")


def _sem_acento_maiusculo(texto: str) -> str:
    base = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in base if unicodedata.category(c) != "Mn").upper()


def classificar_tipo(razao_social: str) -> str:
    """empresa | mei_autonomo.

    MEI e autônomo têm o dono fazendo o serviço — o perfil que a equipe evita
    visitar. Não há um campo de natureza jurídica na lista, então isto é uma
    heurística pelo NOME: documento escrito no nome, ou nome de pessoa sem
    forma jurídica nem palavra de negócio, é tratado como MEI/autônomo.
    """
    nome = _sem_acento_maiusculo(razao_social)
    if _DOCUMENTO_NO_NOME.search(nome):
        return TIPO_MEI
    if _FORMA_JURIDICA.search(nome) or _PALAVRA_DE_EMPRESA.search(nome):
        return TIPO_EMPRESA
    if re.search(r"(\s|-)ME$", nome) and not nome.endswith(" MEI"):
        return TIPO_EMPRESA
    return TIPO_MEI


def normalizar_porte(texto) -> str:
    """"MICRO EMPRESA" -> Micro; "EMPRESA DE PEQUENO PORTE" -> Pequena; "DEMAIS" -> Demais."""
    t = _sem_acento_maiusculo(texto)
    if "MICRO" in t:
        return "Micro"
    if "PEQUENO" in t:
        return "Pequena"
    if "DEMAIS" in t or "MEDIO" in t or "GRANDE" in t:
        return "Demais"
    return "Sem dado"
