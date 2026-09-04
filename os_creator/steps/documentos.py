"""Documentos anexados à OS — PDF, Excel, ZIP e afins, com ABRIR e BAIXAR.

POR QUE ISTO EXISTE: antes o app listava esses anexos numa caixa de mensagem, só com o nome.
Dava para saber que o arquivo existia e nada além disso — não abria, não baixava. E pior: o
`api.get_os_anexos` classificava como IMAGEM tudo que tivesse URL (`is_image = bool(url) or …`),
e como PDF/Excel/ZIP do S3 também vêm com URL pré-assinada, eles iam para a galeria, a prévia
falhava e o arquivo sumia da tela. A classificação virou por EXTENSÃO; esta tela é o destino
de quem não é imagem.

Notas de TEXTO (anexo sem arquivo) continuam aqui, mas sem botão — não há o que baixar.
"""
import io
import os
import subprocess
import sys
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
                             QScrollArea, QWidget, QFileDialog, QMessageBox)

from workers import ApiWorker, slot_seguro

# Ícone por família de arquivo. Texto puro, sem emoji (convenção do projeto): a extensão em
# maiúscula já é o identificador mais rápido de ler numa lista.
def _ext(nome):
    return (os.path.splitext(str(nome or ""))[1] or "").lstrip(".").upper() or "ARQ"


def _baixar_bytes(url):
    """Baixa o conteúdo da URL pré-assinada. Roda em worker — nunca na thread da interface."""
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def _limpar_nome(t, padrao="arquivo"):
    """Nome de arquivo que o Windows aceita. `\\ / : * ? " < > |` são proibidos, e nome
    terminado em ponto ou espaço quebra na hora de gravar."""
    t = "".join("_" if c in '\\/:*?"<>|' else c for c in str(t or "")).strip(" .")
    return (t or padrao)[:120]


def baixar_em_massa(itens, pasta, baixar=None):
    """Grava todos os anexos em `pasta`, uma subpasta por subtarefa.

    Roda em worker — nunca na thread da interface. `baixar` é injetável para o teste rodar sem
    rede. Devolve (gravados, falhas) onde falhas é [(nome, motivo)].

    Um arquivo que falha não derruba o lote: URL pré-assinada expira, e se a décima morrer as
    outras dezenove já baixadas continuam valendo."""
    import requests
    baixar = baixar or _baixar_bytes
    gravados, falhas, usados = [], [], set()
    n_sub = {}
    for i, d in enumerate(itens or [], 1):
        if not isinstance(d, dict):
            continue
        sub = _limpar_nome(d.get("subtarefa") or "", "")
        destino = os.path.join(pasta, sub) if sub else pasta
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError as e:
            falhas.append((d.get("nome") or "anexo", str(e)))
            continue
        # a numeração é POR SUBTAREFA: dentro da pasta da subtarefa a ordem é a do roteiro,
        # e um contador global daria "07, 12, 31" dentro de uma pasta com três arquivos
        n_sub[sub] = n_sub.get(sub, 0) + 1
        k = n_sub[sub]
        if d.get("is_text") or not d.get("url"):
            txt = str(d.get("descricao") or d.get("value") or "").strip()
            if not txt:
                continue
            nome = "%02d - %s.txt" % (k, _limpar_nome(d.get("nome") or "nota", "nota"))
            cam = os.path.join(destino, nome)
            try:
                with io.open(cam, "w", encoding="utf-8") as f:
                    f.write(txt)
                gravados.append(cam)
            except OSError as e:
                falhas.append((nome, str(e)))
            continue
        base = _limpar_nome(d.get("nome") or "anexo_%d" % i)
        nome = "%02d - %s" % (k, base)
        cam = os.path.join(destino, nome)
        # dois anexos com o MESMO nome na mesma subtarefa existem de verdade (o celular manda
        # tudo como image.jpg): sem isto o segundo apagaria o primeiro em silêncio
        raiz, ext = os.path.splitext(cam)
        j = 2
        while cam.lower() in usados or os.path.exists(cam):
            cam = "%s (%d)%s" % (raiz, j, ext)
            j += 1
        usados.add(cam.lower())
        try:
            dados = baixar(d["url"])
            with open(cam, "wb") as f:
                f.write(dados)
            gravados.append(cam)
        except (OSError, requests.RequestException, KeyError, ValueError) as e:
            falhas.append((base, type(e).__name__ + ": " + str(e)[:80]))
    return gravados, falhas


class DocumentosDialog(QDialog):
    def __init__(self, parent, itens, titulo="Documentos da OS"):
        super().__init__(parent)
        from steps.ui import QSS_FORM, MUTED, TEXT, CARD, BORDER
        self._itens = [d for d in (itens or []) if isinstance(d, dict)]
        self._w = None
        self.setWindowTitle(titulo)
        self.setMinimumSize(620, 420)
        self.setStyleSheet(QSS_FORM)
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 14); v.setSpacing(12)

        t = QLabel(titulo)
        t.setStyleSheet(f"color:{TEXT};font-size:15px;font-weight:600;background:transparent;")
        v.addWidget(t)
        n_arq = sum(1 for d in self._itens if d.get("url"))
        sub = QLabel("%d arquivo(s) · %d nota(s) de texto"
                     % (n_arq, len(self._itens) - n_arq))
        sub.setStyleSheet(f"color:{MUTED};font-size:12px;background:transparent;")
        v.addWidget(sub)

        rolo = QScrollArea(); rolo.setWidgetResizable(True)
        rolo.setFrameShape(QScrollArea.Shape.NoFrame)
        rolo.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget(); rolo.setWidget(host)
        lista = QVBoxLayout(host); lista.setContentsMargins(0, 0, 6, 0); lista.setSpacing(8)
        for d in self._itens:
            lista.addWidget(self._linha(d, CARD, BORDER, TEXT, MUTED))
        lista.addStretch(1)
        v.addWidget(rolo, 1)

        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{MUTED};font-size:11.5px;background:transparent;")
        rod = QHBoxLayout(); rod.addWidget(self.hint); rod.addStretch(1)
        # BAIXAR TUDO de uma vez: numa OS de inspeção com 20 fotos, o caminho de um clique por
        # arquivo são 20 diálogos de "salvar como" (pedido do Levi, 04/09)
        self.b_todos = QPushButton("Baixar todos (%d)" % len(self._baixaveis()))
        self.b_todos.setObjectName("btnPrimary")
        self.b_todos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_todos.clicked.connect(self._baixar_todos)
        self.b_todos.setEnabled(bool(self._baixaveis()))
        rod.addWidget(self.b_todos)
        b = QPushButton("Fechar"); b.setObjectName("secondary"); b.clicked.connect(self.accept)
        rod.addWidget(b)
        v.addLayout(rod)

    def _baixaveis(self):
        """Arquivo OU nota de texto — a nota vira .txt, e é ela que costuma explicar a foto."""
        return [d for d in self._itens
                if d.get("url") or str(d.get("descricao") or d.get("value") or "").strip()]

    @slot_seguro
    def _baixar_todos(self):
        if self._w is not None:
            return
        itens = self._baixaveis()
        pasta = QFileDialog.getExistingDirectory(self, "Onde salvar os anexos")
        if not pasta:
            return
        subs = len({(d.get("subtarefa") or "") for d in itens})
        self.b_todos.setEnabled(False)
        self.hint.setText("baixando %d arquivo(s)…" % len(itens))
        self._pasta = pasta
        self._w = ApiWorker(baixar_em_massa, itens, pasta)
        self._w.ok.connect(self._massa_ok)
        self._w.erro.connect(self._massa_erro)
        self._w.start()

    @slot_seguro
    def _massa_ok(self, r):
        self._w = None
        self.b_todos.setEnabled(True)
        gravados, falhas = r
        self.hint.setText("%d arquivo(s) salvos" % len(gravados))
        msg = "%d arquivo(s) salvos em:\n%s" % (len(gravados), self._pasta)
        if falhas:
            msg += ("\n\n%d não vieram (a URL do Fracttal expira; reabrir os documentos "
                    "renova):\n" % len(falhas))
            msg += "\n".join("· %s — %s" % (n, m) for n, m in falhas[:8])
            if len(falhas) > 8:
                msg += "\n· … e mais %d" % (len(falhas) - 8)
        QMessageBox.information(self, "Anexos", msg)
        if gravados and sys.platform.startswith("win"):
            try:
                os.startfile(self._pasta)          # noqa: S606
            except OSError:
                pass

    @slot_seguro
    def _massa_erro(self, m):
        self._w = None
        self.b_todos.setEnabled(True)
        self.hint.setText("")
        QMessageBox.critical(self, "Anexos", "Não consegui baixar:\n%s" % m)

    def _linha(self, d, CARD, BORDER, TEXT, MUTED):
        f = QFrame(); f.setObjectName("docRow")
        f.setStyleSheet("QFrame#docRow{background:%s;border:1px solid %s;border-radius:10px;}"
                        % (CARD, BORDER))
        h = QHBoxLayout(f); h.setContentsMargins(13, 10, 13, 10); h.setSpacing(11)
        nome = d.get("nome") or "anexo"
        tag = QLabel(_ext(nome))
        tag.setFixedWidth(46); tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag.setStyleSheet("background:rgba(166,226,46,0.12);color:#a3d900;border-radius:6px;"
                          "padding:3px 0;font-size:10.5px;font-weight:700;")
        h.addWidget(tag)
        cx = QVBoxLayout(); cx.setSpacing(2)
        ln = QLabel(nome); ln.setWordWrap(True)
        ln.setStyleSheet(f"color:{TEXT};font-size:12.5px;background:transparent;")
        cx.addWidget(ln)
        quem = (d.get("user") or "").strip()
        desc = (d.get("desc") or "").strip()
        sub = " · ".join(x for x in (quem, desc if desc != nome else "") if x)
        if sub:
            ls = QLabel(sub); ls.setWordWrap(True)
            ls.setStyleSheet(f"color:{MUTED};font-size:11px;background:transparent;")
            cx.addWidget(ls)
        h.addLayout(cx, 1)
        if d.get("url"):
            b_abrir = QPushButton("Abrir"); b_abrir.setObjectName("secondary")
            b_abrir.setCursor(Qt.CursorShape.PointingHandCursor)
            b_abrir.clicked.connect(lambda *_, dd=d: self._acao(dd, salvar=False))
            b_baixar = QPushButton("Baixar"); b_baixar.setObjectName("secondary")
            b_baixar.setCursor(Qt.CursorShape.PointingHandCursor)
            b_baixar.clicked.connect(lambda *_, dd=d: self._acao(dd, salvar=True))
            h.addWidget(b_abrir); h.addWidget(b_baixar)
        else:
            nada = QLabel("nota de texto")
            nada.setStyleSheet(f"color:{MUTED};font-size:11px;background:transparent;")
            h.addWidget(nada)
        return f

    @slot_seguro
    def _acao(self, d, salvar):
        if self._w is not None:
            return
        nome = d.get("nome") or "anexo"
        destino = None
        if salvar:
            destino, _ = QFileDialog.getSaveFileName(self, "Salvar anexo", nome)
            if not destino:
                return
        self._pend = (nome, destino)
        self.hint.setText("baixando %s…" % nome)
        self._w = ApiWorker(_baixar_bytes, d["url"])
        self._w.ok.connect(self._chegou); self._w.erro.connect(self._falhou)
        self._w.start()

    @slot_seguro
    def _falhou(self, m):
        self._w = None; self.hint.setText("")
        QMessageBox.critical(self, "Anexo", "Não consegui baixar o arquivo:\n%s" % m)

    @slot_seguro
    def _chegou(self, dados):
        self._w = None; self.hint.setText("")
        nome, destino = getattr(self, "_pend", ("anexo", None))
        try:
            if destino:
                with open(destino, "wb") as f:
                    f.write(dados)
                self.hint.setText("salvo em %s" % os.path.basename(destino))
                return
            # ABRIR: grava numa temporária e entrega ao programa padrão do sistema. Não tentamos
            # renderizar PDF/Excel aqui — o Excel do usuário abre melhor que qualquer visualizador
            # que a gente escrevesse, e ZIP nem faz sentido pré-visualizar.
            pasta = tempfile.mkdtemp(prefix="oscreator_")
            cam = os.path.join(pasta, nome)
            with open(cam, "wb") as f:
                f.write(dados)
            if sys.platform.startswith("win"):
                os.startfile(cam)                                  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", cam])
            else:
                subprocess.Popen(["xdg-open", cam])
            self.hint.setText("aberto no programa padrão")
        except OSError as e:
            QMessageBox.critical(self, "Anexo", "Não consegui gravar o arquivo:\n%s" % e)


def abrir_documentos(parent, itens, titulo="Documentos da OS"):
    if not itens:
        QMessageBox.information(parent, titulo, "Nenhum documento nesta OS.")
        return
    DocumentosDialog(parent, itens, titulo).exec()
