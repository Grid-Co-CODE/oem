"""Aba 'Criar Solicitação' — cria uma Solicitação de Serviço (work request) no Fracttal via
requests.requests_insert. Cascata cliente→usina→tipo→ativo (cliente e usina PESQUISÁVEIS; tipo
com os MESMOS filtros do Criar OS — ALLOWED_TIPOS), + comentários, data, urgência e classificações.
Layout redesenhado (08/07): 4 cards compactos (Descrição · Ativo · Detalhes · Classificação) no estilo
dark premium (steps/ui.py), cards 3 e 4 lado a lado. NENHUMA regra/validação/ID/API mudou."""
from PyQt6.QtCore import Qt, QDateTime, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QGridLayout, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QTextEdit, QLineEdit, QDateTimeEdit, QCheckBox, QPushButton,
                             QMessageBox, QScrollArea)
import api
import solic_spec as sp
from workers import ApiWorker
from steps.step1 import ALLOWED_TIPOS          # mesmos tipos de equipamento do Criar OS
from steps.searchcombo import tornar_pesquisavel
from steps.subtarefas_edit import EditorSubtarefas
from steps.light import Bloco, Valor, ValorObs, grade, QSS as QSS_LIGHT
from steps.ui import QSS_FORM, Card, Dica, campo, Linha, icone_pix, GREEN, GREEN_INK, MUTED

CLIENTES_OCULTOS = {"almoxarifado", "teste - pa"}
_SEL = "— selecione —"
_TODOS_TIPOS = "Todos os tipos"


class SolicitacaoTab(QWidget):
    def __init__(self):
        super().__init__()
        self._assets = []
        self._types = None
        self._wt = None
        self._wc = None
        self._wresp = None
        # QSS_LIGHT depois do QSS_FORM: as regras do light são mais específicas
        # (#objectName) e vencem as genéricas do formulário antigo
        self.setStyleSheet(QSS_FORM + QSS_LIGHT)              # visual novo só nesta tela (sobrepõe o DARK_QSS global)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # nunca rola de lado
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 14, 20, 18)
        lay.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ── topo: ação secundária (várias) + nota de obrigatórios ──
        top = QHBoxLayout()
        b_varias = QPushButton("Várias solicitações")
        b_varias.setObjectName("btnGhost")
        b_varias.setIcon(QIcon(icone_pix("layers", "#d4dae6", 15))); b_varias.setIconSize(QSize(15, 15))
        b_varias.setToolTip("Criar uma solicitação para CADA ativo marcado, de uma só vez")
        b_varias.setCursor(Qt.CursorShape.PointingHandCursor)
        b_varias.clicked.connect(self._abrir_varias)
        top.addWidget(b_varias)
        top.addStretch(1)
        req = QLabel(f"<span style='color:{GREEN};font-weight:700'>*</span> Campos obrigatórios")
        req.setObjectName("uiReqnote")
        top.addWidget(req)
        lay.addLayout(top)

        # ── Bloco 1 — Tema e título ──
        # O TEMA é a mudança central desta tela. Medido em 02/09 sobre 2.500 solicitações: 163
        # títulos se repetem literalmente cobrindo 24,5% delas (padronização feita na mão, por
        # copiar e colar) e só 33,2% seguem o padrão [Usina][Ativo] - Motivo. Escolher o tema
        # resolve os dois de uma vez, e ainda desce a Classificação 1 e as subtarefas da OS.
        self.cb_tema = QComboBox()
        self.cb_tema.addItem("— sem tema —", "")
        for chave, nome in sp.temas():
            self.cb_tema.addItem(nome, chave)
        self.cb_tema.currentIndexChanged.connect(self._on_tema)

        self.desc = QTextEdit()
        self.desc.setPlaceholderText("Título do problema / solicitação")
        self.desc.textChanged.connect(self._marcar_titulo_manual)
        self._titulo_auto = ""          # último título que ESTA tela gerou (ver _sync_titulo)

        # LOGICA LIGHT (aprovada pelo Levi em 03/09, depois de duas rodadas de simulação): cada
        # bloco tem borda e fundo próprios, mas por dentro o campo é RÓTULO + VALOR COMO TEXTO,
        # que vira campo ao clique. Quase tudo aqui já vem respondido pelo tema e pela cascata de
        # ativos — a pessoa confere mais do que digita, e um formulário de caixas de 40 px dizia
        # o contrário.
        self.v_tema = Valor("Tema", self.cb_tema,
                            dica="O tema preenche o título no padrão, sugere a classificação e "
                                 "define as subtarefas que a OS vai pedir. Sem tema, a OS nasce "
                                 "só com a base.")
        # o título é o único campo maior: 2 px acima dos outros valores, porque é o que o PCM lê
        # primeiro — e foi o tamanho que o Levi escolheu na simulação
        self.v_titulo = Valor("Título", self.desc, obrig=True, grande=True,
                              vazio="Título do problema / solicitação",
                              dica="preenchido pelo tema no padrão [Usina][Ativo] - Motivo; dá "
                                   "para reescrever")
        b1 = Bloco(1, "Tema e título")
        b1.add(grade([self.v_tema, None, None]))
        b1.add(self.v_titulo)
        lay.addWidget(b1)

        # ── Bloco 2 — Ativo (cascata) ──
        self.cb_cliente = QComboBox(); tornar_pesquisavel(self.cb_cliente)   # busca + placeholder cinza
        self.cb_cliente.currentIndexChanged.connect(self._on_cli)
        self.cb_usina = QComboBox(); tornar_pesquisavel(self.cb_usina)
        self.cb_usina.currentIndexChanged.connect(self._on_usi)
        self.cb_tipo = QComboBox(); self.cb_tipo.currentIndexChanged.connect(self._refresh_ativos)
        self.busca = QLineEdit(); self.busca.setPlaceholderText("Pesquisar ativo por código ou nome…")
        self.busca.addAction(QIcon(icone_pix("search", MUTED, 15)), QLineEdit.ActionPosition.LeadingPosition)
        self.busca.textChanged.connect(self._refresh_ativos)
        self.cb_ativo = QComboBox()
        # o título depende de usina + ativo, então trocar o ativo o regenera (respeitando o
        # título escrito à mão, que o `_sync_titulo` protege)
        self.cb_ativo.currentIndexChanged.connect(self._sync_titulo)

        self.v_cliente = Valor("Cliente", self.cb_cliente, obrig=True)
        self.v_usina = Valor("Usina", self.cb_usina, obrig=True)
        self.v_tipo = Valor("Tipo de equipamento", self.cb_tipo, obrig=True)
        self.v_ativo = Valor("Ativo", self.cb_ativo, obrig=True)
        # a busca é a ÚNICA exceção da tela: fica sempre aberta, porque o filtro é por digitação
        # e um campo que só aparece depois do clique não convida a digitar
        self.v_busca = Valor("Pesquisar ativo", self.busca, aberto=True)
        b2 = Bloco(2, "Ativo relacionado")
        b2.add(grade([self.v_cliente, self.v_usina, self.v_tipo,
                      self.v_ativo, self.v_busca, None]))
        lay.addWidget(b2)

        # ── Bloco 3 — Detalhes do incidente ──
        self.data = QDateTimeEdit(QDateTime.currentDateTime())
        self.data.setDisplayFormat("dd/MM/yyyy HH:mm"); self.data.setCalendarPopup(True)
        self.urgente = QCheckBox("É urgente?")
        self.urgente.setObjectName("lgChk")
        self.urgente.setCursor(Qt.CursorShape.PointingHandCursor)
        self.coment = QTextEdit()
        self.coment.setPlaceholderText("Informações adicionais sobre o incidente…")
        # Técnico e data sugerida: SUGESTÃO do supervisor para o PCM. A solicitação do Fracttal
        # NÃO tem campo de técnico — verificado nas 2.500: todo campo de pessoa é de quem criou ou
        # de quem mudou o status. Então isso viaja num bloco parseável na observação, o mesmo
        # recurso que o `perf_spec` usa para a prioridade da Performance.
        self.cb_tecnico = QComboBox(); tornar_pesquisavel(self.cb_tecnico)
        self.data_prev = QDateTimeEdit(QDateTime.currentDateTime().addDays(2))
        # data E hora: "amanha" nao diz se e antes ou depois da parada, e o PCM programa por hora
        self.data_prev.setDisplayFormat("dd/MM/yyyy HH:mm"); self.data_prev.setCalendarPopup(True)

        self.v_data = Valor("Data do incidente", self.data, obrig=True)
        self.v_data_prev = Valor("Data sugerida", self.data_prev)
        self.v_tecnico = Valor("Técnico sugerido", self.cb_tecnico)
        urg = QWidget()
        # "uiGroup" e o objectName que o QSS_FORM deixa transparente. Sem ele o widget casa com a
        # regra generica de QWidget do DARK_QSS (#090d18) e pinta um retangulo escuro dentro do
        # bloco, que e #121a2b — foi o que apareceu no primeiro render.
        urg.setObjectName("uiGroup")
        uv = QVBoxLayout(urg); uv.setContentsMargins(0, 0, 0, 0); uv.setSpacing(3)
        ur = QLabel("URGÊNCIA"); ur.setObjectName("lgRotulo")
        uv.addWidget(ur); uv.addWidget(self.urgente)
        self.v_obs = ValorObs("Observação", self.coment)
        b3 = Bloco(3, "Detalhes do incidente")
        # arranjo pedido pelo Levi: urgência ao lado da data do incidente; data sugerida logo
        # abaixo dela, com o técnico sugerido à direita
        b3.add(grade([self.v_data, urg,
                      self.v_data_prev, self.v_tecnico], cols=2, hspace=32))
        b3.add(self.v_obs)

        # ── Bloco 4 — Classificação ──
        self.cb_grupo = QComboBox()
        self.cb_c1 = QComboBox()
        self.cb_c2 = QComboBox()
        self.v_grupo = Valor("Grupo", self.cb_grupo, obrig=True)
        self.v_c1 = Valor("Classificação 1", self.cb_c1, obrig=True)
        self.v_c2 = Valor("Classificação 2", self.cb_c2, vazio="— nenhuma —")
        self.lbl_classif_dica = QLabel("")
        self.lbl_classif_dica.setObjectName("lgDica")
        self.lbl_classif_dica.setWordWrap(True)
        self.lbl_classif_dica.setMinimumWidth(1)
        b4 = Bloco(4, "Classificação")
        b4.add(grade([self.v_grupo, self.v_c1, self.v_c2], cols=1))
        b4.add(self.lbl_classif_dica)

        # blocos 3 e 4 lado a lado: o 3 tem duas colunas de campos e o 4 tem uma, daí a
        # proporção. Abaixo de 1080 px eles empilham.
        self.par34 = QWidget()
        g34 = QGridLayout(self.par34)
        g34.setContentsMargins(0, 0, 0, 0)
        g34.setHorizontalSpacing(14)
        g34.setVerticalSpacing(14)
        g34.addWidget(b3, 0, 0)
        g34.addWidget(b4, 0, 1)
        g34.setColumnStretch(0, 155)
        g34.setColumnStretch(1, 100)
        lay.addWidget(self.par34)

        # ── Bloco 5 — o que a OS vai pedir ──
        # O supervisor vê AGORA o que está pedindo, e o PCM vê a mesma lista antes de aprovar. Sem
        # isso a subtarefa só aparece depois da OS criada — e a API do Fracttal NÃO edita OS já
        # criada, então errar ali custa uma OS cancelada.
        self.lbl_subs = QLabel()          # continua existindo p/ quem lia o resumo em texto
        self.lbl_subs.setVisible(False)
        self.editor_subs = EditorSubtarefas(
            "Sem tema: a OS nasce com as 3 subtarefas da base (descrição, registro fotográfico e "
            "pendência). Escolher um tema acrescenta o roteiro do serviço — e você pode editar.")
        self.card_subs = Bloco(5, "O que a OS vai pedir")
        self.card_subs.add(self.editor_subs)
        lay.addWidget(self.card_subs)
        self._sync_tema()                      # pinta o estado inicial (sem tema)

        # ── ações ──
        acts = QHBoxLayout(); acts.setContentsMargins(0, 2, 0, 0); acts.setSpacing(10); acts.addStretch(1)
        b_limpar = QPushButton("Limpar"); b_limpar.setObjectName("btnGhost")
        b_limpar.setIcon(QIcon(icone_pix("x", "#d4dae6", 15))); b_limpar.setIconSize(QSize(15, 15))
        b_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        b_limpar.setToolTip("Limpar os campos do formulário")
        b_limpar.clicked.connect(self.reset)
        self.btn = QPushButton("Criar Solicitação"); self.btn.setObjectName("btnPrimary")
        self.btn.setIcon(QIcon(icone_pix("send", GREEN_INK, 16))); self.btn.setIconSize(QSize(16, 16))
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self._criar)
        acts.addWidget(b_limpar); acts.addWidget(self.btn)
        lay.addLayout(acts)
        self.hint = QLabel(""); self.hint.setObjectName("hint")
        lay.addWidget(self.hint, 0, Qt.AlignmentFlag.AlignRight)
        lay.addStretch(1)

    # ── dados ──
    def set_assets(self, assets):
        self._assets = assets or []
        cls = sorted({a["cliente"] for a in self._assets
                      if a.get("cliente") and a["cliente"].strip().lower() not in CLIENTES_OCULTOS})
        self.cb_cliente.blockSignals(True)
        self.cb_cliente.clear(); self.cb_cliente.addItem(_SEL); self.cb_cliente.addItems(cls)
        self.cb_cliente.setCurrentIndex(0)
        self.cb_cliente.blockSignals(False)
        self._on_cli()

    def prefill_por_code(self, code):
        """Pré-seleciona cliente → usina → ativo a partir do code de um ativo (ex.: vindo de uma OS).
        Devolve True se conseguiu selecionar o ativo. Os tipos da classificação não são tocados."""
        code = (code or "").strip()
        asset = next((a for a in self._assets if a.get("code") == code), None)
        if not asset:
            return False
        cli, usi = asset.get("cliente"), asset.get("usina")
        ic = self.cb_cliente.findText(cli) if cli else -1
        if ic > 0:
            self.cb_cliente.setCurrentIndex(ic)        # dispara _on_cli → popula usinas
        iu = self.cb_usina.findText(usi) if usi else -1
        if iu > 0:
            self.cb_usina.setCurrentIndex(iu)          # dispara _on_usi → popula tipo + ativos
        if self.cb_tipo.count():
            self.cb_tipo.setCurrentIndex(0)            # "Todos os tipos" p/ não esconder o ativo
        self._refresh_ativos()
        for k in range(self.cb_ativo.count()):
            a = self.cb_ativo.itemData(k)
            if isinstance(a, dict) and a.get("code") == code:
                self.cb_ativo.setCurrentIndex(k)
                return True
        return False

    def _abrir_varias(self):
        """Abre o diálogo 'Várias Solicitações' (uma por ativo marcado)."""
        from steps.varias_solic import abrir_varias_solic
        abrir_varias_solic(self.window())

    def carregar_inicial(self):
        """1ª abertura da aba → busca as listas (grupo/classificações)."""
        if self._types is None and self._wt is None:
            self.hint.setText("carregando listas…")
            self._wt = ApiWorker(api.get_request_types)
            self._wt.ok.connect(self._set_types)
            self._wt.erro.connect(lambda m: self.hint.setText("Erro ao carregar as listas: " + m))
            self._wt.start()
        if self.cb_tecnico.count() <= 1 and self._wresp is None:
            # A lista de técnicos é ACESSÓRIA: se falhar, a tela segue funcionando sem sugestão.
            # Por isso o erro só apaga o placeholder, em vez de aparecer como falha da tela.
            self._wresp = ApiWorker(api.get_responsaveis)
            self._wresp.ok.connect(self._set_tecnicos)
            self._wresp.erro.connect(lambda *_: setattr(self, "_wresp", None))
            self._wresp.start()

    def _set_tecnicos(self, lista):
        self._wresp = None
        self.cb_tecnico.blockSignals(True)
        self.cb_tecnico.clear()
        self.cb_tecnico.addItem(_SEL, None)
        for p in (lista or []):
            self.cb_tecnico.addItem(p.get("name") or "", p.get("id_personnel"))
        self.cb_tecnico.setCurrentIndex(0)
        self.cb_tecnico.blockSignals(False)

    def _set_types(self, t):
        self._wt = None
        self._types = t or {}
        self.hint.setText("")

        def fill(cb, items):
            cb.clear()
            cb.addItem(_SEL, None)
            for it in items:
                cb.addItem(it["description"], it["id"])
        fill(self.cb_grupo, self._types.get("grupo", []))
        fill(self.cb_c1, self._types.get("classif1", []))
        fill(self.cb_c2, self._types.get("classif2", []))

    # ── cascata do ativo (cliente/usina resolvidos por texto — robusto ao combo editável) ──
    def _cli(self):
        t = self.cb_cliente.currentText().strip()
        return t if (t and t != _SEL and self.cb_cliente.findText(t) > 0) else None

    def _usi(self):
        t = self.cb_usina.currentText().strip()
        return t if (t and t != _SEL and self.cb_usina.findText(t) > 0) else None

    def _on_cli(self):
        cli = self._cli()
        us = sorted({a["usina"] for a in self._assets if a.get("cliente") == cli and a.get("usina")}) if cli else []
        self.cb_usina.blockSignals(True)
        self.cb_usina.clear(); self.cb_usina.addItem(_SEL); self.cb_usina.addItems(us)
        self.cb_usina.setCurrentIndex(0)
        self.cb_usina.setEnabled(bool(us))
        self.cb_usina.blockSignals(False)
        self._on_usi()

    def _on_usi(self):
        cli, usi = self._cli(), self._usi()
        # tipos com a MESMA régua do Criar OS (só ALLOWED_TIPOS presentes na usina)
        tipos = sorted({a.get("tipo") for a in self._assets
                        if a.get("cliente") == cli and a.get("usina") == usi
                        and a.get("tipo") in ALLOWED_TIPOS}) if usi else []
        self.cb_tipo.blockSignals(True)
        self.cb_tipo.clear(); self.cb_tipo.addItem(_TODOS_TIPOS); self.cb_tipo.addItems(tipos)
        self.cb_tipo.setEnabled(bool(tipos))
        self.cb_tipo.blockSignals(False)
        self._refresh_ativos()

    def _refresh_ativos(self):
        """Popula o Ativo — só ALLOWED_TIPOS (igual ao Criar OS) + filtro de tipo + busca textual."""
        cli, usi = self._cli(), self._usi()
        tipo = self.cb_tipo.currentText() if self.cb_tipo.currentIndex() > 0 else None
        txt = (self.busca.text() or "").strip().lower()
        self.cb_ativo.clear(); self.cb_ativo.addItem(_SEL, None)
        if not usi:
            return
        for a in sorted([x for x in self._assets if x.get("cliente") == cli and x.get("usina") == usi],
                        key=lambda x: x["label"]):
            if a.get("tipo") not in ALLOWED_TIPOS:
                continue
            if tipo and a.get("tipo") != tipo:
                continue
            if txt and txt not in a["label"].lower():
                continue
            self.cb_ativo.addItem(a["label"], a)

    # ── criar ──
    # ── tema ─────────────────────────────────────────────────────────────────
    def _marcar_titulo_manual(self):
        """Se o texto no campo não é mais o que ESTA tela gerou, o supervisor digitou o dele.

        Sem essa marca, trocar o tema apagaria um título escrito à mão — que é o pior tipo de
        automação: a que desfaz trabalho de gente sem avisar."""
        if self.desc.toPlainText().strip() != self._titulo_auto:
            self._titulo_auto = None            # None = título é do usuário, não mexer

    def _on_tema(self):
        self._sync_tema()
        self._sync_titulo()
        self._sugerir_classificacao()

    def _atualizar_valores(self):
        """Reavisa os rótulos depois de a tela mexer nos combos por código.

        Sem isto o valor mostrado ficaria congelado no que estava antes: a cascata de ativos, o
        prefill do deep link e o `reset` trocam o índice do combo sem passar pelo clique da
        pessoa, e o rótulo não tem como saber sozinho."""
        for v in (getattr(self, n, None) for n in
                  ("v_tema", "v_titulo", "v_cliente", "v_usina", "v_tipo", "v_ativo",
                   "v_data", "v_data_prev", "v_tecnico", "v_obs", "v_grupo", "v_c1", "v_c2")):
            if v is not None:
                v.atualizar()

    def _sync_titulo(self):
        """Regenera o título a partir do tema + usina + ativo. Só quando o campo está vazio ou
        contém exatamente o título que esta tela gerou antes."""
        tema = self.cb_tema.currentData() or ""
        atual = self.desc.toPlainText().strip()
        if not tema or (atual and self._titulo_auto is None):
            return
        asset = self.cb_ativo.currentData() or {}
        novo = sp.titulo(self._usi() or "", (asset.get("description") or "").strip(), tema)
        if not novo:
            return
        self.desc.blockSignals(True)            # não disparar _marcar_titulo_manual na própria escrita
        self.desc.setPlainText(novo)
        self.desc.blockSignals(False)
        self._titulo_auto = novo

    def _sugerir_classificacao(self):
        """Desce a Classificação 1 do tema. É o conserto do campo obrigatório: medido nas 2.500,
        ele mistura a escala binária (39,7%), a de severidade (51,6%) e valores fora de escala
        (8,6%) — escolher no menu é escolher entre réguas que não se comparam."""
        tema = self.cb_tema.currentData() or ""
        if not tema or not self.cb_c1.count():
            return
        alvo = (sp.classificacao(tema).get("classif1") or "").strip().lower()
        if not alvo:
            return
        for i in range(self.cb_c1.count()):
            if self.cb_c1.itemText(i).strip().lower() == alvo:
                self.cb_c1.setCurrentIndex(i)
                return

    def _sync_tema(self):
        """Carrega no editor as subtarefas do tema — e a partir daí quem manda é o editor."""
        tema = self.cb_tema.currentData() or ""
        self.editor_subs.set_itens(sp.de_api(sp.subtarefas(tema) if tema
                                             else sp.subtarefas_base()))
        cl = sp.classificacao(tema) if tema else {}
        self.lbl_classif_dica.setText(
            "sugerida pelo tema: %s · domínio %s%%" % (cl.get("classif1"), cl.get("dominio"))
            if tema and cl.get("classif1") else "")
        if not tema:
            self.lbl_subs.setText(
                f"<span style='color:{MUTED}'>Sem tema: a OS nasce com as 3 subtarefas da base "
                f"(descrição, registro fotográfico e pendência). Escolher um tema acrescenta o "
                f"roteiro do serviço.</span>")
            return
        subs = sp.subtarefas(tema)
        n_tema = len(subs) - len(sp.BASE)
        linhas = []
        for i, s in enumerate(subs, 1):
            marca = ""
            if s["attachments_required"]:
                marca = f" <span style='color:{GREEN}'>· anexo obrigatório</span>"
            elif not s["is_required"]:
                marca = f" <span style='color:{MUTED}'>· opcional</span>"
            linhas.append(f"{i}. {s['description']}{marca}")
        self.lbl_subs.setText(
            f"<b>{len(subs)} subtarefas</b> <span style='color:{MUTED}'>· {n_tema} do tema, "
            f"{len(sp.BASE)} da base</span><br>" + "<br>".join(linhas))

    def _criar(self):
        asset = self.cb_ativo.currentData()
        desc = self.desc.toPlainText().strip()
        c1 = self.cb_c1.currentData()
        if not desc:
            QMessageBox.warning(self, "Título", "O título não pode ficar em branco."); return
        if not asset:
            QMessageBox.warning(self, "Ativo", "Selecione o ativo (cliente → usina → ativo)."); return
        if not c1:
            QMessageBox.warning(self, "Classificação 1", "A Classificação 1 é obrigatória."); return
        self.btn.setEnabled(False); self.hint.setText("criando solicitação…")
        di = self.data.dateTime().toPyDateTime()   # local; create_solicitacao converte p/ UTC
        # A observação leva o relato do supervisor MAIS o bloco [PCM] com tema, técnico e data —
        # é assim que a sugestão chega à fila, já que a solicitação não tem campo para isso.
        obs = sp.observacao_com_bloco(self.coment.toPlainText(), {
            "tema": self.cb_tema.currentData() or "",
            "tecnico": self.cb_tecnico.currentText() if self.cb_tecnico.currentIndex() > 0 else "",
            "data": self.data_prev.dateTime().toString("dd/MM/yyyy HH:mm"),
            # a lista EDITADA vai junto: sem isso o ajuste do supervisor morreria aqui e o PCM
            # veria de novo a lista padrao do tema
            "subtarefas": self.editor_subs.itens(),
        })
        self._wc = ApiWorker(api.create_solicitacao, asset, desc, c1, self.cb_grupo.currentData(),
                             self.cb_c2.currentData(), obs, di,
                             self.urgente.isChecked(),
                             desc_type_1=self._txt(self.cb_c1),
                             desc_type=self._txt(self.cb_grupo),
                             desc_type_2=self._txt(self.cb_c2))
        self._wc.ok.connect(self._ok)
        self._wc.erro.connect(self._err)
        self._wc.start()

    def _txt(self, cb):
        """Texto do dropdown se houver opção real escolhida (índice 0 = '— selecione —')."""
        return cb.currentText() if cb.currentIndex() > 0 else ""

    def _ok(self, r):
        self._wc = None
        self.btn.setEnabled(True); self.hint.setText("")
        num = (r or {}).get("id_code") or "criada"
        QMessageBox.information(self, "Sucesso", f"Solicitação criada — Nº {num}.")
        self.reset()

    def _err(self, m):
        self._wc = None
        self.btn.setEnabled(True); self.hint.setText("")
        QMessageBox.critical(self, "Erro ao criar solicitação", m)

    def reset(self):
        self.desc.clear(); self.coment.clear(); self.urgente.setChecked(False)
        self.busca.blockSignals(True); self.busca.clear(); self.busca.blockSignals(False)
        self.cb_cliente.setCurrentIndex(0)
        for cb in (self.cb_grupo, self.cb_c1, self.cb_c2):
            if cb.count():
                cb.setCurrentIndex(0)
        self.data.setDateTime(QDateTime.currentDateTime())
        self.data_prev.setDateTime(QDateTime.currentDateTime().addDays(2))
        if self.cb_tecnico.count():
            self.cb_tecnico.setCurrentIndex(0)
        self.cb_tema.setCurrentIndex(0)
        self._titulo_auto = ""          # volta a aceitar título automático
        self._atualizar_valores()       # os rótulos voltam a mostrar o que os campos têm agora
        self._sync_tema()
