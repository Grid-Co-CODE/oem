# -*- coding: utf-8 -*-
"""Documento anexado à OS precisa ABRIR e BAIXAR (Levi, 11/09/2026 — o ZIP da OS 11458).

A tela que faz isso (`steps/documentos.py`) existe desde julho, e o `api.get_os_anexos` já
classificava por extensão. O que estava quebrado era o caminho entre as duas coisas, no card da
OS, e de dois jeitos diferentes:

  · nos anexos da OS, o documento caía numa caixa de mensagem que mostrava só o NOME;
  · nos anexos das subtarefas, a lista de documentos nascia `[]` CRAVADA no código, e o filtro
    da galeria era apenas "tem url" — então o ZIP ia para a grade de miniaturas, onde a prévia
    falha e não há botão nenhum.

O efeito era o mesmo nos dois: o arquivo aparecia e não saía do app.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from steps.os_detalhe import OsDetalheDialog as D


FOTO = {"nome": "IMG_2201.jpg", "url": "https://s3/x/IMG_2201.jpg", "is_image": True}
ZIP = {"nome": "evidencias.zip", "url": "https://s3/x/evidencias.zip", "is_image": False}
PDF = {"nome": "laudo.pdf", "url": "https://s3/x/laudo.pdf", "is_image": False}
NOTA = {"nome": "observação do técnico", "url": None, "is_image": False}


def test_o_zip_vai_para_documentos_e_nao_para_a_galeria():
    imgs, docs, notas = D._separar_anexos([FOTO, ZIP])
    assert imgs == [FOTO], "só a foto tem prévia"
    assert docs == [ZIP], "o ZIP tem de ter onde ser baixado"
    assert notas == []


def test_a_url_pre_assinada_nao_decide_nada_sozinha():
    """Era este o erro: foto e ZIP chegam do S3 com URL igual, e quem separa é a extensão."""
    imgs, docs, _ = D._separar_anexos([ZIP, PDF, FOTO])
    assert [a["nome"] for a in imgs] == ["IMG_2201.jpg"]
    assert [a["nome"] for a in docs] == ["evidencias.zip", "laudo.pdf"]


def test_anexo_sem_arquivo_e_nota_de_texto():
    # sem URL não há o que baixar; vai para a galeria como célula clicável
    imgs, docs, notas = D._separar_anexos([NOTA])
    assert (imgs, docs) == ([], [])
    assert notas == [NOTA]


def test_os_tres_destinos_convivem():
    imgs, docs, notas = D._separar_anexos([FOTO, ZIP, NOTA, PDF])
    assert (len(imgs), len(docs), len(notas)) == (1, 2, 1)


@pytest.mark.parametrize("lixo", [None, [], [None, "texto solto", 7]])
def test_lista_torta_nao_derruba_o_card(lixo):
    """O card da OS é desenhado por um slot que engole exceção: um item fora do formato faria a
    metade de baixo da tela sumir em silêncio, que é o pior sintoma possível."""
    assert D._separar_anexos(lixo) == ([], [], [])
