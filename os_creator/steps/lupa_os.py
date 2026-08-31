"""A LUPA das OS — card grande sobreposto ao app, para achar a OS que se quer vincular.

Levi, 31/08: "quando eu clicar aparecerá uma mini tela sobreposta ao OS Creator, em formato de
card gigante não de aba, esse card gigante deixará um sombreamento no fundo para foco total no
card". Daí o diálogo sem moldura, do tamanho da janela, com o fundo escurecido: quem está
procurando uma OS para vincular não deveria ter de decidir também onde olhar.

TRÊS FILTROS, e o de período tem uma regra própria. Escopo (este ativo / a usina inteira), tipo
de tarefa (Corretiva, Corretiva Emergencial, Religamento, Religamento Remoto, Zeladoria) e
PERÍODO EM QUE A OS ESTEVE ABERTA — não a data de abertura. O Levi foi explícito: "se eu
selecionar dia 5 e a OS foi aberta dia 1 e fechada dia 10 então pegará esse período". Filtrar
pela abertura deixaria de fora exatamente a OS que estava em curso no dia que interessa.
"""
from datetime import datetime

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QDateEdit, QLineEdit)

import api
from steps.ui import CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED
from workers import ApiWorker, slot_seguro

# Os tipos que interessam a quem procura a OS de uma ocorrência (lista do Levi, 31/08). Preventiva,
# Inspeção e Administrativa existem no Fracttal e ficam DE FORA por padrão — não é OS de falha.
TIPOS = ["Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto", "Zeladoria"]

_COL = ["OS", "Tipo", "Ativo", "Descrição", "Status", "Aberta", "Fechada"]


def _dt(iso):
    """ISO do Fracttal → datetime. None quando vazio ou fora de formato."""
    s = str(iso or "").strip().replace("T", " ")[:19]
    if len(s) < 10:
        return None
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _br(iso):
    d = _dt(iso)
    return d.strftime("%d/%m/%Y %H:%M") if d else "—"


def esteve_aberta_no_periodo(os_, de, ate) -> bool:
    """A OS estava aberta em algum momento entre `de` e `ate`?

    Sobreposição de intervalos, não data de abertura: a OS vai de `aberta` até `fechada`, e a
    janela de `de` até `ate`. Elas se cruzam quando a OS abriu ANTES do fim da janela e fechou
    DEPOIS do começo dela. OS ainda em aberto (`fechada` vazia) não tem fim — só precisa ter
    aberto antes do fim da janela.

    Sem data de abertura não dá para afirmar nada; nesse caso a OS PASSA, para não sumir da
    lista por falta de um dado que é do cadastro, não da pergunta."""
    ab = _dt(os_.get("aberta"))
    fe = _dt(os_.get("fechada"))
    if ab is None:
        return True
    if ate is not None and ab > ate:
        return False
    if de is not None and fe is not None and fe < de:
        return False
    return True


class _Selo(QPushButton):
    """Botão de filtro que liga e desliga."""
    def __init__(self, texto, ligado, ao_mudar):
        super().__init__(texto)
        self.setCheckable(True)
        self.setChecked(ligado)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton{color:%s;background:transparent;border:1px solid %s;border-radius:999px;"
            "padding:5px 13px;font-size:11.5px;font-weight:700;min-height:0px;}"
            "QPushButton:hover{border-color:%s;}"
            "QPushButton:checked{color:%s;background:%s;border-color:%s;}"
            % (MUTED, BORDER, GREEN, GREEN_INK, GREEN, GREEN))
        self.clicked.connect(lambda *_: ao_mudar())


class LupaOS(QDialog):
    """Card grande com as OS do ativo (ou da usina), para escolher qual vincular.

    `ao_escolher(os_)` recebe o dict da OS escolhida — quem chama decide o que fazer com ela."""

    def __init__(self, pai, ativo, usina, ativos_da_usina, ao_escolher):
        super().__init__(pai)
        self._ativo = ativo or {}
        self._usina = usina or ""
        self._da_usina = ativos_da_usina or []
        self._ao_escolher = ao_escolher
        self._linhas = []
        self._w = None
        self._tipos = {t: True for t in TIPOS}
        # sem ativo resolvido no catálogo (acontece em tracker, cujo cadastro nem sempre existe)
        # o escopo nasce na usina — senão a lupa abriria vazia sem explicar por quê.
        self._escopo_usina = not self._ativo.get("id")

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        janela = pai.window() if pai is not None else None
        if janela is not None:
            self.setGeometry(janela.geometry())

        fundo = QVBoxLayout(self)
        fundo.setContentsMargins(0, 0, 0, 0)
        self._fundo = QWidget()
        # O SOMBREAMENTO. rgba só compõe porque o diálogo é translúcido; num widget opaco a
        # transparência é ignorada e o fundo vira preto chapado.
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

        self._buscar()

    # ── montagem ──────────────────────────────────────────────────────────────────────────
    def _card(self):
        c = QFrame()
        c.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:16px;}" % (CARD, BORDER))
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(13)

        topo = QHBoxLayout()
        t = QLabel("Ordens de serviço")
        t.setStyleSheet("color:%s;font-size:18px;font-weight:800;background:transparent;"
                        "border:none;" % TEXT)
        topo.addWidget(t)
        self._sub = QLabel("")
        self._sub.setStyleSheet("color:%s;font-size:11.5px;background:transparent;border:none;"
                                % MUTED)
        topo.addWidget(self._sub)
        topo.addStretch(1)
        fechar = QPushButton("✕")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setFixedSize(30, 30)
        # padding:0 explícito: o QSS global do app põe padding em QPushButton, e num botão de
        # 30px isso empurrava o glifo para fora da área visível — o ✕ virava um risco.
        fechar.setStyleSheet("QPushButton{background:%s;color:%s;border:1px solid %s;"
                             "border-radius:8px;padding:0px;margin:0px;min-height:0px;"
                             "font-size:14px;font-weight:800;}"
                             "QPushButton:hover{color:%s;border-color:%s;}"
                             % (INPUT, TEXT, BORDER, GREEN, GREEN))
        fechar.clicked.connect(lambda *_: self.reject())
        topo.addWidget(fechar)
        v.addLayout(topo)

        esc = QHBoxLayout()
        esc.setSpacing(8)
        esc.addWidget(self._rot("ONDE"))
        self._b_ativo = _Selo("Este ativo", not self._escopo_usina, lambda: self._trocar_escopo(False))
        self._b_usina = _Selo("A usina inteira", self._escopo_usina, lambda: self._trocar_escopo(True))
        self._b_ativo.setEnabled(bool(self._ativo.get("id")))
        if not self._ativo.get("id"):
            self._b_ativo.setToolTip("este ativo não está no catálogo do Fracttal")
        esc.addWidget(self._b_ativo)
        esc.addWidget(self._b_usina)
        esc.addSpacing(18)
        esc.addWidget(self._rot("QUANDO ESTEVE ABERTA"))
        self._de = QDateEdit(QDate.currentDate().addMonths(-3))
        self._ate = QDateEdit(QDate.currentDate())
        for d in (self._de, self._ate):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.setFixedWidth(126)      # sem largura fixa o ano saía cortado ("31/08/202")
            d.setStyleSheet("QDateEdit{background:%s;border:1px solid %s;border-radius:8px;"
                            "color:%s;font-size:12px;padding:2px 8px;min-height:0px;}"
                            "QDateEdit::drop-down{border:none;width:18px;}" % (INPUT, BORDER, TEXT))
            d.dateChanged.connect(lambda *_: self._pintar())
            esc.addWidget(d)
        limpar = QPushButton("qualquer data")
        limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        limpar.setStyleSheet("QPushButton{background:transparent;border:none;color:%s;"
                             "font-size:11px;font-weight:700;}"
                             "QPushButton:hover{color:%s;}" % (MUTED, GREEN))
        limpar.clicked.connect(self._sem_periodo)
        esc.addWidget(limpar)
        esc.addStretch(1)
        v.addLayout(esc)

        tp = QHBoxLayout()
        tp.setSpacing(8)
        tp.addWidget(self._rot("TIPO"))
        self._selos = {}
        for t_ in TIPOS:
            s = _Selo(t_, True, self._recolher_tipos)
            self._selos[t_] = s
            tp.addWidget(s)
        tp.addSpacing(14)
        self._busca = QLineEdit()
        self._busca.setPlaceholderText("filtrar por número, ativo ou descrição…")
        self._busca.setStyleSheet("QLineEdit{background:%s;border:1px solid %s;border-radius:8px;"
                                  "color:%s;font-size:12px;padding:3px 10px;min-height:0px;}"
                                  "QLineEdit:focus{border-color:%s;}" % (INPUT, BORDER, TEXT, GREEN))
        self._busca.textChanged.connect(lambda *_: self._pintar())
        tp.addWidget(self._busca, 1)
        v.addLayout(tp)

        self.tab = QTableWidget(0, len(_COL))
        self.tab.setHorizontalHeaderLabels(_COL)
        self.tab.verticalHeader().setVisible(False)
        self.tab.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab.setShowGrid(False)
        self.tab.setAlternatingRowColors(False)
        self.tab.setStyleSheet(
            "QTableWidget{background:%s;border:none;color:%s;font-size:12px;outline:0;}"
            "QTableWidget QWidget{background:%s;}"
            "QHeaderView{background:%s;border:none;border-radius:0;}"
            "QHeaderView::section{background:%s;color:%s;border:none;border-radius:0;"
            "border-bottom:1px solid %s;padding:6px 4px;font-size:10px;font-weight:800;}"
            "QTableWidget::item{padding:7px 4px;border-bottom:1px solid rgba(42,53,80,0.4);}"
            "QTableWidget::item:selected{background:rgba(166,226,46,0.14);color:%s;}"
            % (CARD, TEXT, CARD, CARD, CARD, MUTED, BORDER, TEXT))
        self.tab.cellDoubleClicked.connect(self._escolher)
        cab = self.tab.horizontalHeader()
        cab.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)   # a descrição é a longa
        for i in (0, 1, 2, 4, 5, 6):
            cab.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.tab, 1)

        rod = QHBoxLayout()
        self._rodape = QLabel("procurando…")
        self._rodape.setStyleSheet("color:%s;font-size:11.5px;background:transparent;border:none;"
                                   % MUTED)
        rod.addWidget(self._rodape, 1)
        b = QPushButton("Vincular a selecionada")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:9px;"
                        "padding:8px 18px;font-size:12px;font-weight:800;min-height:0px;}"
                        % (GREEN, GREEN_INK))
        b.clicked.connect(lambda *_: self._escolher(self.tab.currentRow(), 0))
        rod.addWidget(b)
        v.addLayout(rod)
        return c

    def _rot(self, t):
        q = QLabel(t)
        q.setStyleSheet("color:%s;font-size:10px;font-weight:800;letter-spacing:1.1px;"
                        "background:transparent;border:none;" % MUTED)
        return q

    # ── dados ─────────────────────────────────────────────────────────────────────────────
    def _ids(self):
        if self._escopo_usina:
            return [a.get("id") for a in self._da_usina if a.get("id")]
        return [self._ativo.get("id")] if self._ativo.get("id") else []

    def _buscar(self):
        ids = self._ids()
        if not ids:
            # a mensagem muda com o escopo: dizer "não achei o ativo" enquanto se olha a usina
            # inteira mandaria a pessoa procurar o problema no lugar errado.
            self._rodape.setText(
                ("a usina %s não tem ativos no catálogo do Fracttal com esse nome — é lacuna de "
                 "cadastro, não falta de OS." % self._usina) if self._escopo_usina else
                "este ativo não está no catálogo do Fracttal; tente a usina inteira.")
            self.tab.setRowCount(0)
            return
        self._rodape.setText("procurando as OS…")
        self._w = ApiWorker(api.os_dos_ativos, ids, 400)
        self._w.ok.connect(self._chegaram)
        self._w.erro.connect(self._falhou)
        self._w.start()

    @slot_seguro
    def _chegaram(self, linhas):
        self._w = None
        self._linhas = linhas or []
        self._pintar()

    @slot_seguro
    def _falhou(self, msg):
        self._w = None
        self._rodape.setText("não consegui buscar: %s" % str(msg)[:120])

    # ── filtros e pintura ─────────────────────────────────────────────────────────────────
    @slot_seguro
    def _trocar_escopo(self, usina):
        self._escopo_usina = bool(usina)
        self._b_ativo.setChecked(not self._escopo_usina)
        self._b_usina.setChecked(self._escopo_usina)
        self._buscar()

    @slot_seguro
    def _recolher_tipos(self):
        self._tipos = {t: s.isChecked() for t, s in self._selos.items()}
        self._pintar()

    @slot_seguro
    def _sem_periodo(self, *_):
        """Abre a janela até onde o dado alcança, em vez de tirar o filtro do caminho: manter os
        campos preenchidos é o que deixa claro qual período está valendo."""
        self._de.setDate(QDate(2020, 1, 1))
        self._ate.setDate(QDate.currentDate().addYears(1))

    def _filtradas(self):
        de = datetime(self._de.date().year(), self._de.date().month(), self._de.date().day())
        ate = datetime(self._ate.date().year(), self._ate.date().month(),
                       self._ate.date().day(), 23, 59, 59)
        termo = api._norm_txt(self._busca.text())
        ligados = {t for t, on in self._tipos.items() if on}
        out = []
        for o in self._linhas:
            tt = str(o.get("tipo_tarefa") or "").strip()
            # o tipo pode vir composto ('A / B') quando a OS tem tarefas de tipos diferentes
            if ligados and not any(t in tt for t in ligados):
                continue
            if not esteve_aberta_no_periodo(o, de, ate):
                continue
            if termo:
                alvo = api._norm_txt(" ".join(str(o.get(k) or "") for k in
                                              ("folio", "ativo", "descricao", "tipo_tarefa")))
                if termo not in alvo:
                    continue
            out.append(o)
        return out

    def _pintar(self):
        vis = self._filtradas()
        self._vis = vis
        onde = ("a usina %s" % self._usina) if self._escopo_usina else (
            api._asset_short_name(self._ativo) or "o ativo")
        self._sub.setText("·  %s" % onde)
        self.tab.setRowCount(0)
        self.tab.setRowCount(len(vis))
        for r, o in enumerate(vis):
            vals = [str(o.get("folio") or "—"), o.get("tipo_tarefa") or "—",
                    (o.get("ativo") or "—")[:34], o.get("descricao") or "—",
                    o.get("status") or "—", _br(o.get("aberta")), _br(o.get("fechada"))]
            for c, txt in enumerate(vals):
                it = QTableWidgetItem(txt)
                if c != 3:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 3 and o.get("descricao"):
                    it.setToolTip(str(o["descricao"]))
                self.tab.setItem(r, c, it)
        total = len(self._linhas)
        self._rodape.setText("%d de %d OS · clique duas vezes na linha para vincular"
                             % (len(vis), total) if total else
                             "nenhuma OS encontrada para este escopo.")

    @slot_seguro
    def _escolher(self, linha, _col=0):
        if not (0 <= linha < len(getattr(self, "_vis", []))):
            return
        escolhida = self._vis[linha]
        if self._ao_escolher:
            self._ao_escolher(escolhida)
        self.accept()
