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
from PyQt6.QtCore import (Qt, QSize, QTimer, QPoint, QDate, QEasingCurve, QPropertyAnimation,
                          QParallelAnimationGroup)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QScrollArea, QFrame, QMessageBox, QComboBox,
                             QGridLayout, QLineEdit, QGraphicsOpacityEffect, QSizePolicy,
                             QDateEdit, QStackedLayout)

from datetime import datetime

import api
import solic_spec as sp
from workers import ApiWorker, slot_seguro
from steps.ui import (QSS_FORM, Card, campo, icone_pix, GREEN, GREEN_INK, MUTED, TEXT,
                      CARD, BORDER, BG, INPUT)
from steps.solicitacao import SolicitacaoTab
from steps.historico_solic import HistoricoSolic

# As três colunas do painel, na ordem do Fracttal. A régua de cada uma sai do que foi medido:
# "pendente" é a solicitação SEM OS vinculada e não cancelada — e não um id_status fixo, porque
# quem decide o status é o servidor (a criação manda 0 e volta 1 ou 7, conforme o caminho).
PENDENTE, ANDAMENTO, FINALIZADA, FORA = "pendente", "andamento", "finalizada", "fora"
_CANCELADAS = {"cancelada", "rejeitada"}
# "Reaberta (refazer)" (AGAIN_REQUEST_TODO) sai do quadro por decisao do Levi (03/09): sao 60
# pedidos que voltaram para o supervisor refazer, e enquanto ele nao refizer nao ha o que o PCM
# aprovar. Deixa-las na coluna Pendentes enchia a fila com 60 itens sobre os quais ele nao pode
# agir — o oposto do que este painel existe para fazer. Continuam visiveis no Historico.
_REFAZER = "reaberta"


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
            f"QFrame#solCard{{background:{CARD};border:1px solid {BORDER};border-radius:7px;}}"
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
        st.setStyleSheet("color:%s;font-size:11px;font-weight:600;background:transparent;"
                         % (s.get("cor_status") or MUTED))
        topo.addWidget(st)
        v.addLayout(topo)

        ativo = QLabel(str(s.get("ativo") or "—"))
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
        risco.setStyleSheet(f"background:{BORDER};border:none;")
        v.addSpacing(3)
        v.addWidget(risco)

        rod = QHBoxLayout()
        rod.setContentsMargins(0, 4, 0, 0)
        quem = QLabel(f"{s.get('criado_por') or '—'} · {(s.get('data') or '')[:10]}")
        quem.setStyleSheet(f"color:{MUTED};font-size:11px;background:transparent;")
        quem.setWordWrap(True)
        quem.setMinimumWidth(1)
        rod.addWidget(quem)
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
        st.setStyleSheet("color:%s;font-size:10.5px;font-weight:600;background:transparent;"
                         % (s.get("cor_status") or MUTED))
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


class _LinhaSub(QFrame):
    """Uma subtarefa. O tipo do campo fica na direita, em cinza: e o que diz ao PCM se aquilo vai
    pedir texto, numero, foto ou so um sim/nao — a diferenca entre checklist e campo em branco."""

    _TIPO = {1: "Texto", 2: "Sim/Não", 3: "Numérico", 4: "Verificação"}

    def __init__(self, i, x, ultima=False):
        super().__init__()
        self.setObjectName("subLinha")
        if ultima:
            self.setProperty("ultima", "1")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 9, 14, 9)
        h.setSpacing(12)
        n = QLabel(str(i))
        n.setFixedWidth(16)
        n.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        h.addWidget(n)
        d = QLabel(str(x.get("description") or ""))
        d.setStyleSheet("color:%s;font-size:12.5px;background:transparent;" % TEXT)
        d.setWordWrap(True)
        d.setMinimumWidth(1)
        h.addWidget(d, 1)
        if x.get("attachments_required"):
            rot, cor = "anexo obrigatório", GREEN
        elif not x.get("is_required"):
            rot, cor = "opcional", MUTED
        else:
            rot, cor = self._TIPO.get(x.get("id_task_form_item_type"), ""), MUTED
        t = QLabel(rot)
        t.setStyleSheet("color:%s;font-size:10.5px;background:transparent;" % cor)
        h.addWidget(t, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)


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
        if isinstance(self.editor, QComboBox):
            self.editor.showPopup()

    def fechar(self):
        self._pilha.setCurrentIndex(0)
        self.atualizar()

    def eventFilter(self, obj, ev):
        # sair do campo fecha: sem isto o editor ficaria aberto ate a proxima selecao, e a
        # linha perderia o formato limpo que e a razao de ele existir.
        if obj is self.editor and ev.type() == ev.Type.FocusOut:
            self.fechar()
        return False

    def atualizar(self):
        if isinstance(self.editor, QComboBox):
            txt = self.editor.currentText() if self.editor.currentData() else ""
        else:
            txt = self.editor.date().toString("dd/MM/yyyy")
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
        self.lbl_titulo = QLabel("Selecione uma solicitação na fila.")
        self.lbl_titulo.setStyleSheet("color:%s;font-size:20px;font-weight:600;"
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
        self.v_aberta = self._valor()
        self.v_aberta.setWordWrap(False)      # "02/09/2026 20:16" em duas linhas nao ajuda ninguem
        self.v_ativo = self._valor()
        self.v_usina = self._valor()
        for col, rot, val in ((0, "Solicitante", self.v_solicitante),
                              (1, "Aberta em", self.v_aberta),
                              (2, "Ativo", self.v_ativo)):
            ficha.addWidget(self._rotulo(rot), 0, col)
            ficha.addWidget(val, 1, col)
        ficha.setRowMinimumHeight(2, 24)   # +5 px: "usina" estava colada no solicitante
        ficha.addWidget(self._rotulo("Usina"), 2, 0)
        ficha.addWidget(self.v_usina, 3, 0, 1, 3)
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
        lin = QHBoxLayout()
        lin.setSpacing(8)
        lin.addWidget(self._fixo("Técnico:"))
        self.cb_resp = QComboBox()
        self.cb_resp.addItem("— selecione —", None)
        self.cb_resp.setMinimumWidth(210)
        self.ed_tecnico = _CampoClicavel(self.cb_resp, "—")
        lin.addWidget(self.ed_tecnico)
        lin.addSpacing(14)
        lin.addWidget(self._fixo("Data pretendida:"))
        self.de_data = QDateEdit()
        self.de_data.setCalendarPopup(True)
        self.de_data.setDisplayFormat("dd/MM/yyyy")
        self.de_data.setDate(QDate.currentDate())
        self.ed_data = _CampoClicavel(self.de_data, "—")
        lin.addWidget(self.ed_data)
        lin.addSpacing(10)
        amb = QLabel("ambos editáveis")
        amb.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        lin.addWidget(amb)
        lin.addStretch(1)
        cxv.addLayout(lin)

        # continua existindo para quem lia o resumo em texto (e para os testes)
        self.lbl_sug = QLabel("")
        self.lbl_sug.setVisible(False)
        self.det.addWidget(cx)

        # ── tema ──
        topo_t = QHBoxLayout()
        topo_t.setSpacing(9)
        topo_t.addWidget(self._rotulo("Tema"))
        self.chip_tema = QLabel("")
        self.chip_tema.setObjectName("chipTema")
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
        self.box_subs = QFrame()
        self.box_subs.setObjectName("boxSubs")
        self.subs_v = QVBoxLayout(self.box_subs)
        self.subs_v.setContentsMargins(0, 0, 0, 0)
        self.subs_v.setSpacing(0)
        self.det.addWidget(self.box_subs)
        self.lbl_subs = QLabel("")          # continua existindo p/ quem lia o resumo em texto
        self.lbl_subs.setVisible(False)

        acoes = QHBoxLayout()
        acoes.setSpacing(10)
        self.b_aprovar = QPushButton("Aprovar e gerar OS")
        self.b_aprovar.setObjectName("btnPrimary")
        self.b_aprovar.setIcon(QIcon(icone_pix("check", GREEN_INK, 16)))
        self.b_aprovar.setIconSize(QSize(16, 16))
        self.b_aprovar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_aprovar.clicked.connect(self._aprovar)
        self.b_devolver = QPushButton("Devolver ao supervisor")
        self.b_devolver.setObjectName("btnGhost")
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
            for l in (self.v_solicitante, self.v_aberta, self.v_ativo, self.v_usina):
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
        self.chip_tema.setText("sugerido pela descrição" if tema else "")

        novo = sp.titulo(s.get("usina") or "", s.get("ativo") or "", tema) if tema else ""
        orig = str(s.get("descricao_full") or s.get("descricao") or "")
        self.lbl_titulo.setText(novo or orig)
        # O PCM está reescrevendo o texto de outra pessoa — precisa ver o que está mudando.
        self.lbl_orig.setText(
            "o supervisor escreveu: <s>%s</s> · título reescrito no padrão" % orig
            if novo and novo != orig else "")
        self.v_solicitante.setText(str(s.get("criado_por") or "—"))
        self.v_aberta.setText(_data_br(s.get("data")))
        self.v_ativo.setText(str(s.get("ativo") or "—"))
        self.v_usina.setText(str(s.get("usina") or "—"))
        tec, dt = bloco.get("tecnico"), bloco.get("data")
        self.lbl_sug.setText("Técnico: %s · Data pretendida: %s" % (tec or "—", dt or "—"))
        d = QDate.fromString(str(dt or ""), "dd/MM/yyyy")
        self.de_data.setDate(d if d.isValid() else QDate.currentDate())
        self.ed_data.lbl.setText(dt if d.isValid() else "—")
        self._pre_selecionar_responsavel(tec)
        self._habilitar(True)
        self._pintar_subs()

    def set_responsaveis(self, pessoas):
        """Lista de quem pode receber a OS. Acessoria: sem ela o PCM ainda ve a fila, mas nao
        consegue aprovar — por isso o botao avisa em vez de falhar calado."""
        atual = self.cb_resp.currentText()
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

    def _pintar_subs(self):
        while self.subs_v.count():
            it = self.subs_v.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        tema = self.cb_tema.currentData() or ""
        self.cb_tema.setProperty("temado", "1" if tema else "0")
        self.cb_tema.style().unpolish(self.cb_tema)
        self.cb_tema.style().polish(self.cb_tema)
        cl = sp.classificacao(tema) if tema else {}
        self.lbl_classif.setText(
            ("Classificação 1: <b style='color:%s'>%s</b>&nbsp;&nbsp;"
             "<span style='color:%s'>domínio %s%%</span>"
             % (TEXT, cl.get("classif1") or "—", MUTED, cl.get("dominio")))
            if tema and cl.get("classif1") else "")
        subs = sp.subtarefas(tema) if tema else sp.subtarefas_base()
        cab = QLabel("A OS vai nascer com <b>%d subtarefas</b>%s"
                     % (len(subs), (" · %d do tema, 3 da base" % (len(subs) - 3)) if tema
                        else " — só a base, porque não há tema"))
        cab.setObjectName("subsCab")
        cab.setTextFormat(Qt.TextFormat.RichText)
        cab.setWordWrap(True)
        cab.setMinimumWidth(1)
        self.subs_v.addWidget(cab)
        for i, x in enumerate(subs, 1):
            self.subs_v.addWidget(_LinhaSub(i, x, i == len(subs)))
        self.lbl_subs.setText("%d subtarefas" % len(subs))

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
        subs = sp.subtarefas(tema) if tema else sp.subtarefas_base()
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
                            note=str(s.get("observacao") or ""))
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


class _CardBotao(QFrame):
    """Card-botao do hub, na MESMA linguagem dos cards da tela inicial do app: icone num quadrado
    verde translucido, titulo, subtitulo, risco verde embaixo e a seta no canto.

    Nao e enfeite: quem abre esta aba acabou de sair daquela tela, e repetir a forma diz "isto e
    a mesma coisa, um nivel abaixo". A primeira versao era um retangulo cinza com texto — sem
    cor, sem hierarquia e sem parentesco nenhum com o resto do app."""

    def __init__(self, titulo, sub, on_click, icone="grid", alto=True):
        super().__init__()
        self.setObjectName("hubCard")
        self.setProperty("alto", "1" if alto else "0")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_click = on_click
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(4)

        topo = QHBoxLayout()
        topo.setSpacing(8)
        sq = QLabel()
        lado = 46 if alto else 34
        sq.setFixedSize(lado, lado)
        sq.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sq.setObjectName("hubIcone")
        sq.setPixmap(icone_pix(icone, GREEN, 24 if alto else 18))
        topo.addWidget(sq)
        topo.addStretch(1)
        v.addLayout(topo)
        v.addSpacing(8 if alto else 4)

        t = QLabel(titulo)
        t.setStyleSheet("font-size:%dpx;font-weight:600;color:%s;background:transparent;"
                        "border:none;" % (17 if alto else 14.5, TEXT))
        v.addWidget(t)
        d = QLabel(sub)
        d.setWordWrap(True)
        d.setMinimumWidth(1)
        d.setStyleSheet("font-size:%dpx;color:%s;background:transparent;border:none;"
                        % (13 if alto else 12, MUTED))
        v.addWidget(d)
        v.addStretch(1)

        seta = QHBoxLayout()
        seta.setContentsMargins(0, 6, 0, 0)
        seta.addStretch(1)
        a = QLabel()
        a.setPixmap(icone_pix("arrow", GREEN, 20 if alto else 16))
        a.setStyleSheet("background:transparent;border:none;")
        seta.addWidget(a)
        v.addLayout(seta)
        if alto:
            self.setMinimumHeight(158)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()


class _Hub(QWidget):
    """A tela de entrada da aba: dois caminhos, e o do PCM abre os tres destinos dele."""

    # Os numeros e a IDEIA vem da referencia de anime.js que o Levi mandou — createScope com
    # `mediaQueries`, e o corpo da animacao lendo `matches` para decidir o EIXO do movimento:
    #     x: isSmall ? 0 : [...], y: isSmall ? [...] : 0
    # Aqui nao ha CSS nem media query, entao o equivalente honesto e a propria geometria do
    # widget: quando ele esta largo os cards estao lado a lado e o movimento natural e vertical;
    # quando esta estreito eles empilham e o movimento passa a ser horizontal. E o mesmo
    # principio — a animacao acompanha o formato da tela em vez de ser fixa.
    STAGGER = 100
    DUR = 340
    DESLOC = 22
    ESTREITO = 900          # abaixo disto os cards empilham: e o nosso "(max-width: ...)"

    def __init__(self, ir):
        super().__init__()
        self._ir = ir
        self._anims = []
        self._aberto = False
        self._entrou = False
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 26, 28, 26)
        v.setSpacing(16)

        t = QLabel("Solicitação / PCM")
        t.setStyleSheet(f"color:{TEXT};font-size:19px;font-weight:600;")
        v.addWidget(t)
        d = QLabel("O supervisor pede. O PCM confere e gera a OS com as subtarefas do tema.")
        d.setStyleSheet(f"color:{MUTED};font-size:13px;")
        v.addWidget(d)

        topo = QHBoxLayout()
        topo.setSpacing(14)
        self.c_nova = _CardBotao("Criar Nova Solicitação",
                                 "Pedir serviço já com tema, técnico sugerido e data pretendida",
                                 lambda: self._ir("nova"), icone="send")
        self.c_pcm = _CardBotao("Área PCM",
                                "Conferir a fila, aprovar e acompanhar o que virou OS",
                                self._abrir_pcm, icone="calcheck")
        topo.addWidget(self.c_nova, 1)
        topo.addWidget(self.c_pcm, 1)
        v.addLayout(topo)

        self.sub = QWidget()
        sv = QHBoxLayout(self.sub)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(12)
        self._subcards = []
        for rot, txt, alvo, ico in (
                ("Painel", "O que está pendente, em andamento e finalizado", "painel", "grid"),
                ("Fila do PCM", "Aprovar uma a uma, com as subtarefas do tema", "fila", "list"),
                ("Histórico", "Tudo o que já passou por aqui", "hist", "clock")):
            c = _CardBotao(rot, txt, lambda a=alvo: self._ir(a), icone=ico, alto=False)
            sv.addWidget(c, 1)
            self._subcards.append(c)
        self.sub.setVisible(False)
        v.addWidget(self.sub)
        v.addStretch(1)

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
        self.sub.setVisible(True)
        QTimer.singleShot(0, self._animar)

    def recolher(self):
        self._aberto = False
        self.sub.setVisible(False)

    # ── animacao ──
    def _matches(self):
        """O nosso `self.matches`: o que vale de verdade sobre o formato atual da tela."""
        return {"estreito": self.width() < self.ESTREITO}

    def _animar(self, cards=None):
        """Entra deslocando, com um leve passar do ponto no fim (OutBack).

        Guarda a referencia do grupo: animacao sem dono e coletada no meio do caminho e o widget
        congela na posicao inicial — some da tela sem erro nenhum."""
        estreito = self._matches()["estreito"]
        for k, c in enumerate(cards or self._subcards):
            ef = QGraphicsOpacityEffect(c)
            c.setGraphicsEffect(ef)
            fim = c.pos()
            # eixo escolhido pelo formato, como no exemplo da doc: empilhado entra pelo lado,
            # lado a lado entra por baixo
            ini = (QPoint(fim.x() - self.DESLOC, fim.y()) if estreito
                   else QPoint(fim.x(), fim.y() + self.DESLOC))
            g = QParallelAnimationGroup(c)
            a1 = QPropertyAnimation(ef, b"opacity", g)
            a1.setDuration(self.DUR)
            a1.setStartValue(0.0)
            a1.setEndValue(1.0)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)
            a2 = QPropertyAnimation(c, b"pos", g)
            a2.setDuration(self.DUR)
            a2.setStartValue(ini)
            a2.setEndValue(fim)
            # OutBack passa alguns pixels do destino e volta — e o que da a sensacao de peso
            # que a curva puramente desacelerada nao tem.
            a2.setEasingCurve(QEasingCurve.Type.OutBack)
            g.addAnimation(a1)
            g.addAnimation(a2)
            QTimer.singleShot(k * self.STAGGER, g.start)
            self._anims.append(g)

    def showEvent(self, e):
        """Os dois cards de cima tambem entram animados, uma vez por abertura do hub."""
        super().showEvent(e)
        if not self._entrou:
            self._entrou = True
            QTimer.singleShot(0, lambda: self._animar([self.c_nova, self.c_pcm]))


class SolicPcmTab(QWidget):
    """A aba. Hub de entrada → Nova solicitação · Painel · Fila do PCM · Histórico, num stack só.

    A ordem da navegação segue o fluxo real, e não a ordem em que as telas foram escritas: quem
    abre a aba na maioria das vezes é o supervisor, para PEDIR."""

    HUB, NOVA, PAINEL, FILA, HIST = 0, 1, 2, 3, 4

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
QLabel#hubIcone { background:rgba(143,206,63,0.14); border-radius:12px; border:none; }

/* CELULA, nao cartao (decisao do Levi, 03/09). A fila e uma tabela: mesmo fundo da pagina,
   sem borda em volta e sem cantos, e cada item separado do seguinte por uma linha so. Cartao
   com borda e respiro fazia cada solicitacao parecer um objeto solto; aqui elas sao linhas de
   uma lista, que e o que sao. A barra verde da esquerda marca a selecionada. */
QFrame#filaCard { background:transparent; border:none;
  border-bottom:1px solid #1b2235; border-left:3px solid transparent; }
QFrame#filaCard:hover { background:#111828; }
QFrame#filaCard[sel="1"] { background:#141b2c; border-left:3px solid #8fce3f; }
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
QFrame#filaCab { background:transparent; border:none; border-bottom:1px solid #232a3d; }
QFrame#divisorV { background:#232a3d; }
QFrame#riscoParcial { background:#232a3d; border:none; }
QLabel#cabCol { color:#8a90a2; font-size:10.5px; font-weight:700; letter-spacing:0.8px;
  background:transparent; }
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
/* acao secundaria dentro de um item de lista: texto, nao botao */
QPushButton#btnLink { background:transparent; border:none; color:#8fce3f; font-size:12px;
  font-weight:600; padding:0 2px; min-height:0; text-align:right; }
QPushButton#btnLink:hover { color:#b4ec42; text-decoration:underline; }
""")
        self._assets = []
        self._wresp = None   # a thread precisa de dono vivo (ver steps/CLAUDE.md)
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
                       (self.FILA, "Fila do PCM"), (self.HIST, "Histórico")):
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
        for w in (self.hub, self.nova, self.painel, self.fila, self.hist):
            self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        self.ir(self.HUB)

    def _do_hub(self, alvo):
        self.ir({"nova": self.NOVA, "painel": self.PAINEL,
                 "fila": self.FILA, "hist": self.HIST}[alvo])

    def ir(self, i):
        self.stack.setCurrentIndex(i)
        # no hub a navegação não aparece: o hub JÁ é o menu, e duas barras de navegação na mesma
        # tela é a pessoa perguntando qual das duas manda.
        for k in range(self._nav.count()):
            w = self._nav.itemAt(k).widget()
            if w:
                w.setVisible(i != self.HUB)
        for b, k in zip(self._btns, (self.NOVA, self.PAINEL, self.FILA, self.HIST)):
            b.setChecked(k == i)
        if i == self.FILA:
            # reaproveita a lista de pessoas que o formulário já buscou — uma chamada em vez de duas
            pessoas = self._pessoas()
            self.fila.set_responsaveis(pessoas)
            if not pessoas and self._wresp is None:
                # o PCM pode abrir a fila antes de o formulário terminar de carregar; sem
                # responsável não sai OS numerada, então buscamos aqui também.
                self._wresp = ApiWorker(api.get_responsaveis)
                self._wresp.ok.connect(self.fila.set_responsaveis)
                self._wresp.start()
            self.fila.set_itens(self.painel.pendentes(), self._assets)
        if i == self.HIST and hasattr(self.hist, "carregar_inicial"):
            self.hist.carregar_inicial()

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
