"""Editor de subtarefas — a mesma lista, editável, nas duas pontas do fluxo.

O supervisor monta na Solicitação; o PCM confere e ajusta na Fila. Um módulo só porque são a
MESMA coisa: se fossem dois editores, o dia em que um ganhasse um tipo de campo novo o outro
ficaria para trás, e a lista que sai daqui é a que vira o checklist da OS.

O tipo de cada linha fica visível e editável de propósito. Ele é o que diz se aquela subtarefa
vai pedir texto, número, foto ou um sim/não — e é exatamente a diferença entre um checklist e um
campo em branco com nome, que foi o que a medição das 414 OS mostrou existir hoje ("Descreva a
atividade realizada" em 43% delas, "Procedimento" em 37%).
"""
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QLineEdit, QFrame)

import solic_spec as sp
from steps.ui import icone_pix, GREEN, MUTED, TEXT

# ordem dos tipos no combo: os dois mais usados primeiro
TIPOS = [("texto", "Texto"), ("simnao", "Sim/Não"), ("verif", "Verificação"),
         ("num", "Numérico")]


class _Linha(QFrame):
    """Uma subtarefa: número, descrição editável, tipo e o × que remove."""

    def __init__(self, i, dados, on_remover, on_mudar):
        super().__init__()
        self.setObjectName("subLinha")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 7, 10, 7)
        h.setSpacing(10)

        self.num = QLabel(str(i))
        self.num.setFixedWidth(16)
        self.num.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        h.addWidget(self.num)

        self.ed = QLineEdit(str(dados.get("desc") or ""))
        self.ed.setObjectName("subTexto")
        self.ed.setPlaceholderText("descreva o que o técnico deve fazer")
        self.ed.textChanged.connect(lambda *_: on_mudar())
        h.addWidget(self.ed, 1)

        self.cb = QComboBox()
        self.cb.setObjectName("subTipo")
        self.cb.setFixedWidth(126)
        for chave, rot in TIPOS:
            self.cb.addItem(rot, chave)
        alvo = dados.get("tipo") or "texto"
        self.cb.setCurrentIndex(max(0, next((k for k, (c, _) in enumerate(TIPOS) if c == alvo), 0)))
        self.cb.currentIndexChanged.connect(lambda *_: on_mudar())
        h.addWidget(self.cb)

        # o anexo obrigatório vem do tema e não se edita aqui: ele é regra do procedimento,
        # não preferência de quem está montando a lista.
        # O rótulo ocupa um espaço FIXO mesmo quando vazio: sem isso a linha que tem anexo
        # empurrava o combo para a esquerda e as colunas dançavam de uma linha para a outra.
        self.anexo = bool(dados.get("anexo"))
        a = QLabel("anexo obrigatório" if self.anexo else "")
        a.setFixedWidth(112)
        a.setStyleSheet("color:%s;font-size:10.5px;background:transparent;" % GREEN)
        h.addWidget(a)

        b = QPushButton("×")
        b.setObjectName("subRemover")
        b.setFixedWidth(28)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip("Remover esta subtarefa")
        b.clicked.connect(lambda: on_remover(self))
        h.addWidget(b)

    def dados(self):
        return {"desc": self.ed.text().strip(), "tipo": self.cb.currentData(),
                "anexo": self.anexo}


class EditorSubtarefas(QWidget):
    """A lista inteira. `itens()` devolve o que está na tela, na ordem da tela."""

    mudou = pyqtSignal()

    def __init__(self, titulo_vazio="Sem tema: a OS nasce com as 3 subtarefas da base."):
        super().__init__()
        self._vazio = titulo_vazio
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.caixa = QFrame()
        self.caixa.setObjectName("boxSubs")
        self.cv = QVBoxLayout(self.caixa)
        self.cv.setContentsMargins(0, 0, 0, 0)
        self.cv.setSpacing(0)

        self.cab = QLabel("")
        self.cab.setObjectName("subsCab")
        self.cab.setTextFormat(Qt.TextFormat.RichText)
        self.cab.setWordWrap(True)
        self.cab.setMinimumWidth(1)
        self.cv.addWidget(self.cab)

        self.linhas_box = QWidget()
        self.lv = QVBoxLayout(self.linhas_box)
        self.lv.setContentsMargins(0, 0, 0, 0)
        self.lv.setSpacing(0)
        self.cv.addWidget(self.linhas_box)

        rod = QHBoxLayout()
        rod.setContentsMargins(12, 8, 12, 10)
        self.b_add = QPushButton("Adicionar subtarefa")
        self.b_add.setObjectName("btnLink")
        self.b_add.setIcon(QIcon(icone_pix("check", GREEN, 13)))
        self.b_add.setIconSize(QSize(13, 13))
        self.b_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_add.clicked.connect(self.adicionar)
        rod.addWidget(self.b_add)
        rod.addStretch(1)
        self.cv.addLayout(rod)
        v.addWidget(self.caixa)
        self._linhas = []

    # ── conteudo ──
    def set_itens(self, itens):
        while self.lv.count():
            it = self.lv.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._linhas = []
        for d in (itens or []):
            self._nova_linha(d)
        self._renumerar()

    def _nova_linha(self, d):
        ln = _Linha(len(self._linhas) + 1, d, self._remover, self._mudou)
        self._linhas.append(ln)
        self.lv.addWidget(ln)
        return ln

    def adicionar(self):
        ln = self._nova_linha({"desc": "", "tipo": "texto"})
        self._renumerar()
        ln.ed.setFocus()
        self._mudou()

    def _remover(self, ln):
        if ln in self._linhas:
            self._linhas.remove(ln)
            ln.setParent(None)
            ln.deleteLater()
            self._renumerar()
            self._mudou()

    def _renumerar(self):
        for i, ln in enumerate(self._linhas, 1):
            ln.num.setText(str(i))
            ln.setProperty("ultima", "1" if i == len(self._linhas) else "0")
            ln.style().unpolish(ln)
            ln.style().polish(ln)
        n = len(self._linhas)
        self.cab.setText("A OS vai nascer com <b>%d subtarefa%s</b>" % (n, "" if n == 1 else "s")
                         if n else "<span style='color:%s'>%s</span>" % (MUTED, self._vazio))

    def _mudou(self):
        self._renumerar()
        self.mudou.emit()

    def itens(self):
        return [ln.dados() for ln in self._linhas if ln.dados()["desc"]]

    def para_api(self):
        """A lista pronta para a criação da OS, preservando o anexo obrigatório do tema."""
        out = []
        for x in self.itens():
            d = sp.para_api([x])[0]
            d["attachments_required"] = bool(x.get("anexo"))
            out.append(d)
        return out

    def set_editavel(self, on):
        self.b_add.setEnabled(on)
        for ln in self._linhas:
            ln.ed.setEnabled(on)
            ln.cb.setEnabled(on)
