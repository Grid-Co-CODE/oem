"""O card grande de ATIVOS — para vincular a ocorrência ao ativo do Fracttal.

Levi, 31/08: "muitas linhas não estão com ativo vinculado... clicando no não vai abrir o card
gigante de ativos". Mesmo formato da lupa de OS: diálogo sem moldura, do tamanho da janela, com
o fundo escurecido.

POR QUE O VÍNCULO PRECISA SER MANUAL EM TRACKER
Medido em 31/08: o Fracttal NÃO tem tracker cadastrado por unidade. O TIM100 tem 151 ativos de
tracker e todos terminam em `.100` — é um por skid/estrutura, não um por tracker. E a numeração
muda de usina para usina (Boa Esperança usa "Tracker 1.1.101"; TIM100, "Tracker 01.100"), com
usinas inteiras sem nenhum (PEIII: zero). Nenhuma régua automática casa isso com o número que a
planilha guarda — daí a escolha ser de quem conhece a usina, e o app só oferecer a lista certa.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QLineEdit)

import api
from steps.ui import CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED
from workers import slot_seguro

_COL = ["Código", "Ativo", "Tipo"]


class LupaAtivos(QDialog):
    """Escolhe um ativo da usina. `ao_escolher(ativo)` recebe o registro do catálogo."""

    def __init__(self, pai, usina, ativos, ao_escolher, sugestao=""):
        super().__init__(pai)
        self._usina = usina or ""
        self._ativos = ativos or []
        self._ao_escolher = ao_escolher
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        janela = pai.window() if pai is not None else None
        if janela is not None:
            self.setGeometry(janela.geometry())

        fundo = QVBoxLayout(self)
        fundo.setContentsMargins(0, 0, 0, 0)
        self._fundo = QWidget()
        self._fundo.setStyleSheet("background:rgba(4,7,14,0.82);")
        fundo.addWidget(self._fundo)
        fv = QVBoxLayout(self._fundo)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.addStretch(1)
        linha = QHBoxLayout()
        linha.addStretch(1)
        linha.addWidget(self._card(), 6)
        linha.addStretch(1)
        fv.addLayout(linha, 20)
        fv.addStretch(1)
        # a sugestão entra JÁ FILTRADA: quem abre daqui está procurando um tracker ou um
        # inversor específico, e digitar o que a própria linha já diz seria trabalho repetido.
        self._busca.setText(str(sugestao or "").strip())
        self._pintar()

    def _card(self):
        c = QFrame()
        c.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:16px;}"
                        % (CARD, BORDER))
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(13)

        topo = QHBoxLayout()
        t = QLabel("Vincular ativo")
        t.setStyleSheet("color:%s;font-size:18px;font-weight:800;background:transparent;"
                        "border:none;" % TEXT)
        topo.addWidget(t)
        sub = QLabel("·  %s" % self._usina)
        sub.setStyleSheet("color:%s;font-size:11.5px;background:transparent;border:none;" % MUTED)
        topo.addWidget(sub)
        topo.addStretch(1)
        fechar = QPushButton("✕")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setFixedSize(30, 30)
        fechar.setStyleSheet("QPushButton{background:%s;color:%s;border:1px solid %s;"
                             "border-radius:8px;padding:0px;margin:0px;min-height:0px;"
                             "font-size:14px;font-weight:800;}"
                             "QPushButton:hover{color:%s;border-color:%s;}"
                             % (INPUT, TEXT, BORDER, GREEN, GREEN))
        fechar.clicked.connect(lambda *_: self.reject())
        topo.addWidget(fechar)
        v.addLayout(topo)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("filtrar por código, nome ou tipo…")
        self._busca.setStyleSheet("QLineEdit{background:%s;border:1px solid %s;border-radius:8px;"
                                  "color:%s;font-size:12px;padding:4px 10px;min-height:0px;}"
                                  "QLineEdit:focus{border-color:%s;}" % (INPUT, BORDER, TEXT, GREEN))
        self._busca.textChanged.connect(lambda *_: self._pintar())
        v.addWidget(self._busca)

        self.tab = QTableWidget(0, len(_COL))
        self.tab.setHorizontalHeaderLabels(_COL)
        self.tab.verticalHeader().setVisible(False)
        self.tab.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab.setStyleSheet(
            "QTableWidget{background:%s;border:1px solid %s;color:%s;font-size:12px;outline:0;"
            "gridline-color:%s;}"
            "QTableWidget QWidget{background:%s;}"
            "QHeaderView{background:%s;border:none;}"
            "QHeaderView::section{background:%s;color:%s;border:none;"
            "border-right:1px solid %s;border-bottom:1px solid %s;"
            "padding:6px 4px;font-size:10px;font-weight:800;}"
            "QTableWidget::item{padding:6px 4px;}"
            "QTableWidget::item:selected{background:rgba(166,226,46,0.16);}"
            % (CARD, BORDER, TEXT, BORDER, CARD, CARD, CARD, MUTED, BORDER, BORDER))
        self.tab.cellDoubleClicked.connect(self._escolher)
        cab = self.tab.horizontalHeader()
        cab.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in (0, 2):
            cab.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.tab, 1)

        rod = QHBoxLayout()
        self._rodape = QLabel("")
        self._rodape.setStyleSheet("color:%s;font-size:11.5px;background:transparent;border:none;"
                                   % MUTED)
        rod.addWidget(self._rodape, 1)
        b = QPushButton("Vincular o selecionado")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:9px;"
                        "padding:8px 18px;font-size:12px;font-weight:800;min-height:0px;}"
                        % (GREEN, GREEN_INK))
        b.clicked.connect(lambda *_: self._escolher(self.tab.currentRow(), 0))
        rod.addWidget(b)
        v.addLayout(rod)
        return c

    def _filtrados(self):
        termo = api._norm_txt(self._busca.text())
        if not termo:
            return list(self._ativos)
        out = []
        for a in self._ativos:
            alvo = api._norm_txt("%s %s %s" % (a.get("code"), api._asset_short_name(a),
                                               a.get("tipo")))
            if termo in alvo:
                out.append(a)
        return out

    def _pintar(self):
        vis = self._filtrados()
        self._vis = vis
        self.tab.setRowCount(0)
        self.tab.setRowCount(len(vis))
        for r, a in enumerate(vis):
            for c, txt in enumerate((str(a.get("code") or "—"),
                                     api._asset_short_name(a) or "—",
                                     str(a.get("tipo") or "—"))):
                it = QTableWidgetItem(txt)
                if c != 1:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tab.setItem(r, c, it)
        self._rodape.setText(
            "%d de %d ativos · clique duas vezes na linha para vincular" % (len(vis), len(self._ativos))
            if self._ativos else
            "esta usina não tem ativo nenhum no catálogo do Fracttal — é lacuna de cadastro.")

    @slot_seguro
    def _escolher(self, linha, _c=0):
        if not (0 <= linha < len(getattr(self, "_vis", []))):
            return
        if self._ao_escolher:
            self._ao_escolher(self._vis[linha])
        self.accept()
