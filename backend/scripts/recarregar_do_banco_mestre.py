#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recarrega os números de venda e o RFM da carteira a partir do banco mestre.

O banco mestre (XMLs de NFe) é a fonte mais completa que existe: tem o CNPJ real
e o histórico inteiro. Este script traz de lá o que a carteira do app tem de
desatualizado e recalcula o RFM sobre a carteira toda.

O que ele NÃO faz, de propósito:
  - não cria cliente novo (CNPJ sem cliente na carteira sai listado no relatório);
  - não toca em endereço, coordenada, telefone, porte ou contato;
  - não toca em nada que o app é dono (status, aceita visita, vínculo).

Uso:
    python backend/scripts/recarregar_do_banco_mestre.py --simular
    python backend/scripts/recarregar_do_banco_mestre.py
    python backend/scripts/recarregar_do_banco_mestre.py --com-historico
    python backend/scripts/recarregar_do_banco_mestre.py "D:/outro/banco_mestre.db"
"""
import os
import sys

# permite importar app.* rodando o script de qualquer diretório
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.database import Base, SessaoLocal, engine  # noqa: E402
from app.models import Cliente, HistoricoItemCliente  # noqa: E402
from app.services import rfm  # noqa: E402
from app.services.fontes import banco_mestre  # noqa: E402
from app.services.cnpj import normalizar_cnpj  # noqa: E402
from app.services.importacao import aplicar_vendas  # noqa: E402

# Caminho padrão: pasta output/ do repositório maior, onde o gerador de banco
# mestre publica o arquivo.
BANCO_MESTRE_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(BACKEND_DIR)), "output", "banco_mestre.db"
)


def _linha(titulo=""):
    print(f"\n{'-' * 62}" + (f"\n{titulo}" if titulo else ""))


def sincronizar_historico(db, caminho: str) -> dict:
    """Upsert do histórico por produto (mesma regra do sync_historico_itens.py)."""
    registros = banco_mestre.ler_historico_itens(caminho)
    existentes = {
        (h.cnpj_normalizado, h.codigo_produto): h
        for h in db.query(HistoricoItemCliente).all()
    }
    criados = atualizados = 0
    for reg in registros:
        chave = (reg["cnpj_normalizado"], reg["codigo_produto"])
        atual = existentes.get(chave)
        if atual is None:
            db.add(HistoricoItemCliente(**reg))
            criados += 1
        else:
            for campo, valor in reg.items():
                setattr(atual, campo, valor)
            atualizados += 1
    return {"linhas": len(registros), "criados": criados, "atualizados": atualizados}


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    simular = "--simular" in sys.argv
    com_historico = "--com-historico" in sys.argv
    caminho = argumentos[0] if argumentos else BANCO_MESTRE_PADRAO

    print(f"Banco mestre: {caminho}")
    print("MODO SIMULAÇÃO — nada será gravado.\n" if simular else "")

    Base.metadata.create_all(bind=engine)
    db = SessaoLocal()

    # Quem já é cliente da carteira entra no cálculo mesmo que as notas dele
    # tenham saído sem nome — ver ler_carteira().
    conhecidos = {
        normalizar_cnpj(c) for (c,) in db.query(Cliente.cnpj).filter(Cliente.cnpj.isnot(None))
    }
    conhecidos.discard("")

    try:
        registros = banco_mestre.ler_carteira(caminho, cnpjs_conhecidos=conhecidos)
    except banco_mestre.BancoMestreInvalido as erro:
        db.close()
        print(f"ERRO: {erro}")
        sys.exit(1)

    if not registros:
        print("ERRO: o banco mestre não tem nenhuma venda para cliente com CNPJ.")
        sys.exit(1)

    ultima = max(r["ultima_compra"] for r in registros if r["ultima_compra"])
    print(f"Empresas com compra no banco mestre: {len(registros)}")
    print(f"Venda mais recente: {ultima:%d/%m/%Y}")

    # O RFM é relativo à carteira inteira — os quintis são calculados sobre
    # TODAS as empresas do banco mestre, inclusive as que ainda não estão no
    # app, senão as notas ficariam distorcidas por um recorte arbitrário.
    rfm.calcular(registros)

    try:
        antes_risco = db.query(Cliente).filter(Cliente.em_risco.is_(True)).count()
        relatorio = aplicar_vendas(db, registros)

        _linha("RESULTADO")
        print(f"Clientes atualizados                 : {relatorio.atualizados}")
        print(f"Recência corrigida (compra mais nova): {relatorio.recencia_corrigida}")
        print(f"Mudaram de faixa                     : {len(relatorio.mudou_faixa)}")
        print(f"SAÍRAM de 'em risco' (alarme falso)  : {len(relatorio.saiu_de_risco)}")
        print(f"ENTRARAM em 'em risco'               : {len(relatorio.entrou_em_risco)}")
        print(f"Sem venda no banco mestre            : {relatorio.sem_venda_no_periodo}")
        print(f"CNPJ vendendo mas fora da carteira   : {len(relatorio.sem_cliente_na_carteira)}")
        print(f"Clientes em risco: {antes_risco} antes -> "
              f"{antes_risco - len(relatorio.saiu_de_risco) + len(relatorio.entrou_em_risco)} depois")

        if relatorio.saiu_de_risco:
            _linha("DEIXAM DE SER 'REATIVAR JÁ' (estavam comprando)")
            for nome in relatorio.saiu_de_risco[:15]:
                print(f"   {nome}")

        if relatorio.mudou_faixa:
            _linha("MUDANÇAS DE FAIXA (primeiras 15)")
            for nome, de, para in relatorio.mudou_faixa[:15]:
                print(f"   {de:>6} -> {para:<6}  {nome[:45]}")

        if relatorio.sem_cliente_na_carteira:
            _linha("EMPRESAS QUE COMPRAM MAS NÃO ESTÃO NA CARTEIRA (primeiras 15)")
            print("   (não foram criadas — precisam de endereço/localização antes)")
            for nome in relatorio.sem_cliente_na_carteira[:15]:
                print(f"   {nome[:55]}")

        if com_historico:
            resultado = sincronizar_historico(db, caminho)
            _linha("HISTÓRICO POR PRODUTO")
            print(f"Linhas no banco mestre: {resultado['linhas']} | "
                  f"criadas: {resultado['criados']} | atualizadas: {resultado['atualizados']}")

        if simular:
            db.rollback()
            _linha()
            print("SIMULAÇÃO — nada foi gravado. Rode sem --simular para aplicar.")
        else:
            db.commit()
            _linha()
            print("Gravado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
