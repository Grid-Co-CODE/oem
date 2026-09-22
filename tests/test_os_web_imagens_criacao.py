# -*- coding: utf-8 -*-
"""Anexar imagens na CRIAÇÃO, pela web (21/09).

A web não ganhou caminho de upload próprio: ela passou a preencher `imagens` no item, que é um
campo que o `create_performance_os` já lia — e é ele quem sobe para o S3 DEPOIS de a OS existir
(o anexo é preso à tarefa; subir antes seria arquivo órfão no S3). O mesmo caminho do app de mesa,
inclusive a contagem de erro por imagem que volta no resultado."""
import base64
import io
import os

from os_web import perf_web

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"x" * 64
PNG = base64.b64encode(_PNG_BYTES).decode()
_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "os_creator", "os_web", "static", "perf.js")


def _corpo(imagens):
    return {"itens": [{"asset": {"id": 1, "code": "INV1", "label": "INV1 — Inversor 1"},
                       "plano_id_task": 9, "plano_id_item": 1, "imagens": imagens}],
            "responsavel": {"id_personnel": 7, "name": "Fulano"},
            "evento": "2026-09-21T08:00", "base": "Plano"}


def test_a_imagem_chega_como_bytes_no_formato_do_app():
    itens, _kw, erro = perf_web.montar_itens(_corpo([{"nome": "foto.png", "b64": PNG}]))
    assert not erro, erro
    imgs = itens[0]["imagens"]
    assert len(imgs) == 1
    assert imgs[0]["nome"] == "foto.png"
    assert imgs[0]["bytes"] == _PNG_BYTES


def test_sem_imagem_o_item_continua_igual():
    itens, _kw, erro = perf_web.montar_itens(_corpo([]))
    assert not erro and itens[0]["imagens"] == []


def test_arquivo_que_nao_e_imagem_recusa_a_criacao_inteira():
    """Recusar é melhor que descartar em silêncio: a pessoa anexou porque importa, e uma OS que
    nasce sem o anexo escolhido é pior do que uma criação que não acontece."""
    _itens, _kw, erro = perf_web.montar_itens(_corpo([{"nome": "planilha.xlsx", "b64": PNG}]))
    assert "não é imagem" in erro and "INV1" in erro


def test_base64_quebrado_recusa_com_o_nome_do_ativo():
    _itens, _kw, erro = perf_web.montar_itens(_corpo([{"nome": "foto.png", "b64": "###"}]))
    assert "não consegui ler" in erro and "INV1" in erro


def test_imagem_grande_demais_recusa_dizendo_o_tamanho():
    grande = base64.b64encode(b"\x89PNG" + b"x" * (perf_web.MAX_BYTES_IMG + 1)).decode()
    _itens, _kw, erro = perf_web.montar_itens(_corpo([{"nome": "foto.png", "b64": grande}]))
    assert "MB" in erro and "limite" in erro


def test_passar_do_limite_por_ativo_recusa():
    muitas = [{"nome": "f%d.png" % i, "b64": PNG} for i in range(perf_web.MAX_IMG_ATIVO + 1)]
    _itens, _kw, erro = perf_web.montar_itens(_corpo(muitas))
    assert "o limite é %d por ativo" % perf_web.MAX_IMG_ATIVO in erro


def test_a_tela_manda_as_imagens_e_deixou_de_dizer_em_breve():
    js = io.open(_JS, encoding="utf-8").read()
    assert "em breve na web" not in js, "a coluna Imagens ainda diz que é promessa"
    # vai no payload da criação — só nome e b64 desde 22/09 (a miniatura `url` ficou de fora)
    assert "imagens: (imgs[a.id] || []).map(x => ({nome: x.nome, b64: x.b64}))" in js
    assert "readAsDataURL" in js                        # escolher arquivo
    assert "clipboardData" in js                        # e colar com Ctrl+V, como no app
