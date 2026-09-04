# -*- coding: utf-8 -*-
"""A tranca da Área PCM (pedido do Levi, 04/09).

O QUE ELA É: uma tranca de porta, não um cofre. O app roda na máquina de quem usa, e quem quiser
mesmo entrar consegue. O que ela impede é o acesso POR ENGANO — o supervisor que clica em "Área
PCM" por curiosidade e aprova uma solicitação sem querer.
"""
import pytest

import pcm_acesso


@pytest.fixture(autouse=True)
def _trancado():
    pcm_acesso.trancar()
    yield
    pcm_acesso.trancar()


def test_a_senha_confere_e_a_errada_nao():
    assert pcm_acesso.confere("PCM@2026")
    assert pcm_acesso.confere("  PCM@2026  "), "espaço colado não pode reprovar"
    assert not pcm_acesso.confere("pcm@2026"), "a senha é sensível a maiúscula"
    assert not pcm_acesso.confere("")
    assert not pcm_acesso.confere(None)


def test_a_senha_nao_aparece_no_codigo():
    """Guardo o HASH, não o texto. Não muda o limite — muda que quem abrir o .exe num editor de
    texto não acha a senha de graça."""
    import io
    import os
    fonte = io.open(os.path.abspath(pcm_acesso.__file__), encoding="utf-8").read()
    assert "PCM@2026" not in fonte.replace('"PCM@2026"', "")  # só a menção no comentário/doc
    assert len(pcm_acesso._HASH) == 64


def test_liberar_vale_pela_sessao_e_trancar_desfaz():
    """Uma vez por sessão: pedir a cada clique faria o PCM digitar dez vezes por dia, e a senha
    acabaria colada no monitor."""
    assert not pcm_acesso.liberado()
    pcm_acesso.liberar()
    assert pcm_acesso.liberado()
    pcm_acesso.trancar()
    assert not pcm_acesso.liberado()


def test_cancelar_a_senha_nao_abre_a_area(qapp, monkeypatch):
    """Cancelar o diálogo tem de deixar a tela como estava — sem os destinos do PCM na tela."""
    from PyQt6.QtWidgets import QInputDialog
    from steps.solic_pcm import _Hub
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))     # o usuário cancelou
    h = _Hub(lambda a: None)
    h._abrir_pcm()
    assert h._area is None, "abriu a área do PCM sem senha"
    assert h._subcards == []


def test_senha_errada_nao_abre_a_area(qapp, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    from steps.solic_pcm import _Hub
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("chutei", True)))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    h = _Hub(lambda a: None)
    h._abrir_pcm()
    assert h._area is None
    assert not pcm_acesso.liberado()


def test_senha_certa_abre_a_area_com_os_quatro_destinos(qapp, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog
    from steps.solic_pcm import _Hub
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("PCM@2026", True)))
    h = _Hub(lambda a: None)
    h._abrir_pcm()
    assert h._area == "pcm"
    assert [c.lbl_titulo.text() for c in h._subcards] == [
        "Painel", "Fila do PCM", "Histórico", "Temas"]


def test_a_area_do_solicitante_nao_pede_senha(qapp):
    """Só o PCM é trancado: pedir senha ao supervisor seria travar quem o app existe para servir."""
    from steps.solic_pcm import _Hub
    h = _Hub(lambda a: None)
    h._abrir_solic()
    assert h._area == "solic"
    assert h.c_nova.lbl_titulo.text() == "Criar Nova Solicitação"
    assert [c.lbl_titulo.text() for c in h._subcards] == ["Painel", "Histórico"]
