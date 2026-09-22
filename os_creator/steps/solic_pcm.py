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
                             QGridLayout, QLineEdit, QSizePolicy, QInputDialog,
                             QDateTimeEdit, QStackedLayout, QDialog, QTextEdit)

from datetime import datetime

import api
import solic_spec as sp
from workers import ApiWorker, slot_seguro
from steps.ui import (QSS_FORM, Card, campo, esvaziar as _esvaziar, icone_pix,
                      GREEN, GREEN_INK, MUTED, TEXT,
                      CARD, BORDER, BG, INPUT)
# O card da tela de Criar OS. Importado, e nao reescrito: o Levi quer as duas telas com a
# mesma forma, e copiar significaria as duas divergirem na primeira alteracao de uma delas.
from steps.performance import _PlanoCard
import pcm_acesso
from steps.searchcombo import tornar_pesquisavel
from steps.ospai import OsPaiPicker
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

# mesmo rotulo do bloco de Tipo de tarefa, no wizard: dois nomes para o mesmo vazio
# fariam a pessoa achar que sao coisas diferentes
_SEM_CLASSIF = "— nenhuma —"
# O tipo com que a OS da fila sempre nasceu. Continua sendo o padrao: o campo existe
# para quem precisa de Religamento ou Preventiva, nao para obrigar uma escolha nova.
_TIPO_PADRAO = "Corretiva"
# CLASSIFICACAO 1 DA OS. Sao DUAS listas diferentes com o mesmo nome no Fracttal, e a confusao
# custou uma rodada: `requests.types_1_list` classifica a SOLICITACAO (e onde vive "Nao Para o
# Ativo", que o tema sugere) e `tasks.tasks_types_list` classifica a OS — "Programada" / "Nao
# Programada". Estes campos sao os da OS, entao a sugestao do tema NAO serve aqui.
# "Programada" e o padrao porque e isto que o PCM esta fazendo ao aprovar: programando. E o
# mesmo par que o app ja usa nas OS de analise e de ETM ("Programada / Eletrica", conferido por
# Levi nas OS 10445/10444/10383 e 10478).
_CLASSIF1_PADRAO = "Programada"
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

    def __init__(self, s: dict, on_analisar=None, pode_editar=True):
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
            # O CARTAO INTEIRO abre a Fila, em QUALQUER coluna (pedido do Levi, 04/09). Antes so
            # os pendentes eram clicaveis: quem queria conferir uma solicitacao ja aprovada tinha
            # de procurar no Historico, sendo que a Fila e onde o detalhe mora. Em andamento e
            # finalizada a Fila abre so para LER — nada editavel, porque a OS ja nasceu.
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._abrir = lambda: on_analisar(s)
            b = QPushButton("Analisar" if pode_editar else "Ver detalhes")
            b.setObjectName("btnLink")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: on_analisar(s))
            rod.addWidget(b)
        v.addLayout(rod)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self, "_abrir", None):
            self._abrir()


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
        # DEBOUNCE. Cada tecla repintava ate 120 cartoes (3 colunas x 40), cada um com meia
        # duzia de QLabel: digitar "inversor" levava 857 ms e enfileirava 320 widgets para
        # destruir. Esperar a pessoa parar de digitar transforma 8 repinturas em 1.
        self._t_busca = QTimer(self)
        self._t_busca.setSingleShot(True)
        self._t_busca.setInterval(250)
        self._t_busca.timeout.connect(self._pintar)
        self.busca.textChanged.connect(self._t_busca.start)
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
        # quem depende desta lista (a Fila) precisa saber que ela mudou — senao o botao
        # Atualizar da Fila recarregaria o Painel e a fila continuaria com a lista velha
        if callable(getattr(self, "on_carregou", None)):
            self.on_carregou()

    @slot_seguro
    def _err(self, m):
        self._w = None
        self.lbl.setText("Erro ao carregar: " + str(m)[:90])
        if callable(getattr(self, "on_carregou", None)):
            self.on_carregou()      # erro tambem e fim de carga: quem espera precisa destravar

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
            _esvaziar(iv)                              # mantém o addStretch do fim
            lista = por[chave]
            cnt.setText(f"{len(lista):,}".replace(",", "."))
            for s in lista[:40]:
                iv.insertWidget(iv.count() - 1,
                                _Cartao(s, self._on_analisar, pode_editar=(chave == PENDENTE)))
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

    def __init__(self, on_mudou=None, embutido=False):
        super().__init__()
        # `embutido` = sem caixa e sem titulo: dentro da coluna "A decisao" ele e so mais uma
        # linha, ao lado de Tecnico e Data. Card dentro de card viraria moldura sobre moldura.
        self.setObjectName("" if embutido else "boxSug")
        self._on_mudou = on_mudou
        self._catalogo = []
        self._sel = []                  # [{'id','description'}]
        self._do_tema = set()           # as que o TEMA pos, em MAIUSCULA — nao as escolhidas a mao
        self._tirados = set()           # as do tema que a PESSOA tirou nesta solicitacao
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 13, 16, 14)
        v.setSpacing(9)

        if embutido:
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)
            # Sem objectName o QFrame cai na regra generica `QWidget{background:#090d18}` do
            # DARK_QSS e pinta o fundo da PAGINA por cima do cartao: o campo ficava visivelmente
            # mais escuro que Tecnico e Data, ao lado (Levi, 16/09). Transparente, ele some.
            self.setStyleSheet("QFrame{background:transparent;border:none;}")
        cab = QLabel("ETIQUETAS DA OS")
        cab.setStyleSheet("color:%s;font-size:10.5px;font-weight:700;letter-spacing:0.8px;"
                          "background:transparent;" % GREEN)
        cab.setVisible(not embutido)
        v.addWidget(cab)

        # EMPILHADAS, nao em linha. Com QHBoxLayout cada etiqueta nova empurrava a fila para a
        # direita e o card crescia na horizontal, espremendo o bloco da sugestao ao lado. Uma por
        # linha cresce so para baixo, que e o unico eixo em que este card tem folga.
        self.fila_chips = QVBoxLayout()
        self.fila_chips.setSpacing(5)
        self.fila_chips.addStretch(1)
        v.addLayout(self.fila_chips)

        self.cb = QComboBox()
        # Embutido na coluna da decisao ele e vizinho de Tecnico e Data, que sao rotulos com
        # risco TRACEJADO. O `campoInline` tras risco VERDE cheio, e so ele acendia na linha
        # (Levi, 16/09: "arrume para ficar igual os demais"). Verde volta no hover, como nos
        # outros — o convite existe, mas nao grita.
        self.cb.setObjectName("etqInline" if embutido else "campoInline")
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
        # QUEM TIROU, TIROU (Levi, 14/09: "hoje se adicionada alguma, nao e possivel retirar e
        # ficar sem etiquetas"). A etiqueta do tema era um chip DESABILITADO, e a unica saida era
        # editar o tema — mudar a regra de todo mundo para resolver um caso. O nome fica guardado
        # em `_tirados` para o `aplicar_regra` nao repor na proxima repintura.
        fora = next((x for x in self._sel if x["id"] == idl), None)
        if fora:
            self._tirados.add(fora["description"].strip().upper())
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
        querem = self.etiquetas_do_tema(tema, ativo) - self._tirados   # o que a pessoa tirou, fica fora
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
        _esvaziar(self.fila_chips)
        for e in self._sel:
            # "(tema)" e nao "(regra)": desde 04/09 a etiqueta e campo do tema, editavel na tela
            # de Temas — nao e mais uma regra do sistema que ninguem consegue mudar.
            do_tema = e["description"].strip().upper() in self._do_tema
            # o "(tema)" continua dizendo DE ONDE ela veio, mas o × agora existe nas duas: a marca
            # e' informacao, nao tranca (Levi, 14/09).
            c = QPushButton("%s  ×" % e["description"] + ("  (tema)" if do_tema else ""))
            c.setObjectName("chipEtqPerf" if do_tema else "chipEtq")
            c.setCursor(Qt.CursorShape.PointingHandCursor)
            c.setToolTip("Vem do tema desta solicitação. Clique para tirar só aqui — o tema "
                         "continua igual para as próximas." if do_tema else "Clique para tirar")
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
        # `_tirados` zera junto: ele vale para a solicitacao que estava aberta, nao para a proxima
        self._sel, self._do_tema, self._tirados = [], set(), set()
        self._pintar()

    def ids(self):
        return [x["id"] for x in self._sel]


class _Observacao(QTextEdit):
    """O relato do supervisor: le-se sempre, edita-se ao clicar.

    Era um `_CampoClicavel` — rotulo que virava editor —, e com 20 linhas de procedimento de
    fabricante o rotulo CORTAVA o ultimo paragrafo sem avisar: na 3620 o texto pedia 404 px e o
    campo dava 400. Sendo o MESMO QTextEdit nos dois estados, o texto rola dentro da caixa —
    nunca corta, nunca empurra a ficha, e clicar nao muda nada de lugar (Levi, 16/09).

    Nao usa setEnabled(False) para travar: o QTextEdit desabilitado pinta o texto de cinza, e no
    modo somente-leitura da fila isso apagaria justamente o que se foi ler."""

    def __init__(self, vazio="— sem observação —"):
        super().__init__()
        self.setObjectName("obsCampo")
        self.setReadOnly(True)
        self.setPlaceholderText(vazio)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setMinimumWidth(1)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setToolTip("clique para editar")
        self.fechou = None
        self.ao_redimensionar = None      # a Fila usa para reavaliar o link "ver inteira"
        self._editavel = True

    def set_editavel(self, on):
        self._editavel = bool(on)
        if not on:
            self.setReadOnly(True)

    def abrir(self):
        if not self._editavel:
            return
        self.setReadOnly(False)
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def fechar(self):
        if self.isReadOnly():
            return
        self.setReadOnly(True)
        if callable(self.fechou):
            self.fechou()

    def atualizar(self):
        pass          # compatibilidade com o _CampoClicavel: o texto ja vive no proprio widget

    def travar_altura(self, px):
        self.setFixedHeight(px)

    def resizeEvent(self, e):
        # Quem descobre que sobrou texto do lado de fora e a barra de rolagem, e ela so sabe
        # DEPOIS que a caixa recebeu o tamanho. Avisar daqui e o unico jeito de perguntar na
        # hora certa: a coluna cresce, a caixa cresce junto, e o link some sozinho.
        super().resizeEvent(e)
        if callable(self.ao_redimensionar):
            self.ao_redimensionar()

    def mousePressEvent(self, e):
        if self.isReadOnly():
            self.abrir()
        super().mousePressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.fechar()


class _CampoClicavel(QWidget):
    """Mostra um VALOR; ao clicar, vira o campo de edicao no mesmo lugar.

    Por que nao deixar o campo aberto sempre: nesta tela o tecnico e a data quase sempre so
    precisam ser CONFIRMADOS — o supervisor ja escreveu. Combo e date picker abertos dao a uma
    conferencia o peso visual de um formulario a preencher. Clicou, edita; saiu, volta a ser
    texto."""

    def __init__(self, editor, vazio="—", altura=24):
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
        #
        # `altura=None` = TEXTO CORRIDO (a observação). Travar em 24 px ali mostrava uma fatia da
        # primeira linha e comia o resto, e ao clicar o editor de 76 px era espremido no mesmo 24
        # — "quando eu clico corta mais ainda" (Levi, 14/09). Campo de uma linha continua travado,
        # que é o que impede a data de "subir" ao virar editor.
        self.setMinimumWidth(1)          # sem isto o campo impõe a própria largura e estoura a ficha
        if altura:
            self.setFixedHeight(altura)
            self.lbl.setFixedHeight(altura)
            self.lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.lbl.setWordWrap(True)
            self.lbl.setMinimumWidth(1)
            self.lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._pilha.addWidget(self.lbl)
        self._pilha.addWidget(editor)
        self._pilha.setCurrentIndex(0)
        editor.installEventFilter(self)
        if isinstance(editor, QComboBox):
            editor.activated.connect(lambda _=0: self.fechar())

    def travar_altura(self, px):
        """Trava a MESMA altura no rotulo e no editor.

        A observacao e o unico campo cuja altura vem do TEXTO, e era ela que quebrava a tela: o
        rotulo embrulhado e o QTextEdit tem hints muito diferentes, entao trocar um pelo outro
        levava a pilha de 92 para 1638 px (medido). Tudo o que vem depois — sugestao, etiquetas,
        tema, subtarefas e os botoes — descia 1,5 mil pixels e sumia da vista, enquanto o texto
        era espremido no editor de 92 px fixos: "o grande texto fica resumido num campo pequeno
        e todo o resto da tela fica escuro" (Levi, 15/09). Com os dois no mesmo numero, clicar
        nao move mais nada."""
        self.setFixedHeight(px)
        self.lbl.setFixedHeight(px)
        self.editor.setFixedHeight(px)

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
        # gancho opcional de quem quer GRAVAR o que foi digitado (a observação usa). Fica aqui,
        # e não no eventFilter, para valer também quando o campo é fechado por código.
        if callable(getattr(self, "fechou", None)):
            self.fechou()

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
        elif isinstance(self.editor, QTextEdit):      # a observação: texto corrido, várias linhas
            txt = self.editor.toPlainText().strip()
        else:
            txt = self.editor.dateTime().toString("dd/MM/yyyy HH:mm")
        self.lbl.setText(txt or self._vazio)

    def setEnabled(self, on):
        super().setEnabled(on)
        self.lbl.setEnabled(on)


class _StatusDialog(QDialog):
    """Escolher o novo status da solicitação e escrever o motivo.

    O catálogo vem da API (`api.status_solicitacao_catalogo`), cruzado com a lista curta do
    `api.STATUS_SOLICITACAO` — os estados que são CONSEQUÊNCIA da OS ficam de fora, porque
    marcá-los à mão faria a tela mentir sobre o que o Fracttal recalcula sozinho."""

    def __init__(self, parent, numero=""):
        super().__init__(parent)
        self.id_status, self.codigo, self.rotulo, self.motivo = None, "", "", ""
        self.setWindowTitle("Mudar status da solicitação")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        t = QLabel("Solicitação %s" % (numero or ""))
        t.setStyleSheet("font-size:15px;font-weight:600;color:%s;background:transparent;" % TEXT)
        v.addWidget(t)

        v.addWidget(self._rot("Novo status"))
        self.cb = QComboBox()
        self.cb.setObjectName("campoInline")
        for ids, cod, rot in api.status_solicitacao_catalogo():
            self.cb.addItem(rot, (ids, cod, rot))
        v.addWidget(self.cb)

        v.addWidget(self._rot("Motivo"))
        self.ed = QTextEdit()
        self.ed.setObjectName("campoInline")
        self.ed.setFixedHeight(88)
        self.ed.setPlaceholderText("por que está mudando — fica no histórico da solicitação")
        self.ed.textChanged.connect(self._upd)
        v.addWidget(self.ed)

        self.aviso = QLabel("O motivo é obrigatório.")
        self.aviso.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        v.addWidget(self.aviso)

        linha = QHBoxLayout()
        linha.addStretch(1)
        b_nao = QPushButton("Cancelar")
        b_nao.setObjectName("secondary")
        b_nao.clicked.connect(self.reject)
        self.b_sim = QPushButton("Mudar status")
        self.b_sim.setObjectName("btnAprovar")
        self.b_sim.setEnabled(False)
        self.b_sim.clicked.connect(self._ok)
        linha.addWidget(b_nao)
        linha.addWidget(self.b_sim)
        v.addLayout(linha)

    def _rot(self, txt):
        l = QLabel(txt)
        l.setStyleSheet("color:%s;font-size:10.5px;font-weight:700;letter-spacing:0.8px;"
                        "background:transparent;" % GREEN)
        return l

    def _upd(self):
        self.b_sim.setEnabled(bool(self.ed.toPlainText().strip()))

    def _ok(self):
        dados = self.cb.currentData()
        if not dados:
            return
        self.id_status, self.codigo, self.rotulo = dados
        self.motivo = self.ed.toPlainText().strip()
        self.accept()


class _Fila(QWidget):
    """Fila do PCM: a lista à esquerda, o detalhe à direita, e a OS nascendo na aprovação."""

    # Piso da caixa de observacao. Abaixo de 92 px o campo vazio parece uma linha qualquer e
    # ninguem descobre que da para escrever nele. Teto nao existe: a caixa cresce com a coluna,
    # e o que nao couber fica atras da rolagem (ou do "ver inteira").
    OBS_MIN = 92
    # A altura dos dois cartoes do topo = o que a decisao PEDE, mais esta margem. Era 30% a mais
    # (16/09, quando os campos ainda eram combos emoldurados); com Tipo e as duas Classificacoes
    # virando linhas, o conteudo encolheu e os mesmos 30% viraram um vazio no rodape do cartao —
    # "achate mais sem comer as palavras, pode ser uma margem de 5 a 10 px" (Levi, 16/09).
    # E MARGEM, nao proporcao, de proposito: assim ela nao cresce junto com o conteudo.
    FOLGA_CARTAO_PX = 8

    def __init__(self, on_voltar, on_atualizar=None):
        super().__init__()
        self._obs_expandida = False
        self._on_atualizar = on_atualizar
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
        # Atualizar AQUI, e nao so no Painel: para sincronizar a fila era preciso voltar ao
        # Painel, atualizar e entrar de novo — tres cliques e a selecao perdida (Levi, 15/09).
        self.b_atualizar = QPushButton("Atualizar")
        self.b_atualizar.setObjectName("secondary")
        self.b_atualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_atualizar.setToolTip("Busca as solicitacoes de novo no Fracttal")
        self.b_atualizar.clicked.connect(self._atualizar)
        topo.addWidget(self.b_atualizar)
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
        # A LISTA ENCOLHE, EM VEZ DE COMER O DETALHE (Levi, 14/09: "cadê a responsividade?"). Ela
        # era 460 FIXOS: numa janela estreita sobrava pouco para a direita, e o que não cabia era
        # cortado na borda — título, solicitante e observação desapareciam pela direita em vez de
        # se ajustarem. Agora ela cede até 300 px, que é onde o cartão ainda se lê.
        cw.setMinimumWidth(300)
        cw.setMaximumWidth(460)
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
        # o conteúdo PODE encolher: sem isto o mínimo dos combos e do campo de texto vira o
        # mínimo do painel inteiro, e o scroll (com a barra horizontal desligada) corta a direita
        d.setMinimumWidth(1)
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
        # em janela estreita o rótulo quebra em vez de ser comido pela direita — era o
        # "SUGERIDO PELO SUPERV" do relato de 14/09
        l.setWordWrap(True)
        l.setMinimumWidth(1)
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
        # O TITULO E EDITAVEL. Ele vira o nome da OS no Fracttal, e a API nao edita OS ja
        # criada — o padrao do tema cobre a maioria, e o campo existe para o que ele nao cobre.
        self.lbl_titulo = QLabel("Selecione uma solicitação na fila.")
        self.lbl_titulo.setStyleSheet("color:%s;font-size:26px;font-weight:600;"
                                      "background:transparent;" % TEXT)
        self.lbl_titulo.setWordWrap(True)
        self.lbl_titulo.setMinimumWidth(1)
        self.lbl_titulo.setCursor(Qt.CursorShape.IBeamCursor)
        self.lbl_titulo.setToolTip("clique para editar o título da OS")
        self.lbl_titulo.mouseReleaseEvent = lambda e: self._abrir_titulo()
        self.ed_titulo = QLineEdit()
        self.ed_titulo.setObjectName("tituloOS")
        self.ed_titulo.setVisible(False)
        self.ed_titulo.editingFinished.connect(self._fechar_titulo)
        self._titulo_manual = False
        self.det.addWidget(self.lbl_titulo)
        self.det.addWidget(self.ed_titulo)

        self.lbl_orig = QLabel("")
        self.lbl_orig.setStyleSheet("color:%s;font-size:12px;background:transparent;" % MUTED)
        self.lbl_orig.setWordWrap(True)
        self.lbl_orig.setMinimumWidth(1)
        self.lbl_orig.setTextFormat(Qt.TextFormat.RichText)
        self.det.addWidget(self.lbl_orig)

        # ── O PEDIDO e A DECISÃO, LADO A LADO (Levi, 16/09) ──
        # A tela era uma coluna só, então o material de LEITURA — que numa solicitação de
        # fabricante chega a 20 linhas de procedimento — ficava na frente do material de
        # DECISÃO. Medido na 3620: o botão Aprovar nascia a 1413 px do topo, numa janela de
        # 844, e metade da largura ficava vazia. Agora o que se lê fica à esquerda, o que se
        # decide à direita, e nenhuma observação empurra o tema e as subtarefas para fora.
        self.v_solicitante = self._valor()
        self.v_ativo = self._valor()
        self.v_usina = self._valor()

        pedido = QFrame()
        pedido.setObjectName("boxLado")
        pv = QVBoxLayout(pedido)
        pv.setContentsMargins(16, 13, 17, 14)
        pv.setSpacing(9)
        pv.addWidget(self._rotulo("O pedido", GREEN))

        ficha = QGridLayout()
        ficha.setHorizontalSpacing(20)
        ficha.setVerticalSpacing(3)
        # USINA primeiro: é por ela que o PCM situa a solicitação — quem pediu e o que quebrou
        # só importam depois de saber ONDE. O ativo ocupa a linha inteira porque é o texto mais
        # longo dos três (o modelo do inversor vem junto) e quebrava em duas na coluna estreita.
        ficha.addWidget(self._rotulo("Usina"), 0, 0)
        ficha.addWidget(self.v_usina, 1, 0)
        ficha.addWidget(self._rotulo("Solicitante"), 0, 1)
        ficha.addWidget(self.v_solicitante, 1, 1)
        ficha.addWidget(self._rotulo("Ativo"), 2, 0, 1, 2)
        ficha.addWidget(self.v_ativo, 3, 0, 1, 2)
        ficha.setColumnStretch(0, 1)
        ficha.setColumnStretch(1, 1)
        pv.addLayout(ficha)

        # OBSERVAÇÃO — o relato do supervisor. Até 14/09 não aparecia em lugar nenhum da Fila: o
        # PCM decidia com o título, que tem mediana de 45 caracteres.
        lin_obs = QHBoxLayout()
        lin_obs.setSpacing(10)
        lin_obs.addWidget(self._rotulo("Observação"))
        lin_obs.addStretch(1)
        self.b_ver_obs = QPushButton("ver inteira")
        self.b_ver_obs.setObjectName("verInteira")
        self.b_ver_obs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_ver_obs.setVisible(False)          # só aparece quando há texto escondido
        self.b_ver_obs.clicked.connect(self._alternar_obs)
        lin_obs.addWidget(self.b_ver_obs)
        pv.addLayout(lin_obs)

        self.ed_obs = _Observacao("sem observação — clique para escrever")
        self.ed_obs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # QUEM MANDA NA ALTURA É A COLUNA, não o texto. Com a caixa dimensionada pelo relato,
        # sobrava um vazio pintado embaixo do cartão do pedido sempre que a decisão era mais
        # alta — "ficaram espaços abertos na página" (Levi, 16/09). Ocupando a folga, o mesmo
        # espaço vira texto visível: o procedimento da Huawei cabe inteiro, sem rolagem.
        self.ed_obs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.ed_obs.setMinimumHeight(self.OBS_MIN)
        self.ed_obs.ao_redimensionar = self._revisar_link_obs
        self.v_obs = self.ed_obs                  # o mesmo widget, com os dois nomes de sempre
        self.v_obs.fechou = self._gravar_obs      # ao sair do campo, grava no Fracttal
        pv.addWidget(self.ed_obs, 1)     # é ela que absorve a folga do cartão
        # O timer é FILHO da tela de propósito: ele morre junto com ela, e um disparo pendente
        # nunca cai num widget já destruído. `QTimer.singleShot(0, self, slot)` — a forma com
        # contexto, que resolveria o mesmo — não existe neste PyQt6: levanta TypeError dentro do
        # resizeEvent, e exceção em método virtual do Qt aborta o processo (exit 127).
        self._t_obs = QTimer(self)
        self._t_obs.setSingleShot(True)
        self._t_obs.setInterval(0)
        self._t_obs.timeout.connect(self._ajustar_altura_obs)
        d_obs = QLabel("Rola aqui dentro e não empurra o resto. Clique no texto para editar.")
        d_obs.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        d_obs.setWordWrap(True)
        d_obs.setMinimumWidth(1)
        pv.addWidget(d_obs)

        # ── a decisão ──
        decisao = QFrame()
        decisao.setObjectName("boxLado")
        dv = QVBoxLayout(decisao)
        dv.setContentsMargins(16, 13, 17, 14)
        dv.setSpacing(11)
        dv.addWidget(self._rotulo("A decisão", GREEN))

        # O responsável da OS É o técnico sugerido — tê-los em dois campos distantes fazia
        # parecer decisões diferentes. Cada valor vira campo ao ser clicado: nesta tela eles
        # quase sempre só precisam ser CONFIRMADOS, e combo aberto dá peso de formulário.
        self.cb_resp = QComboBox(); tornar_pesquisavel(self.cb_resp)
        self.cb_resp.addItem("— selecione —", None)
        self.cb_resp.setMinimumWidth(180)
        self.ed_tecnico = _CampoClicavel(self.cb_resp, "—")
        # data E hora: "amanhã" não diz se é antes ou depois da parada, e o PCM programa por hora
        self.de_data = QDateTimeEdit()
        self.de_data.setCalendarPopup(True)
        self.de_data.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.de_data.setDateTime(QDateTime.currentDateTime())
        self.ed_data = _CampoClicavel(self.de_data, "—")
        self.etiquetas = _CardEtiquetas(embutido=True)

        # TIPO DE TAREFA e CLASSIFICAÇÃO 1 e 2 — campos da OS no Fracttal. Entram como LINHAS,
        # no mesmo desenho de Técnico e Data (rótulo à esquerda, valor com risco tracejado), e
        # não como combos emoldurados: seis campos com moldura ocupavam meio cartão, e nenhum
        # deles é a decisão principal desta tela — o tema e as subtarefas são (Levi, 16/09).
        self.cb_tipo = QComboBox(); tornar_pesquisavel(self.cb_tipo)
        self.cb_tipo.addItem(_TIPO_PADRAO, _TIPO_PADRAO)
        self.cb_c1 = QComboBox(); tornar_pesquisavel(self.cb_c1)
        self.cb_c1.addItem(_SEM_CLASSIF, "")
        self.cb_c2 = QComboBox(); tornar_pesquisavel(self.cb_c2)
        self.cb_c2.addItem(_SEM_CLASSIF, "")
        for cb in (self.cb_tipo, self.cb_c1, self.cb_c2):
            cb.setObjectName("etqInline")     # o mesmo risco tracejado dos valores ao lado

        lin = QGridLayout()
        lin.setHorizontalSpacing(12)
        lin.setVerticalSpacing(10)
        linhas = (("Técnico:", self.ed_tecnico), ("Data:", self.ed_data),
                  ("Etiquetas:", self.etiquetas), ("Tipo de tarefa:", self.cb_tipo),
                  ("Classificação 1:", self.cb_c1), ("Classificação 2:", self.cb_c2))
        for r, (rot, w) in enumerate(linhas):
            lin.addWidget(self._fixo(rot), r, 0,
                          Qt.AlignmentFlag.AlignTop if r == 2 else Qt.AlignmentFlag.AlignVCenter)
            lin.addWidget(w, r, 1)
        lin.setColumnStretch(1, 1)
        dv.addLayout(lin)
        # o "domínio X%" fica COLADO nas linhas de classificação, que é o que ele explica: lá
        # embaixo, depois do tema, virava uma frase solta sem dono
        self.lbl_classif = QLabel("")
        self.lbl_classif.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        self.lbl_classif.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_classif.setWordWrap(True)
        self.lbl_classif.setMinimumWidth(1)
        dv.addWidget(self.lbl_classif)
        dv.addStretch(1)      # a folga dos 30% se reparte entre os blocos

        # continua existindo para quem lia o resumo em texto (e para os testes)
        self.lbl_sug = QLabel("")
        self.lbl_sug.setVisible(False)

        # ── tema e OS pai, na mesma linha ──
        # A OS que nasce aqui nunca teve como ser vinculada a uma pai: o campo só existia em
        # Criar OS, COS e PCM, e quem aprovava pela fila tinha de abrir a OS no Fracttal depois.
        topo_t = QHBoxLayout()
        topo_t.setSpacing(9)
        topo_t.addWidget(self._rotulo("Tema"))
        self.chip_tema = QLabel("")
        # objectName PROPRIO: o `chipTema` e o selo verde dos cartoes da fila, e mexer nele
        # aqui repintaria a lista inteira. Aqui e so uma legenda do campo ao lado (Levi, 16/09).
        self.chip_tema.setObjectName("chipSugerido")
        self.chip_tema.setVisible(False)
        topo_t.addWidget(self.chip_tema)
        topo_t.addStretch(1)

        # mesma busca dos demais selects: a lista de temas é editável e só cresce
        self.cb_tema = QComboBox(); tornar_pesquisavel(self.cb_tema)
        self.cb_tema.setObjectName("cbTema")
        self.cb_tema.addItem("— sem tema —", "")
        for chave, nome in sp.temas():
            self.cb_tema.addItem(nome, chave)
        # `lambda *_`, e NÃO `connect(self._pintar_subs)`: currentIndexChanged manda o ÍNDICE,
        # que caía no parâmetro `do_bloco` e virava `set_itens(2)` — "int object is not
        # iterable". Exceção dentro de slot do PyQt6 ABORTA o processo (0xC0000409), então
        # escolher qualquer tema que não fosse o primeiro FECHAVA o app.
        self.cb_tema.currentIndexChanged.connect(lambda *_: self._pintar_subs())
        self.os_pai = OsPaiPicker()
        # O conteudo aqui e um NUMERO de OS — 7 digitos no maior caso. O picker nasce com 260 px
        # de largura minima por causa do texto de ajuda; nesta tela a dica cabe no rotulo, e a
        # largura que sobra vai para a coluna do pedido.
        self.os_pai.setMinimumWidth(130)
        self.os_pai.lineEdit().setPlaceholderText("nº da OS")   # o rótulo acima já diz "OS pai"
        g_tp = QGridLayout()
        g_tp.setHorizontalSpacing(14)
        g_tp.setVerticalSpacing(3)
        g_tp.addLayout(topo_t, 0, 0)
        g_tp.addWidget(self._rotulo("OS pai (opcional)"), 0, 1)
        g_tp.addWidget(self.cb_tema, 1, 0)
        g_tp.addWidget(self.os_pai, 1, 1)
        g_tp.setColumnStretch(0, 4)   # o tema é o campo que se lê; a OS pai quase sempre fica vazia
        g_tp.setColumnStretch(1, 1)
        dv.addLayout(g_tp)
        dv.addStretch(1)

        dv.addStretch(1)

        # ── as subtarefas, em FAIXA DE LARGURA INTEIRA ──
        # O PCM edita a lista também. Ele é quem conhece o ativo e a equipe: o tema acerta o
        # roteiro geral, e o ajuste fino — "neste inversor tem de medir também X" — só quem
        # aprova sabe. Sem isso ele voltaria a montar a OS na mão no Fracttal web, que é
        # exatamente o passo que esta tela existe para eliminar.
        self.editor_subs = EditorSubtarefas(
            "Sem tema: a OS nasce com as 3 subtarefas da base. Da para aprovar assim, e da para "
            "acrescentar o que faltar.")
        # Elas saem da coluna da decisão por dois motivos medidos: com 13 subtarefas (a 3620) a
        # coluna ficava com o dobro da altura da outra, e era o que abria o vazio que o Levi viu;
        # e, espremidas em 58% da largura, as linhas mostravam meia frase. Em faixa inteira, a
        # descrição cabe e as duas caixas de cima empatam.
        caixa_subs = QFrame()
        caixa_subs.setObjectName("boxLado")
        sv = QVBoxLayout(caixa_subs)
        sv.setContentsMargins(16, 13, 17, 14)
        sv.setSpacing(9)
        sv.addWidget(self._rotulo("As subtarefas da OS", GREEN))
        sv.addWidget(self.editor_subs)

        colunas = QHBoxLayout()
        colunas.setContentsMargins(0, 14, 0, 2)
        colunas.setSpacing(16)
        # MESMA ALTURA nas duas: quem estica é a caixa da observação lá dentro, então o que
        # antes era buraco agora é texto. Alinhar pelo topo (a primeira tentativa) só mudava o
        # vazio de lugar — de dentro do cartão para debaixo dele.
        # Cada cartao termina onde o conteudo dele termina: esticado, o mais curto ganharia um
        # retangulo vazio por dentro, que e o que parece defeito. A faixa das subtarefas, logo
        # abaixo e de ponta a ponta, e quem fecha a composicao.
        # 42 -> 50 (+20%, pedido do Levi em 16/09): a coluna da decisao devolve essa largura
        # sem aperto porque o campo que sobrava nela — a OS pai — cabe em 7 digitos.
        colunas.addWidget(pedido, 50, Qt.AlignmentFlag.AlignTop)    # o pedido se le...
        colunas.addWidget(decisao, 50, Qt.AlignmentFlag.AlignTop)   # ...a decisao se preenche
        self._cx_pedido, self._cx_decisao = pedido, decisao
        self.det.addLayout(colunas)
        self.det.addSpacing(14)
        self.det.addWidget(caixa_subs)
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
        # MUDAR O STATUS SEM SAIR DAQUI (Levi, 14/09: "como no fracttal"). Antes o PCM tinha duas
        # saídas — aprovar, que gera OS, e devolver — e qualquer outro desfecho (rejeitar, resolver
        # sem OS, reabrir) só existia no Fracttal web. Fica ao lado das outras ações, mas em
        # botão discreto: mudar status é o caminho MENOS comum, e o verde continua sendo aprovar.
        self.b_status = QPushButton("Mudar status…")
        self.b_status.setObjectName("secondary")
        self.b_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_status.setToolTip("Rejeitar, reabrir, resolver sem OS… com o motivo registrado")
        self.b_status.clicked.connect(self._mudar_status)
        self.b_devolver = QPushButton("Devolver ao supervisor")
        self.b_devolver.setObjectName("btnDevolver")
        self.b_devolver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_devolver.clicked.connect(self._devolver)
        acoes.addWidget(self.b_aprovar)
        acoes.addWidget(self.b_devolver)
        acoes.addWidget(self.b_status)
        acoes.addStretch(1)
        self.det.addLayout(acoes)
        # A DICA SAIU DA LINHA DOS BOTÕES. Ela ocupava ~200 px na mesma faixa e, em janela
        # estreita, os três botões perdiam a disputa e apareciam cortados no meio da palavra
        # ("provar e ge", "er ao sup"). Embaixo, ela não briga com ninguém por espaço.
        self.hint = QLabel("Aprovar avança para a próxima")
        self.hint.setStyleSheet("color:%s;font-size:12px;background:transparent;" % MUTED)
        self.hint.setWordWrap(True)
        self.hint.setMinimumWidth(1)
        self.det.addWidget(self.hint)
        self.det.addStretch(1)
        self._habilitar(False)

    # -- titulo da OS --
    def _abrir_titulo(self):
        if getattr(self, "_so_leitura", False) or not self._sel:
            return
        self.ed_titulo.setText(self.lbl_titulo.text())
        self.lbl_titulo.setVisible(False)
        self.ed_titulo.setVisible(True)
        self.ed_titulo.setFocus()
        self.ed_titulo.selectAll()

    def _fechar_titulo(self):
        t = (self.ed_titulo.text() or "").strip()
        if t:
            # MARCA que foi escrito a mao. Sem isso, trocar o tema depois regeraria o titulo e
            # apagaria o que o PCM digitou.
            self._titulo_manual = (t != self._titulo_do_tema())
            self.lbl_titulo.setText(t)
        self.ed_titulo.setVisible(False)
        self.lbl_titulo.setVisible(True)

    def _titulo_do_tema(self):
        """O titulo que o tema geraria agora — a referencia para saber se o PCM mexeu."""
        sel = self._sel or {}
        tema = self.cb_tema.currentData() or ""
        if tema:
            return sp.titulo(sel.get("usina") or "", sel.get("ativo") or "", tema)
        return str(sel.get("descricao_full") or sel.get("descricao") or "")

    def set_somente_leitura(self, on):
        """Trava tudo o que grava. Usado quando o Painel abre uma solicitação que já virou OS."""
        self._so_leitura = bool(on)
        self._habilitar(not on and self._sel is not None)
        self.hint.setText("Esta solicitação já saiu da fila — aqui é só consulta."
                          if on else "Aprovar avança para a próxima")

    def _atualizar(self):
        """Recarrega a fila sem sair dela. Quem busca continua sendo o Painel — a lista e uma so,
        e duas buscas em paralelo dariam duas verdades na mesma tela."""
        if not callable(self._on_atualizar):
            return
        self.b_atualizar.setEnabled(False)
        self.b_atualizar.setText("atualizando…")
        self._on_atualizar()

    def fim_da_atualizacao(self):
        """Chamado pela aba quando a lista voltou — no sucesso E no erro, senao o botao fica
        preso em "atualizando…" e a pessoa acha que a tela travou."""
        self.b_atualizar.setEnabled(True)
        self.b_atualizar.setText("Atualizar")

    def set_tipos_classif(self, d):
        """Recebe as listas vivas do Fracttal (a aba busca uma vez e reparte).

        Guardadas por NOME, que é como a criação da OS as consome: o `clonar_os` resolve o id no
        catálogo na hora de montar o payload."""
        d = d or {}
        atual_tipo = self.cb_tipo.currentText()
        self.cb_tipo.blockSignals(True)
        self.cb_tipo.clear()
        for it in (d.get("tipos") or []):
            nome = it.get("description") or ""
            if nome:
                self.cb_tipo.addItem(nome, nome)
        if not self.cb_tipo.count():
            self.cb_tipo.addItem(_TIPO_PADRAO, _TIPO_PADRAO)
        i = self.cb_tipo.findText(atual_tipo if atual_tipo != _TIPO_PADRAO else _TIPO_PADRAO)
        self.cb_tipo.setCurrentIndex(max(0, i))
        self.cb_tipo.blockSignals(False)
        for cb, chave in ((self.cb_c1, "c1"), (self.cb_c2, "c2")):
            atual = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(_SEM_CLASSIF, "")
            for it in (d.get(chave) or []):
                nome = it.get("description") or ""
                if nome:
                    cb.addItem(nome, nome)
            i = cb.findText(atual)
            cb.setCurrentIndex(i if i > 0 else 0)
            cb.blockSignals(False)
        self._sugerir_classif()

    def _sugerir_classif(self):
        """Preenche Classificacao 1 e 2 DA OS com o padrao, e explica de onde ele veio.

        So preenche campo vazio: quem escolheu outra nao pode ve-la trocar sozinha ao mexer em
        qualquer outra coisa da ficha.

        A Classificacao 1 do TEMA nao entra aqui — ela classifica a solicitacao ("Nao Para o
        Ativo"), nao a OS. Ja o `tipo` do tema ("Eletrica", "Limpeza e Conservacao") e disciplina,
        que e exatamente a Classificacao 2 da OS."""
        tema = self.cb_tema.currentData() or ""
        disciplina = (sp.classificacao(tema) or {}).get("tipo") or "" if tema else ""
        posto = []
        for cb, nome in ((self.cb_c1, _CLASSIF1_PADRAO), (self.cb_c2, disciplina)):
            if not nome or cb.currentIndex() > 0:
                continue
            i = cb.findText(nome)
            if i > 0:
                cb.setCurrentIndex(i)
                posto.append(nome)
        # a linha de baixo so existe enquanto os campos estiverem no padrao; trocou, ela some,
        # porque ai ela nao descreve mais o que esta na tela
        no_padrao = (self.cb_c1.currentText() == _CLASSIF1_PADRAO
                     and (not disciplina or self.cb_c2.currentText() == disciplina))
        self.lbl_classif.setText(
            "padrão das OS do PCM — troque se este caso for diferente"
            if posto or (no_padrao and self.cb_c1.currentIndex() > 0) else "")

    def classificacoes(self):
        """(classif 1, classif 2) pelo NOME — vazio = sem classificação."""
        return (self.cb_c1.currentData() or "", self.cb_c2.currentData() or "")

    def tipo_tarefa(self):
        """O tipo com que a OS vai nascer. Sem escolha, o de sempre."""
        return (self.cb_tipo.currentData() or self.cb_tipo.currentText() or _TIPO_PADRAO)

    def _ajustar_altura_obs(self):
        """Fixa a altura dos DOIS cartoes e deixa a caixa da observacao preencher o que sobra.

        A conta anterior derivava a altura da caixa medindo o cartao ao vivo, e o valor mudava
        conforme o layout se assentava — dois relatos diferentes davam cartoes de tamanhos
        diferentes (140 e 171 px de caixa, medido). Impondo a altura e deixando o proprio layout
        repartir, o cartao fica igual para relato de uma linha ou de trinta, que e a regra:
        "caso o texto da observacao aumente o card nao aumenta, sera limitado por um scrol"
        (Levi, 16/09).

        `sizeHint` e nao `height` na decisao: as duas esticam juntas, entao medir a altura REAL
        seria medir a si mesma e o valor subiria a cada passada."""
        if getattr(self, "_obs_expandida", False):
            # "ver inteira": o cartao solta a altura e mostra o relato inteiro
            doc = self.ed_obs.document()
            larg = self.ed_obs.viewport().width()
            if larg > 40:
                doc.setTextWidth(larg)
            preciso = int(doc.size().height()) + 18
            self._cx_pedido.setMinimumHeight(0)
            self._cx_pedido.setMaximumHeight(16777215)
            self.ed_obs.setMinimumHeight(preciso)
            self.ed_obs.setMaximumHeight(preciso)
        else:
            base = self._cx_decisao.sizeHint().height() + self.FOLGA_CARTAO_PX
            if self._cx_decisao.minimumHeight() != base:
                self._cx_decisao.setMinimumHeight(base)
            if self._cx_pedido.maximumHeight() != base:
                self._cx_pedido.setFixedHeight(base)
            self.ed_obs.setMinimumHeight(self.OBS_MIN)
            self.ed_obs.setMaximumHeight(16777215)      # QWIDGETSIZE_MAX: quem limita e o cartao
        self._revisar_link_obs()

    def _revisar_link_obs(self):
        """"ver inteira" so quando sobra texto atras da rolagem. `setVisible` so quando MUDA:
        isto roda de dentro do resize da caixa, e mexer no layout a cada passada realimentaria
        o proprio evento."""
        expandida = getattr(self, "_obs_expandida", False)
        quer = bool(expandida or self.ed_obs.verticalScrollBar().maximum() > 0)
        if quer != self.b_ver_obs.isVisible():
            self.b_ver_obs.setVisible(quer)
        alvo = "ver menos" if expandida else "ver inteira"
        if self.b_ver_obs.text() != alvo:
            self.b_ver_obs.setText(alvo)

    def _alternar_obs(self):
        """"ver inteira" solta o teto da caixa; "ver menos" devolve. Quem so quer conferir um
        detalhe rola dentro da caixa; quem vai LER o procedimento do fabricante abre tudo."""
        self._obs_expandida = not getattr(self, "_obs_expandida", False)
        self._ajustar_altura_obs()

    def resizeEvent(self, e):
        # A quebra de linha muda com a largura, e com ela a altura que o texto pede. ADIADO de
        # proposito: mexer na altura DENTRO do resizeEvent realimenta o proprio evento, e a
        # forma com contexto (`self`) faz o Qt cancelar o disparo se a tela morrer antes.
        super().resizeEvent(e)
        t = getattr(self, "_t_obs", None)
        if t is not None:
            t.start()

    def _habilitar(self, on):
        if getattr(self, "_so_leitura", False):
            on = False
        self.b_aprovar.setEnabled(on)
        self.b_devolver.setEnabled(on)
        self.cb_tema.setEnabled(on)
        self.lbl_titulo.setEnabled(on)
        self.cb_resp.setEnabled(on)
        self.ed_tecnico.setEnabled(on)
        self.ed_data.setEnabled(on)
        # `set_editavel`, e nao setEnabled: QTextEdit desabilitado pinta o texto de cinza, e no
        # modo somente-leitura isso apagaria justamente o relato que a pessoa abriu para ler
        self.v_obs.set_editavel(on)
        self.os_pai.setEnabled(on)
        self.cb_tipo.setEnabled(on)
        self.cb_c1.setEnabled(on)
        self.cb_c2.setEnabled(on)
        self.b_status.setEnabled(on)
        self.editor_subs.set_editavel(on)

    # ── carga ──
    def set_itens(self, itens, assets, selecionar=None):
        self._so_leitura = False        # carga nova volta ao normal; quem quer travar diz depois
        self._itens = itens or []
        self._assets = assets or []
        _esvaziar(self.lista)
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
        self.chip_tema.setText("SUGERIDO PELA DESCRIÇÃO" if tema else "")
        self.chip_tema.setVisible(bool(tema))

        novo = sp.titulo(s.get("usina") or "", s.get("ativo") or "", tema) if tema else ""
        orig = str(s.get("descricao_full") or s.get("descricao") or "")
        self._titulo_manual = False    # solicitação nova: o padrão do tema volta a mandar
        self.lbl_titulo.setText(novo or orig)
        # O PCM está reescrevendo o texto de outra pessoa — precisa ver o que está mudando.
        self.lbl_orig.setText(
            "o supervisor escreveu: <s>%s</s> · título reescrito no padrão" % orig
            if novo and novo != orig else "")
        self.v_solicitante.setText(str(s.get("criado_por") or "—"))
        self.v_ativo.setText(str(s.get("ativo") or "—"))
        self.v_usina.setText(str(s.get("usina") or "—"))
        # SÓ O RELATO no campo; o bloco [PCM] fica guardado para ser devolvido na gravação.
        # Ele não é conteúdo, é o transporte do tema/técnico/subtarefas até aqui — e é dele que
        # a grade de subtarefas logo abaixo é montada. Mostrar os dois fazia o PCM ler a mesma
        # lista duas vezes (Levi, 15/09).
        bruto = str(s.get("observacao") or "")
        self._obs_original = sp.relato(bruto)
        self._obs_bloco = sp.so_bloco(bruto)
        self.ed_obs.setPlainText(self._obs_original)
        self.v_obs.atualizar()
        self._ajustar_altura_obs()
        self._t_obs.start()           # segunda passada, ja com a ficha desenhada
        self.os_pai.limpar()          # a pai da anterior nao vale para esta
        self.cb_c1.setCurrentIndex(0)   # a classificação é a do tema DESTA solicitação
        self.cb_c2.setCurrentIndex(0)
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
        # CINTO: `do_bloco` e uma LISTA de subtarefas. Se vier outra coisa — foi o indice que
        # o `currentIndexChanged` mandava, e que abortava o processo em `set_itens(2)` —, ignora
        # em vez de derrubar o app. A conexao ja passa `lambda *_`; isto e a segunda tranca,
        # porque exceção dentro de slot do PyQt6 nao levanta: mata o processo (0xC0000409).
        if do_bloco is not None and not isinstance(do_bloco, (list, tuple)):
            do_bloco = None
        tema = self.cb_tema.currentData() or ""
        self.cb_tema.setProperty("temado", "1" if tema else "0")
        self.cb_tema.style().unpolish(self.cb_tema)
        self.cb_tema.style().polish(self.cb_tema)
        # trocar o tema pode ligar ou desligar a regra da PERFORMANCE
        if getattr(self, "etiquetas", None) is not None and self._sel:
            self.etiquetas.aplicar_regra(tema, (self._sel or {}).get("ativo") or "")
        # o tema regenera o titulo — a nao ser que o PCM tenha escrito o dele
        if self._sel and not getattr(self, "_titulo_manual", False):
            self.lbl_titulo.setText(self._titulo_do_tema())
        self._sugerir_classif()
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

    @slot_seguro
    def _mudar_status(self, *_):
        """Troca o status da solicitação no Fracttal, com o motivo — a mesma rota do cancelamento.

        O MOTIVO É OBRIGATÓRIO aqui, e no Fracttal não é. É escolha: status trocado sem motivo
        vira exatamente o tipo de registro que ninguém consegue explicar três meses depois, e
        quem abre a solicitação de novo não tem a quem perguntar."""
        s = self._sel
        if not s:
            return
        dlg = _StatusDialog(self, str(s.get("numero") or s.get("id_code") or ""))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        idc = s.get("id_code") or s.get("numero") or s.get("id")
        self.b_status.setEnabled(False)
        self.hint.setText("mudando o status…")
        self._w_st = ApiWorker(api.mudar_status_solicitacao, idc, dlg.id_status, dlg.codigo, dlg.motivo)
        self._w_st.ok.connect(lambda _r, r=dlg.rotulo: self._status_ok(r))
        self._w_st.erro.connect(self._status_erro)
        self._w_st.start()

    @slot_seguro
    def _status_ok(self, rotulo):
        self.b_status.setEnabled(True)
        self.hint.setText("status alterado para %s" % rotulo)
        QMessageBox.information(self, "Status", "A solicitação passou para “%s”." % rotulo)
        self.carregar(force=True) if hasattr(self, "carregar") else None

    @slot_seguro
    def _status_erro(self, msg):
        self.b_status.setEnabled(True)
        self.hint.setText("")
        QMessageBox.warning(self, "Status", "Não consegui mudar o status.\n\n%s" % str(msg)[:220])

    @slot_seguro
    def _gravar_obs(self):
        """Grava a observação no Fracttal ao sair do campo — e só se ela mudou.

        SEM BOTÃO SALVAR de propósito: o resto desta ficha já funciona assim (técnico, data,
        tema), e um botão só para este campo faria a pessoa procurar o dos outros. Gravar sem
        mudança seria escrever no sistema do cliente à toa, então a comparação com o texto
        original é o que decide."""
        s = self._sel
        if not s or getattr(self, "_so_leitura", False):
            return
        novo = self.ed_obs.toPlainText().strip()
        if novo == str(getattr(self, "_obs_original", "") or "").strip():
            return
        idc = s.get("id_code") or s.get("numero") or s.get("id")
        # o bloco volta junto, intacto: sem isto, editar a observação apagaria o tema, o técnico
        # e as subtarefas que o supervisor escolheu, e a fila abriria com a lista padrão do tema
        bloco = getattr(self, "_obs_bloco", "")
        inteiro = (novo + "\n\n" + bloco).strip() if bloco else novo
        self._w_obs = ApiWorker(api.editar_observacao_solicitacao, idc, inteiro)
        self._w_obs.ok.connect(lambda _r, t=novo: self._obs_gravou(t))
        self._w_obs.erro.connect(self._obs_falhou)
        self._w_obs.start()

    @slot_seguro
    def _obs_gravou(self, texto):
        self._obs_original = texto
        if isinstance(self._sel, dict):
            # a lista em memória acompanha, sem recarregar — com o bloco de volta, que é o que
            # está de fato gravado no Fracttal
            bloco = getattr(self, "_obs_bloco", "")
            self._sel["observacao"] = (texto + "\n\n" + bloco).strip() if bloco else texto

    @slot_seguro
    def _obs_falhou(self, msg):
        # volta o texto ANTERIOR: deixar na tela algo que não está no Fracttal é pior do que
        # perder a digitação, porque a pessoa vai embora achando que gravou.
        self.ed_obs.setPlainText(str(getattr(self, "_obs_original", "") or ""))
        self.v_obs.atualizar()
        QMessageBox.warning(self, "Observação",
                            "Não consegui gravar a observação no Fracttal.\n\n%s" % str(msg)[:200])

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
        # o que vai para a OS e o TITULO DA TELA: se o PCM editou, e o dele que vale — a
        # mesma regra das subtarefas, que ja saem do editor e nao do padrao do tema
        titulo = (self.lbl_titulo.text() or "").strip() or self._titulo_do_tema()
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
                            idr, self.cb_resp.currentText(), tipo=self.tipo_tarefa(),
                            note=str(s.get("observacao") or ""),
                            etiqueta_ids=self.etiquetas.ids(),
                            id_parent=self.os_pai.id_parent(),
                            classif=self.classificacoes())
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

    def definir(self, titulo, sub):
        """Troca o texto do card sem recria-lo.

        O card do solicitante VIRA "Criar Nova Solicitacao" depois que a area abre. E o MESMO
        objeto, entao a grade nao se mexe e o card nao pisca — recriar faria a linha inteira
        saltar. Os dois rotulos vem do `_PlanoCard`, que passou a guarda-los para isto."""
        self.lbl_titulo.setText(titulo)
        self.lbl_sub.setText(sub)

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
        d = QLabel("Escolha a sua área. O <b>solicitante</b> pede o serviço e acompanha o que "
                   "pediu; o <b>PCM</b> confere a fila, aprova e padroniza os temas.")
        d.setObjectName("uiAjuda")
        d.setWordWrap(True)
        v.addWidget(d)

        # GRADE de 2 colunas, igual a de Criar OS. Nao e so estetica: com o card do plano, que e
        # largo (tile + texto + seta), tres lado a lado espremem o subtitulo em duas linhas.
        self.g_topo = QGridLayout()
        self.g_topo.setSpacing(14)
        self.c_nova = _CardBotao("Área do Solicitante",
                                 "Pedir serviço, acompanhar o que pediu e ver o histórico",
                                 self._abrir_solic, icone="send", badge="Supervisor")
        self.c_pcm = _CardBotao("Área PCM",
                                "Conferir a fila, aprovar e padronizar os temas",
                                self._abrir_pcm, icone="calcheck", badge="PCM")
        v.addLayout(self.g_topo)

        self.sub = QWidget()
        self.g_sub = QGridLayout(self.sub)
        self.g_sub.setContentsMargins(0, 0, 0, 0)
        self.g_sub.setSpacing(14)          # o mesmo respiro da grade de cima: uma grade so
        # OS DESTINOS DEPENDEM DA AREA. As duas pessoas que usam o app fazem trabalhos
        # diferentes e ate agora viam a mesma lista.
        self.DESTINOS = {
            "solic": (("Painel", "O que você pediu: pendente, em andamento e finalizado",
                       "painel", "grid", "Acompanhar"),
                      ("Histórico", "Tudo o que já passou por aqui", "hist", "clock",
                       "Consultar")),
            "pcm": (("Painel", "O que está pendente, em andamento e finalizado",
                     "painel", "grid", "Acompanhar"),
                    ("Fila do PCM", "Aprovar uma a uma, com as subtarefas do tema",
                     "fila", "list", "Aprovar"),
                    ("Histórico", "Tudo o que já passou por aqui", "hist", "clock",
                     "Consultar"),
                    ("Temas", "Padronizar nome, subtarefas e tipo de equipamento",
                     "temas", "layers", "Padronizar")),
        }
        self._subcards = []
        self._area = None
        self.sub.setVisible(False)
        v.addWidget(self.sub)
        v.addStretch(1)
        self._estreito = None
        self._reflow(inicial=True)

    # ── navegacao ──
    def _montar_sub(self, area):
        """Refaz os cards de baixo para a area escolhida."""
        _esvaziar(self.g_sub, guardar_ultimo=False)
        self._subcards = []
        for rot, txt, alvo, ico, bd in self.DESTINOS[area]:
            self._subcards.append(
                _CardBotao(rot, txt, lambda a=alvo: self._ir(a), icone=ico, badge=bd))
        self._area = area
        self._estreito = None          # forca o refluxo a reposicionar os cards novos
        self._reflow(inicial=True)
        cols = 1 if self._matches()["estreito"] else self.COLS
        for i, c in enumerate(self._subcards):
            self.g_sub.addWidget(c, i // cols, i % cols)
        for i in range(min(cols, len(self._subcards))):
            self.g_sub.setColumnStretch(i, 1)

    def _abrir_solic(self):
        """1o clique abre a area; a partir dai o card E o "Criar Nova Solicitacao".

        E o caminho que o supervisor faz dez vezes por dia, e ficava atras de mais um passo."""
        if self._area == "solic":
            self._ir("nova")
            return
        self.c_pcm.marcar_ativo(False)
        self.c_nova.definir("Criar Nova Solicitação",
                            "Pedir serviço já com tema, técnico sugerido e data pretendida")
        self.c_nova.marcar_ativo(True)
        self._montar_sub("solic")
        self.sub.setVisible(True)

    def _abrir_pcm(self):
        """1o clique abre os tres destinos; 2o vai direto para a fila, que e onde o PCM trabalha.

        O estado fica num atributo e nao em `isVisible()`: isVisible responde pela cadeia
        inteira de pais, entao seria False com a aba em segundo plano — e o segundo clique
        reabriria em vez de navegar."""
        if self._area == "pcm":
            self._ir("fila")
            return
        if not self._liberar_pcm():
            return
        self._aberto = True
        self.c_nova.definir("Área do Solicitante",
                            "Pedir serviço, acompanhar o que pediu e ver o histórico")
        self.c_nova.marcar_ativo(False)
        self.c_pcm.marcar_ativo(True)
        self._montar_sub("pcm")
        self.sub.setVisible(True)

    def _liberar_pcm(self) -> bool:
        """A senha da area do PCM. TRANCA DE PORTA, nao cofre.

        O app roda na maquina de quem usa: quem quiser mesmo entrar consegue. O que isto impede
        e o acesso POR ENGANO — o supervisor que clica em "Area PCM" por curiosidade e aprova
        uma solicitacao sem querer. Uma vez por sessao, porque pedir a cada clique faria o PCM
        digitar dez vezes por dia e a senha acabaria colada no monitor.
        """
        if pcm_acesso.liberado():
            return True
        txt, ok = QInputDialog.getText(self, "Área PCM",
                                       "Senha da área do PCM:", QLineEdit.EchoMode.Password)
        if not ok:
            return False
        if not pcm_acesso.confere(txt):
            QMessageBox.warning(self, "Área PCM", "Senha incorreta.")
            return False
        pcm_acesso.liberar()
        return True

    def recolher(self):
        self._aberto = False
        self._area = None
        self.c_pcm.marcar_ativo(False)
        self.c_nova.marcar_ativo(False)
        self.c_nova.definir("Área do Solicitante",
                            "Pedir serviço, acompanhar o que pediu e ver o histórico")
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
                         (self.g_sub, list(self._subcards))):
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
/* a legenda ao lado de TEMA: branco, negrito, caixa alta — sem selo e sem verde. O verde da
   ficha e reservado ao que o supervisor escreveu, e um selo ali competia com o proprio campo. */
QLabel#chipSugerido { background:transparent; color:#ffffff; font-size:10.5px;
  font-weight:700; letter-spacing:0.8px; padding:0 0 0 2px; }
QFrame#boxSug { background:#141b2c; border:1px solid #232a3d; border-radius:10px; }
/* as duas colunas da ficha: o pedido (o que se le) e a decisao (o que se preenche) */
QFrame#boxLado { background:#121A2B; border:1px solid #232c45; border-radius:12px; }
/* a observacao e a MESMA caixa lendo ou editando — o verde so marca qual dos dois estados */
QTextEdit#obsCampo { background:#161d30; border:1px solid #232c45; border-radius:10px;
  color:#dfe3ee; font-size:13px; padding:8px 11px; }
QTextEdit#obsCampo:hover { border-color:#39456a; }
QTextEdit#obsCampo:focus { border:1px solid #8fce3f; }
QPushButton#verInteira { background:transparent; border:none; color:#a9d96a; font-size:12px;
  padding:0 2px; min-height:0; font-weight:600; }
QPushButton#verInteira:hover { color:#c2ec78; }
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
/* o campo de etiquetas na coluna da decisao: mesmo risco dos valores editaveis ao lado */
QComboBox#etqInline { background:transparent; border:none; border-bottom:1px dashed #39405a;
  border-radius:0; color:#e8ebf2; font-size:13px; min-height:24px; max-height:24px;
  padding:0 2px; }
QComboBox#etqInline:hover { color:#ffffff; border-bottom:1px dashed #8fce3f; }
QComboBox#etqInline:focus { border-bottom:1px solid #8fce3f; }
QComboBox#etqInline::drop-down { border:none; width:0px; }
QComboBox#etqInline QAbstractItemView { background:#161d30; color:#e8ebf2;
  border:1px solid #222c43; selection-background-color:rgba(143,206,63,0.18); outline:none; }
/* tema escolhido = borda verde: e o campo que decide o checklist da OS */
QComboBox#cbTema[temado="1"] { border:1px solid #8fce3f; }
/* o titulo da OS aberto para edicao: mesmo tamanho e peso do rotulo, para a linha nao pular */
QLineEdit#tituloOS { background:transparent; border:none; border-bottom:1px solid #8fce3f;
  border-radius:0; color:#ffffff; font-size:26px; font-weight:600; padding:0 2px; }
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
        self.fila = _Fila(lambda: self.ir(self.PAINEL), on_atualizar=self._atualizar_fila)
        self.painel.on_carregou = self._painel_carregou
        self._wcls = None
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
            if self._wcls is None and self.fila.cb_c1.count() <= 1:
                # as listas de Classificação 1 e 2 vêm do Fracttal; uma busca só, na 1ª entrada
                self._wcls = ApiWorker(api.get_tipos_classif)
                self._wcls.ok.connect(self._espalhar_classif)
                self._wcls.erro.connect(lambda *_: setattr(self, "_wcls", None))
                self._wcls.start()
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

    def _atualizar_fila(self):
        """Botao Atualizar da Fila: manda o Painel buscar de novo. A re-alimentacao da fila
        acontece no `_painel_carregou`, que roda quando a resposta chega."""
        self.painel.carregar(force=True)

    def _painel_carregou(self):
        """A lista do Painel mudou. Se a Fila esta aberta, ela acompanha — mantendo a
        solicitacao que estava selecionada, se ela continuar pendente."""
        self.fila.fim_da_atualizacao()
        if self.stack.currentIndex() != self.FILA:
            return
        pendentes = self.painel.pendentes()
        atual = (self.fila._sel or {}).get("id_code")
        manter = next((x for x in pendentes if x.get("id_code") == atual), None)
        self.fila.set_itens(pendentes, self._assets, selecionar=manter)

    @slot_seguro
    def _espalhar_classif(self, d):
        self._wcls = None
        self.fila.set_tipos_classif(d)

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
        """Abre a Fila na solicitação clicada — venha ela de qualquer coluna do Painel.

        Se ela não está mais pendente, a Fila entra em modo LEITURA: o detalhe aparece inteiro e
        nada é editável, porque a OS já nasceu e a API do Fracttal não edita OS criada. Deixar os
        campos ativos ali seria oferecer uma edição que morre no botão."""
        pendentes = self.painel.pendentes()
        so_leitura = not any(x is s or x.get("id_code") == s.get("id_code") for x in pendentes)
        self.ir(self.FILA)   # ja carrega os responsaveis; a ordem importa (ver _selecionar)
        itens = pendentes if not so_leitura else (pendentes + [s])
        self.fila.set_itens(itens, self._assets, selecionar=s)
        self.fila.set_somente_leitura(so_leitura)

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
