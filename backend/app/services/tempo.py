"""Fuso horário do negócio.

O app roda no Brasil, mas o servidor (Render, EUA) e o banco guardam tudo em
UTC. Sem esse ajuste, "hoje" e a data de retorno combinada eram calculadas
pelo relógio do servidor — até 3h à frente do Brasil — e uma visita feita às
22h de terça virava "quarta-feira" no sistema; o "riscado" de quem já foi
visitado na Rota do Dia zerava às 21h em vez de à meia-noite.

O Brasil não observa mais horário de verão desde 2019, então um deslocamento
fixo de -3h (Brasília) é seguro e não precisa de biblioteca de fuso horário.
Se algum dia a base de usuários crescer para outros fusos do país, isso vira
uma preferência por usuário — hoje é uma constante de propósito.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

HORAS_BRASIL_ATRAS_DE_UTC = 3


def agora_utc() -> datetime:
    """Instante atual em UTC, ingênuo (sem tzinfo) — mesmo formato das colunas
    DateTime do banco. Equivalente ao descontinuado datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoje_brasil() -> date:
    """Data de calendário 'hoje', no horário de Brasília — não a data UTC nem
    a data local do servidor."""
    return (agora_utc() - timedelta(hours=HORAS_BRASIL_ATRAS_DE_UTC)).date()


def inicio_do_dia_brasil_em_utc(dia: date) -> datetime:
    """Meia-noite de `dia` no horário de Brasília, convertida para o UTC
    ingênuo usado nas colunas do banco (ex.: Visita.inicio) — o limite certo
    para filtrar 'visitas a partir da meia-noite local'."""
    meia_noite_brasil = datetime.combine(dia, datetime.min.time())
    return meia_noite_brasil + timedelta(hours=HORAS_BRASIL_ATRAS_DE_UTC)
