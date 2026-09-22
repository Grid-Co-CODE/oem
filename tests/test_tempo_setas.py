# -*- coding: utf-8 -*-
"""Setas do campo de tempo: o passo de 30 min e o visual limpo (Levi, 15/09).

Duas regras nasceram juntas e quebram de formas diferentes:
  1. a seta anda de 30 em 30 — é a unidade em que o plano de tarefa é escrito;
  2. a caixa escura nativa do Windows sai de cena — e aí vem a armadilha do Qt: assim que o
     ::up-button é estilizado, o indicador nativo PARA de ser desenhado. Sem imagem no ::up-arrow
     o campo fica sem seta nenhuma e ninguém descobre que dá para clicar. O teste 3 guarda isso.
"""
import os
import re

import pytest


@pytest.fixture(scope="module")
def tempo(qapp):
    from steps.pcm import _TempoTarefa
    return _TempoTarefa


def _anda(cls, inicio, passos):
    from PyQt6.QtCore import QTime
    w = cls()
    w.setTime(QTime.fromString(inicio, "HH:mm"))
    w.stepBy(passos)
    return w.time().toString("HH:mm")


def test_a_seta_anda_de_30_em_30(tempo):
    assert _anda(tempo, "02:00", 1) == "02:30"
    assert _anda(tempo, "02:00", -1) == "01:30"


def test_arredonda_para_o_multiplo_na_direcao_do_passo(tempo):
    """01:10 não vira 01:40: vai para o múltiplo seguinte, que é o que se espera de um campo
    que anda em blocos. Para baixo, o múltiplo anterior."""
    assert _anda(tempo, "01:10", 1) == "01:30"
    assert _anda(tempo, "01:10", -1) == "01:00"


def test_nunca_zera_o_tempo_da_tarefa(tempo):
    """OS com duração 0 nasce sem tempo previsto. O piso é 15 min — que é o padrão do próprio
    Fracttal quando o plano não diz nada — e é reversível: de 00:30 desce para 00:15 e volta."""
    assert _anda(tempo, "00:15", -1) == "00:15"
    assert _anda(tempo, "00:30", -1) == "00:15"
    assert _anda(tempo, "00:15", 1) == "00:30"


def test_no_limite_a_seta_trava_em_vez_de_andar_ao_contrario(tempo):
    """23:40 subindo ia para 23:30 — a seta de SUBIR fazia o número DESCER."""
    assert _anda(tempo, "23:40", 1) == "23:40"
    assert _anda(tempo, "23:40", -1) == "23:30"


def test_as_duas_folhas_trazem_as_setas_limpas():
    """O visual vale para a tela inteira do app, não só para as telas do redesign."""
    from steps.ui import QSS_FORM, QSS_SETAS
    from app import DARK_QSS
    assert QSS_SETAS, "sem QSS_SETAS as setas voltam a ser as do Windows, dentro da caixa escura"
    assert QSS_SETAS in QSS_FORM
    assert QSS_SETAS in DARK_QSS
    assert "background:transparent" in QSS_SETAS      # a caixa escura é justamente o que sai


def test_botao_estilizado_sem_imagem_deixaria_o_campo_cego():
    """A armadilha do Qt, virada teste: se um dia alguém estilizar o botão e tirar a imagem,
    a seta some da tela e o campo parece um rótulo."""
    from steps.ui import QSS_SETAS
    assert "QAbstractSpinBox::up-button" in QSS_SETAS
    for lado in ("up", "down"):
        achou = re.search(r'QAbstractSpinBox::%s-arrow\s*\{[^}]*image:url\("([^"]+)"\)' % lado,
                          QSS_SETAS)
        assert achou, "o ::%s-arrow precisa de imagem" % lado
        assert os.path.exists(achou.group(1)), "o arquivo da seta %s não foi gravado" % lado
