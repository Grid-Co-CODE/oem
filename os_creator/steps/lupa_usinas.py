"""O card grande de USINAS — para corrigir o nome da usina que não bate com o cadastro.

Levi, 31/08: "quando a usina não tiver vinculada o nome fica vermelho, ao clicar abre um card
gigante mostrando os clientes em drill down, quando eu clico abrem as usinas e eu escolho".

O QUE ESTÁ SENDO CORRIGIDO: a coluna 'Usina' da planilha é digitada à mão e nem sempre casa com
o cadastro do Fracttal. Medido em 31/08: das duas abas, 8 nomes não casam com nada — 'Santarém 2'
(17 ocorrências), 'PEIII' (13), 'PEII' (12), 'Santa Bárbara I' (7) e mais quatro, 54 ocorrências
no total. Sem casar a usina, nenhum ativo daquela linha resolve, e a ocorrência fica órfã.

O QUE É GRAVADO: o NOME da usina, seco — 'Petrolina 3', e não o código 'PTL300' nem o nome longo
do cadastro 'Axis - Petrolina 3 - PE'.

Era o código até 08/09, por casar com o ativo pelo segmento (`_codigo_bate_usina`) e por ser o
formato que a maioria das linhas já usava. Levi mandou trocar: "eu não quero que fique o código
da usina, eu quero o nome da usina". O nome continua casando o ativo — `_ativos_da_usina` tenta o
código e cai para o nome (`_nomes_de_usina_batem`), e o nome seco está contido no longo do
cadastro. O que se perde é precisão em nome curto demais; o que se ganha é uma coluna que se lê.
"""
import collections
import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
                             QPushButton, QListWidget, QListWidgetItem, QLineEdit,
                             QAbstractItemView)

import api
from steps.ui import CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED
from workers import slot_seguro


_UF = re.compile(r"^[A-Z]{2}$")


def nome_curto(cliente, nome):
    """"Axis - Petrolina 3 - PE" → "Petrolina 3". O nome da usina, sem o cliente e sem o estado.

    É ESTE que vai para a planilha. O Fracttal guarda o nome longo porque precisa desambiguar
    cliente; a coluna Usina sempre teve o nome seco — 'Boa Esperança do Sul 1 e 2',
    'Piracicaba I' —, e escrever 'Axis - Petrolina 3 - PE' ali seria trocar uma grafia estranha
    por outra.

    Conservador de propósito: só tira o começo se ele for exatamente o cliente, e só tira o fim
    se for sigla de estado. Nome fora do padrão volta inteiro — encurtar errado faria a linha
    casar com a usina errada no `_nomes_de_usina_batem`, que é pior que um nome comprido."""
    nome = str(nome or "").strip()
    cliente = str(cliente or "").strip()
    partes = [p.strip() for p in nome.split(" - ")]
    if len(partes) >= 2 and cliente and partes[0].casefold() == cliente.casefold():
        partes = partes[1:]
    if len(partes) >= 2 and _UF.match(partes[-1]):
        partes = partes[:-1]
    return " - ".join(partes) or nome


def _desempatar(usinas):
    """Nome curto que serve para DUAS usinas volta a levar o cliente na frente.

    Medido no catálogo de 08/09: "Linhares 1" existe na Axis (74 ativos) e na Thopen (54). O
    código desambiguava sozinho; o nome não. Sem isto, gravar "Linhares 1" deixaria a linha
    apontando para duas usinas de clientes diferentes, e o `_ativos_da_usina` escolheria pela
    ordem do catálogo — errado em silêncio, que é a classe de erro que este app não aceita.

    Vale para nome CONTIDO em outro, não só igual: o casamento por nome usa substring, então
    "Cabine 1" alcança "Cabine 1 TESTE TESTE" do mesmo jeito.

    O desempate é o nome COMPLETO do cadastro, e não "cliente + curto" colado. Colar parecia mais
    bonito e quebrou três: 'Solier - Cascavel' virou 'Solier Qair - Solier - Cascavel', que não
    existe em ativo nenhum — o nome do cadastro nem sempre tem a forma "Cliente - Nome - UF". O
    nome completo casa por construção: ele É o campo do ativo."""
    def n(u):
        return api._norm_txt(u["curto"])
    empatados = [u for u in usinas
                 if any(o is not u and (n(u) == n(o) or n(u) in n(o)) for o in usinas)]
    for u in empatados:
        u["curto"] = u["nome"]


def usinas_do_catalogo(ativos):
    """[{cliente, nome, curto, codigo, n}] — uma entrada por usina do Fracttal.

    O código sai do `code` do ativo: é o penúltimo segmento ('THPN-SDN100-INVR1.1' → 'SDN100',
    'JCD100-INVR2.1' → 'JCD100'). O formato tem 2 ou 3 segmentos conforme o cliente ter prefixo,
    e é sempre o penúltimo — o último é o próprio equipamento. Vence o código mais frequente da
    usina: um ativo com código fora do padrão não desloca os outros milhares."""
    por_usina = collections.defaultdict(list)
    for a in ativos or []:
        nome = str(a.get("usina") or "").strip()
        if not nome:
            continue
        por_usina[(str(a.get("cliente") or "").strip(), nome)].append(a)
    out = []
    for (cli, nome), lst in por_usina.items():
        cods = collections.Counter()
        for a in lst:
            partes = str(a.get("code") or "").split("-")
            if len(partes) >= 2 and partes[-2].strip():
                cods[partes[-2].strip()] += 1
        if not cods:
            continue
        out.append({"cliente": cli or "sem cliente", "nome": nome,
                    "curto": nome_curto(cli, nome),
                    "codigo": cods.most_common(1)[0][0], "n": len(lst)})
    _desempatar(out)
    return sorted(out, key=lambda u: (api._norm_txt(u["cliente"]), api._norm_txt(u["nome"])))


class LupaUsinas(QDialog):
    """Clientes à esquerda, usinas do cliente à direita. `ao_escolher(usina)` recebe o dict."""

    def __init__(self, pai, ativos, ao_escolher, atual=""):
        super().__init__(pai)
        self._usinas = usinas_do_catalogo(ativos)
        self._ao_escolher = ao_escolher
        self._atual = str(atual or "")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        janela = pai.window() if pai is not None else None
        if janela is not None:
            self.setGeometry(janela.geometry())

        fundo = QVBoxLayout(self)
        fundo.setContentsMargins(0, 0, 0, 0)
        f = QWidget()
        f.setStyleSheet("background:rgba(4,7,14,0.82);")
        fundo.addWidget(f)
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.addStretch(1)
        linha = QHBoxLayout()
        linha.addStretch(1)
        linha.addWidget(self._card(), 5)
        linha.addStretch(1)
        fv.addLayout(linha, 16)
        fv.addStretch(1)
        self._pintar_clientes()

    def _lista(self):
        w = QListWidget()
        w.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        w.setStyleSheet(
            "QListWidget{background:%s;border:1px solid %s;border-radius:10px;color:%s;"
            "font-size:12.5px;outline:0;padding:4px;}"
            "QListWidget::item{padding:7px 9px;border-radius:7px;}"
            "QListWidget::item:selected{background:rgba(166,226,46,0.16);color:%s;}"
            % (INPUT, BORDER, TEXT, TEXT))
        return w

    def _card(self):
        c = QFrame()
        c.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:16px;}"
                        % (CARD, BORDER))
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(13)

        topo = QHBoxLayout()
        t = QLabel("Vincular usina")
        t.setStyleSheet("color:%s;font-size:18px;font-weight:800;background:transparent;"
                        "border:none;" % TEXT)
        topo.addWidget(t)
        sub = QLabel("·  a planilha diz “%s”, que não existe no cadastro" % self._atual)
        sub.setStyleSheet("color:%s;font-size:11.5px;background:transparent;border:none;" % MUTED)
        topo.addWidget(sub)
        topo.addStretch(1)
        fechar = QPushButton("✕")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setFixedSize(30, 30)
        fechar.setStyleSheet("QPushButton{background:%s;color:%s;border:1px solid %s;"
                             "border-radius:8px;padding:0px;margin:0px;min-height:0px;"
                             "font-size:14px;font-weight:800;}"
                             "QPushButton:hover{color:%s;border-color:%s;}"
                             % (INPUT, TEXT, BORDER, GREEN, GREEN))
        fechar.clicked.connect(lambda *_: self.reject())
        topo.addWidget(fechar)
        v.addLayout(topo)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("filtrar por cliente, usina ou código…")
        self._busca.setStyleSheet("QLineEdit{background:%s;border:1px solid %s;border-radius:8px;"
                                  "color:%s;font-size:12px;padding:4px 10px;min-height:0px;}"
                                  "QLineEdit:focus{border-color:%s;}" % (INPUT, BORDER, TEXT, GREEN))
        self._busca.textChanged.connect(lambda *_: self._pintar_clientes())
        v.addWidget(self._busca)

        colunas = QHBoxLayout()
        colunas.setSpacing(12)
        esq = QVBoxLayout()
        esq.setSpacing(6)
        esq.addWidget(self._rot("CLIENTE"))
        self._l_cli = self._lista()
        self._l_cli.currentRowChanged.connect(lambda *_: self._pintar_usinas())
        esq.addWidget(self._l_cli)
        colunas.addLayout(esq, 2)
        dir_ = QVBoxLayout()
        dir_.setSpacing(6)
        dir_.addWidget(self._rot("USINA"))
        self._l_usi = self._lista()
        self._l_usi.itemDoubleClicked.connect(lambda *_: self._escolher())
        dir_.addWidget(self._l_usi)
        colunas.addLayout(dir_, 3)
        v.addLayout(colunas, 1)

        rod = QHBoxLayout()
        self._rodape = QLabel("")
        self._rodape.setStyleSheet("color:%s;font-size:11.5px;background:transparent;border:none;"
                                   % MUTED)
        rod.addWidget(self._rodape, 1)
        b = QPushButton("Vincular a selecionada")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:9px;"
                        "padding:8px 18px;font-size:12px;font-weight:800;min-height:0px;}"
                        % (GREEN, GREEN_INK))
        b.clicked.connect(lambda *_: self._escolher())
        rod.addWidget(b)
        v.addLayout(rod)
        return c

    def _rot(self, t):
        q = QLabel(t)
        q.setStyleSheet("color:%s;font-size:10px;font-weight:800;letter-spacing:1.1px;"
                        "background:transparent;border:none;" % MUTED)
        return q

    def _filtradas(self):
        termo = api._norm_txt(self._busca.text())
        if not termo:
            return self._usinas
        # a BUSCA continua alcançando o código e o nome longo, mesmo que a lista só mostre o
        # curto: quem digita "GTA500" ou "SP" está procurando, não escolhendo.
        return [u for u in self._usinas
                if termo in api._norm_txt("%s %s %s %s"
                                          % (u["cliente"], u["nome"], u["curto"], u["codigo"]))]

    def _pintar_clientes(self):
        self._vis = self._filtradas()
        clientes = []
        for u in self._vis:
            if u["cliente"] not in clientes:
                clientes.append(u["cliente"])
        self._clientes = clientes
        self._l_cli.blockSignals(True)
        self._l_cli.clear()
        for cli in clientes:
            n = sum(1 for u in self._vis if u["cliente"] == cli)
            self._l_cli.addItem(QListWidgetItem("%s   ·  %d usina(s)" % (cli, n)))
        self._l_cli.blockSignals(False)
        if clientes:
            self._l_cli.setCurrentRow(0)
        self._pintar_usinas()

    def _pintar_usinas(self):
        r = self._l_cli.currentRow()
        cli = self._clientes[r] if 0 <= r < len(self._clientes) else None
        self._usi_vis = [u for u in self._vis if u["cliente"] == cli]
        self._l_usi.clear()
        for u in self._usi_vis:
            # SÓ O NOME (Levi, 08/09: "quero que apareça e salve só Guaratingueta 5"). Mostrar
            # "Thopen - Guaratingueta 5 - SP · GTA500" e gravar "Guaratingueta 5" seria pedir
            # para a pessoa escolher uma coisa e receber outra. O cliente já está na coluna da
            # esquerda, e a UF não decide nada aqui. Quem tem xará continua com o nome completo,
            # que é o que vai ser gravado também — ver `_desempatar`.
            self._l_usi.addItem(QListWidgetItem(u["curto"]))
        self._rodape.setText("%d usina(s) · clique duas vezes para vincular" % len(self._usi_vis)
                             if self._usi_vis else "nenhuma usina neste filtro.")

    @slot_seguro
    def _escolher(self, *_):
        r = self._l_usi.currentRow()
        if not (0 <= r < len(getattr(self, "_usi_vis", []))):
            return
        if self._ao_escolher:
            self._ao_escolher(self._usi_vis[r])
        self.accept()
