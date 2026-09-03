"""Editor de subtarefas — a mesma lista, editável, nas duas pontas do fluxo.

O supervisor monta na Solicitação; o PCM confere e ajusta na Fila. Um módulo só porque são a
MESMA coisa: se fossem dois editores, o dia em que um ganhasse um tipo de campo novo o outro
ficaria para trás, e a lista que sai daqui é a que vira o checklist da OS.

FORMATO DE LINHA, NÃO DE CARD (decisão do Levi, 03/09). Cada subtarefa é uma linha sutil sobre
o fundo da página, separada da seguinte por um risco. O texto e o tipo PARECEM texto e viram
campo ao clique; o anexo obrigatório é um checkbox que já vem marcado quando o tema manda e a
pessoa marca ou desmarca. Os números ficam em verde Grid.

O ESTILO MORA AQUI DENTRO, de propósito. Em Qt a folha de estilo do ancestral mais próximo vence:
quando as regras ficavam no SolicPcmTab, o SolicitacaoTab — que tem folha própria (QSS_FORM) —
engolia a regra de QLineEdit e os campos apareciam como caixas preenchidas de 40 px, o "estilo
card" que o Levi rejeitou. Com o editor carregando o próprio estilo, ele fica igual nas duas
telas por construção, e não por sorte na ordem dos ancestrais.
"""
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QLineEdit, QFrame, QCheckBox)

import solic_spec as sp
from steps.ui import icone_pix, GREEN, MUTED, TEXT

# ordem dos tipos no combo: os dois mais usados primeiro
TIPOS = [("texto", "Texto"), ("simnao", "Sim/Não"), ("verif", "Verificação"),
         ("num", "Numérico")]

RISCO = "#222c43"          # a mesma linha da tabela da Fila e do Painel

QSS = f"""
QWidget#subEditor, QWidget#subLinhas {{ background:transparent; }}
QLabel#subsCab {{ color:{MUTED}; font-size:11.5px; padding:2px 0 6px 0; background:transparent;
  border:none; }}
QFrame#subLinha {{ background:transparent; border:none; border-bottom:1px solid {RISCO}; }}
QFrame#subLinha[ultima="1"] {{ border-bottom:none; }}
QLabel#subNum {{ color:{GREEN}; font-size:11.5px; font-weight:700; background:transparent; }}

/* o TEXTO parece texto: sem caixa, sem fundo. O sublinhado pontilhado no hover e o convite,
   e o verde no foco diz "agora voce esta editando". */
QLineEdit#subTexto {{ background:transparent; border:none; border-bottom:1px solid transparent;
  border-radius:0; color:{TEXT}; font-size:12.5px; min-height:24px; max-height:24px;
  padding:0 2px; }}
QLineEdit#subTexto:hover {{ border-bottom:1px dashed #39405a; }}
QLineEdit#subTexto:focus {{ border-bottom:1px solid {GREEN}; }}
QLineEdit#subTexto:disabled {{ color:#5a6072; }}

/* o TIPO tambem parece texto: e um combo sem caixa e sem seta, que abre ao clique */
QComboBox#subTipo {{ background:transparent; border:none; border-bottom:1px solid transparent;
  border-radius:0; color:{MUTED}; font-size:11.5px; min-height:24px; max-height:24px;
  padding:0 2px; }}
QComboBox#subTipo:hover {{ color:{TEXT}; border-bottom:1px dashed #39405a; }}
QComboBox#subTipo::drop-down {{ border:none; width:0px; }}
QComboBox#subTipo::down-arrow {{ image:none; width:0px; }}
QComboBox#subTipo QAbstractItemView {{ background:#161d30; color:{TEXT}; border:1px solid {RISCO};
  selection-background-color:rgba(143,206,63,0.18); outline:none; }}

/* o ANEXO e decisao de quem monta a lista: checkbox, e nao rotulo */
QCheckBox#subAnexo {{ color:{MUTED}; font-size:11px; spacing:6px; background:transparent; }}
QCheckBox#subAnexo:checked {{ color:{GREEN}; }}
QCheckBox#subAnexo::indicator {{ width:13px; height:13px; border:1px solid #39405a;
  border-radius:3px; background:transparent; }}
QCheckBox#subAnexo::indicator:hover {{ border-color:{GREEN}; }}
QCheckBox#subAnexo::indicator:checked {{ background:{GREEN}; border-color:{GREEN}; }}

/* padding:0 e OBRIGATORIO: a regra generica de QPushButton traz padding:9px 14px, e numa
   largura fixa de 26 px isso nao deixava espaco nenhum para o glifo — o botao existia, respondia
   ao clique e nao pintava um pixel. */
QPushButton#subRemover {{ background:transparent; border:1px solid transparent; color:#6b7388;
  font-size:16px; font-weight:700; min-height:22px; max-height:22px; padding:0; border-radius:5px; }}
QPushButton#subRemover:hover {{ color:#ffffff; background:rgba(224,85,85,0.85);
  border-color:#e05555; }}
QPushButton#subAdd {{ background:transparent; border:none; color:{GREEN}; font-size:12px;
  font-weight:600; padding:0 2px; min-height:0; text-align:left; }}
QPushButton#subAdd:hover {{ color:#b4ec42; text-decoration:underline; }}
"""


class _Linha(QFrame):
    """Uma subtarefa: número verde, texto, tipo, anexo (checkbox) e o × que remove."""

    def __init__(self, i, dados, on_remover, on_mudar):
        super().__init__()
        self.setObjectName("subLinha")
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 5, 2, 5)
        h.setSpacing(10)

        self.num = QLabel(str(i))
        self.num.setObjectName("subNum")
        self.num.setFixedWidth(22)
        h.addWidget(self.num)

        self.ed = QLineEdit(str(dados.get("desc") or ""))
        self.ed.setObjectName("subTexto")
        self.ed.setPlaceholderText("descreva o que o técnico deve fazer")
        self.ed.setToolTip("clique para editar")
        self.ed.textChanged.connect(lambda *_: on_mudar())
        h.addWidget(self.ed, 1)

        self.cb = QComboBox()
        self.cb.setObjectName("subTipo")
        self.cb.setFixedWidth(96)
        self.cb.setToolTip("clique para trocar o tipo")
        for chave, rot in TIPOS:
            self.cb.addItem(rot, chave)
        alvo = dados.get("tipo") or "texto"
        self.cb.setCurrentIndex(max(0, next((k for k, (c, _) in enumerate(TIPOS) if c == alvo), 0)))
        self.cb.currentIndexChanged.connect(lambda *_: on_mudar())
        h.addWidget(self.cb)

        # Checkbox, e nao rotulo: o tema so da o DEFAULT. Quem monta a lista decide se aquela
        # linha exige foto — e o padrao vem marcado quando o tema manda, para a decisao ser
        # "tirar", que e consciente, e nao "lembrar de por".
        self.chk = QCheckBox("anexo obrigatório")
        self.chk.setObjectName("subAnexo")
        self.chk.setChecked(bool(dados.get("anexo")))
        self.chk.setFixedWidth(128)
        self.chk.stateChanged.connect(lambda *_: on_mudar())
        h.addWidget(self.chk)

        b = QPushButton("×")
        b.setObjectName("subRemover")
        b.setFixedWidth(26)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip("Remover esta subtarefa")
        b.clicked.connect(lambda: on_remover(self))
        h.addWidget(b)

    @property
    def anexo(self):
        return self.chk.isChecked()

    def dados(self):
        return {"desc": self.ed.text().strip(), "tipo": self.cb.currentData(),
                "anexo": self.chk.isChecked()}


class EditorSubtarefas(QWidget):
    """A lista inteira. `itens()` devolve o que está na tela, na ordem da tela."""

    mudou = pyqtSignal()

    def __init__(self, titulo_vazio="Sem tema: a OS nasce com as 3 subtarefas da base."):
        super().__init__()
        self.setObjectName("subEditor")
        self.setStyleSheet(QSS)              # o estilo mora aqui — ver o docstring do modulo
        self._vazio = titulo_vazio
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.cab = QLabel("")
        self.cab.setObjectName("subsCab")
        self.cab.setTextFormat(Qt.TextFormat.RichText)
        self.cab.setWordWrap(True)
        self.cab.setMinimumWidth(1)
        v.addWidget(self.cab)

        self.linhas_box = QWidget()
        self.linhas_box.setObjectName("subLinhas")
        self.lv = QVBoxLayout(self.linhas_box)
        self.lv.setContentsMargins(0, 0, 0, 0)
        self.lv.setSpacing(0)
        v.addWidget(self.linhas_box)

        rod = QHBoxLayout()
        rod.setContentsMargins(4, 8, 0, 2)
        # "+" e nao um "check": o simbolo tem de dizer ACRESCENTAR. O check vinha de quando o
        # botao foi copiado do rodape da fila, e dizia a coisa errada. Nao ha icone de mais no
        # conjunto do app, entao o glifo vai no proprio texto do botao.
        self.b_add = QPushButton("+   Adicionar subtarefa")
        self.b_add.setObjectName("subAdd")
        self.b_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_add.clicked.connect(self.adicionar)
        rod.addWidget(self.b_add)
        rod.addStretch(1)
        v.addLayout(rod)
        self._linhas = []
        # compatibilidade com quem chamava .caixa (a moldura escura que deixou de existir)
        self.caixa = self.linhas_box

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
        ln = self._nova_linha({"desc": "", "tipo": "texto", "anexo": False})
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
        self.cab.setText("A OS vai nascer com <b style='color:%s'>%d subtarefa%s</b>"
                         % (TEXT, n, "" if n == 1 else "s")
                         if n else "<span style='color:%s'>%s</span>" % (MUTED, self._vazio))

    def _mudou(self):
        self._renumerar()
        self.mudou.emit()

    def itens(self):
        return [ln.dados() for ln in self._linhas if ln.dados()["desc"]]

    def para_api(self):
        """A lista pronta para a criação da OS, com o anexo como a pessoa deixou."""
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
            ln.chk.setEnabled(on)
