"""Configurações da aplicação, lidas de variáveis de ambiente / arquivo .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Caminho absoluto do banco SQLite (pasta backend), independente do diretório atual.
_BANCO_PADRAO = (Path(__file__).resolve().parent.parent / "rota.db").as_posix()


class Configuracoes(BaseSettings):
    # URL do banco. Padrão: SQLite local. Trocar para Postgres ao subir na nuvem.
    database_url: str = f"sqlite:///{_BANCO_PADRAO}"

    # Segredo para assinar os tokens de login. Em produção, definir AUTH_SECRET no .env.
    auth_secret: str = "troque-este-segredo-em-producao-ppg-rota"
    # Validade do login em dias (longo: o app fica logado no celular do vendedor).
    token_dias: int = 60

    # Origem extra liberada no CORS (URL do frontend em produção).
    cors_origem_extra: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


config = Configuracoes()
