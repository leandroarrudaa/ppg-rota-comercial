"""Testes do fuso horário do negócio (app/services/tempo.py).

Reproduz o bug original: o servidor guarda tudo em UTC e roda 3h à frente de
Brasília. Sem o ajuste, uma visita feita às 22h de uma terça (01h de quarta em
UTC) era contada como "quarta" pelo sistema.
"""
from datetime import date, datetime

from app.services import tempo


def test_inicio_do_dia_brasil_em_utc_e_meia_noite_local_mais_3h():
    limite = tempo.inicio_do_dia_brasil_em_utc(date(2026, 8, 24))
    assert limite == datetime(2026, 8, 24, 3, 0, 0)


def test_hoje_brasil_bate_com_utc_no_meio_do_dia(monkeypatch):
    """Longe da virada, a data em Brasília e em UTC coincidem."""
    monkeypatch.setattr(tempo, "agora_utc", lambda: datetime(2026, 8, 24, 15, 0, 0))
    assert tempo.hoje_brasil() == date(2026, 8, 24)


def test_visita_das_22h_de_terca_continua_sendo_terca_em_brasilia(monkeypatch):
    """01h de quarta em UTC == 22h de terça em Brasília — 'hoje' não pode
    virar quarta só porque o relógio do servidor já virou o dia."""
    monkeypatch.setattr(tempo, "agora_utc", lambda: datetime(2026, 8, 26, 1, 0, 0))
    assert tempo.hoje_brasil() == date(2026, 8, 25)


def test_visita_da_1h_da_manha_ja_virou_o_dia_em_brasilia(monkeypatch):
    """Do outro lado da virada: 1h UTC de quarta é 22h de terça, mas 4h UTC de
    quarta já é 1h de quarta em Brasília — o dia já virou."""
    monkeypatch.setattr(tempo, "agora_utc", lambda: datetime(2026, 8, 26, 4, 0, 0))
    assert tempo.hoje_brasil() == date(2026, 8, 26)
