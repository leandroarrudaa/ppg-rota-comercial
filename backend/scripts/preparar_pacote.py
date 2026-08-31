#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o pacote de atualização a partir do banco mestre.

O banco_mestre.db tem 139 MB; o pacote sai com poucos MB. É ele que sobe pela
tela de importação do app — assim ninguém precisa lidar com senha de banco nem
mandar um arquivo enorme para um serviço de plano gratuito.

Uso:
    python backend/scripts/preparar_pacote.py
    python backend/scripts/preparar_pacote.py "D:/outro/banco_mestre.db"
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.services.fontes import banco_mestre, pacote  # noqa: E402

RAIZ = os.path.dirname(BACKEND_DIR)
BANCO_MESTRE_PADRAO = os.path.join(os.path.dirname(RAIZ), "output", "banco_mestre.db")
SAIDA_PADRAO = os.path.join(RAIZ, "pacote-atualizacao.ppg")


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    caminho = argumentos[0] if argumentos else BANCO_MESTRE_PADRAO
    saida = argumentos[1] if len(argumentos) > 1 else SAIDA_PADRAO

    print(f"Lendo o banco mestre: {caminho}")
    try:
        # Manda TUDO, inclusive as vendas sem nome de cliente na nota. Este
        # script roda no escritório e não fala com o banco do app, então não
        # tem como saber quem já é cliente — quem filtra é o servidor, que
        # sabe. Foi o que fez 58 clientes reais ficarem de fora numa versão
        # anterior deste fluxo.
        carteira = banco_mestre.ler_carteira(caminho, incluir_genericos=True)
        historico = banco_mestre.ler_historico_itens(caminho)
        depara = banco_mestre.ler_depara_codigo_cnpj(caminho)
    except banco_mestre.BancoMestreInvalido as erro:
        print(f"\nERRO: {erro}")
        sys.exit(1)

    print(f"  empresas com compra : {len(carteira)}")
    print(f"  linhas de histórico : {len(historico)}")
    print(f"  códigos no de-para  : {len(depara)}")

    if not carteira:
        print("\nERRO: o banco mestre não tem nenhuma venda para cliente com CNPJ.")
        sys.exit(1)

    ultima = max((r["ultima_compra"] for r in carteira if r["ultima_compra"]), default=None)
    if ultima:
        print(f"  venda mais recente  : {ultima:%d/%m/%Y}")

    tamanho = pacote.escrever(saida, carteira=carteira, historico=historico, depara=depara)
    print(f"\nPacote gerado: {saida}")
    print(f"Tamanho: {tamanho / 1_048_576:.1f} MB")
    print("\nAgora abra o app, vá em Vínculos > Importar e envie esse arquivo.")


if __name__ == "__main__":
    main()
