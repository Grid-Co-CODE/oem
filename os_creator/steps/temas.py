# -*- coding: utf-8 -*-
"""Temas — a tela onde o PCM padroniza sem depender de release.

O QUE ELA RESOLVE. Até 04/09/2026 os temas viviam num dicionário Python em `solic_spec.py`:
mudar o nome de um tema, acrescentar uma subtarefa ou marcar anexo obrigatório exigia editar
código e subir versão nova para todo mundo. O Levi pediu que isso passasse para a mão do PCM.

A REGRA QUE ELE FEZ QUESTÃO: o **tipo de equipamento** do tema não é etiqueta. Quando o tema for
escolhido na Solicitação, ele FILTRA a lista de ativos — escolher "Inversor — inspeção e medição"
deixa aparecer só inversores. É o campo que faz esta tela valer mais do que um cadastro bonito.

ARQUIVAR, E NÃO EXCLUIR. Um tema usado em 751 solicitações não pode sumir: some da lista de
escolha e o histórico continua de pé, porque a OS guarda as subtarefas copiadas no momento em
que nasceu. Editar um tema nunca mexe em OS já criada.

A forma segue a tela de Fila do PCM — lista à esquerda, detalhe à direita, uma linha separando
cada item da seguinte. É a mesma leitura: escolher de um lado, decidir do outro.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
                             QLineEdit, QComboBox, QScrollArea, QGridLayout, QMessageBox,
                             QSizePolicy)

import solic_spec as sp
import temas_store as ts
from steps.subtarefas_edit import EditorSubtarefas
from steps.ui import GREEN, MUTED, TEXT, CARD, BORDER, esvaziar as _esvaziar
from workers import ApiWorker, slot_seguro

# Os tipos vêm do CADASTRO, e não de uma lista escrita à mão. É o mesmo campo `tipo` que o
# filtro de ativos compara em `solicitacao._refresh_ativos`, então os dois nunca divergem — uma
# lista minha teria "Tracker" onde o Fracttal diz "Estrutura Trackers", e o filtro nunca casaria.
TIPOS_EQUIP = []


class _Celula(QFrame):
    """Uma linha da lista de temas. Mesma célula da Fila do PCM: sem borda em volta, separada
    da seguinte por um risco, barra verde na selecionada."""

    def __init__(self, t, on_click):
        super().__init__()
        self.dados = t
        self._on_click = on_click
        self.setObjectName("filaCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 12, 11)
        v.setSpacing(3)

        n = QLabel(t.get("nome") or t["chave"])
        n.setStyleSheet("color:%s;font-size:13.5px;font-weight:600;background:transparent;" % TEXT)
        n.setWordWrap(True)
        n.setMinimumWidth(1)
        v.addWidget(n)

        lin = QHBoxLayout()
        lin.setSpacing(6)
        eq = (t.get("tipo_equipamento") or "").strip()
        chip = QLabel(eq or "sem equipamento")
        chip.setObjectName("chipTema" if eq else "chipVazio")
        f = chip.font()
        f.setPixelSize(11)
        chip.setFont(f)
        chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lin.addWidget(chip)
        n_subs = len(t.get("subtarefas") or [])
        meta = QLabel("%d subtarefa%s · %s solicitações"
                      % (n_subs, "" if n_subs == 1 else "s", t.get("solicitacoes") or 0))
        meta.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        meta.setMinimumWidth(1)
        lin.addWidget(meta, 1)
        v.addLayout(lin)
        if t.get("arquivado"):
            a = QLabel("arquivado")
            a.setObjectName("chipVazio")
            a.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            v.addWidget(a)

    def marcar(self, on):
        self.setProperty("sel", "1" if on else "0")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click(self.dados)


class TemasTab(QWidget):
    """A aba. Lista à esquerda, edição à direita, salvar por tema."""

    def __init__(self, on_voltar=None):
        super().__init__()
        self._itens = []
        self._sel = None
        self._cels = []
        self._sujo = False
        self._w = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        cab = QFrame()
        cab.setObjectName("filaCab")
        topo = QHBoxLayout(cab)
        topo.setContentsMargins(14, 9, 16, 9)
        topo.setSpacing(12)
        if on_voltar:
            b = QPushButton("← Voltar")
            b.setObjectName("btnVoltar")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(on_voltar)
            topo.addWidget(b)
        tit = QLabel("Temas")
        tit.setStyleSheet("color:%s;font-size:15px;font-weight:600;background:transparent;" % TEXT)
        topo.addWidget(tit)
        topo.addStretch(1)
        self.lbl_cont = QLabel("")
        self.lbl_cont.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_cont.setStyleSheet("color:%s;font-size:12.5px;background:transparent;" % MUTED)
        topo.addWidget(self.lbl_cont)
        v.addWidget(cab)

        corpo = QHBoxLayout()
        corpo.setSpacing(0)

        # ── esquerda ──
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        cc = QWidget()
        cc.setObjectName("cabColBar")
        ccl = QHBoxLayout(cc)
        ccl.setContentsMargins(14, 10, 12, 9)
        rot = QLabel("TEMAS")
        rot.setStyleSheet("color:#8a90a2;font-size:10.5px;font-weight:700;letter-spacing:0.8px;"
                          "background:transparent;")
        ccl.addWidget(rot)
        ccl.addStretch(1)
        self.b_novo = QPushButton("+ novo tema")
        self.b_novo.setObjectName("btnLink")
        self.b_novo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_novo.clicked.connect(self._novo)
        ccl.addWidget(self.b_novo)
        col.addWidget(cc)

        cx = QWidget()
        cxl = QVBoxLayout(cx)
        cxl.setContentsMargins(12, 9, 12, 9)
        self.ed_busca = QLineEdit()
        self.ed_busca.setPlaceholderText("Buscar tema…")
        # mesmo debounce do Painel: repintar a lista a cada tecla cria e destroi dezenas de
        # widgets, e cada setParent(None) piscava uma janela de topo
        self._t_busca = QTimer(self)
        self._t_busca.setSingleShot(True)
        self._t_busca.setInterval(250)
        self._t_busca.timeout.connect(self._pintar_lista)
        self.ed_busca.textChanged.connect(self._t_busca.start)
        cxl.addWidget(self.ed_busca)
        col.addWidget(cx)

        esq = QScrollArea()
        esq.setWidgetResizable(True)
        esq.setFrameShape(QScrollArea.Shape.NoFrame)
        esq.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        esq.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                          "QScrollArea > QWidget > QWidget{background:transparent;}")
        inner = QWidget()
        self.lista = QVBoxLayout(inner)
        self.lista.setContentsMargins(0, 0, 0, 0)
        self.lista.setSpacing(0)
        self.lista.addStretch(1)
        esq.setWidget(inner)
        col.addWidget(esq, 1)
        cw = QWidget()
        cw.setLayout(col)
        cw.setFixedWidth(340)
        corpo.addWidget(cw)

        div = QFrame()
        div.setObjectName("divisorV")
        div.setFixedWidth(1)
        corpo.addWidget(div)

        # ── direita ──
        dsc = QScrollArea()
        dsc.setWidgetResizable(True)
        dsc.setFrameShape(QScrollArea.Shape.NoFrame)
        dsc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        dsc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                          "QScrollArea > QWidget > QWidget{background:transparent;}")
        d = QWidget()
        self.det = QVBoxLayout(d)
        self.det.setContentsMargins(20, 16, 20, 16)
        self.det.setSpacing(12)
        dsc.setWidget(d)
        corpo.addWidget(dsc, 1)
        v.addLayout(corpo, 1)

        self._montar_detalhe()
        self._habilitar(False)

    # ── detalhe ──
    def _rotulo(self, txt):
        l = QLabel(txt.upper())
        l.setStyleSheet("color:%s;font-size:10.5px;font-weight:700;letter-spacing:0.8px;"
                        "background:transparent;" % MUTED)
        return l

    def _montar_detalhe(self):
        self.lbl_tit = QLabel("Escolha um tema à esquerda.")
        self.lbl_tit.setStyleSheet("color:%s;font-size:22px;font-weight:600;"
                                   "background:transparent;" % TEXT)
        self.lbl_tit.setWordWrap(True)
        self.lbl_tit.setMinimumWidth(1)
        self.det.addWidget(self.lbl_tit)

        self.lbl_uso = QLabel("")
        self.lbl_uso.setStyleSheet("color:%s;font-size:12.5px;background:transparent;" % MUTED)
        self.lbl_uso.setWordWrap(True)
        self.lbl_uso.setMinimumWidth(1)
        self.det.addWidget(self.lbl_uso)

        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(5)
        self.ed_nome = QLineEdit()
        self.cb_equip = QComboBox()
        self.cb_equip.addItem("— não filtra —")
        self.cb_tipo_os = QComboBox()
        self.cb_tipo_os.addItems(["", "Elétrica", "Mecânica", "Civil", "Preditiva", "Outros"])
        for col, rot, w in ((0, "Nome do tema", self.ed_nome),
                            (1, "Tipo de equipamento", self.cb_equip),
                            (2, "Tipo de OS", self.cb_tipo_os)):
            g.addWidget(self._rotulo(rot), 0, col)
            g.addWidget(w, 1, col)
        g.setColumnStretch(0, 14)
        g.setColumnStretch(1, 10)
        g.setColumnStretch(2, 10)
        self.det.addLayout(g)

        # O aviso do filtro fica COLADO no campo, e não no rodapé: é a consequência menos óbvia
        # desta tela, e quem escolhe o tipo precisa saber na hora o que vai acontecer.
        self.lbl_filtro = QLabel("")
        self.lbl_filtro.setStyleSheet("color:%s;font-size:11.5px;background:transparent;" % MUTED)
        self.lbl_filtro.setWordWrap(True)
        self.lbl_filtro.setMinimumWidth(1)
        self.cb_equip.currentIndexChanged.connect(self._sync_filtro)
        self.det.addWidget(self.lbl_filtro)

        g2 = QGridLayout()
        g2.setHorizontalSpacing(14)
        g2.setVerticalSpacing(5)
        self.ed_motivo = QLineEdit()
        self.cb_c1 = QComboBox()
        self.cb_c1.addItems(["", "Não Para o Ativo",
                             "Leve (Não Parou o Ativo, mas Afetou a Eficiência)",
                             "Moderado (Impacto Parcial no Ativo)",
                             "Grave (Parou o Ativo)"])
        for col, rot, w in ((0, "Motivo (vira o título da OS)", self.ed_motivo),
                            (1, "Classificação 1", self.cb_c1)):
            g2.addWidget(self._rotulo(rot), 0, col)
            g2.addWidget(w, 1, col)
        g2.setColumnStretch(0, 1)
        g2.setColumnStretch(1, 1)
        self.det.addLayout(g2)

        # ETIQUETAS DO TEMA. Antes de 04/09 quem decidia era `sp.exige_performance()`, uma
        # funcao com `if tema.startswith("tracker")` e uma lista de gatilhos por nome de ativo —
        # acrescentar uma etiqueta a um tema exigia release. Agora e campo do tema, e por isso
        # na Fila o chip diz "(tema)" e nao "(regra)".
        self.det.addWidget(self._rotulo("Etiquetas que a OS vai levar"))
        self.fila_etq = QHBoxLayout()
        self.fila_etq.setSpacing(6)
        self.fila_etq.addStretch(1)
        self.det.addLayout(self.fila_etq)
        self.cb_etq = QComboBox()
        self.cb_etq.addItem("+ adicionar etiqueta", None)
        self.cb_etq.activated.connect(self._add_etq)
        self.det.addWidget(self.cb_etq)
        self._etq_cat = []
        self._etqs = []

        self.editor = EditorSubtarefas("Sem subtarefas: a OS vai nascer só com as 3 da base.")
        self.det.addWidget(self.editor)
        for w in (self.ed_nome, self.ed_motivo):
            w.textChanged.connect(self._marcar_sujo)
        for w in (self.cb_equip, self.cb_tipo_os, self.cb_c1):
            w.currentIndexChanged.connect(self._marcar_sujo)
        self.editor.mudou.connect(self._marcar_sujo)

        acoes = QHBoxLayout()
        acoes.setSpacing(10)
        self.b_salvar = QPushButton("Salvar tema")
        self.b_salvar.setObjectName("btnAprovar")
        self.b_salvar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_salvar.clicked.connect(self._salvar)
        self.b_desc = QPushButton("Descartar alterações")
        self.b_desc.setObjectName("btnDevolver")
        self.b_desc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_desc.clicked.connect(lambda: self._selecionar(self._sel))
        self.b_arq = QPushButton("Arquivar")
        self.b_arq.setObjectName("btnDevolver")
        self.b_arq.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_arq.clicked.connect(self._arquivar)
        acoes.addWidget(self.b_salvar)
        acoes.addWidget(self.b_desc)
        acoes.addWidget(self.b_arq)
        acoes.addStretch(1)
        self.hint = QLabel("")
        self.hint.setStyleSheet("color:%s;font-size:12px;background:transparent;" % MUTED)
        self.hint.setWordWrap(True)
        self.hint.setMinimumWidth(1)
        acoes.addWidget(self.hint)
        self.det.addLayout(acoes)
        self.det.addStretch(1)

    def _sync_filtro(self):
        eq = self._equip_atual()
        self.lbl_filtro.setText(
            "Ao escolher este tema na Solicitação, a lista de ativos vai mostrar só "
            "<b style='color:%s'>%s</b>." % (TEXT, eq) if eq
            else "Sem tipo de equipamento, este tema não filtra a lista de ativos.")

    def _habilitar(self, on):
        for w in (self.ed_nome, self.ed_motivo, self.cb_equip, self.cb_tipo_os, self.cb_c1,
                  self.cb_etq, self.b_salvar, self.b_desc, self.b_arq):
            w.setEnabled(on)
        self.editor.set_editavel(on)
        if on and not ts.pode_gravar():
            self.b_salvar.setEnabled(False)
            self.b_arq.setEnabled(False)
            self.hint.setText("Sem o GRIDCO_SQL_TOKEN nesta máquina: dá para ver e ajustar, "
                              "mas não para salvar. Peça o token ao Levi.")

    # ── etiquetas ──
    def set_catalogo_etiquetas(self, itens):
        """O catálogo do Fracttal. Sem ele o PCM não tem o que escolher, mas as etiquetas já
        gravadas continuam aparecendo — o tema guarda o NOME, não o id."""
        self._etq_cat = [str(x.get("description") or "").strip()
                         for x in (itens or []) if str(x.get("description") or "").strip()]
        self._encher_cb_etq()

    def _encher_cb_etq(self):
        postas = {x.upper() for x in self._etqs}
        self.cb_etq.blockSignals(True)
        self.cb_etq.clear()
        self.cb_etq.addItem("+ adicionar etiqueta", None)
        for nome in sorted(self._etq_cat):
            if nome.upper() not in postas:
                self.cb_etq.addItem(nome, nome)
        self.cb_etq.setCurrentIndex(0)
        self.cb_etq.blockSignals(False)

    def _add_etq(self, i):
        nome = self.cb_etq.itemData(i)
        if not nome:
            return
        self._etqs.append(nome)
        self._marcar_sujo()
        self._pintar_etqs()

    def _pintar_etqs(self):
        _esvaziar(self.fila_etq)
        for nome in self._etqs:
            c = QPushButton("%s  ×" % nome)
            c.setObjectName("chipEtq")
            c.setCursor(Qt.CursorShape.PointingHandCursor)
            c.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            c.clicked.connect(lambda _=False, n=nome: self._tirar_etq(n))
            self.fila_etq.insertWidget(self.fila_etq.count() - 1, c)
        self._encher_cb_etq()

    def _tirar_etq(self, nome):
        self._etqs = [x for x in self._etqs if x != nome]
        self._marcar_sujo()
        self._pintar_etqs()

    def set_tipos_de_ativo(self, assets):
        """Enche o combo de tipo com os tipos que EXISTEM no cadastro, do mais comum ao menos.

        Ordenar por frequência não é enfeite: "Estrutura Trackers" (6.909 ativos) e "Inversor"
        (2.247) são o que o PCM escolhe quase sempre, e ficam no topo em vez de perdidos numa
        lista alfabética de mais de trinta tipos."""
        import collections
        c = collections.Counter(a.get("tipo") for a in (assets or []) if a.get("tipo"))
        if not c:
            return
        atual = self.cb_equip.currentText()
        self.cb_equip.blockSignals(True)
        self.cb_equip.clear()
        self.cb_equip.addItem("— não filtra —")
        for tipo, n in c.most_common():
            self.cb_equip.addItem("%s  (%d)" % (tipo, n), tipo)
        self.cb_equip.blockSignals(False)
        i = self.cb_equip.findText(atual)
        self.cb_equip.setCurrentIndex(i if i > 0 else 0)

    def _equip_atual(self):
        """O tipo escolhido, SEM a contagem entre parênteses — é ele que vai para o banco."""
        i = self.cb_equip.currentIndex()
        return str(self.cb_equip.itemData(i) or "") if i > 0 else ""

    # ── carga ──
    def carregar_inicial(self, forcar=False):
        # OS TIPOS SAEM DO CADASTRO, e a tela busca sozinha se ninguém entregou. Antes dependia
        # de a aba já ter os ativos carregados; quem abria Temas antes disso via o combo de tipo
        # de equipamento com uma opção só — o "não tem a opção tipo de equipamento" de 04/09.
        if self.cb_equip.count() <= 1:
            try:
                import api
                self.set_tipos_de_ativo(api.load_assets_cached() or [])
            except Exception:
                pass
        if self._itens and not forcar:
            return
        self.hint.setText("carregando temas…")
        self._w = ApiWorker(ts.carregar, None, True)
        self._w.ok.connect(self._set_itens)
        self._w.erro.connect(self._erro)
        self._w.start()

    @slot_seguro
    def _set_itens(self, itens):
        self._w = None
        self.hint.setText("")
        self._itens = list(itens or [])
        self._pintar_lista()
        if self._itens and self._sel is None:
            self._selecionar(self._itens[0])

    @slot_seguro
    def _erro(self, m):
        self._w = None
        self.hint.setText("Erro ao carregar do banco: %s — mostrando os temas do app." % m)
        self._itens = ts.da_semente()
        self._pintar_lista()

    def _pintar_lista(self):
        termo = (self.ed_busca.text() or "").strip().lower()
        _esvaziar(self.lista)
        self._cels = []
        vis = [t for t in self._itens
               if not termo or termo in ((t.get("nome") or "") + " " + t["chave"]).lower()]
        for t in vis:
            c = _Celula(t, self._selecionar)
            c.marcar(self._sel is not None and t["chave"] == self._sel.get("chave"))
            self.lista.insertWidget(self.lista.count() - 1, c)
            self._cels.append(c)
        ativos = sum(1 for t in self._itens if not t.get("arquivado"))
        sem = sum(1 for t in self._itens
                  if not t.get("arquivado") and not (t.get("subtarefas") or []))
        self.lbl_cont.setText("<b style='color:%s'>%d</b> temas" % (GREEN, ativos)
                              + ("<span style='color:%s'> · %d sem checklist</span>"
                                 % (MUTED, sem) if sem else ""))

    # ── seleção ──
    def _selecionar(self, t):
        self._sel = t
        for c in self._cels:
            c.marcar(t is not None and c.dados.get("chave") == t.get("chave"))
        if not t:
            self.lbl_tit.setText("Escolha um tema à esquerda.")
            self.lbl_uso.setText("")
            self._habilitar(False)
            return
        self.lbl_tit.setText(t.get("nome") or t["chave"])
        self.lbl_uso.setText(
            "Usado em %s solicitações. O que estiver aqui é o que a OS vai levar quando o PCM "
            "escolher este tema. Editar não mexe em OS já criada." % (t.get("solicitacoes") or 0))
        self.ed_nome.setText(t.get("nome") or "")
        self.ed_motivo.setText(t.get("motivo") or "")
        eq = (t.get("tipo_equipamento") or "").strip()
        j = next((k for k in range(self.cb_equip.count())
                  if self.cb_equip.itemData(k) == eq), 0) if eq else 0
        self.cb_equip.setCurrentIndex(j)
        i = self.cb_tipo_os.findText(t.get("tipo_os") or "")
        self.cb_tipo_os.setCurrentIndex(i if i >= 0 else 0)
        i = self.cb_c1.findText(t.get("classif1") or "")
        self.cb_c1.setCurrentIndex(i if i >= 0 else 0)
        self.editor.set_itens(list(t.get("subtarefas") or []))
        # A MESMA regra da Fila (`ts.etiquetas_efetivas`). Sem isto, tema sem o campo aparecia
        # aqui com lista vazia enquanto a Fila punha a PERFORMANCE nele — o PCM não via, e não
        # conseguia tirar, uma etiqueta que estava sendo aplicada.
        self._etqs = ts.etiquetas_efetivas(dict(t, chave=t.get("chave") or ""))
        self._pintar_etqs()
        self.b_arq.setText("Desarquivar" if t.get("arquivado") else "Arquivar")
        self._habilitar(True)
        self._sync_filtro()
        self._sujo = False
        self.hint.setText("")

    def _marcar_sujo(self):
        self._sujo = True

    def _novo(self):
        base = {"chave": "", "nome": "", "motivo": "", "classif1": "", "tipo_os": "",
                "tipo_equipamento": "", "solicitacoes": 0, "arquivado": False,
                "subtarefas": [], "etiquetas": []}
        self._itens.insert(0, base)
        self._pintar_lista()
        self._selecionar(base)
        self.ed_nome.setFocus()

    # ── gravação ──
    def _chave_de(self, nome):
        """A chave nasce do NOME, sem acento e sem espaço. É ela que a observação da solicitação
        carrega, então precisa ser estável e legível — `inversor_inspecao`, não um número."""
        import unicodedata
        t = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
        t = "".join(c if c.isalnum() else "_" for c in t.lower())
        while "__" in t:
            t = t.replace("__", "_")
        return t.strip("_")[:48]

    def _salvar(self):
        t = self._sel
        if not t:
            return
        nome = (self.ed_nome.text() or "").strip()
        if not nome:
            QMessageBox.warning(self, "Temas", "O tema precisa de um nome.")
            return
        chave = t.get("chave") or self._chave_de(nome)
        if not chave:
            QMessageBox.warning(self, "Temas", "Não consegui gerar a chave a partir desse nome.")
            return
        if not t.get("chave") and any(x.get("chave") == chave for x in self._itens):
            QMessageBox.warning(self, "Temas", "Já existe um tema com esse nome.")
            return
        novo = dict(t, chave=chave, nome=nome,
                    motivo=(self.ed_motivo.text() or "").strip(),
                    classif1=self.cb_c1.currentText(),
                    tipo_os=self.cb_tipo_os.currentText(),
                    tipo_equipamento=self._equip_atual(),
                    subtarefas=self.editor.itens(),
                    etiquetas=list(self._etqs))
        self.b_salvar.setEnabled(False)
        self.hint.setText("salvando…")
        self._w = ApiWorker(ts.salvar, novo)
        self._w.ok.connect(lambda *_: self._salvou(novo))
        self._w.erro.connect(self._erro_salvar)
        self._w.start()

    @slot_seguro
    def _salvou(self, novo):
        self._w = None
        self._sujo = False
        self.b_salvar.setEnabled(True)
        self.hint.setText("salvo — vale para as próximas OS")
        ts.aplicar_no_spec()          # a Solicitação e a Fila passam a ver o tema novo na hora
        self.carregar_inicial(forcar=True)
        QTimer.singleShot(4000, lambda: self.hint.setText(""))

    @slot_seguro
    def _erro_salvar(self, m):
        self._w = None
        self.b_salvar.setEnabled(True)
        self.hint.setText("Não salvou: %s" % m)

    def _arquivar(self):
        t = self._sel
        if not t or not t.get("chave"):
            return
        indo = not t.get("arquivado")
        if indo and QMessageBox.question(
                self, "Arquivar tema",
                "Arquivar “%s”?\n\nEle some da lista de escolha da Solicitação e da Fila. "
                "As OS que já nasceram com ele não mudam — cada OS guarda as subtarefas "
                "copiadas no momento em que foi criada." % (t.get("nome") or t["chave"]),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self.hint.setText("arquivando…" if indo else "desarquivando…")
        self._w = ApiWorker(ts.arquivar, t["chave"], indo)
        self._w.ok.connect(lambda *_: self._salvou(t))
        self._w.erro.connect(self._erro_salvar)
        self._w.start()
