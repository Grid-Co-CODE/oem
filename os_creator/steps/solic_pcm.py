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
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QScrollArea, QFrame, QMessageBox, QComboBox,
                             QGridLayout, QLineEdit)

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
PENDENTE, ANDAMENTO, FINALIZADA = "pendente", "andamento", "finalizada"
_CANCELADAS = {"cancelada", "rejeitada"}


def coluna_de(s: dict) -> str:
    """Em que coluna do painel esta solicitação cai.

    Não usa id_status de propósito: a solicitação criada pelo app volta como OPEN_STATUS (1) e a
    criada pela web do Fracttal, como REQUEST_TODO (7) — as duas pendentes. O que separa de
    verdade é ter ou não OS vinculada."""
    st = (s.get("status") or "").strip().lower()
    if any(c in st for c in _CANCELADAS):
        return FINALIZADA
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
        st.setStyleSheet(f"color:{MUTED};font-size:11px;")
        topo.addWidget(st)
        v.addLayout(topo)

        ativo = QLabel(str(s.get("ativo") or "—"))
        ativo.setStyleSheet(f"color:{MUTED};font-size:12px;")
        ativo.setWordWrap(True)
        v.addWidget(ativo)

        d = QLabel(str(s.get("descricao") or "—"))
        d.setStyleSheet(f"color:{TEXT};font-size:13px;")
        d.setWordWrap(True)
        v.addWidget(d)

        rod = QHBoxLayout()
        quem = QLabel(f"{s.get('criado_por') or '—'} · {(s.get('data') or '')[:10]}")
        quem.setStyleSheet(f"color:{MUTED};font-size:11px;")
        rod.addWidget(quem)
        rod.addStretch(1)
        # O TEMA é o que o Fracttal não mostra — e é a razão de existir este painel.
        tema = (sp.parse(s.get("observacao")) or {}).get("tema") or ""
        if tema:
            nome = (sp.TEMAS.get(tema) or {}).get("nome") or tema
            t = QLabel(nome)
            t.setStyleSheet(f"color:{GREEN};font-size:11px;font-weight:600;")
            rod.addWidget(t)
        elif on_analisar:
            t = QLabel("sem tema")
            t.setStyleSheet(f"color:{MUTED};font-size:11px;")
            rod.addWidget(t)
        elif s.get("os_folio"):
            t = QLabel(f"OS {s['os_folio']}")
            t.setStyleSheet(f"color:{MUTED};font-size:11px;")
            rod.addWidget(t)
        v.addLayout(rod)

        if on_analisar:
            b = QPushButton("Analisar")
            b.setObjectName("btnPrimary")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: on_analisar(s))
            v.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)


class _Painel(QWidget):
    """Kanban de três colunas. Só a coluna Pendentes tem ação — nas outras duas quem trabalha é
    a OS, não a solicitação, e duplicar ação criaria dois lugares para a mesma coisa."""

    def __init__(self, on_analisar):
        super().__init__()
        self._on_analisar = on_analisar
        self._rows = []
        self._w = None
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        topo = QHBoxLayout()
        self.lbl = QLabel("carregando solicitações…")
        self.lbl.setStyleSheet(f"color:{MUTED};font-size:12.5px;")
        topo.addWidget(self.lbl)
        topo.addStretch(1)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Filtrar por usina, ativo ou texto…")
        self.busca.setFixedWidth(260)
        self.busca.textChanged.connect(self._pintar)
        topo.addWidget(self.busca)
        b = QPushButton("Atualizar")
        b.setObjectName("btnGhost")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.carregar(True))
        topo.addWidget(b)
        v.addLayout(topo)

        self.cols = {}
        grade = QHBoxLayout()
        grade.setSpacing(12)
        for chave, titulo in ((PENDENTE, "Pendentes"), (ANDAMENTO, "Em andamento"),
                              (FINALIZADA, "Finalizadas")):
            box = QWidget()
            bv = QVBoxLayout(box)
            bv.setContentsMargins(0, 0, 0, 0)
            bv.setSpacing(8)
            cab = QLabel(titulo)
            cab.setStyleSheet(f"color:{TEXT};font-weight:600;font-size:14px;")
            bv.addWidget(cab)
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
            self.cols[chave] = (cab, titulo, iv)
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
        for s in self._rows:
            if q and q not in (" ".join(str(s.get(k) or "") for k in
                                        ("usina", "ativo", "descricao", "criado_por")).lower()):
                continue
            por[coluna_de(s)].append(s)
        for chave, (cab, titulo, iv) in self.cols.items():
            while iv.count() > 1:                      # mantém o addStretch do fim
                it = iv.takeAt(0)
                w = it.widget()
                if w:                                  # takeAt devolve espaçador sem widget
                    w.setParent(None)
                    w.deleteLater()
            lista = por[chave]
            cab.setText(f"{titulo}  ({len(lista)})")
            for s in lista[:40]:
                iv.insertWidget(iv.count() - 1,
                                _Cartao(s, self._on_analisar if chave == PENDENTE else None))
        self.lbl.setText(f"{len(por[PENDENTE])} pendentes · {len(por[ANDAMENTO])} em andamento · "
                         f"{len(por[FINALIZADA])} finalizadas")


class _Fila(QWidget):
    """Fila do PCM: a lista à esquerda, o detalhe à direita, e a OS nascendo na aprovação."""

    def __init__(self, on_voltar):
        super().__init__()
        self._itens = []
        self._sel = None
        self._assets = []
        self._w = None
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        topo = QHBoxLayout()
        b = QPushButton("← Voltar ao painel")
        b.setObjectName("btnGhost")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(on_voltar)
        topo.addWidget(b)
        topo.addStretch(1)
        self.lbl_cont = QLabel("")
        self.lbl_cont.setStyleSheet(f"color:{MUTED};font-size:12.5px;")
        topo.addWidget(self.lbl_cont)
        v.addLayout(topo)

        corpo = QHBoxLayout()
        corpo.setSpacing(14)

        # esquerda: a fila
        esq = QScrollArea()
        esq.setWidgetResizable(True)
        esq.setFixedWidth(310)
        esq.setFrameShape(QScrollArea.Shape.NoFrame)
        esq.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                          "QScrollArea > QWidget > QWidget{background:transparent;}")
        inner = QWidget()
        self.lista = QVBoxLayout(inner)
        self.lista.setContentsMargins(0, 0, 6, 0)
        self.lista.setSpacing(8)
        self.lista.addStretch(1)
        esq.setWidget(inner)
        corpo.addWidget(esq)

        # direita: o detalhe
        dir_sc = QScrollArea()
        dir_sc.setWidgetResizable(True)
        dir_sc.setFrameShape(QScrollArea.Shape.NoFrame)
        dir_sc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollArea > QWidget > QWidget{background:transparent;}")
        d = QWidget()
        self.det = QVBoxLayout(d)
        self.det.setContentsMargins(0, 0, 0, 0)
        self.det.setSpacing(12)
        dir_sc.setWidget(d)
        corpo.addWidget(dir_sc, 1)
        v.addLayout(corpo, 1)

        self._montar_detalhe()

    # ── detalhe ──
    def _montar_detalhe(self):
        self.lbl_titulo = QLabel("Selecione uma solicitação na fila.")
        self.lbl_titulo.setStyleSheet(f"color:{TEXT};font-size:17px;font-weight:600;")
        self.lbl_titulo.setWordWrap(True)
        self.lbl_orig = QLabel("")
        self.lbl_orig.setStyleSheet(f"color:{MUTED};font-size:12px;")
        self.lbl_orig.setWordWrap(True)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet(f"color:{MUTED};font-size:12.5px;")
        self.lbl_meta.setWordWrap(True)
        self.lbl_sug = QLabel("")
        self.lbl_sug.setStyleSheet(f"color:{TEXT};font-size:13px;")
        self.lbl_sug.setWordWrap(True)

        self.cb_tema = QComboBox()
        self.cb_tema.addItem("— sem tema —", "")
        for chave, nome in sp.temas():
            self.cb_tema.addItem(nome, chave)
        self.cb_tema.currentIndexChanged.connect(self._pintar_subs)

        self.lbl_subs = QLabel("")
        self.lbl_subs.setStyleSheet(f"color:{TEXT};font-size:13px;")
        self.lbl_subs.setWordWrap(True)
        self.lbl_subs.setTextFormat(Qt.TextFormat.RichText)

        c = Card(1, "Solicitação")
        c.add(self.lbl_titulo)
        c.add(self.lbl_orig)
        c.add(self.lbl_meta)
        c.add(self.lbl_sug)
        self.det.addWidget(c)

        # O responsável é OBRIGATÓRIO para a OS nascer numerada (fase 2 do `clonar_os`). Vem
        # pré-selecionado com o técnico que o supervisor sugeriu — é o que fecha o ciclo do fluxo.
        self.cb_resp = QComboBox()
        self.cb_resp.addItem("— selecione —", None)

        c2 = Card(2, "Tema e subtarefas")
        c2.add(campo("Tema", self.cb_tema))
        c2.add(campo("Responsável pela OS", self.cb_resp, obrig=True))
        c2.add(self.lbl_subs)
        self.det.addWidget(c2)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.b_devolver = QPushButton("Devolver ao supervisor")
        self.b_devolver.setObjectName("btnGhost")
        self.b_devolver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_devolver.clicked.connect(self._devolver)
        self.b_aprovar = QPushButton("Aprovar e gerar OS")
        self.b_aprovar.setObjectName("btnPrimary")
        self.b_aprovar.setIcon(QIcon(icone_pix("check", GREEN_INK, 16)))
        self.b_aprovar.setIconSize(QSize(16, 16))
        self.b_aprovar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_aprovar.clicked.connect(self._aprovar)
        acoes.addWidget(self.b_devolver)
        acoes.addWidget(self.b_aprovar)
        self.det.addLayout(acoes)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.det.addWidget(self.hint, 0, Qt.AlignmentFlag.AlignRight)
        self.det.addStretch(1)
        self._habilitar(False)

    def _habilitar(self, on):
        self.b_aprovar.setEnabled(on)
        self.b_devolver.setEnabled(on)
        self.cb_tema.setEnabled(on)
        self.cb_resp.setEnabled(on)

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
        for s in self._itens:
            self.lista.insertWidget(self.lista.count() - 1, _Cartao(s, self._selecionar))
        self.lbl_cont.setText(f"{len(self._itens)} aguardando aprovação")
        self._selecionar(selecionar or (self._itens[0] if self._itens else None))

    def _selecionar(self, s):
        self._sel = s
        if not s:
            self.lbl_titulo.setText("Nada na fila.")
            self.lbl_orig.setText("")
            self.lbl_meta.setText("")
            self.lbl_sug.setText("")
            self._habilitar(False)
            self._pintar_subs()
            return
        bloco = sp.parse(s.get("observacao")) or {}
        tema = bloco.get("tema") or ""
        i = next((i for i in range(self.cb_tema.count()) if self.cb_tema.itemData(i) == tema), 0)
        self.cb_tema.blockSignals(True)
        self.cb_tema.setCurrentIndex(i)
        self.cb_tema.blockSignals(False)

        novo = sp.titulo(s.get("usina") or "", s.get("ativo") or "", tema) if tema else ""
        orig = str(s.get("descricao_full") or s.get("descricao") or "")
        self.lbl_titulo.setText(novo or orig)
        # O PCM está mudando o texto de outra pessoa — precisa ver o que está mudando.
        self.lbl_orig.setText(f"o supervisor escreveu: {orig}" if novo and novo != orig else "")
        self.lbl_meta.setText(f"Nº {s.get('id_code')} · {s.get('criado_por') or '—'} · "
                              f"{(s.get('data') or '')[:16]}\n{s.get('usina') or '—'} · "
                              f"{s.get('ativo') or '—'}")
        tec, dt = bloco.get("tecnico"), bloco.get("data")
        self.lbl_sug.setText(
            f"<b>Sugerido pelo supervisor:</b> técnico {tec or '—'} · data {dt or '—'}"
            if (tec or dt) else f"<span style='color:{MUTED}'>Sem sugestão de técnico ou data.</span>")
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
            return
        for i in range(self.cb_resp.count()):
            if self.cb_resp.itemText(i).strip().lower() == alvo:
                self.cb_resp.setCurrentIndex(i)
                return
        self.cb_resp.setCurrentIndex(0)

    def _pintar_subs(self):
        tema = self.cb_tema.currentData() or ""
        if not tema:
            self.lbl_subs.setText(
                f"<span style='color:{MUTED}'>Sem tema: a OS nasce com as 3 subtarefas da base. "
                f"Dá para aprovar assim — é pior que o ideal e melhor que hoje.</span>")
            return
        subs = sp.subtarefas(tema)
        linhas = []
        for i, s in enumerate(subs, 1):
            extra = (f" <span style='color:{GREEN}'>· anexo obrigatório</span>"
                     if s["attachments_required"] else
                     (f" <span style='color:{MUTED}'>· opcional</span>" if not s["is_required"] else ""))
            linhas.append(f"{i}. {s['description']}{extra}")
        self.lbl_subs.setText(f"<b>{len(subs)} subtarefas</b><br>" + "<br>".join(linhas))

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


class SolicPcmTab(QWidget):
    """A aba. Painel → Nova solicitação → Fila do PCM → Histórico, num stack só."""

    PAINEL, NOVA, FILA, HIST = 0, 1, 2, 3

    def __init__(self):
        super().__init__()
        self.setStyleSheet(QSS_FORM)
        self._assets = []
        self._wresp = None   # a thread precisa de dono vivo (ver steps/CLAUDE.md)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        nav = QHBoxLayout()
        nav.setContentsMargins(16, 10, 16, 0)
        nav.setSpacing(8)
        self._btns = []
        for i, rot in ((self.PAINEL, "Painel"), (self.NOVA, "Nova solicitação"),
                       (self.FILA, "Fila do PCM"), (self.HIST, "Histórico")):
            b = QPushButton(rot)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=i: self.ir(k))
            nav.addWidget(b)
            self._btns.append(b)
        nav.addStretch(1)
        v.addLayout(nav)

        self.stack = QStackedWidget()
        self.painel = _Painel(self._analisar)
        self.nova = SolicitacaoTab()
        self.fila = _Fila(lambda: self.ir(self.PAINEL))
        self.hist = HistoricoSolic()
        for w in (self.painel, self.nova, self.fila, self.hist):
            self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        self.ir(self.PAINEL)

    def ir(self, i):
        self.stack.setCurrentIndex(i)
        for k, b in enumerate(self._btns):
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
