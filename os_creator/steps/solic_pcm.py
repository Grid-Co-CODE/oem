"""Aba 'Solicitação / PCM' — o fluxo inteiro da solicitação num lugar só.

Quatro páginas, uma navegação: Painel (kanban) · Nova solicitação · Fila do PCM · Histórico.

POR QUE UMA ABA SÓ (decisão do Levi, 02/09): antes havia "Criar Solicitação" e "Histórico de
Solicitação" em abas separadas, e o painel novo seria uma terceira. Três lugares mostrando
solicitação é três lugares para procurar — e o PCM, que é quem mais usa, precisaria pular entre
elas para aprovar uma única solicitação.

O QUE ESTE FLUXO CONSERTA (medido em 02/09 sobre 2.500 solicitações e 414 OS):
  - a coluna Pendentes do Fracttal existe e ninguém olha: 62 solicitações reabertas estão lá sem
    OS, com mediana de 86 dias paradas e a mais antiga de 06/02;
  - a OS nasce sem checklist — as duas "subtarefas" mais comuns são "Descreva a atividade
    realizada" (43%) e "Procedimento" (37%), que são campo em branco com nome;
  - quem converte a solicitação em OS é o PCM, à mão, no Fracttal web — sem tema e sem subtarefa.

A aprovação aqui NÃO cria um passo novo: dá lugar melhor a um passo que já acontece fora do app.
"""
from PyQt6.QtCore import Qt, QSize, QTimer, QDate, QDateTime, QTime
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QScrollArea, QFrame, QMessageBox, QComboBox,
                             QGridLayout, QLineEdit, QSizePolicy,
                             QDateTimeEdit, QStackedLayout)

from datetime import datetime

import api
import solic_spec as sp
from workers import ApiWorker, slot_seguro
from steps.ui import (QSS_FORM, Card, campo, icone_pix, GREEN, GREEN_INK, MUTED, TEXT,
                      CARD, BORDER, BG, INPUT)
# O card da tela de Criar OS. Importado, e nao reescrito: o Levi quer as duas telas com a
# mesma forma, e copiar significaria as duas divergirem na primeira alteracao de uma delas.
from steps.performance import _PlanoCard
from steps.subtarefas_edit import EditorSubtarefas
from steps.solicitacao import SolicitacaoTab
from steps.historico_solic import HistoricoSolic
from steps.temas import TemasTab

# As três colunas do painel, na ordem do Fracttal. A régua de cada uma sai do que foi medido:
# "pendente" é a solicitação SEM OS vinculada e não cancelada — e não um id_status fixo, porque
# quem decide o status é o servidor (a criação manda 0 e volta 1 ou 7, conforme o caminho).
# Cores desta tela, definidas pelo Levi em 03/09. Ficam nomeadas porque nao saem da paleta
# de steps/ui.py: la o CARD e #121A2B e a BORDER e #2A3550, e ele quis outro par aqui.
SUPERFICIE = "#161d30"      # cabecalhos e celulas
RISCO      = "#222c43"      # as linhas da tabela

PENDENTE, ANDAMENTO, FINALIZADA, FORA = "pendente", "andamento", "finalizada", "fora"
_CANCELADAS = {"cancelada", "rejeitada"}
# "Reaberta (refazer)" (AGAIN_REQUEST_TODO) sai do quadro por decisao do Levi (03/09): sao 60
# pedidos que voltaram para o supervisor refazer, e enquanto ele nao refizer nao ha o que o PCM
# aprovar. Deixa-las na coluna Pendentes enchia a fila com 60 itens sobre os quais ele nao pode
# agir — o oposto do que este painel existe para fazer. Continuam visiveis no Historico.
_REFAZER = "reaberta"


def _clarear(hexcor, fator=0.5):
    """Cor 50% mais clara que a dada — o caminho ate o branco, cortado no meio.

    E o que o Levi pediu para a borda do status: mesma familia da fonte, so que recuada, para o
    contorno ler como moldura e nao como um segundo texto."""
    c = str(hexcor or "").lstrip("#")
    if len(c) != 6:
        return "#39405a"
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(x + (255 - x) * fator) for x in (r, g, b))


def _ativo_curto(txt) -> str:
    """So o nome do ativo — sem endereco, sem estado, sem lote.

    O `items_description` do Fracttal traz o cadastro inteiro numa string so: "Estrutura
    Trackers 2a Secao Colonia Tapejara, Lote N 152-Re, ...". O que identifica o ativo esta antes
    da primeira virgula; o resto e endereco, e num cartao de fila ele so rouba altura."""
    t = str(txt or "").split("{")[0].strip()
    return (t.split(",")[0].strip() or t)[:46]


def coluna_de(s: dict) -> str:
    """Em que coluna do painel esta solicitação cai.

    Não usa id_status de propósito: a solicitação criada pelo app volta como OPEN_STATUS (1) e a
    criada pela web do Fracttal, como REQUEST_TODO (7) — as duas pendentes. O que separa de
    verdade é ter ou não OS vinculada."""
    st = (s.get("status") or "").strip().lower()
    if any(c in st for c in _CANCELADAS):
        return FINALIZADA
    if _REFAZER in st and not s.get("id_work_order"):
        return FORA
    if not s.get("id_work_order"):
        return PENDENTE
    return FINALIZADA if "conclu" in st or "resolvid" in st else ANDAMENTO


class _Cartao(QFrame):
    """Cartão do painel — mesmo formato do Fracttal para ninguém reaprender."""

    def __init__(self, s: dict, on_analisar=None):
        super().__init__()
        self.setObjectName("solCard")
        self.setStyleSheet(
            f"QFrame#solCard{{background:{SUPERFICIE};border:1px solid {RISCO};"
            "border-radius:7px;}"
            f"QFrame#solCard QLabel{{background:transparent;border:none;}}")
        v = QVBoxLayout(self)
        v.setContentsMargins(13, 11, 13, 11)
        v.setSpacing(5)

        topo = QHBoxLayout()
        n = QLabel(f"Nº {s.get('id_code') or '—'}")
        n.setStyleSheet("color:#6FA8DC;font-size:12px;font-weight:600;")
        topo.addWidget(n)
        topo.addStretch(1)
        st = QLabel(s.get("status") or "—")
        cor = s.get("cor_status") or MUTED
        st.setStyleSheet("color:%s;font-size:10.5px;font-weight:600;background:transparent;"
                         "border:1px solid %s;border-radius:9px;padding:1px 8px;"
                         % (cor, _clarear(cor)))
        topo.addWidget(st)
        v.addLayout(topo)

        # ATIVO · USINA, e so isso. Antes vinha o `items_description` cru, com endereco e
        # estado, que ocupava duas ou tres linhas do cartao sem dizer nada que ajude a decidir.
        alvo = " · ".join(x for x in (_ativo_curto(s.get("ativo")), str(s.get("usina") or ""))
                          if x and x != "—")
        ativo = QLabel(alvo or "—")
        ativo.setStyleSheet(f"color:{MUTED};font-size:12px;")
        ativo.setWordWrap(True)
        ativo.setMinimumWidth(1)     # sem isto o rotulo com wordWrap nao encolhe e estoura a coluna
        v.addWidget(ativo)

        d = QLabel(str(s.get("descricao") or "—"))
        d.setStyleSheet(f"color:{TEXT};font-size:13px;")
        d.setWordWrap(True)
        d.setMinimumWidth(1)
        v.addWidget(d)

        # O TEMA é o que o Fracttal não mostra — e é a razão de existir este painel.
        tema = (sp.parse(s.get("observacao")) or {}).get("tema") or ""
        if tema or on_analisar or s.get("os_folio"):
            if tema:
                txt, cor, peso = (sp.TEMAS.get(tema) or {}).get("nome") or tema, GREEN, "600"
            elif s.get("os_folio"):
                txt, cor, peso = f"OS {s['os_folio']}", MUTED, "400"
            else:
                txt, cor, peso = "sem tema", MUTED, "400"
            t = QLabel(txt)
            t.setStyleSheet(f"color:{cor};font-size:11px;font-weight:{peso};"
                            "background:transparent;")
            t.setWordWrap(True)
            t.setMinimumWidth(1)
            v.addWidget(t)

        # Uma linha separa a informação da ação. O Analisar vira texto verde no canto: o botão
        # cheio dava a um item de lista o mesmo peso visual do "Aprovar e gerar OS", que é a
        # decisão de verdade — e eram vários na tela ao mesmo tempo.
        risco = QFrame()
        risco.setFixedHeight(1)
        risco.setStyleSheet(f"background:{RISCO};border:none;")
        v.addSpacing(3)
        v.addWidget(risco)

        rod = QHBoxLayout()
        rod.setContentsMargins(0, 4, 0, 0)
        # nome e data lado a lado, e o nome NAO quebra linha: "Singrid Vieira" virava duas
        # linhas e esticava o cartao inteiro. Nome longo e aparado com "…", e o inteiro fica no
        # tooltip — aparar sem tooltip esconderia quem pediu.
        quem = QLabel()
        quem.setStyleSheet(f"color:{MUTED};font-size:11px;background:transparent;")
        quem.setWordWrap(False)
        quem.setMinimumWidth(1)
        quem.setToolTip(str(s.get("criado_por") or ""))
        fm = quem.fontMetrics()
        quem.setText(fm.elidedText(str(s.get("criado_por") or "—"),
                                   Qt.TextElideMode.ElideRight, 168))
        rod.addWidget(quem)
        data = QLabel(_data_br(s.get("data")).split(" ")[0])
        data.setStyleSheet(f"color:{MUTED};font-size:11px;background:transparent;")
        rod.addWidget(data)
        rod.addStretch(1)
        if on_analisar:
            b = QPushButton("Analisar")
            b.setObjectName("btnLink")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: on_analisar(s))
            rod.addWidget(b)
        v.addLayout(rod)


class _Painel(QWidget):
    """Kanban de três colunas. Só a coluna Pendentes tem ação — nas outras duas quem trabalha é
    a OS, não a solicitação, e duplicar ação criaria dois lugares para a mesma coisa."""

    def __init__(self, on_analisar):
        super().__init__()
        self._on_analisar = on_analisar
        self._rows = []
        self._w = None
        v = QVBoxLayout(self)
        # zero margem e zero espaco: o cabecalho tem de ser a primeira LINHA do quadro, nao uma
        # faixa flutuando acima dele. O respiro vai por dentro, nas colunas.
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        cab = QFrame()
        cab.setObjectName("filaCab")
        topo = QHBoxLayout(cab)
        topo.setContentsMargins(14, 9, 14, 9)
        topo.setSpacing(12)
        tit = QLabel("Solicitações")
        tit.setStyleSheet(f"color:{TEXT};font-size:15px;font-weight:600;background:transparent;")
        topo.addWidget(tit)
        # a contagem NAO fica aqui: ela vive no cabecalho de cada coluna, ao lado do nome dela.
        # Repetir os tres numeros em cima seria dizer duas vezes a mesma coisa.
        self.lbl = QLabel("carregando…")
        self.lbl.setStyleSheet(f"color:{MUTED};font-size:12px;background:transparent;")
        topo.addWidget(self.lbl)
        topo.addStretch(1)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Filtrar por usina, ativo ou texto…")
        self.busca.setFixedWidth(260)
        self.busca.textChanged.connect(self._pintar)
        topo.addWidget(self.busca)
        b = QPushButton("Atualizar")
        b.setObjectName("btnVoltar")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.carregar(True))
        topo.addWidget(b)
        v.addWidget(cab)

        self.cols = {}
        grade = QHBoxLayout()
        grade.setContentsMargins(14, 10, 14, 12)
        grade.setSpacing(12)
        for chave, titulo, cor in ((PENDENTE, "Pendentes", "#8fce3f"),
                                   (ANDAMENTO, "Em andamento", "#e8a33d"),
                                   (FINALIZADA, "Finalizadas", "#6FA8DC")):
            box = QWidget()
            bv = QVBoxLayout(box)
            bv.setContentsMargins(0, 0, 0, 0)
            bv.setSpacing(8)
            # nome a esquerda, contagem a direita — a barrinha colorida e o que deixa as tres
            # colunas distinguiveis de relance, sem depender de ler o titulo.
            lin = QHBoxLayout()
            lin.setSpacing(8)
            barra = QFrame()
            barra.setFixedSize(3, 15)
            barra.setStyleSheet(f"background:{cor};border-radius:1px;")
            lin.addWidget(barra)
            cab = QLabel(titulo)
            cab.setStyleSheet(f"color:{TEXT};font-weight:600;font-size:14px;"
                              "background:transparent;")
            lin.addWidget(cab)
            lin.addStretch(1)
            cnt = QLabel("")
            cnt.setStyleSheet(f"color:{cor};font-size:13px;font-weight:600;"
                              "background:transparent;")
            lin.addWidget(cnt)
            bv.addLayout(lin)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QScrollArea.Shape.NoFrame)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            # QScrollArea pinta a cor de janela e o QWidget interno aparece como retângulo mais
            # claro; ver steps/CLAUDE.md. Estes dois seletores são o que resolve.
            sc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollArea > QWidget > QWidget{background:transparent;}")
            inner = QWidget()
            iv = QVBoxLayout(inner)
            iv.setContentsMargins(0, 0, 6, 0)
            iv.setSpacing(9)
            iv.addStretch(1)
            sc.setWidget(inner)
            bv.addWidget(sc, 1)
            grade.addWidget(box, 1)
            self.cols[chave] = (cnt, titulo, iv)
            if chave != FINALIZADA:          # linha entre as colunas, menos depois da ultima
                d = QFrame()
                d.setObjectName("divisorV")
                d.setFixedWidth(1)
                grade.addWidget(d)
        v.addLayout(grade, 1)

    def carregar(self, force=False):
        if self._w is not None:
            return
        self.lbl.setText("carregando solicitações…")
        self._w = ApiWorker(api.list_minhas_solicitacoes, "TODOS", 400)
        self._w.ok.connect(self._ok)
        self._w.erro.connect(self._err)
        self._w.start()

    @slot_seguro
    def _ok(self, rows):
        self._w = None
        self._rows = rows or []
        self._pintar()

    @slot_seguro
    def _err(self, m):
        self._w = None
        self.lbl.setText("Erro ao carregar: " + str(m)[:90])

    def pendentes(self):
        return [s for s in self._rows if coluna_de(s) == PENDENTE]

    def _pintar(self):
        q = (self.busca.text() or "").strip().lower()
        por = {PENDENTE: [], ANDAMENTO: [], FINALIZADA: []}
        fora = 0
        for s in self._rows:
            if q and q not in (" ".join(str(s.get(k) or "") for k in
                                        ("usina", "ativo", "descricao", "criado_por")).lower()):
                continue
            col = coluna_de(s)
            if col == FORA:                    # devolvidas para refazer: nao ha o que aprovar
                fora += 1
                continue
            por[col].append(s)
        for chave, (cnt, titulo, iv) in self.cols.items():
            while iv.count() > 1:                      # mantém o addStretch do fim
                it = iv.takeAt(0)
                w = it.widget()
                if w:                                  # takeAt devolve espaçador sem widget
                    w.setParent(None)
                    w.deleteLater()
            lista = por[chave]
            cnt.setText(f"{len(lista):,}".replace(",", "."))
            for s in lista[:40]:
                iv.insertWidget(iv.count() - 1,
                                _Cartao(s, self._on_analisar if chave == PENDENTE else None))
        # o unico numero que sobra em cima e o que NAO esta no quadro — se ele sumisse de vez,
        # 60 pedidos parados com o supervisor viravam invisiveis para todo mundo.
        self.lbl.setText(f"· {fora} devolvidas para refazer, fora do quadro" if fora else "")


def _hoje_iso():
    return datetime.now().strftime("%Y-%m-%d")


def _data_br(iso):
    """'2026-09-02T14:20:03' -> '02/09/2026 14:20'. Data ISO na tela e ruido: ninguem le ano
    primeiro, e o PCM precisa bater o olho e saber se e de hoje."""
    t = str(iso or "")[:16].replace("T", " ")
    if len(t) < 10:
        return "—"
    d = "%s/%s/%s" % (t[8:10], t[5:7], t[0:4])
    return (d + " " + t[11:16]).strip()


def _ha_quanto(iso):
    """'ha 2 h', 'ontem', '12/08'. Tempo relativo perto e absoluto longe — o que importa na fila
    e a solicitacao estar parada, e 86 dias de mediana nao cabem em 'ha 2064 h'."""
    t = str(iso or "")[:19].replace("T", " ")
    try:
        d = datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            d = datetime.strptime(t[:10], "%Y-%m-%d")
        except ValueError:
            return ""
    seg = (datetime.now() - d).total_seconds()
    if seg < 3600:
        return "agora"
    if seg < 86400:
        return "há %d h" % int(seg // 3600)
    if seg < 172800:
        return "ontem"
    if seg < 86400 * 7:
        return "há %d dias" % int(seg // 86400)
    return d.strftime("%d/%m")


class _CartaoFila(QFrame):
    """Cartao da coluna da fila. Compacto de proposito: a coluna e uma LISTA para escolher, e o
    lugar de ler a solicitacao inteira e o painel da direita. O cartao gordo do painel, reusado
    aqui, pedia 451 px de largura e saia cortado."""

    def __init__(self, s: dict, on_click):
        super().__init__()
        self.dados = s
        self._on_click = on_click
        self.setObjectName("filaCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 11, 12, 12)
        v.setSpacing(3)

        topo = QHBoxLayout()
        n = QLabel("Nº %s" % (s.get("id_code") or "—"))
        n.setStyleSheet("color:#6FA8DC;font-size:11.5px;font-weight:700;background:transparent;")
        topo.addWidget(n)
        topo.addStretch(1)
        st = QLabel(str(s.get("status") or ""))
        cor = s.get("cor_status") or MUTED
        st.setStyleSheet("color:%s;font-size:10px;font-weight:600;background:transparent;"
                         "border:1px solid %s;border-radius:8px;padding:1px 7px;"
                         % (cor, _clarear(cor)))
        topo.addWidget(st)
        v.addLayout(topo)

        u = QLabel(str(s.get("usina") or "—"))
        u.setStyleSheet("color:%s;font-size:13.5px;font-weight:600;background:transparent;" % TEXT)
        u.setWordWrap(True)
        u.setMinimumWidth(1)
        v.addWidget(u)

        a = QLabel(str(s.get("ativo") or "—"))
        a.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        a.setWordWrap(True)
        a.setMinimumWidth(1)
        v.addWidget(a)

        # a data ABSOLUTA mora aqui, no tooltip: ela saiu da ficha da direita porque e subdado —
        # quem varre a fila decide pelo tempo relativo ("ha 21 h"), e so quer o dia e a hora
        # exatos quando para em cima de uma solicitacao (pedido do Levi, 04/09)
        self.setToolTip("Aberta em %s" % _data_br(s.get("data")))
        quem = QLabel("%s · %s" % (s.get("criado_por") or "—", _ha_quanto(s.get("data"))))
        quem.setStyleSheet("color:%s;font-size:11px;background:transparent;" % MUTED)
        quem.setWordWrap(True)
        quem.setMinimumWidth(1)
        v.addWidget(quem)

        tema = (sp.parse(s.get("observacao")) or {}).get("tema") or ""
        # O chip NAO quebra linha: ele tem fundo arredondado com padding desenhado para UMA
        # linha, e "Protecao — transformador e cabine" virava duas (28 px contra 15) — o fundo
        # ficava torto e passava por cima da borda do cartao. Texto longo e aparado com "…".
        self._chip = QLabel()
        self._chip_txt = ((sp.TEMAS.get(tema) or {}).get("nome") or tema) if tema else "sem tema"
        self._chip.setObjectName("chipTema" if tema else "chipVazio")
        self._chip.setWordWrap(False)
        self._chip.setMinimumWidth(1)
        self._chip.setToolTip(self._chip_txt)
        f = self._chip.font()
        f.setPixelSize(11)
        self._chip.setFont(f)
        v.addWidget(self._chip, 0, Qt.AlignmentFlag.AlignLeft)
        self._aparar_chip()

    def _aparar_chip(self):
        """Apara o nome do tema na largura que sobra. O padding do chip (8 px de cada lado) e a
        margem do cartao entram na conta — sem isso o texto encosta na borda."""
        disp = max(40, self.width() - 26 - 20)
        fm = self._chip.fontMetrics()
        self._chip.setText(fm.elidedText(self._chip_txt, Qt.TextElideMode.ElideRight, disp))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._aparar_chip()

    def marcar(self, ativo: bool):
        self.setProperty("sel", "1" if ativo else "0")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click(self.dados)


class _CardEtiquetas(QFrame):
    """As etiquetas que a OS vai levar, ao lado da sugestao do supervisor.

    A etiqueta e o que faz a OS aparecer (ou sumir) nos acompanhamentos depois — e hoje ela e
    posta a mao, no Fracttal web, depois da OS criada. Aqui ela entra na aprovacao, junto com o
    resto, e a regra da Performance e aplicada sozinha.
    """

    def __init__(self, on_mudou=None):
        super().__init__()
        self.setObjectName("boxSug")
        self._on_mudou = on_mudou
        self._catalogo = []
        self._sel = []                  # [{'id','description'}]
        self._do_tema = set()           # as que o TEMA pos, em MAIUSCULA — nao as escolhidas a mao
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 13, 16, 14)
        v.setSpacing(9)

        cab = QLabel("ETIQUETAS DA OS")
        cab.setStyleSheet("color:%s;font-size:10.5px;font-weight:700;letter-spacing:0.8px;"
                          "background:transparent;" % GREEN)
        v.addWidget(cab)

        # EMPILHADAS, nao em linha. Com QHBoxLayout cada etiqueta nova empurrava a fila para a
        # direita e o card crescia na horizontal, espremendo o bloco da sugestao ao lado. Uma por
        # linha cresce so para baixo, que e o unico eixo em que este card tem folga.
        self.fila_chips = QVBoxLayout()
        self.fila_chips.setSpacing(5)
        self.fila_chips.addStretch(1)
        v.addLayout(self.fila_chips)

        self.cb = QComboBox()
        self.cb.setObjectName("campoInline")
        self.cb.addItem("+ adicionar etiqueta", None)
        self.cb.activated.connect(self._escolheu)
        v.addWidget(self.cb)

        self.aviso = QLabel("")
        self.aviso.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        self.aviso.setWordWrap(True)
        self.aviso.setMinimumWidth(1)
        v.addWidget(self.aviso)
        v.addStretch(1)

    # ── catalogo ──
    def set_catalogo(self, itens):
        self._catalogo = list(itens or [])
        self._encher_combo()

    def _encher_combo(self):
        escolhidas = {x["id"] for x in self._sel}
        self.cb.blockSignals(True)
        self.cb.clear()
        self.cb.addItem("+ adicionar etiqueta", None)
        for e in self._catalogo:
            if e.get("id") not in escolhidas:
                self.cb.addItem(str(e.get("description") or ""), e.get("id"))
        self.cb.setCurrentIndex(0)
        self.cb.blockSignals(False)

    def _escolheu(self, i):
        idl = self.cb.itemData(i)
        if idl is None:
            return
        self._sel.append({"id": idl, "description": self.cb.itemText(i)})
        self._pintar()

    def _remover(self, idl):
        self._sel = [x for x in self._sel if x["id"] != idl]
        self._pintar()

    # ── a regra ──
    def etiquetas_do_tema(self, tema, ativo):
        """As etiquetas que ESTE tema carrega, em MAIUSCULA para comparar.

        Sai da tela de Temas, onde o PCM acrescenta e tira. Se o tema ainda nao tem a lista —
        os que ja estavam gravados antes de 04/09 nao tem —, a regra antiga
        (`sp.exige_performance`) responde: senao a PERFORMANCE deixaria de entrar em tracker,
        ETM e garantia no dia da atualizacao, sem ninguem ter pedido."""
        t = sp.TEMAS.get(tema) or {}
        if "etiquetas" in t:
            return {str(x).strip().upper() for x in (t.get("etiquetas") or []) if str(x).strip()}
        nomes = [x["description"] for x in self._sel]
        return ({sp.ETIQUETA_PERFORMANCE}
                if sp.exige_performance(tema, ativo, nomes) else set())

    def aplicar_regra(self, tema, ativo):
        """Poe as etiquetas do tema e tira as que ELE tinha posto quando o tema muda.

        So mexe no que a propria lista do tema colocou (`self._do_tema`): etiqueta que o PCM
        acrescentou a mao fica, mesmo trocando o tema — desfazer escolha de gente sem avisar e
        o pior tipo de automacao."""
        querem = self.etiquetas_do_tema(tema, ativo)
        # sai o que veio do tema anterior e nao vale mais
        self._sel = [x for x in self._sel
                     if x["description"].strip().upper() not in (self._do_tema - querem)]
        tem = {x["description"].strip().upper() for x in self._sel}
        postas = set()
        for nome in sorted(querem - tem):
            alvo = next((e for e in self._catalogo
                         if str(e.get("description") or "").strip().upper() == nome), None)
            if alvo:
                self._sel.append({"id": alvo["id"], "description": alvo["description"]})
                postas.add(nome)
        self._do_tema = (self._do_tema & querem) | postas | (querem & tem)
        self._pintar()

    def _pintar(self):
        while self.fila_chips.count() > 1:
            it = self.fila_chips.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for e in self._sel:
            # "(tema)" e nao "(regra)": desde 04/09 a etiqueta e campo do tema, editavel na tela
            # de Temas — nao e mais uma regra do sistema que ninguem consegue mudar.
            do_tema = e["description"].strip().upper() in self._do_tema
            c = QPushButton(("%s  (tema)" % e["description"]) if do_tema
                            else ("%s  ×" % e["description"]))
            c.setObjectName("chipEtqPerf" if do_tema else "chipEtq")
            c.setCursor(Qt.CursorShape.PointingHandCursor)
            if do_tema:
                c.setEnabled(False)
                c.setToolTip("Vem do tema. Para mudar, edite o tema na aba Temas.")
            else:
                c.clicked.connect(lambda _=False, i=e["id"]: self._remover(i))
            c.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            self.fila_chips.insertWidget(self.fila_chips.count() - 1, c,
                                         0, Qt.AlignmentFlag.AlignLeft)
        self._encher_combo()
        # a legenda da PERFORMANCE saiu (pedido do Levi, 04/09): quando a regra vale, o proprio
        # chip aparece marcado com "(regra)" e leva a explicacao no tooltip — a frase embaixo
        # dizia de novo o que o chip ja diz.
        if not self._sel:
            self.aviso.setText("Nenhuma etiqueta — a OS nasce sem marcação.")
        else:
            self.aviso.setText("")
        if self._on_mudou:
            self._on_mudou()

    def limpar(self):
        self._sel, self._do_tema = [], set()
        self._pintar()

    def ids(self):
        return [x["id"] for x in self._sel]


class _CampoClicavel(QWidget):
    """Mostra um VALOR; ao clicar, vira o campo de edicao no mesmo lugar.

    Por que nao deixar o campo aberto sempre: nesta tela o tecnico e a data quase sempre so
    precisam ser CONFIRMADOS — o supervisor ja escreveu. Combo e date picker abertos dao a uma
    conferencia o peso visual de um formulario a preencher. Clicou, edita; saiu, volta a ser
    texto."""

    def __init__(self, editor, vazio="—"):
        super().__init__()
        self._vazio = vazio
        self.editor = editor
        self._pilha = QStackedLayout(self)
        self._pilha.setContentsMargins(0, 0, 0, 0)
        self.lbl = QLabel(vazio)
        self.lbl.setObjectName("valorEditavel")
        self.lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl.setToolTip("clique para editar")
        editor.setObjectName("campoInline")
        # ALTURA TRAVADA nos dois estados. O rotulo tem ~20 px (13 px de fonte + padding + risco)
        # e o campo tem 24 fixos pela QSS; a pilha se dimensiona pelo maior, e o texto do rotulo
        # ficava centrado em 24 enquanto o do campo assentava mais acima — ao clicar, a data
        # "subia". Com os dois em 24 e a mesma ancoragem, o valor nao sai da linha.
        self.setFixedHeight(24)
        self.lbl.setFixedHeight(24)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._pilha.addWidget(self.lbl)
        self._pilha.addWidget(editor)
        self._pilha.setCurrentIndex(0)
        editor.installEventFilter(self)
        if isinstance(editor, QComboBox):
            editor.activated.connect(lambda _=0: self.fechar())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.abrir()

    def abrir(self):
        self._pilha.setCurrentIndex(1)
        self.editor.setFocus(Qt.FocusReason.MouseFocusReason)
        # singleShot: o widget acabou de aparecer na pilha, e chamar showPopup no mesmo ciclo
        # abre a lista com a geometria antiga — em alguns casos ela nem aparece, que foi o
        # "mesmo clicando no campo de técnico não está carregando" que o Levi viu.
        if isinstance(self.editor, QComboBox):
            QTimer.singleShot(0, self.editor.showPopup)

    def fechar(self):
        self._pilha.setCurrentIndex(0)
        self.atualizar()

    def eventFilter(self, obj, ev):
        # sair do campo fecha — MENOS quando quem tirou o foco foi a lista DESTE campo.
        #
        # PopupFocusReason significa "o foco saiu porque o seu proprio popup abriu". Fechar aqui
        # escondia o combo e matava a lista junto: era o "clico e nao aparece nada" que o Levi
        # viu em tema, cliente, usina, ativo, tecnico, grupo e as duas classificacoes.
        #
        # A segunda condicao e cinto e suspensorio: o motivo do FocusOut varia entre plataformas,
        # o estado da lista nao. Enquanto ela estiver aberta, este campo nao fecha por foco.
        if obj is self.editor and ev.type() == ev.Type.FocusOut:
            if ev.reason() == Qt.FocusReason.PopupFocusReason:
                return False
            if isinstance(self.editor, QComboBox) and self.editor.view().isVisible():
                return False
            self.fechar()
        return False

    def atualizar(self):
        if isinstance(self.editor, QComboBox):
            txt = self.editor.currentText() if self.editor.currentData() else ""
        else:
            txt = self.editor.dateTime().toString("dd/MM/yyyy HH:mm")
        self.lbl.setText(txt or self._vazio)

    def setEnabled(self, on):
        super().setEnabled(on)
        self.lbl.setEnabled(on)


class _Fila(QWidget):
    """Fila do PCM: a lista à esquerda, o detalhe à direita, e a OS nascendo na aprovação."""

    def __init__(self, on_voltar):
        super().__init__()
        self._itens = []
        self._sel = None
        self._assets = []
        self._w = None
        v = QVBoxLayout(self)
        # zero margem: as linhas da tabela tem de encostar nas bordas da area, senao o
        # cabecalho vira uma faixa flutuando em vez da primeira linha do conjunto.
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # O cabecalho e uma FAIXA pintada, nao uma linha solta de widgets: ele separa
        # "onde estou" de "o que estou decidindo", e o Voltar perde a borda para nao competir
        # com o botao de aprovar, que e a unica acao de verdade desta tela.
        cab = QFrame()
        cab.setObjectName("filaCab")
        topo = QHBoxLayout(cab)
        topo.setContentsMargins(14, 9, 16, 9)
        topo.setSpacing(12)
        b = QPushButton("← Voltar")
        b.setObjectName("btnVoltar")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(on_voltar)
        topo.addWidget(b)
        tit = QLabel("Fila do PCM")
        tit.setStyleSheet(f"color:{TEXT};font-size:15px;font-weight:600;background:transparent;")
        topo.addWidget(tit)
        topo.addStretch(1)
        self.lbl_cont = QLabel("")
        self.lbl_cont.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_cont.setStyleSheet(f"color:{MUTED};font-size:12.5px;background:transparent;")
        topo.addWidget(self.lbl_cont)
        v.addWidget(cab)

        corpo = QHBoxLayout()
        corpo.setSpacing(0)          # o divisor vertical faz o papel do espaco

        # esquerda: a fila
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        cab_col = QLabel("AGUARDANDO APROVAÇÃO")
        cab_col.setObjectName("cabCol")
        cab_col.setContentsMargins(14, 10, 14, 9)
        col.addWidget(cab_col)
        esq = QScrollArea()
        esq.setWidgetResizable(True)
        # 460 e nao 310: medido nos pendentes reais, o cartao pede entre 363 e 451 px de largura
        # minima (o rodape "quem · quando · tema" nao quebra linha). Com 310 TODO cartao saia
        # cortado no meio do botao Analisar, e a barra horizontal so escondia o problema.
        esq.setFrameShape(QScrollArea.Shape.NoFrame)
        # sem isto o cartao nao encolhe para os 310: o QLabel com wordWrap pede a largura do texto
        # inteiro, aparece barra horizontal e o botao Analisar fica cortado ao meio. A mesma linha
        # existe nas colunas do painel — esta copia a tinha perdido.
        esq.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        esq.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                          "QScrollArea > QWidget > QWidget{background:transparent;}")
        inner = QWidget()
        self.lista = QVBoxLayout(inner)
        self.lista.setContentsMargins(0, 0, 0, 0)
        self.lista.setSpacing(0)      # sem respiro: quem separa uma celula da outra e a linha
        self.lista.addStretch(1)
        esq.setWidget(inner)
        col.addWidget(esq, 1)
        cw = QWidget()
        cw.setLayout(col)
        cw.setFixedWidth(460)
        corpo.addWidget(cw)
        # a linha que separa a lista do detalhe, de cima a baixo — e o que faz os dois lados
        # lerem como duas colunas de uma tabela, e nao como dois blocos independentes
        div = QFrame()
        div.setObjectName("divisorV")
        div.setFixedWidth(1)
        corpo.addWidget(div)

        # direita: o detalhe
        dir_sc = QScrollArea()
        dir_sc.setWidgetResizable(True)
        dir_sc.setFrameShape(QScrollArea.Shape.NoFrame)
        dir_sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        dir_sc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollArea > QWidget > QWidget{background:transparent;}")
        d = QWidget()
        self.det = QVBoxLayout(d)
        # o respiro saiu da area e veio para dentro do detalhe: assim as linhas da tabela
        # encostam nas bordas e o conteudo continua com margem para respirar
        self.det.setContentsMargins(20, 16, 20, 14)
        self.det.setSpacing(12)
        dir_sc.setWidget(d)
        corpo.addWidget(dir_sc, 1)
        v.addLayout(corpo, 1)

        self._montar_detalhe()

    # ── detalhe ──
    # ── detalhe ──
    def _rotulo(self, txt, cor=MUTED):
        """Rótulo em caixa alta pequena: dá hierarquia sem gastar mais uma cor.

        O verde é reservado para o que o supervisor escreveu — é a informação que o PCM está
        ali para conferir, e ela precisa saltar do resto da ficha."""
        l = QLabel(txt.upper())
        l.setStyleSheet("color:%s;font-size:10.5px;font-weight:700;letter-spacing:0.8px;"
                        "background:transparent;" % cor)
        return l

    def _fixo(self, txt):
        """A palavra que rotula um valor editável na mesma linha ('Técnico:', 'Data:')."""
        l = QLabel(txt)
        l.setStyleSheet("color:%s;font-size:13px;font-weight:600;background:transparent;" % TEXT)
        return l

    def _valor(self, txt=""):
        l = QLabel(txt)
        l.setStyleSheet("color:%s;font-size:13px;background:transparent;" % TEXT)
        l.setWordWrap(True)
        l.setMinimumWidth(1)
        return l

    def _montar_detalhe(self):
        # 26 px = 30% acima dos 20 originais. Sem icone antes: o titulo ja e o maior texto da
        # tela e nao precisa de marcador para dizer onde comeca (pedido do Levi, 04/09).
        self.lbl_titulo = QLabel("Selecione uma solicitação na fila.")
        self.lbl_titulo.setStyleSheet("color:%s;font-size:26px;font-weight:600;"
                                      "background:transparent;" % TEXT)
        self.lbl_titulo.setWordWrap(True)
        self.lbl_titulo.setMinimumWidth(1)
        self.det.addWidget(self.lbl_titulo)

        self.lbl_orig = QLabel("")
        self.lbl_orig.setStyleSheet("color:%s;font-size:12px;background:transparent;" % MUTED)
        self.lbl_orig.setWordWrap(True)
        self.lbl_orig.setMinimumWidth(1)
        self.lbl_orig.setTextFormat(Qt.TextFormat.RichText)
        self.det.addWidget(self.lbl_orig)

        # ── a ficha do pedido ──
        ficha = QGridLayout()
        ficha.setContentsMargins(0, 12, 0, 2)
        ficha.setHorizontalSpacing(26)
        ficha.setVerticalSpacing(3)
        self.v_solicitante = self._valor()
        self.v_ativo = self._valor()
        self.v_usina = self._valor()
        # USINA primeiro: e por ela que o PCM situa a solicitacao — quem pediu e o que quebrou
        # so importam depois de saber ONDE. "Aberta em" saiu daqui (pedido do Levi, 04/09): a
        # data absoluta e subdado, e virou tooltip do cartao da fila, onde ja existe o tempo
        # relativo ("ha 21 h") que e o que se le de relance.
        for col, rot, val in ((0, "Usina", self.v_usina),
                              (1, "Solicitante", self.v_solicitante),
                              (2, "Ativo", self.v_ativo)):
            ficha.addWidget(self._rotulo(rot), 0, col)
            ficha.addWidget(val, 1, col)
        # as tres colunas dividem a largura por igual. Antes so a ultima esticava, entao
        # SOLICITANTE e ABERTA EM ficavam espremidos na esquerda e a data quebrava em duas linhas.
        for c in (0, 1, 2):
            ficha.setColumnStretch(c, 1)
        self.det.addLayout(ficha)

        # ── o que o supervisor sugeriu, e que o PCM confirma ou troca ──
        # Linha PARCIAL: nao encosta nas laterais de proposito. Uma linha de ponta a ponta
        # separaria SECOES da tela; esta separa dois blocos da MESMA ficha — o que o Fracttal
        # informou e o que o supervisor sugeriu.
        risco = QWidget()
        rl = QHBoxLayout(risco)
        rl.setContentsMargins(40, 14, 40, 8)
        r1 = QFrame()
        r1.setObjectName("riscoParcial")
        r1.setFixedHeight(1)
        rl.addWidget(r1, 1)
        self.det.addWidget(risco)

        cx = QFrame()
        cx.setObjectName("boxSug")
        cxv = QVBoxLayout(cx)
        cxv.setContentsMargins(16, 13, 16, 14)
        cxv.setSpacing(9)
        cxv.addWidget(self._rotulo("Sugerido pelo supervisor", GREEN))

        # Uma linha só, e cada valor vira campo ao ser clicado. O responsável da OS É o técnico
        # sugerido — tê-los em dois campos distantes fazia parecer decisões diferentes, e o
        # combo aberto o tempo todo dava peso de formulário a algo que quase sempre é só
        # confirmar o que o supervisor já escreveu.
        lin = QGridLayout()
        # UMA LINHA POR CAMPO, com o rotulo numa coluna so. Lado a lado os dois sobravam espaco
        # a direita e o card ficava largo a toa; empilhados, os dois cards do par cabem em 50/50
        # (pedido do Levi, 04/09). A legenda "ambos editaveis" saiu: o sublinhado pontilhado do
        # `valorEditavel` ja e o convite, e a frase repetia o que o campo mostra.
        self.cb_resp = QComboBox()
        self.cb_resp.addItem("— selecione —", None)
        self.cb_resp.setMinimumWidth(180)
        self.ed_tecnico = _CampoClicavel(self.cb_resp, "—")
        # data E hora: "amanha" nao diz se e antes ou depois da parada, e o PCM programa por hora
        self.de_data = QDateTimeEdit()
        self.de_data.setCalendarPopup(True)
        self.de_data.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.de_data.setDateTime(QDateTime.currentDateTime())
        self.ed_data = _CampoClicavel(self.de_data, "—")
        lin.setHorizontalSpacing(10)
        lin.setVerticalSpacing(9)
        lin.addWidget(self._fixo("Técnico:"), 0, 0)
        lin.addWidget(self.ed_tecnico, 0, 1)
        lin.addWidget(self._fixo("Data sugerida:"), 1, 0)
        lin.addWidget(self.ed_data, 1, 1)
        lin.setColumnStretch(1, 1)
        cxv.addLayout(lin)

        # continua existindo para quem lia o resumo em texto (e para os testes)
        self.lbl_sug = QLabel("")
        self.lbl_sug.setVisible(False)
        self.etiquetas = _CardEtiquetas()
        par = QHBoxLayout()
        par.setSpacing(12)
        # 50/50: o bloco da sugestao tinha 70% e sobrava espaco, enquanto o de etiquetas ficava
        # espremido em 30% justamente onde as etiquetas empilham para baixo (pedido do Levi)
        par.addWidget(cx, 1)
        par.addWidget(self.etiquetas, 1)
        self.det.addLayout(par)

        # ── tema ──
        topo_t = QHBoxLayout()
        topo_t.setSpacing(9)
        topo_t.addWidget(self._rotulo("Tema"))
        self.chip_tema = QLabel("")
        self.chip_tema.setObjectName("chipTema")
        self.chip_tema.setVisible(False)
        topo_t.addWidget(self.chip_tema)
        topo_t.addStretch(1)
        self.det.addLayout(topo_t)

        self.cb_tema = QComboBox()
        self.cb_tema.setObjectName("cbTema")
        self.cb_tema.addItem("— sem tema —", "")
        for chave, nome in sp.temas():
            self.cb_tema.addItem(nome, chave)
        self.cb_tema.currentIndexChanged.connect(self._pintar_subs)
        self.det.addWidget(self.cb_tema)

        self.lbl_classif = QLabel("")
        self.lbl_classif.setStyleSheet("color:%s;font-size:12px;background:transparent;" % MUTED)
        self.lbl_classif.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_classif.setWordWrap(True)
        self.lbl_classif.setMinimumWidth(1)
        self.det.addWidget(self.lbl_classif)

        # ── as subtarefas, como lista numerada ──
        # O PCM edita a lista tambem. Ele e quem conhece o ativo e a equipe: o tema acerta o
        # roteiro geral, e o ajuste fino — "neste inversor tem de medir tambem X" — so quem
        # aprova sabe. Sem isso ele voltaria a montar a OS na mao no Fracttal web, que e
        # exatamente o passo que esta tela existe para eliminar.
        self.editor_subs = EditorSubtarefas(
            "Sem tema: a OS nasce com as 3 subtarefas da base. Da para aprovar assim, e da para "
            "acrescentar o que faltar.")
        self.det.addWidget(self.editor_subs)
        self.lbl_subs = QLabel("")          # continua existindo p/ quem lia o resumo em texto
        self.lbl_subs.setVisible(False)

        acoes = QHBoxLayout()
        acoes.setSpacing(10)
        self.b_aprovar = QPushButton("Aprovar e gerar OS")
        self.b_aprovar.setObjectName("btnAprovar")
        self.b_aprovar.setIcon(QIcon(icone_pix("check", GREEN_INK, 16)))
        self.b_aprovar.setIconSize(QSize(16, 16))
        self.b_aprovar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_aprovar.clicked.connect(self._aprovar)
        self.b_devolver = QPushButton("Devolver ao supervisor")
        self.b_devolver.setObjectName("btnDevolver")
        self.b_devolver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_devolver.clicked.connect(self._devolver)
        acoes.addWidget(self.b_aprovar)
        acoes.addWidget(self.b_devolver)
        acoes.addStretch(1)
        self.hint = QLabel("Aprovar avança para a próxima")
        self.hint.setStyleSheet("color:%s;font-size:12px;background:transparent;" % MUTED)
        acoes.addWidget(self.hint)
        self.det.addLayout(acoes)
        self.det.addStretch(1)
        self._habilitar(False)

    def _habilitar(self, on):
        self.b_aprovar.setEnabled(on)
        self.b_devolver.setEnabled(on)
        self.cb_tema.setEnabled(on)
        self.cb_resp.setEnabled(on)
        self.ed_tecnico.setEnabled(on)
        self.ed_data.setEnabled(on)
        self.editor_subs.set_editavel(on)

    # ── carga ──
    def set_itens(self, itens, assets, selecionar=None):
        self._itens = itens or []
        self._assets = assets or []
        while self.lista.count() > 1:
            it = self.lista.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cartoes = []
        for s in self._itens:
            c = _CartaoFila(s, self._selecionar)
            self.lista.insertWidget(self.lista.count() - 1, c)
            self._cartoes.append(c)
        hoje = _hoje_iso()
        novas = sum(1 for s in self._itens if str(s.get("data") or "")[:10] == hoje)
        self.lbl_cont.setText(
            "<b style='color:%s'>%d</b> aguardando" % (GREEN, len(self._itens))
            + ("<span style='color:%s'> · </span><b>%d</b> chegaram hoje" % (MUTED, novas)
               if novas else ""))
        self._selecionar(selecionar or (self._itens[0] if self._itens else None))

    def _selecionar(self, s):
        self._sel = s
        for c in getattr(self, "_cartoes", []):
            c.marcar(c.dados is s)
        if not s:
            self.lbl_titulo.setText("Nada na fila.")
            for l in (self.lbl_orig, self.lbl_sug, self.lbl_classif, self.chip_tema):
                l.setText("")
            self.chip_tema.setVisible(False)
            for l in (self.v_solicitante, self.v_ativo, self.v_usina):
                l.setText("—")
            self.ed_tecnico.lbl.setText("—")
            self.ed_data.lbl.setText("—")
            self._habilitar(False)
            self._pintar_subs()
            return
        bloco = sp.parse(s.get("observacao")) or {}
        tema = bloco.get("tema") or ""
        i = next((i for i in range(self.cb_tema.count()) if self.cb_tema.itemData(i) == tema), 0)
        self.cb_tema.blockSignals(True)
        self.cb_tema.setCurrentIndex(i)
        self.cb_tema.blockSignals(False)
        # o chip tem fundo proprio: vazio ele pinta um retangulo verde sem texto dentro
        self.chip_tema.setText("sugerido pela descrição" if tema else "")
        self.chip_tema.setVisible(bool(tema))

        novo = sp.titulo(s.get("usina") or "", s.get("ativo") or "", tema) if tema else ""
        orig = str(s.get("descricao_full") or s.get("descricao") or "")
        self.lbl_titulo.setText(novo or orig)
        # O PCM está reescrevendo o texto de outra pessoa — precisa ver o que está mudando.
        self.lbl_orig.setText(
            "o supervisor escreveu: <s>%s</s> · título reescrito no padrão" % orig
            if novo and novo != orig else "")
        self.v_solicitante.setText(str(s.get("criado_por") or "—"))
        self.v_ativo.setText(str(s.get("ativo") or "—"))
        self.v_usina.setText(str(s.get("usina") or "—"))
        tec, dt = bloco.get("tecnico"), bloco.get("data")
        self.lbl_sug.setText("Técnico: %s · Data pretendida: %s" % (tec or "—", dt or "—"))
        # aceita os DOIS formatos: as solicitacoes ja criadas trazem so a data
        d = QDateTime.fromString(str(dt or ""), "dd/MM/yyyy HH:mm")
        if not d.isValid():
            so_dia = QDate.fromString(str(dt or ""), "dd/MM/yyyy")
            d = QDateTime(so_dia, QTime(8, 0)) if so_dia.isValid() else QDateTime()
        self.de_data.setDateTime(d if d.isValid() else QDateTime.currentDateTime())
        self.ed_data.lbl.setText(d.toString("dd/MM/yyyy HH:mm") if d.isValid() else "—")
        self._pre_selecionar_responsavel(tec)
        self._habilitar(True)
        self._pintar_subs(do_bloco=bloco.get("subtarefas"))
        self.etiquetas.limpar()
        self.etiquetas.aplicar_regra(tema, s.get("ativo") or "")

    def set_responsaveis(self, pessoas):
        """Lista de quem pode receber a OS. Acessoria: sem ela o PCM ainda ve a fila, mas nao
        consegue aprovar — por isso o botao avisa em vez de falhar calado."""
        atual = self.cb_resp.currentText()
        if not pessoas:
            self.cb_resp.blockSignals(True)
            self.cb_resp.clear()
            self.cb_resp.addItem("carregando técnicos…", None)
            self.cb_resp.blockSignals(False)
            return
        self.cb_resp.blockSignals(True)
        self.cb_resp.clear()
        self.cb_resp.addItem("— selecione —", None)
        for p in (pessoas or []):
            self.cb_resp.addItem(p.get("name") or "", p.get("id_personnel"))
        self.cb_resp.blockSignals(False)
        self._pre_selecionar_responsavel(atual)

    def _pre_selecionar_responsavel(self, nome):
        """Pre-seleciona o tecnico que o SUPERVISOR sugeriu. E o que fecha o ciclo: a sugestao
        dele deixa de ser texto na observacao e vira o responsavel da OS."""
        alvo = (nome or "").strip().lower()
        if not alvo:
            self.cb_resp.setCurrentIndex(0)
            self.ed_tecnico.atualizar()
            return
        for i in range(self.cb_resp.count()):
            if self.cb_resp.itemText(i).strip().lower() == alvo:
                self.cb_resp.setCurrentIndex(i)
                self.ed_tecnico.atualizar()
                return
        self.cb_resp.setCurrentIndex(0)
        # o nome sugerido aparece mesmo sem casar na lista: some-lo faria parecer que o
        # supervisor nao sugeriu ninguem, quando ele sugeriu alguem que nao esta cadastrado
        self.ed_tecnico.lbl.setText(nome or "—")

    def _pintar_subs(self, do_bloco=None):
        """Carrega a lista no editor. `do_bloco` tem PRECEDENCIA sobre o tema: se o supervisor
        editou as subtarefas na solicitacao, o que ele escreveu e o ponto de partida — trocar
        pela lista padrao do tema desfaria o trabalho dele sem avisar."""
        tema = self.cb_tema.currentData() or ""
        self.cb_tema.setProperty("temado", "1" if tema else "0")
        self.cb_tema.style().unpolish(self.cb_tema)
        self.cb_tema.style().polish(self.cb_tema)
        # trocar o tema pode ligar ou desligar a regra da PERFORMANCE
        if getattr(self, "etiquetas", None) is not None and self._sel:
            self.etiquetas.aplicar_regra(tema, (self._sel or {}).get("ativo") or "")
        cl = sp.classificacao(tema) if tema else {}
        self.lbl_classif.setText(
            ("Classificação 1: <b style='color:%s'>%s</b>&nbsp;&nbsp;"
             "<span style='color:%s'>domínio %s%%</span>"
             % (TEXT, cl.get("classif1") or "—", MUTED, cl.get("dominio")))
            if tema and cl.get("classif1") else "")
        if do_bloco:
            self.editor_subs.set_itens(do_bloco)
        # A LISTA NUNCA FICA VAZIA. Antes o `else` bastava, mas se o bloco do supervisor viesse
        # com subtarefas que nao sobrevivem a conversao (descricao em branco, por exemplo), o
        # editor terminava sem nenhuma linha — e ai aparecia so a frase "a OS nasce com as 3
        # subtarefas da base" sem as tres em lugar nenhum, que foi o que o Levi estranhou.
        # Decidir pelo RESULTADO, e nao pela intencao, fecha esse caminho.
        if not self.editor_subs.itens():
            self.editor_subs.set_itens(
                sp.de_api(sp.subtarefas(tema) if tema else sp.subtarefas_base()))
        self.lbl_subs.setText("%d subtarefas" % len(self.editor_subs.itens()))

    # ── ações ──
    def _asset_da(self, s):
        """Registro completo do ativo da solicitação. None quando não dá para ter CERTEZA.

        Só id_item e código valem. NÃO casar por nome: "Chave Seccionadora 1" existe em várias
        usinas, e ao aprovar a 3534 (TESTE - PA) o casamento por nome escolheu o ativo da APG100
        — outra usina, de cliente de verdade. A criação falhou por outro motivo e o erro não
        chegou a produzir OS, mas teria criado no lugar errado sem dar erro nenhum.

        Devolver None e pedir para recarregar é sempre melhor do que acertar por acaso."""
        idi = s.get("id_item")
        if idi:
            for a in self._assets:
                if a.get("id") == idi:
                    return a
        code = (s.get("code") or "").strip()
        if code:
            for a in self._assets:
                if (a.get("code") or "").strip() == code:
                    return a
        return None

    def _aprovar(self):
        s = self._sel
        if not s:
            return
        asset = self._asset_da(s)
        if not asset:
            QMessageBox.warning(self, "Ativo", "Não achei o ativo desta solicitação no catálogo. "
                                               "Recarregue os ativos e tente de novo.")
            return
        tema = self.cb_tema.currentData() or ""
        # o que vai para a OS e o que esta NA TELA, nao o padrao do tema: o PCM acabou de editar
        subs = self.editor_subs.para_api() or sp.subtarefas_base()
        titulo = sp.titulo(s.get("usina") or "", s.get("ativo") or "", tema) if tema else \
            str(s.get("descricao_full") or s.get("descricao") or "")
        n = len(subs)
        if QMessageBox.question(
                self, "Aprovar e gerar OS",
                f"Criar a OS “{titulo}” com {n} subtarefa(s)?\n\n"
                "A API do Fracttal NÃO edita OS já criada — confira as subtarefas antes.") \
                != QMessageBox.StandardButton.Yes:
            return
        idr = self.cb_resp.currentData()
        if not idr:
            QMessageBox.warning(self, "Responsável",
                                "Escolha o responsável pela OS.\n\n"
                                "Sem responsável a tarefa é criada mas NÃO vira OS numerada — ela "
                                "fica pendente no kanban do Fracttal e ninguém a vê.")
            return
        self._habilitar(False)
        self.hint.setText("criando a OS…")
        # `aprovar_solicitacao` e não `create_os_rpc`: a criação da OS tem DUAS fases. O
        # `create_os_rpc` cria só a TAREFA e devolve `id_task`; quem transforma a tarefa em OS
        # numerada é o `_work_order_insert` da fase 2, e ele exige responsável. Chamando só a
        # fase 1, a aprovação criava tarefa solta e devolvia wo_folio=None — sem erro nenhum.
        # E ela retoma: se uma tentativa anterior parou no meio, o Fracttal recusa a segunda
        # tarefa (unique_violation por solicitação) e a solicitação ficaria presa para sempre.
        self._w = ApiWorker(api.aprovar_solicitacao, asset, titulo, subs, s.get("id_code"),
                            idr, self.cb_resp.currentText(),
                            note=str(s.get("observacao") or ""),
                            etiqueta_ids=self.etiquetas.ids())
        self._w.ok.connect(self._os_ok)
        self._w.erro.connect(self._os_err)
        self._w.start()

    @slot_seguro
    def _os_ok(self, r):
        """O `clonar_os` devolve ENVELOPE — {'ok','os':{...},'erro','aviso'} — e devolve ok=True
        mesmo quando só criou a tarefa e não a OS numerada. Ler `r['wo_folio']` direto dava
        "OS criada" para todo caso, inclusive o que não criou OS nenhuma."""
        self._w = None
        self.hint.setText("")
        self._habilitar(True)
        r = r or {}
        folio = ((r.get("os") or {}).get("wo_folio")) or None
        if not r.get("ok"):
            QMessageBox.critical(self, "Erro ao criar a OS",
                                 str(r.get("erro") or "a API não disse o motivo."))
            return
        if not folio:
            # tarefa criada sem virar OS: fica pendente no kanban e some da vista de todo mundo.
            QMessageBox.warning(self, "OS não numerada",
                                f"{r.get('aviso') or 'A OS não recebeu número.'} "
                                "A solicitação continua na fila.")
            return
        QMessageBox.information(self, "OS criada", f"OS {folio} criada a partir da solicitação "
                                                   f"Nº {(self._sel or {}).get('id_code')}.")
        # Aprovar avança para a próxima: são vários na fila e voltar à lista a cada uma
        # transformaria N decisões em 2N cliques.
        restantes = [x for x in self._itens if x is not self._sel]
        self.set_itens(restantes, self._assets)

    @slot_seguro
    def _os_err(self, m):
        self._w = None
        self.hint.setText("")
        self._habilitar(True)
        QMessageBox.critical(self, "Erro ao criar a OS", str(m))

    def _devolver(self):
        s = self._sel
        if not s:
            return
        QMessageBox.information(
            self, "Devolver ao supervisor",
            "Ainda não implementado.\n\nDevolver muda o status da solicitação no Fracttal, e o "
            "servidor recusa se a conta não tiver essa permissão — precisa ser testado com a "
            "conta do PCM antes de entrar.")


class _CardBotao(_PlanoCard):
    """O card do hub, na MESMA forma da tela de Criar OS — porque E a mesma classe.

    Medido em 04/09 antes de escrever qualquer coisa: `steps/performance.py` nao tem uma unica
    ocorrencia de QGraphicsEffect, QPropertyAnimation ou QEasingCurve. A tela que o Levi apontou
    como referencia nao tem animacao nem sombra; tem um QFrame de raio 14 que troca a borda para
    verde no hover, e mais nada. Herdar em vez de copiar garante que continue assim nas duas.

    O que esta casca acrescenta e so o que o hub precisa e o plano nao tem: o estado ATIVO — o
    card que abriu os tres de baixo — e rotulos que encolhem, sem os quais a grade nao reflui.
    """

    def __init__(self, titulo, sub, on_click, icone="grid", badge=""):
        super().__init__(icone, titulo, badge, sub, on_click)
        self._ativo = False
        self.setProperty("ativo", "0")
        # "N subtarefas" e dos planos do Fracttal — aqui o rotulo ficaria eternamente em
        # "... subtarefas" esperando uma contagem que nunca vem. Mesmo tratamento que o card
        # Tickets recebe na tela de Criar OS.
        self.sub_lbl.setVisible(False)
        # e o iconezinho de lista que fica ao lado dele: escondendo so o rotulo sobra um "≡"
        # solto embaixo do subtitulo. O maximumWidth separa: ele e o unico QLabel do card com
        # setFixedSize(13, 13).
        for lbl in self.findChildren(QLabel):
            if lbl.maximumWidth() == 13:
                lbl.setVisible(False)
        # DEIXA O CARD ENCOLHER. Sem isto o minimo do hub vai a 1009 px contra um limiar de 790,
        # e o refluxo para uma coluna nunca engata — exatamente o codigo morto que o teste do
        # refluxo existe para impedir. Um QLabel com wordWrap so quebra a linha se puder ser mais
        # estreito que o texto, e o padrao dele e exigir o texto inteiro.
        # O filtro pelo maximumWidth separa sozinho quem pode encolher: o tile do icone e a seta
        # usam setFixedSize, entao o maximo deles e a propria largura; so os rotulos de texto
        # ficam com o maximo aberto do Qt.
        for lbl in self.findChildren(QLabel):
            if lbl.maximumWidth() >= 16777215:
                lbl.setMinimumWidth(1)

    def _pintar(self):
        # a folha e do proprio widget (nao vem do ancestral), entao trocar o estado e reescreve-la
        self.setStyleSheet(
            "QFrame#planoCard{background:%s;border:1px solid %s;border-radius:14px;}"
            "QFrame#planoCard:hover{border:1px solid %s;}"
            % (CARD, GREEN if self._ativo else BORDER, GREEN))

    def marcar_ativo(self, on):
        """Borda verde acesa no card que abriu os tres de baixo.

        E o que liga o que apareceu a quem foi clicado. Sem isso os tres destinos surgem na tela
        sem dizer de onde vieram."""
        if on == self._ativo:
            return
        self._ativo = on
        # a propriedade e o contrato OBSERVAVEL do estado: sem ela, "este card esta ativo" ficaria
        # so dentro da folha de estilo, onde nem teste nem outra tela consegue perguntar
        self.setProperty("ativo", "1" if on else "0")
        self._pintar()


class _Hub(QWidget):
    """A tela de entrada da aba: dois caminhos, e o do PCM abre os tres destinos dele.

    SEM ANIMACAO, de proposito. O Levi pediu esta tela na forma da de Criar OS, e aquela tela
    nao anima nada: `steps/performance.py` nao tem uma unica ocorrencia de QGraphicsEffect,
    QPropertyAnimation ou QEasingCurve. Os cards simplesmente estao la, e a unica reacao e a
    borda ficar verde no hover.

    Havia aqui uma entrada em cascata que custou tres correcoes em dois dias — card preso
    apagado, card piscando, entrada espacada — e cada uma so aparecia no app de verdade, nunca
    no teste. A tela que ele apontou como boa e a que nao tem nada disso.
    """

    COLS = 2                # colunas da grade, como na tela de Criar OS
    # 360 e nao 300: o card do plano leva tile de 44, texto e seta de 34 na mesma linha, entao
    # ele precisa de mais largura que o card antigo antes de valer a pena empilhar.
    LARG_CARD = 360         # largura confortavel de um card; base do limiar de refluxo

    def __init__(self, ir):
        super().__init__()
        self._ir = ir
        self._aberto = False
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 26, 28, 26)
        v.setSpacing(16)

        t = QLabel("Solicitação / PCM")
        t.setStyleSheet(f"color:{TEXT};font-size:19px;font-weight:600;")
        v.addWidget(t)
        # mesma voz da tela de Criar OS: uma frase que diz o que cada clique FAZ, e nao o que a
        # tela e. Quem abre isto aqui na maioria das vezes e o supervisor, para pedir.
        d = QLabel("Escolha o que vai fazer. <b>Criar Nova Solicitação</b> é o pedido do "
                   "supervisor; em <b>Área PCM</b> ficam a fila de aprovação, o acompanhamento "
                   "e o histórico.")
        d.setObjectName("uiAjuda")
        d.setWordWrap(True)
        v.addWidget(d)

        # GRADE de 2 colunas, igual a de Criar OS. Nao e so estetica: com o card do plano, que e
        # largo (tile + texto + seta), tres lado a lado espremem o subtitulo em duas linhas.
        self.g_topo = QGridLayout()
        self.g_topo.setSpacing(14)
        self.c_nova = _CardBotao("Criar Nova Solicitação",
                                 "Pedir serviço já com tema, técnico sugerido e data pretendida",
                                 lambda: self._ir("nova"), icone="send", badge="Supervisor")
        self.c_pcm = _CardBotao("Área PCM",
                                "Conferir a fila, aprovar e acompanhar o que virou OS",
                                self._abrir_pcm, icone="calcheck", badge="PCM")
        v.addLayout(self.g_topo)

        self.sub = QWidget()
        self.g_sub = QGridLayout(self.sub)
        self.g_sub.setContentsMargins(0, 0, 0, 0)
        self.g_sub.setSpacing(14)          # o mesmo respiro da grade de cima: uma grade so
        self._subcards = []
        for rot, txt, alvo, ico, bd in (
                ("Painel", "O que está pendente, em andamento e finalizado",
                 "painel", "grid", "Acompanhar"),
                ("Fila do PCM", "Aprovar uma a uma, com as subtarefas do tema",
                 "fila", "list", "Aprovar"),
                ("Histórico", "Tudo o que já passou por aqui", "hist", "clock", "Consultar"),
                ("Temas", "Padronizar nome, subtarefas e tipo de equipamento",
                 "temas", "layers", "Padronizar")):
            c = _CardBotao(rot, txt, lambda a=alvo: self._ir(a), icone=ico, badge=bd)
            self._subcards.append(c)
        self.sub.setVisible(False)
        v.addWidget(self.sub)
        v.addStretch(1)
        self._estreito = None
        self._reflow(inicial=True)

    # ── navegacao ──
    def _abrir_pcm(self):
        """1o clique abre os tres destinos; 2o vai direto para a fila, que e onde o PCM trabalha.

        O estado fica num atributo e nao em `isVisible()`: isVisible responde pela cadeia
        inteira de pais, entao seria False com a aba em segundo plano — e o segundo clique
        reabriria em vez de navegar."""
        if self._aberto:
            self._ir("fila")
            return
        self._aberto = True
        self.c_pcm.marcar_ativo(True)
        self.sub.setVisible(True)

    def recolher(self):
        self._aberto = False
        self.c_pcm.marcar_ativo(False)
        self.sub.setVisible(False)

    # ── refluxo ──
    def _reflow(self, inicial=False):
        """Coloca os cards em coluna ou em linha, conforme a largura.

        E a metade que faltava para a referencia de `mediaQueries` fazer sentido: la o LAYOUT
        muda junto, e por isso trocar o eixo do movimento significa alguma coisa."""
        estreito = self._matches()["estreito"]
        if estreito == self._estreito:
            return False
        self._estreito = estreito
        cols = 1 if estreito else self.COLS
        # os cards entram DIRETO na grade. Ate 04/09 cada um vinha embrulhado numa moldura sem
        # layout, que existia so para a animacao poder move-los a mao; sem animacao ela some.
        for g, itens in ((self.g_topo, [self.c_nova, self.c_pcm]),
                         (self.g_sub, self._subcards)):
            for w in itens:
                g.removeWidget(w)
            for i in range(g.columnCount()):
                g.setColumnStretch(i, 0)
            # 2 colunas, como a tela de Criar OS. O terceiro card do PCM cai sozinho na linha
            # de baixo — que e exatamente o que o card Tickets faz naquela tela.
            for i, w in enumerate(itens):
                g.addWidget(w, i // cols, i % cols)
            for i in range(min(cols, len(itens))):
                g.setColumnStretch(i, 1)
            g.invalidate()
            g.activate()
        return not inicial

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # o escopo do anime.js REEXECUTA quando a media query muda; aqui, quando o formato muda,
        # o layout se refaz e a entrada roda de novo no eixo novo
        self._reflow()

    # ── animacao ──
    def _limiar(self):
        """A largura a partir da qual os tres cards ainda cabem lado a lado, com folga.

        NAO usar sizeHint(): os rotulos tem wordWrap e minimumWidth(1), entao o sizeHint do card
        colapsa para ~110 px e o limiar sairia em 383 — abaixo de qualquer largura real."""
        return (self.LARG_CARD * self.COLS
                + self.g_sub.spacing() * (self.COLS - 1) + 56)

    def _matches(self):
        """O nosso `self.matches`: o que vale de verdade sobre o formato atual da tela."""
        return {"estreito": self.width() < self._limiar()}



class SolicPcmTab(QWidget):
    """A aba. Hub de entrada → Nova solicitação · Painel · Fila do PCM · Histórico, num stack só.

    A ordem da navegação segue o fluxo real, e não a ordem em que as telas foram escritas: quem
    abre a aba na maioria das vezes é o supervisor, para PEDIR."""

    HUB, NOVA, PAINEL, FILA, HIST, TEMAS = 0, 1, 2, 3, 4, 5

    def __init__(self):
        super().__init__()
        self.setStyleSheet(QSS_FORM + """
QPushButton#navPag { background:transparent; color:#8a90a2; border:none;
  border-bottom:2px solid transparent; padding:7px 14px; font-size:13.5px; font-weight:600;
  min-height:0; }
QPushButton#navPag:hover { color:#e6e8ef; }
QPushButton#navPag:checked { color:#e8ebf2; border-bottom:2px solid #8fce3f; }
/* mesma forma dos cards da tela inicial do app: o risco verde embaixo e o que da cor e
   parentesco. Sem ele o card e um retangulo cinza com texto dentro. */
QFrame#hubCard { background:#161d30; border:1px solid #232a3d;
  border-bottom:2px solid #8fce3f; border-radius:14px; }
QFrame#hubCard:hover { border:1px solid #8fce3f; border-bottom:2px solid #8fce3f;
  background:#18203a; }
/* ATIVO: e o card que abriu os tres de baixo. A borda engorda e o icone acende, para o olho
   ligar o que apareceu a quem foi clicado. */
QFrame#hubCard[ativo="1"] { border:1px solid #8fce3f; border-bottom:4px solid #A6E22E;
  background:#18203a; }
QFrame#hubCard[ativo="1"] QLabel#hubIcone { background:rgba(166,226,46,0.30); }
QLabel#hubIcone { background:rgba(143,206,63,0.14); border-radius:12px; border:none; }

/* CELULA, nao cartao (decisao do Levi, 03/09). A fila e uma tabela: mesmo fundo da pagina,
   sem borda em volta e sem cantos, e cada item separado do seguinte por uma linha so. Cartao
   com borda e respiro fazia cada solicitacao parecer um objeto solto; aqui elas sao linhas de
   uma lista, que e o que sao. A barra verde da esquerda marca a selecionada. */
QFrame#filaCard { background:transparent; border:none;
  border-bottom:1px solid #222c43; border-left:3px solid transparent; }
QFrame#filaCard:hover { background:#161d30; }
QFrame#filaCard[sel="1"] { background:#161d30; border-left:3px solid #8fce3f; }
/* sem font-size aqui de proposito: o QSS venceria o setFont e o fontMetrics() do rotulo
   passaria a mentir — media 403 px num texto que pinta com 150, e o elide comia o nome do
   tema sem necessidade. O tamanho vai por setFont, em _CartaoFila. */
QLabel#chipTema { background:rgba(143,206,63,0.14); color:#a9d96a; border-radius:5px;
  padding:2px 8px; font-weight:600; }
QLabel#chipVazio { background:rgba(138,144,162,0.12); color:#8a90a2; border-radius:5px;
  padding:2px 8px; }
QFrame#boxSug { background:#141b2c; border:1px solid #232a3d; border-radius:10px; }
QFrame#boxSubs { background:#141b2c; border:1px solid #232a3d; border-radius:10px; }
QLabel#subsCab { color:#8a90a2; font-size:11.5px; padding:10px 14px;
  border-bottom:1px solid #212840; background:transparent; }
QFrame#subLinha { border-bottom:1px solid #1b2235; background:transparent; }
QFrame#subLinha[ultima="1"] { border-bottom:none; }

/* o cabecalho e a PRIMEIRA LINHA da tabela: sem cantos e sem bordas laterais, so o risco de
   baixo, que atravessa a largura inteira e amarra o titulo as celulas da lista e do detalhe. */
QFrame#filaCab { background:#161d30; border:none; border-bottom:1px solid #222c43; }
QFrame#divisorV { background:#222c43; }
QFrame#riscoParcial { background:#222c43; border:none; }
QLabel#cabColBar { background:#161d30; }
QLabel#cabCol { color:#8a90a2; font-size:10.5px; font-weight:700; letter-spacing:0.8px;
  background:#0b1020; border-bottom:1px solid #222c43; }
QPushButton#btnVoltar { background:transparent; border:none; color:#8a90a2; font-size:13px;
  font-weight:600; padding:2px 4px; min-height:0; }
QPushButton#btnVoltar:hover { color:#e6e8ef; }
/* valor que vira campo ao clicar: sublinhado pontilhado e o convite, sem virar botao */
QLabel#valorEditavel { color:#e8ebf2; font-size:13px; background:transparent;
  border-bottom:1px dashed #39405a; padding:1px 2px; }
QLabel#valorEditavel:hover { color:#ffffff; border-bottom:1px dashed #8fce3f; }
QLabel#valorEditavel:disabled { color:#5a6072; border-bottom:1px dashed #262d42; }
/* tema escolhido = borda verde: e o campo que decide o checklist da OS */
QComboBox#cbTema[temado="1"] { border:1px solid #8fce3f; }
QPushButton#chipEtq { background:rgba(138,144,162,0.14); color:#c9d0e0; border:1px solid #39405a;
  border-radius:9px; padding:2px 9px; font-size:10.5px; font-weight:600; min-height:0; }
QPushButton#chipEtq:hover { border-color:#e05555; color:#ffffff; }
QPushButton#chipEtqPerf { background:rgba(166,226,46,0.16); color:#A6E22E;
  border:1px solid rgba(166,226,46,0.55); border-radius:9px; padding:2px 9px; font-size:10.5px;
  font-weight:700; min-height:0; }
QPushButton#chipEtqPerf:disabled { color:#A6E22E; }
/* o campo aberto dentro do _CampoClicavel: só o risco verde embaixo. A moldura inteira comia
   os minutos da hora, porque a regra genérica do formulário traz padding e raio. */
QDateTimeEdit#campoInline, QComboBox#campoInline {
  background:transparent; border:none; border-bottom:1px solid #8fce3f; border-radius:0;
  color:#e8ebf2; font-size:13px; min-height:24px; max-height:24px; padding:0 2px; }
QDateTimeEdit#campoInline::drop-down, QComboBox#campoInline::drop-down { border:none; width:0px; }
QComboBox#campoInline QAbstractItemView { background:#161d30; color:#e8ebf2;
  border:1px solid #222c43; selection-background-color:rgba(143,206,63,0.18); outline:none; }
/* Os dois botoes da fila NAO tem o mesmo peso: aprovar e a decisao, devolver e a excecao.
   Dois retangulos iguais lado a lado obrigam a ler os dois toda vez. O primario ganha altura,
   raio maior e um assentamento (borda inferior mais escura) que o levanta do fundo; o outro
   perde o preenchimento e vira contorno discreto. */
QPushButton#btnAprovar { background:#A6E22E; color:#0B1020; border:none;
  border-bottom:2px solid #6d9c14; border-radius:11px; min-height:44px; padding:0 22px;
  font-size:13.5px; font-weight:700; }
QPushButton#btnAprovar:hover { background:#b8f03f; border-bottom:2px solid #7fae1c; }
QPushButton#btnAprovar:pressed { background:#8fce3f; border-bottom:2px solid #6d9c14;
  margin-top:2px; }
QPushButton#btnAprovar:disabled { background:#2c3142; color:#6b7080; border-bottom:2px solid #232a3d; }
QPushButton#btnDevolver { background:transparent; color:#9aa3b8; border:1px solid #222c43;
  border-radius:11px; min-height:44px; padding:0 18px; font-size:13px; font-weight:600; }
QPushButton#btnDevolver:hover { color:#e6e8ef; border-color:#3d4a6b; background:#141b2c; }
QPushButton#btnDevolver:disabled { color:#5a6072; border-color:#232a3d; }

/* acao secundaria dentro de um item de lista: texto, nao botao */
QPushButton#btnLink { background:transparent; border:none; color:#8fce3f; font-size:12px;
  font-weight:600; padding:0 2px; min-height:0; text-align:right; }
QPushButton#btnLink:hover { color:#b4ec42; text-decoration:underline; }
""")
        self._assets = []
        self._wresp = None   # a thread precisa de dono vivo (ver steps/CLAUDE.md)
        self._wetq = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        nav = QHBoxLayout()
        nav.setContentsMargins(16, 10, 16, 0)
        nav.setSpacing(8)
        self._btns = []
        self._nav = nav
        b0 = QPushButton("‹ Início")
        b0.setObjectName("navPag")
        b0.setCursor(Qt.CursorShape.PointingHandCursor)
        b0.clicked.connect(lambda: self.ir(self.HUB))
        nav.addWidget(b0)
        for i, rot in ((self.NOVA, "Nova solicitação"), (self.PAINEL, "Painel"),
                       (self.FILA, "Fila do PCM"), (self.HIST, "Histórico"),
                       (self.TEMAS, "Temas")):
            b = QPushButton(rot)
            b.setObjectName("navPag")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=i: self.ir(k))
            nav.addWidget(b)
            self._btns.append(b)
        nav.addStretch(1)
        v.addLayout(nav)

        self.stack = QStackedWidget()
        self.hub = _Hub(self._do_hub)
        self.nova = SolicitacaoTab()
        self.painel = _Painel(self._analisar)
        self.fila = _Fila(lambda: self.ir(self.PAINEL))
        self.hist = HistoricoSolic()
        self.temas = TemasTab(lambda: self.ir(self.HUB))
        for w in (self.hub, self.nova, self.painel, self.fila, self.hist, self.temas):
            self.stack.addWidget(w)
            # O QStackedWidget se dimensiona pela MAIOR de todas as paginas, mesmo as escondidas.
            # Com isto o Historico — cuja barra de filtros pede 1025 px — impunha a largura
            # minima dele ao hub, que pede 485. Marcando as paginas ocultas como Ignored, o
            # stack passa a seguir so a que esta na tela, e cada uma encolhe ate o proprio limite.
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        v.addWidget(self.stack, 1)
        self.ir(self.HUB)

    def _do_hub(self, alvo):
        self.ir({"nova": self.NOVA, "painel": self.PAINEL, "fila": self.FILA,
                 "hist": self.HIST, "temas": self.TEMAS}[alvo])

    def ir(self, i):
        # sair do hub RECOLHE os tres do PCM: voltando, o clique em Area PCM roda a cascata
        # inteira outra vez, em vez de encontrar os cards ja abertos e parados
        if i != self.HUB and self.stack.currentIndex() == self.HUB:
            self.hub.recolher()
        self.stack.setCurrentIndex(i)
        for k in range(self.stack.count()):
            w = self.stack.widget(k)
            pol = (QSizePolicy.Policy.Preferred if k == i else QSizePolicy.Policy.Ignored)
            w.setSizePolicy(pol, pol)
        self.stack.widget(i).adjustSize()
        # no hub a navegação não aparece: o hub JÁ é o menu, e duas barras de navegação na mesma
        # tela é a pessoa perguntando qual das duas manda.
        for k in range(self._nav.count()):
            w = self._nav.itemAt(k).widget()
            if w:
                w.setVisible(i != self.HUB)
        for b, k in zip(self._btns,
                        (self.NOVA, self.PAINEL, self.FILA, self.HIST, self.TEMAS)):
            b.setChecked(k == i)
        if i == self.FILA:
            # reaproveita a lista de pessoas que o formulário já buscou — uma chamada em vez de duas
            pessoas = self._pessoas()
            self.fila.set_responsaveis(pessoas)
            if not self.fila.etiquetas._catalogo:
                self._wetq = ApiWorker(api.get_labels)
                self._wetq.ok.connect(self._espalhar_etiquetas)
                self._wetq.start()
            if not pessoas:
                # 20 s e o tempo medido do carregamento inicial. Sem dizer isso, o campo aparece
                # vazio e a pessoa conclui que nao ha tecnico cadastrado — foi o que aconteceu.
                self.fila.ed_tecnico.lbl.setText("carregando técnicos…")
            if not pessoas and self._wresp is None:
                # o PCM pode abrir a fila antes de o formulário terminar de carregar; sem
                # responsável não sai OS numerada, então buscamos aqui também.
                self._wresp = ApiWorker(api.get_responsaveis)
                self._wresp.ok.connect(self.fila.set_responsaveis)
                self._wresp.start()
            self.fila.set_itens(self.painel.pendentes(), self._assets)
        if i == self.HIST and hasattr(self.hist, "carregar_inicial"):
            self.hist.carregar_inicial()
        if i == self.TEMAS:
            # os tipos da tela saem do CADASTRO, nao de uma lista escrita a mao: e o mesmo
            # campo `tipo` que o filtro de ativos compara, entao os dois nunca divergem
            self.temas.set_tipos_de_ativo(self._assets)
            # o catalogo de etiquetas e o MESMO que a Fila usa. Se ela ja buscou, reaproveita;
            # senao busca aqui — duas telas pedindo a mesma lista ao Fracttal e requisicao a toa
            cat = getattr(self.fila.etiquetas, "_catalogo", None)
            if cat:
                self.temas.set_catalogo_etiquetas(cat)
            elif self._wetq is None:
                self._wetq = ApiWorker(api.get_labels)
                self._wetq.ok.connect(self._espalhar_etiquetas)
                self._wetq.start()
            self.temas.carregar_inicial()

    @slot_seguro
    def _espalhar_etiquetas(self, cat):
        """Uma busca, duas telas: a Fila escolhe a etiqueta da OS e Temas define a do tema."""
        self._wetq = None
        self.fila.etiquetas.set_catalogo(cat)
        self.temas.set_catalogo_etiquetas(cat)

    def _pessoas(self):
        """A lista de tecnicos que o formulario ja carregou, no formato do get_responsaveis."""
        cb = getattr(self.nova, "cb_tecnico", None)
        if cb is None:
            return []
        return [{"name": cb.itemText(i), "id_personnel": cb.itemData(i)}
                for i in range(cb.count()) if cb.itemData(i)]

    def _analisar(self, s):
        self.ir(self.FILA)   # ja carrega os responsaveis; a ordem importa (ver _selecionar)
        self.fila.set_itens(self.painel.pendentes(), self._assets, selecionar=s)

    # ── o que o app.py chama ──
    def set_assets(self, assets):
        self._assets = assets or []
        if hasattr(self.nova, "set_assets"):
            self.nova.set_assets(assets)

    def carregar_inicial(self):
        if hasattr(self.nova, "carregar_inicial"):
            self.nova.carregar_inicial()
        self.painel.carregar()

    def abrir_nova(self):
        """Deep link do detalhe da OS: 'Criar Solicitação deste ativo' cai aqui."""
        self.ir(self.NOVA)
