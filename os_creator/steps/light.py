"""Peças da "lógica light": bloco numerado com borda e campo que vira editável ao clique.

É o desenho que o Levi aprovou em 03/09/2026, depois de duas rodadas de simulação. A ideia:
um formulário cheio de caixas de 40 px transmite "preencha tudo", quando na verdade quase todo
campo já vem respondido pelo tema e pela cascata de ativos, e a pessoa só CONFERE. Então o valor
aparece como texto, com um pontilhado discreto por baixo, e vira campo no lugar quando clicado.

Isto é o mesmo princípio do `_CampoClicavel` da Fila do PCM, generalizado — lá nasceu para o
técnico e a data sugerida, aqui vale para o formulário inteiro.

O estilo mora AQUI, e não na tela que usa. Em Qt a folha do ancestral mais próximo vence: quando
as regras do editor de subtarefas moravam no SolicPcmTab, o SolicitacaoTab — que tem QSS_FORM
próprio — engolia a regra de QLineEdit e os campos apareciam como caixas preenchidas numa tela e
como texto na outra. Estilo que viaja com o widget não tem esse problema.
"""
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
                             QComboBox, QLineEdit, QTextEdit, QDateTimeEdit, QDateEdit,
                             QStackedLayout, QSizePolicy)

from steps.ui import icone_pix, GREEN, MUTED, TEXT, CARD

RISCO = "#222c43"
PONTILHADO = "#39405a"
FRACO = "#5a6072"
# O azul já existe na linguagem do app: é o Nº da solicitação nos cartões da fila. A observação
# usa ele para separar o relato livre — texto que a pessoa escreve do zero — dos campos que o
# sistema preencheu. Cor nova para isso seria inventar vocabulário sem necessidade.
AZUL = "#6FA8DC"
AZUL_FRACO = "#3d6690"

QSS = f"""
QFrame#blocoLight {{ background:{CARD}; border:1px solid {RISCO}; border-radius:12px; }}
QLabel#blocoNum {{ color:{GREEN}; font-size:13px; font-weight:700; background:transparent; }}
QLabel#blocoTit {{ color:{TEXT}; font-size:14.5px; font-weight:600; background:transparent; }}
QLabel#lgRotulo {{ color:{MUTED}; font-size:10.5px; font-weight:700; letter-spacing:0.8px;
  background:transparent; }}
QLabel#lgObrig {{ color:{GREEN}; font-size:10.5px; font-weight:700; background:transparent; }}
QLabel#lgDica {{ color:{MUTED}; font-size:12px; background:transparent; }}

/* o VALOR parece texto e convida ao clique com o pontilhado */
QLabel#lgValor {{ color:{TEXT}; font-size:13px; background:transparent; padding:2px 2px 3px 2px;
  border-bottom:1px dashed {PONTILHADO}; }}
QLabel#lgValor:hover {{ color:#ffffff; border-bottom:1px dashed {GREEN}; }}
QLabel#lgValor[vazio="1"] {{ color:{FRACO}; }}
QLabel#lgValor[grande="1"] {{ font-size:15px; font-weight:600; padding:3px 2px 4px 2px; }}

/* o campo aberto: sem caixa, só o sublinhado verde */
QLineEdit#lgCampo, QComboBox#lgCampo, QDateTimeEdit#lgCampo, QDateEdit#lgCampo {{
  background:transparent; border:none; border-bottom:1px solid {GREEN}; border-radius:0;
  color:{TEXT}; font-size:13px; min-height:26px; max-height:26px; padding:0 2px; }}
QLineEdit#lgCampo[grande="1"] {{ font-size:15px; font-weight:600; min-height:28px; max-height:28px; }}
QTextEdit#lgCampo {{ background:transparent; border:none; border-bottom:1px solid {GREEN};
  border-radius:0; color:{TEXT}; font-size:13px; padding:0 2px; }}
QTextEdit#lgCampo[grande="1"] {{ font-size:15px; font-weight:600; }}
QComboBox#lgCampo::drop-down {{ border:none; width:0px; }}
QComboBox#lgCampo::down-arrow {{ image:none; width:0px; }}
QComboBox#lgCampo QAbstractItemView {{ background:#161d30; color:{TEXT}; border:1px solid {RISCO};
  selection-background-color:rgba(143,206,63,0.18); outline:none; }}
QDateTimeEdit#lgCampo::drop-down, QDateEdit#lgCampo::drop-down {{ border:none; width:0px; }}

/* a observação: caixa de verdade, com borda azul, porque é texto livre e não campo preenchido */
QLabel#lgObs {{ color:{TEXT}; font-size:13px; background:rgba(111,168,220,0.045);
  border:1px solid {AZUL_FRACO}; border-radius:8px; padding:8px 12px; }}
QLabel#lgObs:hover {{ border-color:{AZUL}; background:rgba(111,168,220,0.08); }}
QLabel#lgObs[vazio="1"] {{ color:{FRACO}; }}
QTextEdit#lgObsEd {{ color:{TEXT}; font-size:13px; background:rgba(111,168,220,0.06);
  border:1px solid {AZUL}; border-radius:8px; padding:6px 10px; }}

/* checkbox verde, o mesmo do "anexo obrigatório" do editor de subtarefas */
QCheckBox#lgChk {{ color:{MUTED}; font-size:12.5px; spacing:7px; background:transparent;
  min-height:26px; }}
QCheckBox#lgChk:checked {{ color:{GREEN}; }}
QCheckBox#lgChk::indicator {{ width:14px; height:14px; border:1px solid {PONTILHADO};
  border-radius:3px; background:transparent; }}
QCheckBox#lgChk::indicator:hover {{ border-color:{GREEN}; }}
QCheckBox#lgChk::indicator:checked {{ background:{GREEN}; border-color:{GREEN}; }}

/* card de aviso: verde translucido, o mesmo tratamento do quadrado do ícone no hub */
QFrame#lgAviso {{ background:rgba(143,206,63,0.07); border:1px solid rgba(143,206,63,0.28);
  border-radius:9px; }}
QLabel#lgAvisoTxt {{ color:{MUTED}; font-size:12px; background:transparent; }}
QLabel#lgAvisoIco {{ background:transparent; }}
"""


def _ler(w, fmt="dd/MM/yyyy HH:mm"):
    """O texto que representa o valor atual do widget, seja ele qual for."""
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, (QDateTimeEdit, QDateEdit)):
        d = w.dateTime() if isinstance(w, QDateTimeEdit) else w.date()
        return d.toString(fmt if isinstance(w, QDateTimeEdit) else "dd/MM/yyyy")
    if isinstance(w, QTextEdit):
        return w.toPlainText().strip()
    if isinstance(w, QLineEdit):
        return w.text()
    return ""


def _placeholder(txt):
    """True quando o texto é uma dica ('— selecione —', 'Todos os…'), e não um valor."""
    t = (txt or "").strip().lower()
    return (not t) or t.startswith("—") or t.startswith("(") or "selecione" in t


class Valor(QWidget):
    """Rótulo em caixa alta + valor como texto; clicar no valor abre o widget no mesmo lugar.

    O widget é o MESMO objeto que a tela já usava (`self.cb_cliente`, `self.data_prev`…), só
    re-parentado para dentro daqui. É o que permite trocar a roupa do formulário sem tocar em
    `_criar`, `prefill_por_code`, nos workers nem nos testes: todos continuam falando com o
    combo pelo nome de sempre.
    """

    def __init__(self, rotulo, editor, obrig=False, vazio="— selecione —", grande=False,
                 aberto=False, dica=""):
        super().__init__()
        self.editor = editor
        self._vazio_txt = vazio
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)

        if rotulo:
            lin = QHBoxLayout()
            lin.setSpacing(3)
            r = QLabel(rotulo.upper())
            r.setObjectName("lgRotulo")
            lin.addWidget(r)
            if obrig:
                o = QLabel("*")
                o.setObjectName("lgObrig")
                lin.addWidget(o)
            lin.addStretch(1)
            v.addLayout(lin)

        editor.setObjectName("lgCampo")
        if grande:
            editor.setProperty("grande", "1")
        if isinstance(editor, QTextEdit):
            editor.setFixedHeight(30 if grande else 26)
            editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.lbl = QLabel("")
        self.lbl.setObjectName("lgValor")
        if grande:
            self.lbl.setProperty("grande", "1")
        self.lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl.setToolTip("clique para editar")
        self.lbl.setMinimumWidth(1)
        self.lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        # A pilha vive num container de altura FIXA. Sem isto o QStackedLayout se dimensiona
        # pelo sizeHint da maior pagina, e o sizeHint de um QTextEdit e ~192 px mesmo com
        # setFixedHeight(30) — o rotulo do titulo esticava para 192 px e virava uma caixa vazia
        # gigante no meio do bloco 1. Medido: label sizeHint 28, desc sizeHint 192, pilha 192.
        self.caixa = QWidget()
        self.caixa.setObjectName("uiGroup")          # QSS_FORM deixa este objectName transparente
        self.pilha = QStackedLayout(self.caixa)
        self.pilha.setContentsMargins(0, 0, 0, 0)
        self.pilha.addWidget(self.lbl)
        self.pilha.addWidget(editor)
        self.pilha.setCurrentIndex(1 if aberto else 0)
        alt = editor.maximumHeight()
        self.caixa.setFixedHeight(alt if alt < 16000 else max(28, self.lbl.sizeHint().height()))
        v.addWidget(self.caixa)
        self._sempre_aberto = aberto

        if dica:
            d = QLabel(dica)
            d.setObjectName("lgDica")
            d.setWordWrap(True)
            d.setMinimumWidth(1)
            v.addWidget(d)

        editor.installEventFilter(self)
        if isinstance(editor, QComboBox):
            editor.activated.connect(lambda *_: self.fechar())
        # O rotulo se atualiza SOZINHO quando o widget muda, venha a mudanca do clique da pessoa
        # ou do codigo. A cascata de ativos, o prefill do deep link e o reset trocam o indice do
        # combo por dentro; sem esta ligacao o valor mostrado ficaria congelado no anterior, e a
        # tela mentiria sobre o que vai ser enviado.
        for sinal in ("currentIndexChanged", "dateTimeChanged", "dateChanged", "textChanged"):
            sig = getattr(editor, sinal, None)
            if sig is not None:
                sig.connect(lambda *_: self.atualizar())
        self.atualizar()

    # ── abrir / fechar ──
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.abrir()

    def abrir(self):
        if self._sempre_aberto:
            return
        self.pilha.setCurrentIndex(1)
        self.editor.setFocus(Qt.FocusReason.MouseFocusReason)
        # A lista abre no PRIMEIRO clique, inclusive nos combos pesquisáveis (cliente, usina,
        # ativo). Antes o `showPopup` era só para os não-editáveis: nos outros o primeiro clique
        # apenas trocava o rótulo pelo campo, e era preciso clicar de novo para ver as opções.
        # O singleShot é necessário porque o widget acabou de aparecer na pilha — chamar
        # showPopup no mesmo ciclo abre a lista com a geometria antiga.
        if isinstance(self.editor, QComboBox):
            QTimer.singleShot(0, self.editor.showPopup)

    def fechar(self):
        if self._sempre_aberto:
            return
        self.pilha.setCurrentIndex(0)
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
        txt = _ler(self.editor)
        vazio = _placeholder(txt)
        self.lbl.setText(txt if not vazio else (txt or self._vazio_txt))
        self.lbl.setProperty("vazio", "1" if vazio else "0")
        self.lbl.style().unpolish(self.lbl)
        self.lbl.style().polish(self.lbl)

    def setEnabled(self, on):
        super().setEnabled(on)
        self.lbl.setEnabled(on)


class ValorObs(Valor):
    """A observação: caixa com borda azul, porque é texto livre e não campo preenchido."""

    def __init__(self, rotulo, editor, altura=78):
        super().__init__(rotulo, editor, vazio="Informações adicionais sobre o incidente…")
        self.lbl.setObjectName("lgObs")
        self.lbl.setWordWrap(True)
        self.lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        editor.setObjectName("lgObsEd")
        editor.setFixedHeight(altura)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.caixa.setFixedHeight(altura)
        self.atualizar()


class Bloco(QFrame):
    """Seção numerada com borda própria. Por dentro continua leve — sem caixa por campo."""

    def __init__(self, num, titulo):
        super().__init__()
        self.setObjectName("blocoLight")
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 18)
        v.setSpacing(0)

        cab = QHBoxLayout()
        cab.setSpacing(10)
        n = QLabel(str(num))
        n.setObjectName("blocoNum")
        n.setFixedWidth(18)
        t = QLabel(titulo)
        t.setObjectName("blocoTit")
        cab.addWidget(n)
        cab.addWidget(t)
        cab.addStretch(1)
        v.addLayout(cab)
        v.addSpacing(12)

        self.corpo = QVBoxLayout()
        self.corpo.setContentsMargins(28, 0, 0, 0)
        self.corpo.setSpacing(14)
        v.addLayout(self.corpo)
        v.addStretch(1)

    def add(self, w):
        if isinstance(w, QWidget):
            self.corpo.addWidget(w)
        else:
            self.corpo.addLayout(w)
        return self


def grade(itens, cols=3, hspace=36, vspace=14):
    """Distribui os campos em colunas iguais. `itens` aceita None para deixar a célula vazia."""
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(hspace)
    g.setVerticalSpacing(vspace)
    for i, w in enumerate(itens):
        if w is not None:
            g.addWidget(w, i // cols, i % cols)
    for c in range(cols):
        g.setColumnStretch(c, 1)
    return g


class Aviso(QFrame):
    """Recado curto ao lado do campo, com ícone de alerta.

    Existe porque a dica embaixo do campo empurrava o que vem depois para longe: no bloco 1 ela
    separava o tema do título, que é justamente o par que a pessoa lê junto."""

    def __init__(self, texto):
        super().__init__()
        self.setObjectName("lgAviso")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(9)
        ico = QLabel()
        ico.setObjectName("lgAvisoIco")
        ico.setPixmap(icone_pix("alert", GREEN, 15))
        ico.setFixedWidth(15)
        ico.setAlignment(Qt.AlignmentFlag.AlignTop)
        h.addWidget(ico)
        t = QLabel(texto)
        t.setObjectName("lgAvisoTxt")
        t.setWordWrap(True)
        t.setMinimumWidth(1)
        h.addWidget(t, 1)
