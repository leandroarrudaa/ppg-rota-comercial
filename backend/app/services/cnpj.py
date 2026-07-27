"""Normalização de CNPJ — função única usada em todo cruzamento de dados.

O banco_mestre.db guarda CNPJ só com dígitos (34904577000140); a base mestra da
carteira usa formatado (34.904.577/0001-40). Todo join entre as duas fontes DEVE
passar por aqui para não reintroduzir o bug de formato.
"""
import re


def normalizar_cnpj(valor: str | None) -> str:
    """Remove tudo que não é dígito. Devolve string vazia para None/vazio."""
    if not valor:
        return ""
    return re.sub(r"\D", "", str(valor))
