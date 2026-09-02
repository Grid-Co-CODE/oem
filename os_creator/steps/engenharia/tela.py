"""Tela da Engenharia — esqueleto.

Nasce vazia de propósito: o conteúdo é da Engenharia, e desenhá-lo aqui anularia o motivo do
arranjo (docs/ambiente-compartilhado-engenharia.md, §7). O que já vem pronto é a moldura — a tela
aparece na grade, o Voltar funciona e as cores vêm do tema.

REGRA DESTA PASTA: cor só por nome importado de `steps/ui.py`. Nenhum hexadecimal escrito à mão —
o teste `tests/test_fronteira_engenharia.py` reprova. O motivo não é gosto: o `CLAUDE.md` da raiz
manda um valor e o `steps/ui.py` usa outro, então quem escreve à mão escolhe entre dois valores em
conflito e a tela sai fora do tema sem ninguém notar. Nome resolve para o que o código usa de fato.
"""
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from steps.ui import MUTED, TEXT


class EngenhariaTab(QWidget):
    """Moldura da área.

    Sem `_selfnav`, quem desenha o "← Voltar" é o `_wrap_modo` do `app.py`; desenhar outro aqui
    deixaria dois Voltar na mesma tela (`steps/CLAUDE.md`).

    O `border:none` em cada QLabel não é excesso: QLabel herda de QFrame, e uma regra de borda no
    card pai vaza para todo filho — foi assim que um ponto de status de 6px virou círculo pintado.
    """

    def __init__(self, on_voltar=None):
        super().__init__()
        self._on_voltar = on_voltar          # guardado para quando a área tiver navegação própria
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(8)

        titulo = QLabel("Engenharia")
        titulo.setStyleSheet(
            f"font-size:20px; font-weight:600; color:{TEXT}; background:transparent; border:none;")
        v.addWidget(titulo)

        sub = QLabel("Área em construção pela Engenharia. O primeiro fluxo será OS de ETM.")
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"font-size:13px; color:{MUTED}; background:transparent; border:none;")
        v.addWidget(sub)

        v.addStretch(1)
