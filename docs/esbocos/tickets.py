"""Esboço v2 — aba Tickets do OS Creator (Trackers + Strings).

DESCARTÁVEL: mockup para aprovação, não código de produção.
Dados REAIS da Gridco Performance API (sheet 123 = Trackers), em trk_raw.json.

O que a v2 acrescentou, tudo vindo do retorno do Levi (28/08):
  · O ticket tem CICLO DE VIDA, e ele é o elemento principal da tela — não os campos.
  · AZUL = a OS está "Em Verificação". O técnico diz que acabou, ninguém confirmou. É onde o
    problema volta a existir sem ninguém perceber ("muitos técnicos fecham OS sem resolver").
  · Fim da ocorrência tem TRÊS fontes, nesta ordem: data da tarefa (real, do cronômetro),
    data da OS (aproximada) ou digitada à mão. A tela diz qual está valendo.
  · Dá para DESMARCAR o fim e reabrir o ticket.
  · Data e hora em tudo — a hora é metade do cálculo de indisponibilidade.
"""
import io
import json
import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
                             QAbstractItemView, QComboBox, QDateTimeEdit, QTextEdit, QScrollArea,
                             QSizePolicy, QGridLayout)

BG, CARD, INPUT, BORDER = "#0B1020", "#121A2B", "#1A2337", "#2A3550"
GREEN, GREEN_INK, TEXT, MUTED = "#A6E22E", "#0B1020", "#FFFFFF", "#8A93A8"
# semântica de estado — separada do verde da marca, que é só acento
VERM, AMBAR, AZUL, VERDE = "#e05454", "#eb8b57", "#4a9eff", "#3fb27f"

_AQUI = os.path.dirname(os.path.abspath(__file__))

# ── ciclo de vida do ticket ──────────────────────────────────────────────────
# (chave, rótulo curto, cor). A ordem É o fluxo; a tela desenha nesta ordem.
CICLO = [("aberta",     "Aberta",          VERM),
         ("com_os",     "OS criada",       AMBAR),
         ("verificando", "Em verificação",  AZUL),
         ("encerrada",  "Encerrada",       VERDE)]
COR_ESTADO = {k: c for k, _, c in CICLO}
NOME_ESTADO = {k: n for k, n, _ in CICLO}


def lbl(t, cor=TEXT, px=13, peso=400, ital=False, esp=None, mono=False):
    q = QLabel(str(t))
    q.setStyleSheet("color:%s;font-size:%spx;font-weight:%s;background:transparent;border:none;%s%s%s"
                    % (cor, px, peso, "font-style:italic;" if ital else "",
                       "letter-spacing:%spx;" % esp if esp else "",
                       "font-family:Consolas,monospace;" if mono else ""))
    return q


def secao(t, cor=MUTED):
    return lbl(t, cor, 10, 800, esp=1.2)


def regua():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background:%s;border:none;" % BORDER)
    return f


class Painel(QFrame):
    def __init__(self, larg=None):
        super().__init__()
        self.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:14px;}"
                           % (CARD, BORDER))
        if larg:
            self.setFixedWidth(larg)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 16, 18, 16)
        self.v.setSpacing(12)


class Chip(QPushButton):
    def __init__(self, texto, ligado=False, cor=GREEN):
        super().__init__(texto)
        self.setCheckable(True)
        self.setChecked(ligado)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton{color:%s;background:transparent;border:1px solid %s;border-radius:999px;"
            "padding:5px 13px;font-size:11.5px;font-weight:700;}"
            "QPushButton:hover{border-color:%s;}"
            "QPushButton:checked{color:%s;background:%s;border-color:%s;}"
            % (MUTED, BORDER, cor, GREEN_INK, cor, cor))


class Tile(QFrame):
    """Contador do topo. A cor é do ESTADO, não decoração — quem bate o olho já sabe onde doer."""
    def __init__(self, n, rotulo, cor, dica=""):
        super().__init__()
        self.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:12px;"
                           "border-top:2px solid %s;}" % (CARD, BORDER, cor))
        v = QVBoxLayout(self)
        v.setContentsMargins(15, 11, 15, 12)
        v.setSpacing(1)
        v.addWidget(lbl(n, cor, 25, 800))
        v.addWidget(lbl(rotulo, TEXT, 11.5, 700))
        if dica:
            d = lbl(dica, MUTED, 10.5)
            d.setWordWrap(True)
            v.addWidget(d)


class Ciclo(QWidget):
    """A barra de ciclo de vida. É o elemento PRINCIPAL do painel — o resto são campos."""
    def __init__(self, atual):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        idx = [k for k, _, _ in CICLO].index(atual)
        for i, (k, nome, cor) in enumerate(CICLO):
            passou, agora = i < idx, i == idx
            c = cor if (passou or agora) else BORDER
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            ponto = QLabel("●" if (passou or agora) else "○")
            ponto.setStyleSheet("color:%s;font-size:%spx;background:transparent;border:none;"
                                % (c, 15 if agora else 11))
            ponto.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(ponto)
            col.addWidget(lbl(nome, c if agora else MUTED, 9.5, 800 if agora else 600))
            w = QWidget()
            w.setLayout(col)
            h.addWidget(w)
            if i < len(CICLO) - 1:
                tr = QFrame()
                tr.setFixedHeight(2)
                tr.setStyleSheet("background:%s;border:none;margin-bottom:14px;"
                                 % (cor if passou else BORDER))
                h.addWidget(tr, 1)


def _qss_campo(ro=False):
    # O fundo é SEMPRE o INPUT (Levi, 28/08). Antes o somente-leitura usava BG, mais escuro que o
    # card, e virava um buraco na tela. Somente-leitura se distingue pela cor do TEXTO, não por
    # um fundo diferente — o campo continua parecendo um campo.
    return ("background:%s;border:1px solid %s;border-radius:9px;padding:7px 10px;"
            "color:%s;font-size:12.5px;" % (INPUT, BORDER, MUTED if ro else TEXT))


def campo(valor="", ro=False, ph=""):
    e = QLineEdit(str(valor or ""))
    e.setReadOnly(ro)
    if ph:
        e.setPlaceholderText(ph)
    e.setStyleSheet("QLineEdit{%s}" % _qss_campo(ro))
    return e


def lista(opcoes, atual=None):
    c = QComboBox()
    c.addItems(opcoes)
    if atual and atual in opcoes:
        c.setCurrentText(atual)
    c.setStyleSheet("QComboBox{%s}QComboBox::drop-down{border:none;width:18px;}"
                    "QComboBox QAbstractItemView{background:%s;color:%s;border:1px solid %s;"
                    "selection-background-color:%s;selection-color:%s;}"
                    % (_qss_campo(), CARD, TEXT, BORDER, GREEN, GREEN_INK))
    return c


def data(dt=None):
    d = QDateTimeEdit()
    d.setDisplayFormat("dd/MM/yyyy HH:mm")
    d.setCalendarPopup(True)
    if dt:
        d.setDateTime(QDateTime.fromString(str(dt)[:16].replace("T", " "), "yyyy-MM-dd HH:mm"))
    d.setStyleSheet("QDateTimeEdit{%s}QDateTimeEdit::drop-down{border:none;}" % _qss_campo())
    return d


def rotulado(rotulo, widget, dica=None, cor_dica=GREEN):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    t = QHBoxLayout()
    t.setSpacing(7)
    t.addWidget(lbl(rotulo, MUTED, 10.5, 700))
    if dica:
        t.addWidget(lbl(dica, cor_dica, 9.5, 800))
    t.addStretch(1)
    v.addLayout(t)
    v.addWidget(widget)
    return w


def carregar():
    d = json.load(io.open(os.path.join(_AQUI, "trk_raw.json"), encoding="utf-8"))
    rows = d if isinstance(d, list) else d.get("rows") or d.get("items") or []
    idx = {c: k for k, c in enumerate(rows[0].get("headers") or [])}
    out = []
    for r in rows[1:]:
        v = r.get("values") or []
        def g(c):
            k = idx.get(c)
            return v[k] if k is not None and k < len(v) else None
        if not g("Usina"):
            continue
        n = r.get("row_number") or 0
        # SIMULADO no esboço: a coluna OS não existe na aba hoje (nem em Trackers nem em Strings).
        # Criá-la é parte do trabalho, e só depois que a aba sair do sync do Excel.
        os_num = "" if n % 3 == 0 else str(10800 + (n % 97))
        st_os = ("Em Verificação" if n % 7 == 0 else
                 "Concluída" if n % 5 == 0 else "Em Processo") if os_num else ""
        estado = ("aberta" if not os_num else
                  "verificando" if st_os == "Em Verificação" else
                  "encerrada" if st_os == "Concluída" else "com_os")
        out.append({"row": n, "os": os_num, "status_os": st_os, "estado": estado,
                    "usina": g("Usina"), "status": g("Status"), "skid": g("Nº do SKID"),
                    "trk": g("Nº do tracker / Identificação"), "inv": g("Inversor"),
                    "cli": g("Cliente"), "uf": g("UF"), "sup": g("Supervisor(a)"),
                    "resp": g("Responsável"), "causa": g("Causa raiz"),
                    "plano": g("Plano de ação"), "gridco": g("Responsabilidade da Grid Co.?"),
                    "ini": g("Início da ocorrência"), "fim": g("Fim da ocorrência"),
                    "cg": g("Comentários gerais")})
    return out


def horas(ini, fim=None):
    """A conta que hoje é fórmula do Excel e passa a ser do app."""
    try:
        a = datetime.fromisoformat(str(ini)[:19])
    except Exception:
        return None
    try:
        b = datetime.fromisoformat(str(fim)[:19]) if fim else datetime.now()
    except Exception:
        b = datetime.now()
    return round((b - a).total_seconds() / 3600.0, 1)


class Mock(QWidget):
    def __init__(self, dados):
        super().__init__()
        self.setWindowTitle("Esboço v2 — Tickets no OS Creator")
        self.setStyleSheet("background:%s;" % BG)
        self.resize(1520, 880)
        self._todos = dados
        self._abertas = [d for d in dados if d["status"] != "Em conformidade" and not d["fim"]]
        # o selecionado é de propósito um EM VERIFICAÇÃO — é o estado novo que o esboço precisa provar
        self._sel = next((d for d in self._abertas if d["estado"] == "verificando"),
                         self._abertas[0])

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 18, 26, 20)
        raiz.setSpacing(14)
        raiz.addLayout(self._cabecalho())
        raiz.addLayout(self._tiles())

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(self._filtros())
        corpo.addWidget(self._lista(), 1)
        corpo.addWidget(self._painel())
        raiz.addLayout(corpo)

    def _cabecalho(self):
        cab = QHBoxLayout()
        cab.setSpacing(16)
        b = QPushButton("← Voltar")
        b.setFixedHeight(36)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:transparent;color:%s;border:1px solid %s;"
                        "border-radius:10px;padding:0 16px;font-size:13px;font-weight:600;}"
                        "QPushButton:hover{border-color:%s;}" % (TEXT, BORDER, GREEN))
        cab.addWidget(b)
        cx = QVBoxLayout()
        cx.setSpacing(1)
        cx.addWidget(lbl("Tickets", TEXT, 20, 800))
        s = lbl("Gridco Performance API · aba Trackers", MUTED, 12)
        s.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        cx.addWidget(s)
        cab.addLayout(cx)
        cab.addSpacing(20)
        for nome, on in (("Trackers", True), ("Strings", False)):
            cab.addWidget(Chip(nome, on))
        cab.addStretch(1)
        busca = QLineEdit()
        busca.setPlaceholderText("usina, skid, nº do tracker, nº da OS…")
        busca.setFixedSize(320, 36)
        busca.setStyleSheet("QLineEdit{%s}" % _qss_campo())
        cab.addWidget(busca)
        return cab

    def _tiles(self):
        h = QHBoxLayout()
        h.setSpacing(12)
        c = {k: sum(1 for d in self._abertas if d["estado"] == k) for k, _, _ in CICLO}
        h.addWidget(Tile(len(self._abertas), "Em aberto", GREEN, "o conjunto de trabalho"))
        h.addWidget(Tile(c["aberta"], "Sem OS", VERM, "parado e ninguém foi olhar"))
        h.addWidget(Tile(c["com_os"], "Com OS, em campo", AMBAR, "técnico ainda não fechou"))
        h.addWidget(Tile(c["verificando"], "Em verificação", AZUL,
                         "o técnico fechou — ninguém confirmou"))
        return h

    def _filtros(self):
        p = Painel(220)
        p.v.addWidget(secao("ESTADO"))
        for k, nome, cor in CICLO:
            n = sum(1 for d in self._abertas if d["estado"] == k)
            l = QHBoxLayout()
            l.setSpacing(8)
            l.addWidget(Chip(nome, k == "verificando", cor))
            l.addStretch(1)
            l.addWidget(lbl(str(n), MUTED, 11.5))
            p.v.addLayout(l)
        p.v.addWidget(regua())
        p.v.addWidget(secao("USINA"))
        cont = {}
        for d in self._abertas:
            cont[d["usina"]] = cont.get(d["usina"], 0) + 1
        for u, n in sorted(cont.items(), key=lambda x: -x[1])[:8]:
            l = QHBoxLayout()
            l.setSpacing(8)
            l.addWidget(lbl(str(u)[:19], MUTED, 12))
            l.addStretch(1)
            l.addWidget(lbl(str(n), MUTED, 11))
            p.v.addLayout(l)
        p.v.addStretch(1)
        p.v.addWidget(regua())
        nota = lbl("A ronda do WhatsApp lê Status=Parado com Fim vazio. "
                   "Desmarcar o fim devolve o tracker para a ronda.", MUTED, 10, ital=True)
        nota.setWordWrap(True)
        p.v.addWidget(nota)
        return p

    def _lista(self):
        p = Painel()
        topo = QHBoxLayout()
        topo.addWidget(secao("OCORRÊNCIAS"))
        topo.addStretch(1)
        nova = QPushButton("Criar OS de tracker parado")
        nova.setCursor(Qt.CursorShape.PointingHandCursor)
        nova.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:9px;"
                           "padding:8px 15px;font-size:12px;font-weight:800;}" % (GREEN, GREEN_INK))
        topo.addWidget(nova)
        p.v.addLayout(topo)

        vis = sorted(self._abertas, key=lambda d: (d["estado"] != "verificando",
                                                   d["estado"] != "aberta"))[:15]
        t = QTableWidget(len(vis), 7)
        t.setHorizontalHeaderLabels(["", "Usina", "Skid / Tracker", "OS", "Causa raiz",
                                     "Início da ocorrência", "Há"])
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setShowGrid(False)
        t.setStyleSheet(
            "QTableWidget{background:transparent;border:none;color:%s;font-size:12.5px;outline:0;}"
            "QHeaderView::section{background:transparent;color:%s;border:none;"
            "border-bottom:1px solid %s;padding:8px 4px;font-size:10px;font-weight:800;}"
            "QTableWidget::item{padding:9px 4px;border-bottom:1px solid rgba(42,53,80,0.4);}"
            "QTableWidget::item:focus{border:none;}"
            "QTableWidget::item:selected{background:rgba(166,226,46,0.12);color:%s;}"
            % (TEXT, MUTED, BORDER, TEXT))
        sel_row = 0
        for r, d in enumerate(vis):
            if d is self._sel:
                sel_row = r
            h = horas(d["ini"])
            cor = COR_ESTADO[d["estado"]]
            # tarja de estado: cor na FORMA, não só no texto — dá para ler a lista sem ler as letras
            tarja = QTableWidgetItem("▐")
            tarja.setForeground(_cor(cor))
            t.setItem(r, 0, tarja)
            vals = (str(d["usina"])[:20],
                    "%s / %s" % (d["skid"] or "—", d["trk"] or "—"),
                    d["os"] or "sem OS",
                    d["causa"] or "aguardando técnico",
                    str(d["ini"])[:16].replace("T", " ") if d["ini"] else "—",
                    "%.0f d" % (h / 24) if h else "—")
            for c, v in enumerate(vals, start=1):
                it = QTableWidgetItem(str(v))
                if c == 3 and v == "sem OS":
                    it.setForeground(_cor(VERM))
                if c == 4 and v == "aguardando técnico":
                    it.setForeground(_cor(MUTED))
                if c == 6 and h and h / 24 > 30:
                    it.setForeground(_cor(VERM))
                t.setItem(r, c, it)
        t.setColumnWidth(0, 14)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in (0, 2, 3, 4, 5, 6):
            t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        t.selectRow(sel_row)
        p.v.addWidget(t)
        return p

    def _painel(self):
        p = Painel(452)
        d = self._sel
        cor = COR_ESTADO[d["estado"]]

        # o título da seção CARREGA o estado (Levi, 28/08) — em vez de dizer só "OCORRÊNCIA" e
        # repetir a informação numa caixa logo abaixo
        topo = QHBoxLayout()
        topo.addWidget(secao("OCORRÊNCIA", MUTED))
        if d["os"]:
            topo.addWidget(lbl("·", BORDER, 10, 800))
            topo.addWidget(lbl("OS %s está: %s" % (d["os"], d["status_os"]), cor, 10, 800, esp=1.2))
        else:
            topo.addWidget(lbl("·  SEM OS", VERM, 10, 800, esp=1.2))
        topo.addStretch(1)
        topo.addWidget(lbl("linha %s" % d["row"], MUTED, 10, ital=True))
        p.v.addLayout(topo)

        p.v.addWidget(lbl(str(d["usina"]), TEXT, 17, 800))
        # ativo e cabine vêm do CATÁLOGO do Fracttal, não da planilha — a coluna `Inversor` da aba
        # está suja (212 vazios, e o resto com anotações do tipo "A ser verificado"). A cadeia real
        # do tracker é Tracker → Estrutura Trackers → Usina: NÃO passa por cabine, então aqui a
        # cabine aparece vazia. Na aba Strings ela existe (Inversor → QGBT → SKID → Cabine).
        ident = QHBoxLayout()
        ident.setSpacing(14)
        for rot, val, cor_v in (("ATIVO", "Tracker %s" % (d["trk"] or "—"), GREEN),
                                ("SKID", d["skid"] or "—", TEXT),
                                ("CABINE", "não se aplica a tracker", MUTED)):
            c = QVBoxLayout()
            c.setSpacing(1)
            c.addWidget(lbl(rot, MUTED, 9, 800, esp=1.1))
            c.addWidget(lbl(val, cor_v, 12.5, 700 if cor_v != MUTED else 400,
                            ital=(cor_v == MUTED)))
            w = QWidget()
            w.setLayout(c)
            ident.addWidget(w)
        ident.addStretch(1)
        p.v.addLayout(ident)
        p.v.addWidget(Ciclo(d["estado"]))

        # o aviso do estado atual, na cor do estado
        av = QFrame()
        av.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:11px;}"
                         % (_rgba(cor, 0.10), _rgba(cor, 0.45)))
        avv = QVBoxLayout(av)
        avv.setContentsMargins(13, 10, 13, 10)
        avv.setSpacing(3)
        # a caixa perdeu o título repetido — quem diz o estado agora é o cabeçalho da seção.
        # Aqui fica só a CONSEQUÊNCIA, que é o que a pessoa precisa saber para agir.
        txt = {"verificando": "O técnico fechou a tarefa, mas ninguém confirmou que resolveu. "
                              "O fim abaixo é provisório — se o problema persistir, desmarque.",
               "aberta": "Nenhuma OS vinculada: o tracker está parado e ninguém foi mandado olhar.",
               "com_os": "OS aberta, técnico ainda em campo. O fim chega quando ela for concluída.",
               "encerrada": "OS concluída e verificada. A indisponibilidade abaixo está fechada."}
        m = lbl(txt.get(d["estado"], ""), MUTED, 11)
        m.setWordWrap(True)
        avv.addWidget(m)
        p.v.addWidget(av)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                         "QScrollArea > QWidget > QWidget{background:transparent;}")
        dentro = QWidget()
        v = QVBoxLayout(dentro)
        v.setContentsMargins(0, 2, 8, 0)
        v.setSpacing(13)

        # Cliente, UF, Supervisor e Responsável SAÍRAM (Levi, 28/08): vêm do catálogo, não mudam
        # e não são decisão de ninguém nesta tela. Ocupavam metade do painel para não dizer nada.
        v.addWidget(secao("VEM DO TÉCNICO · pela OS", AZUL))
        v.addWidget(rotulado("Causa raiz", campo(d["causa"], ro=True,
                                                 ph="aguardando retorno da OS %s" % (d["os"] or "—")),
                             dica="só o técnico", cor_dica=AZUL))
        v.addWidget(rotulado("Responsabilidade da Grid Co.?",
                             lista(["(a definir)", "Sim", "Não"], d["gridco"])))

        v.addWidget(regua())
        v.addWidget(secao("PRAZOS"))
        v.addWidget(rotulado("Início da ocorrência", data(d["ini"]), dica="data e hora"))
        v.addWidget(self._bloco_fim(d))

        v.addWidget(regua())
        v.addWidget(secao("COMENTÁRIOS"))
        ta = QTextEdit(str(d["cg"] or ""))
        ta.setFixedHeight(56)
        ta.setStyleSheet("QTextEdit{%s}" % _qss_campo())
        v.addWidget(ta)
        v.addStretch(1)
        sc.setWidget(dentro)
        p.v.addWidget(sc, 1)

        p.v.addWidget(regua())
        rod = QHBoxLayout()
        rod.setSpacing(9)
        salvar = QPushButton("Salvar")
        salvar.setCursor(Qt.CursorShape.PointingHandCursor)
        salvar.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:10px;"
                             "padding:10px 22px;font-size:13px;font-weight:800;}" % (GREEN, GREEN_INK))
        abrir = QPushButton("Abrir OS %s" % (d["os"] or "—"))
        abrir.setEnabled(bool(d["os"]))
        abrir.setCursor(Qt.CursorShape.PointingHandCursor)
        abrir.setStyleSheet("QPushButton{background:transparent;color:%s;border:1px solid %s;"
                            "border-radius:10px;padding:10px 16px;font-size:12.5px;font-weight:700;}"
                            "QPushButton:disabled{color:%s;}" % (TEXT, BORDER, BORDER))
        rod.addWidget(salvar)
        rod.addWidget(abrir)
        rod.addStretch(1)
        p.v.addLayout(rod)
        return p

    def _bloco_fim(self, d):
        """As três fontes do Fim da ocorrência + o botão de desmarcar.
        É o núcleo do retorno do Levi: tarefa de preferência, OS ou manual como alternativa,
        e sempre reversível — porque técnico fecha OS sem resolver."""
        w = QFrame()
        w.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:12px;}"
                        % (INPUT, _rgba(AZUL, 0.40)))
        v = QVBoxLayout(w)
        v.setContentsMargins(13, 11, 13, 12)
        v.setSpacing(9)
        t = QHBoxLayout()
        t.addWidget(secao("FIM DA OCORRÊNCIA", AZUL))
        t.addStretch(1)
        t.addWidget(lbl("provisório", AZUL, 9.5, 800))
        v.addLayout(t)

        # a linha "origem: ..." saiu (Levi, 28/08) — os chips logo abaixo já dizem qual está valendo
        v.addWidget(lbl("03/08/2026 11:57", TEXT, 15, 800))

        expl = lbl("A tarefa da OS não tem hora registrada (o cronômetro não foi usado). "
                   "Escolha de onde vem o fim:", MUTED, 10.5)
        expl.setWordWrap(True)
        v.addWidget(expl)

        opc = QHBoxLayout()
        opc.setSpacing(7)
        for nome, on, ativo in (("Da tarefa", False, False),
                                ("Da OS", True, True),
                                ("Digitar", False, True)):
            c = Chip(nome, on, AZUL)
            c.setEnabled(ativo)
            opc.addWidget(c)
        opc.addStretch(1)
        v.addLayout(opc)
        v.addWidget(lbl("\"Da tarefa\" indisponível: sem cronômetro, a tarefa fecha sem hora",
                        MUTED, 9.5, ital=True))

        v.addWidget(regua())
        h = horas(d["ini"], "2026-08-03T11:57:43")
        li = QHBoxLayout()
        li.addWidget(lbl("Indisponibilidade", MUTED, 11, 700))
        li.addStretch(1)
        li.addWidget(lbl("%s h" % (h if h else "—"), GREEN, 15, 800))
        v.addLayout(li)

        des = QPushButton("Desmarcar fim e reabrir a ocorrência")
        des.setCursor(Qt.CursorShape.PointingHandCursor)
        des.setStyleSheet("QPushButton{background:transparent;color:%s;border:1px solid %s;"
                          "border-radius:9px;padding:8px 12px;font-size:11.5px;font-weight:700;}"
                          "QPushButton:hover{background:%s;}" % (VERM, _rgba(VERM, 0.5),
                                                                 _rgba(VERM, 0.12)))
        v.addWidget(des)
        return w


def _cor(hexa):
    from PyQt6.QtGui import QColor
    return QColor(hexa)


def _rgba(hexa, a):
    h = hexa.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "rgba(%d,%d,%d,%.2f)" % (r, g, b, a)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Mock(carregar())
    w.show()
    sys.exit(app.exec())
