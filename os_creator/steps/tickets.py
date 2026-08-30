"""Aba Tickets — ocorrências de Trackers e Strings vindas da Gridco Performance API.

FASE 1: SOMENTE LEITURA. Nada aqui escreve. A escrita depende de a aba sair do upload do
pipeline antes (spec §8) — enquanto o `.xlsx` subir com replace=true, qualquer gravação nossa
seria apagada no sync seguinte.

A tela é uma só para as duas abas: 15 das 23 colunas de Trackers e 15 das 18 de Strings são
idênticas, então o que muda entre elas é só o bloco de extras.

A coluna `OS` (spec §8) não existe ainda — nasce só na fase 2, depois do corte do pipeline.
`estado_do_ticket` recebe `num_os` sempre vazio e por isso só devolve "aberta" ou "encerrada"
nesta fase; os outros três estados (com_os/verificando/a_fechar) ficam desenhados na tela
(filtros, faixa de contadores, ciclo de vida) prontos para quando a coluna existir, mas não
acontecem em dado real hoje. Não é bug — é a tela pronta para a fase 2 sem precisar ser refeita."""
import re
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit,
                             QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
                             QAbstractItemView, QScrollArea, QTextEdit, QSizePolicy)

import api
import tickets_api
import tickets_ativo
import tickets_calc
import tickets_spec
from steps.ui import CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED
from workers import ApiWorker, slot_seguro

# perto do que a aba Ativos já usa (LIMITE_TABELA=400): Trackers tem 2.781 linhas na planilha,
# e desenhar todas de uma vez é custo de layout sem ganho — quem quer uma usina específica usa
# a busca ou o filtro de usina à esquerda.
_LIMITE_TABELA = 400

# ordem dos estados na lista: quem precisa de gente primeiro. `a_fechar` vem junto de `com_os`
# porque é a mesma espera — a diferença é só de quem depende.
_PESO_ESTADO = {"verificando": 0, "aberta": 1, "a_fechar": 2, "com_os": 3, "encerrada": 4}


def ordenar_ocorrencias(ocs):
    """Primeiro o que precisa de gente; dentro do mesmo estado, a mais velha na frente."""
    return sorted(ocs, key=lambda o: (_PESO_ESTADO.get(o.get("_estado"), 9),
                                      -(o.get("_dias") or 0)))


# ── texto do aviso por estado (painel da direita) ───────────────────────────────────────────
# Adaptado do esboço: tirei toda referência a "desmarque"/"Salvar" — não existe botão que grave
# nesta fase, e prometer uma ação que não está na tela confundiria mais do que ajudaria.
_TXT_AVISO = {
    "aberta": "Nenhuma OS vinculada ainda: a ocorrência está em aberto e ninguém foi mandado olhar.",
    "com_os": "OS aberta, técnico em campo. O fim chega quando ela for concluída.",
    "verificando": "O técnico fechou a tarefa, mas ninguém confirmou que resolveu. Fique de olho: "
                   "o problema pode voltar a existir sem ninguém perceber.",
    "a_fechar": "OS concluída pelo técnico; falta só registrar o Fim da ocorrência para fechar de vez.",
    "encerrada": "Fim registrado. A indisponibilidade abaixo está fechada.",
}

# o que muda entre as duas abas na tabela central: rótulo da coluna + como tirar o valor da linha.
# Em Trackers o SKID vem da PLANILHA (coluna "Nº do SKID"); em Strings essa coluna não existe — o
# extra correspondente é o nome do inversor, e SKID/Cabine dele vêm do catálogo (ver _repintar_ident).
_EXTRA_COL = {
    "Trackers": ("Skid / Tracker",
                 lambda oc: "%s / %s" % (oc.get("Nº do SKID") or "—",
                                         oc.get("Nº do tracker / Identificação") or "—")),
    "Strings": ("Inversor", lambda oc: str(oc.get("Inversor") or "—")),
}


# ── datas: mesma tolerância de tickets_calc, sem reimplementar o parser ────────────────────
def _fmt_dt(v, com_hora=True):
    d = tickets_calc._para_dt(v)
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def _dias_desde(ini, fim):
    """Dias entre o Início e o Fim (ou até agora, se ainda aberta). None quando não dá para
    calcular — mesma régua do `indisponibilidade_horas`: número plausível e errado é pior que
    traço na tela."""
    a = tickets_calc._para_dt(ini)
    if a is None:
        return None
    b = tickets_calc._para_dt(fim) or datetime.now()
    if b < a:
        return None
    return (b - a).days


# ── casar o nome da coluna 'Inversor' (aba Strings) com o ativo do catálogo ────────────────
def _numero(s):
    """Sequência numérica do nome do ativo: 'Inversor 2.18' → '2.18'. Mesma extração de
    steps/performance.py::_aplicar_sug_pendente (deep link gridos://)."""
    m = re.search(r"\d+(?:[.\-]\d+)*", str(s or ""))
    return m.group(0).replace("-", ".") if m else ""


def _codigo_bate_usina(code_norm, usina_norm):
    """O `code` do ativo casa com o código de usina da planilha se `usina_norm` for um dos
    segmentos do `code` separados por '-', SEM contar o último (o próprio 'INVRx.y').

    Por que segmento inteiro, não `startswith`/`in`: o formato do `code` é inconsistente —
    'JCD100-INVR2.1' (2 segmentos) convive com '2C-IPX100-INVR1.1' e
    'THPN-SDN100-INVR1.1' (3 segmentos, prefixo de cliente). Medido no `assets_cache.json`
    real: 437 dos 1.710 inversores (26%) têm esse prefixo extra — um `startswith(usina + "-")`
    sozinho perde esses 437 inteiros. E precisa ser o segmento INTEIRO, não substring: senão
    'IPX10' casaria dentro de 'IPX100-INVR...' (mesma classe do bug do número do inversor,
    um nível acima)."""
    segmentos = code_norm.split("-")
    return usina_norm in segmentos[:-1]


def _nomes_de_usina_batem(a, b):
    """Mesmo padrão de steps/performance.py::_aplicar_sug_pendente para casar usina por nome
    (igual, ou um contém o outro, normalizado) — usado só quando o casamento por código não
    achou nada."""
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def _achar_inversor(nome, usina_ticket, todos):
    """Resolve no catálogo o ativo Inversor citado na coluna 'Inversor' da aba Strings.

    Três armadilhas achadas com dado real (medidas em 29/08, rodada de revisão da Tarefa 7):

    1) A coluna 'Usina' da aba Strings é MISTA, não é sempre código. Medido nas 233 linhas ao
       vivo: a maioria traz o CÓDIGO ('JCD100', 'TIM100'), mas 56 (24%) trazem o NOME DE
       EXIBIÇÃO ('Demerval Lobao', 'Santarém 1', 'Boa Esperança do Sul 1 e 2') — não é regra
       fixa, é o que quem preencheu a linha digitou. Por isso o casamento tenta `code` primeiro
       (função `_codigo_bate_usina`) e só cai para `usina` (nome de exibição do catálogo,
       `_nomes_de_usina_batem`) quando o escopo por código vier vazio — código é mais preciso
       quando existe, nome é o único caminho quando não.
    2) Ver `_codigo_bate_usina`: o formato do `code` muda com prefixo de cliente (26% dos
       inversores). Comparar por SEGMENTO inteiro resolve os dois formatos de uma vez.
    3) Dentro da usina, número exato primeiro. Conferido no `assets_cache.json` real: 250
       colisões deste tipo em 103 usinas — ex. THPN-TNB100 tem 'Inversor 2.1' E 'Inversor 2.18'
       ao mesmo tempo (e 2.10 a 2.19 inteiros). Um `in` ingênuo casaria a primeira ocorrência da
       lista, sempre errado para 9 dos 10 inversores de cada dezena. Mesmo algoritmo (número
       exato → substring só se os números não colidirem) de
       steps/performance.py::_aplicar_sug_pendente, que existe por causa desse bug real no deep
       link gridos://.

    Mesmo com as três, ~33 das 233 linhas (14%) não resolvem — não é bug: é lacuna real do
    cadastro (ex. MTS200 sem o bloco 2 cadastrado no Fracttal). 'não encontrado no catálogo'
    ali é a resposta certa, não um erro do casamento."""
    if not nome or not todos:
        return None
    alvo = api._norm_txt(nome)
    alvo_n = _numero(nome)
    un = api._norm_txt(usina_ticket)
    if not un:
        return None

    candidatos = [a for a in todos if api._norm_txt(a.get("tipo")) == "inversor"
                  and _codigo_bate_usina(api._norm_txt(a.get("code")), un)]
    if not candidatos:
        candidatos = [a for a in todos if api._norm_txt(a.get("tipo")) == "inversor"
                      and _nomes_de_usina_batem(un, api._norm_txt(a.get("usina")))]
    if not candidatos:
        return None

    for a in candidatos:
        snome = api._asset_short_name(a)
        if api._norm_txt(snome) == alvo or (alvo_n and alvo_n == _numero(snome)):
            return a
    for a in candidatos:
        snome = api._asset_short_name(a)
        nm = api._norm_txt(snome)
        if alvo and (alvo in nm or nm in alvo):
            sn = _numero(snome)
            if alvo_n and sn and alvo_n != sn:
                continue
            return a

    # ÚLTIMO RECURSO — o catálogo manda, o número do ticket vira ÍNDICE (Levi, 30/08:
    # "o que os tickets pedem é só abrir o leque de opções de acordo com o Fracttal").
    #
    # Caso real: o MTS200 tem 40 inversores cadastrados, bloco 1 numerado 1.1..1.20 e bloco 2
    # numerado 2.21..2.40 — em sequência global, em vez de reiniciar em 1 como todas as outras
    # usinas fazem. Os tickets pedem 2.2..2.19 e nenhum casa, então 33 ocorrências ficavam sem
    # SKID nem cabine. Aqui o "2.5" do ticket passa a significar "o 5º inversor do bloco 2 no
    # catálogo", que no MTS200 é o 2.25.
    #
    # NÃO É SILENCIOSO de propósito: o painel mostra o nome do ativo que foi resolvido, então o
    # analista vê "Inversor 2.25" para um ticket que dizia 2.5 e percebe o descompasso. E só
    # entra depois que o número exato falhou — usina bem cadastrada nunca passa por aqui.
    #
    # ATENÇÃO A QUEM FOR MEXER: se um dia alguém renumerar o bloco 2 do MTS200 no Fracttal para
    # 2.1..2.20, o casamento exato volta a funcionar e este trecho para de ser exercitado
    # sozinho. Ele não precisa ser removido, mas deixa de ser necessário.
    partes = str(alvo_n).split(".")
    if len(partes) == 2 and all(x.isdigit() for x in partes):
        bloco, indice = partes[0], int(partes[1])
        do_bloco = []
        for a in candidatos:
            n = str(_numero(api._asset_short_name(a))).split(".")
            if len(n) == 2 and n[0] == bloco and n[1].isdigit():
                do_bloco.append((int(n[1]), a))
        do_bloco.sort()
        if 1 <= indice <= len(do_bloco):
            return do_bloco[indice - 1][1]
    return None


def _limpar_layout(layout):
    """Esvazia um layout p/ reconstruir (mesmo padrão de steps/ativos.py::_arvore/_carregar_os):
    remover e agendar deleteLater dos widgets, senão a reconstrução sobrepõe linhas antigas.

    RECURSIVO: `_pinta_filtros` põe LAYOUTS dentro do layout de estado (cada linha é um
    QHBoxLayout com chip + contagem), não só widgets soltos como as outras telas. `it.widget()`
    é None para um item que é layout, então a versão não-recursiva não destruía nada ali — o
    chip antigo ficava vivo, por baixo do novo, na mesma geometria (medido: 10 repinturas =
    50 chips vivos, sem teto). Pior: o chip novo tem fundo transparente quando desligado, então
    o chip antigo 'ligado' (fundo colorido) aparecia por baixo e o filtro nunca mais parecia
    desligado depois do primeiro clique — `_repintar` roda a cada pausa de 220ms na busca, a
    cada clique de filtro e a cada troca de aba, então o vazamento era constante."""
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w:
            w.setParent(None)
            w.deleteLater()
            continue
        sub = it.layout()
        if sub:
            _limpar_layout(sub)          # mata os widgets de dentro antes do layout sumir


# ── pequenos componentes visuais (mesmo padrão do esboço aprovado) ─────────────────────────
def _lbl(t, cor=TEXT, px=13, peso=400, ital=False, esp=None):
    q = QLabel(str(t))
    q.setStyleSheet("color:%s;font-size:%spx;font-weight:%s;background:transparent;border:none;%s%s"
                    % (cor, px, peso, "font-style:italic;" if ital else "",
                       "letter-spacing:%spx;" % esp if esp else ""))
    return q


def _secao(t, cor=MUTED):
    return _lbl(t, cor, 10, 800, esp=1.2)


def _regua():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background:%s;border:none;" % BORDER)
    return f


def _cor(hexa):
    from PyQt6.QtGui import QColor
    return QColor(hexa)


def _rgba(hexa, a):
    h = hexa.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "rgba(%d,%d,%d,%.2f)" % (r, g, b, a)


def _qss_campo(cor_texto=MUTED):
    # Fundo SEMPRE o INPUT (Levi, 28/08): um fundo mais escuro que o card vira buraco na tela.
    # Nesta fase TODO campo é somente-leitura — a cor do texto (MUTED, o padrão aqui) é o único
    # sinal disso, nunca o fundo (senão o campo para de parecer um campo). A busca do cabeçalho
    # é a exceção: é o único campo que a pessoa de fato usa, e passa cor_texto=TEXT.
    return ("background:%s;border:1px solid %s;border-radius:9px;padding:7px 10px;"
            "color:%s;font-size:12.5px;" % (INPUT, BORDER, cor_texto))


def _campo(ph=""):
    e = QLineEdit()
    e.setReadOnly(True)
    if ph:
        e.setPlaceholderText(ph)
    e.setStyleSheet("QLineEdit{%s}" % _qss_campo())
    return e


def _rotulado(rotulo, widget, dica=None, cor_dica=GREEN):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    t = QHBoxLayout()
    t.setSpacing(7)
    t.addWidget(_lbl(rotulo, MUTED, 10.5, 700))
    if dica:
        t.addWidget(_lbl(dica, cor_dica, 9.5, 800))
    t.addStretch(1)
    v.addLayout(t)
    v.addWidget(widget)
    return w


class _Painel(QFrame):
    def __init__(self, larg=None):
        super().__init__()
        self.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:14px;}"
                           % (CARD, BORDER))
        if larg:
            self.setFixedWidth(larg)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 16, 18, 16)
        self.v.setSpacing(12)


class _Chip(QPushButton):
    def __init__(self, texto, ligado=False, cor=GREEN, ao_clicar=None):
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
        if ao_clicar:
            # `clicked` do Qt manda um bool (checked) — o chamador não precisa saber disso.
            self.clicked.connect(lambda _checked=False: ao_clicar())


class _Tile(QFrame):
    """Contador do topo. A cor é do ESTADO, não decoração — quem bate o olho já sabe onde doer."""
    def __init__(self, n, rotulo, cor, dica=""):
        super().__init__()
        self.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:12px;"
                           "border-top:2px solid %s;}" % (CARD, BORDER, cor))
        v = QVBoxLayout(self)
        v.setContentsMargins(15, 11, 15, 12)
        v.setSpacing(1)
        v.addWidget(_lbl(f"{n:,}".replace(",", "."), cor, 25, 800))
        v.addWidget(_lbl(rotulo, TEXT, 11.5, 700))
        if dica:
            d = _lbl(dica, MUTED, 10.5)
            d.setWordWrap(True)
            v.addWidget(d)


class _Segmentado(QFrame):
    """Barra de segmentos: um bloco só, com divisórias finas, em vez de N pílulas soltas.

    Levi, 30/08: "esse filtro de estado é feio demais, esse cabeçalho arredondado é feio demais".
    As pílulas (`border-radius:999px`) empilhadas na coluna da esquerda gastavam altura, cada uma
    com contorno próprio, e o conjunto lia como uma lista de botões em vez de um controle. Aqui é
    um controle: o segmento ativo se marca por preenchimento suave mais um filete no topo, não
    por contorno, e a contagem viaja junto do rótulo — o que dispensou a faixa de tiles que ficava
    logo acima repetindo os mesmos números."""

    def __init__(self, itens, ao_clicar):
        # itens: [(chave, rótulo, cor, contagem, ligado)]
        super().__init__()
        self.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:10px;}"
                           % (INPUT, BORDER))
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        for i, (chave, rotulo, cor, n, ligado) in enumerate(itens):
            if i:
                div = QFrame()
                div.setFixedWidth(1)
                div.setStyleSheet("background:%s;border:none;" % BORDER)
                h.addWidget(div)
            h.addWidget(self._segmento(chave, rotulo, cor, n, ligado, ao_clicar,
                                       primeiro=(i == 0), ultimo=(i == len(itens) - 1)))

    def _segmento(self, chave, rotulo, cor, n, ligado, ao_clicar, primeiro, ultimo):
        b = QPushButton()
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setCheckable(True)
        b.setChecked(ligado)
        b.setText("%s   %s" % (rotulo, n))
        # cantos só nas pontas, para o conjunto ler como UM bloco
        e = "10px" if primeiro else "0"
        d = "10px" if ultimo else "0"
        b.setStyleSheet(
            "QPushButton{color:%s;background:transparent;border:none;"
            "border-top:2px solid transparent;"
            "border-top-left-radius:%s;border-bottom-left-radius:%s;"
            "border-top-right-radius:%s;border-bottom-right-radius:%s;"
            "padding:9px 16px;font-size:12px;font-weight:700;text-align:center;}"
            "QPushButton:hover{color:%s;}"
            "QPushButton:checked{color:%s;background:%s;border-top:2px solid %s;}"
            % (MUTED, e, e, d, d, TEXT, cor, _rgba(cor, 0.13), cor))
        b.clicked.connect(lambda _c=False, k=chave: ao_clicar(k))
        return b


class _LinhaClicavel(QWidget):
    """Linha de usina no filtro da esquerda: nome + contagem, clicável (mesmo padrão de
    steps/ativos.py::_LinhaUsina). Clicar de novo na mesma usina limpa o filtro."""
    def __init__(self, texto, contagem, selecionada, ao_clicar):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ao_clicar = ao_clicar
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 3, 0, 3)
        h.setSpacing(8)
        h.addWidget(_lbl(texto, GREEN if selecionada else MUTED, 12, 700 if selecionada else 400))
        h.addStretch(1)
        h.addWidget(_lbl(str(contagem), MUTED, 11))

    def mousePressEvent(self, e):
        if self._ao_clicar:
            self._ao_clicar()


class TicketsTab(QWidget):
    """Catálogo de ocorrências: lista + painel. Leitura."""
    _selfnav = True          # o wrapper do app NÃO põe a barra de Voltar — o daqui é o único

    def __init__(self, on_voltar=None):
        super().__init__()
        self._on_voltar = on_voltar
        self._aba = "Trackers"
        self._ocs, self._sel = [], None
        self._visiveis = []
        self._estados_filtro = set()      # vazio = todos os estados
        self._usina_filtro = ""
        self._todos_ativos, self._por_id = [], {}
        self._ativos_prontos = False
        self._ativos_falhou = False
        self._w = self._wa = None
        self._monta()
        self._carregar()

    # ── montagem ─────────────────────────────────────────────────────────────────────────
    def _monta(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 18, 26, 20)
        raiz.setSpacing(14)
        raiz.addLayout(self._cabecalho())
        self._tiles_box = QHBoxLayout()
        self._tiles_box.setSpacing(12)
        raiz.addLayout(self._tiles_box)

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(self._coluna_filtros())
        corpo.addWidget(self._coluna_lista(), 1)
        corpo.addWidget(self._coluna_painel())
        raiz.addLayout(corpo, 1)
        self._selecionar(None)

    def _cabecalho(self):
        cab = QHBoxLayout()
        cab.setSpacing(16)
        if self._on_voltar:
            b = QPushButton("← Voltar")
            b.setFixedHeight(36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{background:transparent;color:%s;border:1px solid %s;"
                            "border-radius:10px;padding:0 16px;font-size:13px;font-weight:600;}"
                            "QPushButton:hover{border-color:%s;}" % (TEXT, BORDER, GREEN))
            b.clicked.connect(self._on_voltar)
            cab.addWidget(b)
        cx = QVBoxLayout()
        cx.setSpacing(1)
        cx.addWidget(_lbl("Tickets", TEXT, 20, 800))
        self._sub = _lbl("carregando ocorrências…", MUTED, 12)
        self._sub.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        cx.addWidget(self._sub)
        cab.addLayout(cx)
        cab.addSpacing(20)
        self._chips_aba = {}
        for nome in tickets_spec.ABAS:
            c = _Chip(nome, nome == self._aba, GREEN, ao_clicar=lambda n=nome: self._trocar_aba(n))
            self._chips_aba[nome] = c
            cab.addWidget(c)
        cab.addStretch(1)
        self._busca = QLineEdit()
        self._busca.setPlaceholderText("usina, skid, tracker/inversor, causa…")
        self._busca.setFixedSize(320, 36)
        self._busca.setStyleSheet("QLineEdit{%s}" % _qss_campo(TEXT))
        self._t_busca = QTimer(self)
        self._t_busca.setSingleShot(True)
        self._t_busca.setInterval(220)
        self._t_busca.timeout.connect(self._repintar)
        self._busca.textChanged.connect(lambda *_: self._t_busca.start())
        cab.addWidget(self._busca)
        return cab

    def _coluna_filtros(self):
        # SÓ usina. O filtro de estado subiu para a barra segmentada do topo (Levi, 30/08): aqui
        # embaixo ele dividia uma coluna de 220px com a lista de usinas, e o resultado era que
        # NENHUMA das duas cabia — com 12 usinas + o aviso de corte + a nota da ronda, o Qt
        # espremia as linhas abaixo da altura mínima e elas se sobrepunham, ilegíveis.
        p = _Painel(212)
        p.v.addWidget(_secao("USINA"))
        # rolagem em vez de corte: a lista nunca mais comprime, e a usina que não coube fica a
        # um scroll de distância em vez de sumir.
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # O seletor filho sozinho NÃO bastou (Levi, 30/08: "o plano de fundo está mais escuro
        # que os demais"): abaixo de CAUSA RAIZ aparecia a cor de JANELA dentro do card. O
        # viewport e o widget de conteúdo precisam ser pintados explicitamente — o seletor
        # descendente não alcança os dois níveis em todos os estilos do Qt.
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                         "QScrollArea > QWidget > QWidget{background:transparent;}")
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.viewport().setStyleSheet("background:transparent;")
        sc.viewport().setStyleSheet("background:transparent;")
        dentro = QWidget()
        dentro.setStyleSheet("background:transparent;")
        self._filtro_usina_box = QVBoxLayout(dentro)
        self._filtro_usina_box.setContentsMargins(0, 0, 6, 0)
        self._filtro_usina_box.setSpacing(2)
        sc.setWidget(dentro)
        p.v.addWidget(sc, 1)
        return p

    def _coluna_lista(self):
        p = _Painel()
        topo = QHBoxLayout()
        topo.addWidget(_secao("OCORRÊNCIAS"))
        topo.addStretch(1)
        p.v.addLayout(topo)

        self.tab = QTableWidget(0, 7)
        # a coluna se chama 'Dias', não 'Há': ver o comentário em _pinta_tabela sobre por que
        # um único rótulo temporal não serve pras duas leituras que a célula carrega.
        self.tab.setHorizontalHeaderLabels(["", "Usina", "Skid / Tracker", "OS", "Causa raiz",
                                            "Início da ocorrência", "Dias"])
        self.tab.verticalHeader().setVisible(False)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab.setShowGrid(False)
        # outline:0 + item:focus (custou tempo antes): sem isso o retângulo de foco da célula
        # clicada desenha uma borda por dentro do item e espreme o texto.
        self.tab.setStyleSheet(
            "QTableWidget{background:transparent;border:none;color:%s;font-size:12.5px;outline:0;}"
            "QHeaderView::section{background:transparent;color:%s;border:none;"
            "border-bottom:1px solid %s;padding:8px 4px;font-size:10px;font-weight:800;}"
            "QTableWidget::item{padding:9px 4px;border-bottom:1px solid rgba(42,53,80,0.4);}"
            "QTableWidget::item:focus{border:none;outline:none;}"
            "QTableWidget::item:selected{background:rgba(166,226,46,0.12);color:%s;}"
            % (TEXT, MUTED, BORDER, TEXT))
        self.tab.itemSelectionChanged.connect(self._sel_tabela)
        self.tab.setColumnWidth(0, 14)
        self.tab.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tab.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in (0, 2, 3, 4, 5, 6):
            self.tab.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        p.v.addWidget(self.tab, 1)
        self._rodape = _lbl("—", MUTED, 11.5)
        p.v.addWidget(self._rodape)
        return p

    def _coluna_painel(self):
        p = _Painel(452)
        self._p_conteudo = QWidget()
        cv = QVBoxLayout(self._p_conteudo)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(12)

        # o título da seção CARREGA o estado (Levi, 28/08) — em vez de "OCORRÊNCIA" seco e
        # repetir a informação numa caixa abaixo.
        topo = QHBoxLayout()
        topo.addWidget(_secao("OCORRÊNCIA"))
        self._p_estado_topo = _lbl("", tickets_spec.COR_ESTADO["aberta"], 10, 800, esp=1.2)
        topo.addWidget(self._p_estado_topo)
        topo.addStretch(1)
        self._p_row = _lbl("", MUTED, 10, ital=True)
        topo.addWidget(self._p_row)
        cv.addLayout(topo)

        self._p_usina = _lbl("—", TEXT, 17, 800)
        self._p_usina.setWordWrap(True)
        cv.addWidget(self._p_usina)

        self._ident_box = QHBoxLayout()
        self._ident_box.setSpacing(14)
        cv.addLayout(self._ident_box)

        self._ciclo_box = QHBoxLayout()
        self._ciclo_box.setContentsMargins(0, 0, 0, 0)
        self._ciclo_box.setSpacing(0)
        cv.addLayout(self._ciclo_box)

        self._p_aviso = QFrame()
        avv = QVBoxLayout(self._p_aviso)
        avv.setContentsMargins(13, 10, 13, 10)
        avv.setSpacing(3)
        self._p_aviso_txt = _lbl("", MUTED, 11)
        self._p_aviso_txt.setWordWrap(True)
        avv.addWidget(self._p_aviso_txt)
        cv.addWidget(self._p_aviso)

        # scroll transparente: o QWidget interno do QScrollArea pinta a cor de janela por padrão
        # e vira um retângulo mais claro dentro do card — o seletor filho cobre viewport E env.
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                         "QScrollArea > QWidget > QWidget{background:transparent;}")
        dentro = QWidget()
        dentro.setStyleSheet("background:transparent;")
        v = QVBoxLayout(dentro)
        v.setContentsMargins(0, 2, 8, 0)
        v.setSpacing(13)

        # Cliente, UF, Supervisor e Responsável SAÍRAM (Levi, 28/08): vêm do catálogo, não mudam
        # e não são decisão de ninguém nesta tela.
        v.addWidget(_secao("CAUSA RAIZ", tickets_spec.COR_ESTADO["verificando"]))
        self._p_causa = _campo(ph="aguardando técnico")
        v.addWidget(_rotulado("Causa raiz", self._p_causa, dica="só o técnico",
                              cor_dica=tickets_spec.COR_ESTADO["verificando"]))
        self._p_resp = _campo()
        v.addWidget(_rotulado("Responsabilidade da Grid Co.?", self._p_resp))

        v.addWidget(_regua())
        v.addWidget(_secao("PRAZOS"))
        self._p_ini = _campo()
        v.addWidget(_rotulado("Início da ocorrência", self._p_ini, dica="data e hora"))
        self._p_fim = _campo()
        v.addWidget(_rotulado("Fim da ocorrência", self._p_fim))
        self._p_indisp = _campo()
        v.addWidget(_rotulado("Indisponibilidade", self._p_indisp, dica="janela solar 06–18h"))

        v.addWidget(_regua())
        v.addWidget(_secao("COMENTÁRIOS"))
        self._p_coment = QTextEdit()
        self._p_coment.setReadOnly(True)
        self._p_coment.setFixedHeight(56)
        self._p_coment.setStyleSheet("QTextEdit{%s}" % _qss_campo())
        v.addWidget(self._p_coment)
        v.addStretch(1)
        sc.setWidget(dentro)
        cv.addWidget(sc, 1)

        p.v.addWidget(self._p_conteudo, 1)
        self._p_hint = _lbl("selecione uma ocorrência à esquerda", MUTED, 12, ital=True)
        self._p_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._p_hint.setWordWrap(True)
        p.v.addWidget(self._p_hint, 1)
        return p

    # ── dados: duas cargas independentes (ocorrências guiam a tela; catálogo só enriquece o
    # painel — se ele falhar ou demorar, a lista principal continua útil) ──────────────────
    def _carregar(self):
        self._sub.setText("carregando ocorrências…")
        self._buscar_ocorrencias()
        self._buscar_ativos()

    def _buscar_ocorrencias(self):
        # marca PARA QUAL aba este pedido foi feito: se a pessoa trocar de aba de novo antes da
        # resposta chegar, uma resposta atrasada da aba ANTERIOR não pode sobrescrever a atual.
        aba_pedida = self._aba
        sheet_id = tickets_spec.ABAS[self._aba]["sheet_id"]
        self._w = ApiWorker(tickets_api.listar_linhas, sheet_id)
        self._w.ok.connect(lambda linhas, a=aba_pedida: self._ocs_chegaram(linhas, a))
        self._w.erro.connect(self._falhou)
        self._w.start()

    def _buscar_ativos(self):
        if self._ativos_prontos:
            return          # catálogo já veio (cache de 24h) — troca de aba não busca de novo
        self._wa = ApiWorker(api.load_assets_cached)
        self._wa.ok.connect(self._ativos_chegaram)
        self._wa.erro.connect(self._ativos_falharam)
        self._wa.start()

    @slot_seguro
    def _ativos_falharam(self, _msg):
        # é só enriquecimento do painel (SKID/Cabine de Strings) — sem ele a lista principal
        # continua útil. Mas sem marcar a falha, o painel ficaria dizendo 'carregando catálogo…'
        # para sempre, o que é pior que admitir que não deu: parece travado, não indisponível.
        self._wa = None
        self._ativos_prontos = True
        self._ativos_falhou = True
        if self._aba == "Strings" and self._sel is not None:
            self._repintar_ident(self._sel)

    @slot_seguro
    def _falhou(self, msg):
        self._w = None
        self._sub.setText("não consegui carregar as ocorrências: %s" % str(msg)[:120])
        self._repintar()          # zera tiles/filtros/tabela em vez de deixá-los como estavam

    @slot_seguro
    def _ocs_chegaram(self, linhas, aba_pedida):
        self._w = None
        if aba_pedida != self._aba:
            return           # resposta de uma troca de aba já abandonada — descarta
        ocs = []
        for row in (linhas or []):
            # 'Em conformidade' não é ocorrência: é o check periódico dizendo que o tracker está
            # bem. Medido em 28/08 (docs/esbocos/tickets_trackers_amostra.json, 999 linhas): 734
            # são 'Em conformidade' (418 delas até SEM Fim). Sem este filtro a régua 'Sem OS'
            # contaria ~654 em vez das 236 ocorrências reais (Parado/Com problemas) — um número
            # plausível e completamente errado. A coluna Status só existe em Trackers, então em
            # Strings esta linha nunca dispara (todo row.get aqui vem None).
            if str(row.get("Status") or "").strip().lower() == "em conformidade":
                continue
            num_os = row.get("OS")                    # coluna nasce na fase 2 — hoje é sempre None
            status_os = row.get("Status da OS")        # idem
            fim = row.get("Fim da ocorrência")
            ini = row.get("Início da ocorrência")
            row["_estado"] = tickets_spec.estado_do_ticket(num_os, status_os, fim)
            row["_dias"] = _dias_desde(ini, fim)
            row["_horas"] = tickets_calc.indisponibilidade_horas(ini, fim)
            ocs.append(row)
        self._ocs = ocs
        self._estados_filtro.clear()
        self._usina_filtro = ""
        n_txt = f"{len(ocs):,}".replace(",", ".")
        self._sub.setText("Gridco Performance API · aba %s · %s ocorrências"
                          % (tickets_spec.ABAS[self._aba]["rotulo"], n_txt))
        self._repintar()

    @slot_seguro
    def _ativos_chegaram(self, ativos):
        self._wa = None
        self._todos_ativos = [a for a in (ativos or []) if isinstance(a, dict)]
        self._por_id = tickets_ativo.indexar(self._todos_ativos)
        self._ativos_prontos = True
        # se já tinha uma ocorrência de Strings selecionada, os campos SKID/Cabine que estavam
        # em 'carregando catálogo…' saem do escuro sem precisar clicar de novo na linha.
        if self._aba == "Strings" and self._sel is not None:
            self._repintar_ident(self._sel)

    # ── eventos (aba / filtros / busca) ─────────────────────────────────────────────────────
    # os 4 slots daqui até _repintar são ligados direto a clique/timeout do Qt. Provado com
    # controle de três vias (28/08): slot decorado que levanta exceção SOBREVIVE (loga o
    # traceback e segue); slot sem decorador que levanta MATA o processo — exit 127, sem
    # mensagem, sem log, a janela some. Como são o clique mais comum da tela, ficar sem
    # @slot_seguro aqui é o pior lugar possível para não ter.
    @slot_seguro
    def _trocar_aba(self, nome):
        if nome == self._aba or nome not in tickets_spec.ABAS:
            return
        self._aba = nome
        for n, c in self._chips_aba.items():
            c.setChecked(n == nome)
        self._ocs = []
        self._sel = None
        self._estados_filtro.clear()
        self._usina_filtro = ""
        self._sub.setText("carregando ocorrências…")
        self._repintar()             # esvazia lista/tiles já — não deixa a aba anterior pendurada
        self._buscar_ocorrencias()

    # ver o comentário de _trocar_aba: sem @slot_seguro, uma exceção aqui não falha só o
    # filtro — derruba o app inteiro, sem mensagem.
    @slot_seguro
    def _chip_estado(self, chave):
        if chave in self._estados_filtro:
            self._estados_filtro.discard(chave)
        else:
            self._estados_filtro.add(chave)
        self._repintar()

    # ver o comentário de _trocar_aba: mesma exposição — clique direto do usuário sem rede de
    # segurança contra exceção.
    @slot_seguro
    def _clicar_usina(self, usina):
        self._usina_filtro = "" if self._usina_filtro == usina else usina
        self._repintar()

    # ── repintura ────────────────────────────────────────────────────────────────────────
    # ligado direto ao timeout do QTimer da busca (_t_busca) além de ser chamado pelos 3 slots
    # acima — é o coração da tela. Ver o comentário de _trocar_aba: sem @slot_seguro, uma
    # exceção aqui é a janela sumindo sem mensagem, não um traceback no log.
    @slot_seguro
    def _repintar(self):
        termo = api._norm_txt(self._busca.text())
        rotulo_extra, valor_extra = _EXTRA_COL[self._aba]

        def _passa(oc):
            # "+30d" não é estado: é o recorte de aberta há mais de 30 dias, o mesmo alarme
            # vermelho da coluna Dias, oferecido como filtro na barra do topo.
            if "+30d" in self._estados_filtro:
                if oc["_estado"] == "encerrada" or (oc.get("_dias") or 0) <= 30:
                    return False
            estados_reais = self._estados_filtro - {"+30d"}
            if estados_reais and oc["_estado"] not in estados_reais:
                return False
            if self._usina_filtro and oc.get("Usina") != self._usina_filtro:
                return False
            if not termo:
                return True
            campos = [oc.get("Usina"), oc.get("Causa raiz"), valor_extra(oc)]
            texto = api._norm_txt(" ".join(str(c) for c in campos if c not in (None, "")))
            return termo in texto

        filtradas = ordenar_ocorrencias([o for o in self._ocs if _passa(o)])
        total = len(filtradas)
        self._visiveis = filtradas[:_LIMITE_TABELA]

        self._pinta_estados()
        self._pinta_filtros()
        self._pinta_tabela(rotulo_extra, valor_extra)
        extra = total - _LIMITE_TABELA
        self._rodape.setText("%s ocorrências" % f"{total:,}".replace(",", ".")
                             + (" · mostrando as %d primeiras, refine a busca" % _LIMITE_TABELA
                                if extra > 0 else ""))
        if self._visiveis:
            self.tab.selectRow(0)          # dispara _sel_tabela → popula o painel
        else:
            self._selecionar(None)

    def _pinta_estados(self):
        """A barra segmentada do topo: filtro de estado E contagem, num controle só.

        Antes eram DUAS coisas dizendo o mesmo: uma faixa de tiles com os números e, na coluna
        da esquerda, uma pilha de pílulas para filtrar por estado. Os números eram os mesmos e a
        pilha comia a altura que a lista de usinas precisava (Levi, 30/08). Fundidos aqui, logo
        depois dos botões de Trackers/Strings, que é onde ele pediu."""
        _limpar_layout(self._tiles_box)
        itens = []
        for k, rotulo, cor in tickets_spec.ESTADOS:
            qtd = sum(1 for o in self._ocs if o["_estado"] == k)
            # nesta fase os 3 estados do meio dependem da coluna OS, que não existe (spec §8):
            # dariam zero fixo para sempre. Zero em "Em verificação" lê como "nada pendente de
            # conferência", que é mentira — o conceito é que ainda não existe. Some até a fase 2.
            if qtd == 0 and k in ("com_os", "verificando", "a_fechar"):
                continue
            itens.append((k, rotulo, cor, qtd, k in self._estados_filtro))
        # o alarme que a coluna Dias já pinta de vermelho, disponível como filtro
        antigas = sum(1 for o in self._ocs
                      if o["_estado"] != "encerrada" and (o.get("_dias") or 0) > 30)
        itens.append(("+30d", "Abertas há +30 dias", tickets_spec.COR_ESTADO["aberta"],
                      antigas, "+30d" in self._estados_filtro))
        self._tiles_box.addWidget(_Segmentado(itens, self._chip_estado))
        self._tiles_box.addStretch(1)

    def _pinta_filtros(self):
        _limpar_layout(self._filtro_usina_box)
        cont = {}
        for o in self._ocs:
            u = o.get("Usina") or "—"
            cont[u] = cont.get(u, 0) + 1
        usinas_por_volume = sorted(cont.items(), key=lambda x: -x[1])
        # TODAS as usinas: a coluna rola desde 30/08, então não há mais motivo para cortar.
        # O corte antigo (12) existia porque a lista dividia altura com o filtro de estado e
        # nem cabia — e cortar sem avisar fazia uma usina que ficou de fora parecer inexistente.
        for u, n in usinas_por_volume:
            self._filtro_usina_box.addWidget(
                _LinhaClicavel(str(u)[:22], n, u == self._usina_filtro,
                              lambda usi=u: self._clicar_usina(usi)))
        # mesmo tratamento que o rodapé da tabela já dá pro corte de _LIMITE_TABELA: cortar a
        # lista SEM avisar faz uma usina que ficou de fora parecer que não existe. Medido em
        # 29/08: Trackers tem 63 usinas e só as top-N cabem aqui — a maioria não aparecia, em
        # silêncio. O corte é só da LISTA; a busca do cabeçalho filtra sobre `self._ocs`
        # inteiro, então ela alcança as que não estão desenhadas.


    def _pinta_tabela(self, rotulo_extra, valor_extra):
        self.tab.setHorizontalHeaderLabels(["", "Usina", rotulo_extra, "OS", "Causa raiz",
                                            "Início da ocorrência", "Dias"])
        self.tab.blockSignals(True)
        self.tab.setRowCount(0)
        self.tab.setRowCount(len(self._visiveis))
        for r, oc in enumerate(self._visiveis):
            estado = oc["_estado"]
            cor_estado = tickets_spec.COR_ESTADO.get(estado, MUTED)
            tarja = QTableWidgetItem("▐")
            tarja.setForeground(_cor(cor_estado))
            self.tab.setItem(r, 0, tarja)

            causa = oc.get("Causa raiz")
            causa_completa = str(causa).strip() if causa not in (None, "") else "aguardando técnico"
            # trunca a CÉLULA (não o dado): com ResizeToContents, uma causa raiz digitada longa
            # ('Afundamento de estrutura tracker...') empurra Início/Dias para fora da tela e a
            # tabela nasce com barra de rolagem horizontal — medido ao abrir com dado real, o
            # esboço não pegou isso porque usava texto mais curto. O texto inteiro continua
            # disponível: tooltip na célula e por extenso no painel da direita.
            causa_txt = (causa_completa[:39] + "…") if len(causa_completa) > 40 else causa_completa

            # a coluna OS ainda não existe (fase 2) — 'encerrada' aqui sempre veio de um Fim
            # digitado à mão, sem OS nenhuma envolvida, então mostrar 'sem OS' em vermelho seria
            # alarmar por um caso já resolvido. Fica neutro; só quem está ABERTA é urgência real.
            num_os = str(oc.get("OS") or "").strip()
            if num_os:
                os_txt, os_cor = num_os, TEXT
            elif estado == "encerrada":
                os_txt, os_cor = "—", MUTED
            else:
                os_txt, os_cor = "sem OS", tickets_spec.COR_ESTADO["aberta"]

            dias = oc.get("_dias")
            # DECISÃO (revisão de 29/08): '_dias' mede coisas diferentes por estado — em
            # 'aberta' é IDADE (quanto tempo já passou, e ainda está contando); em 'encerrada'
            # é DURAÇÃO (quanto tempo durou, do Início ao Fim, parado no passado). O cabeçalho
            # 'Há' prometia idade nos dois casos, e os dois nunca coincidem: a ocorrência
            # MAB200 mostrava 'Há 11 d' com 221 dias de idade real; SMP100 'Há 5 d' com 150;
            # TIM100 'Há 4 d' com 181 (casos reais, medidos ao vivo). 60% das linhas são
            # encerradas, então não é a exceção, é o caso comum.
            # Mantive as DUAS leituras (não colapsei pra uma só idade) porque o `alarme` logo
            # abaixo já trata as encerradas como passado resolvido, não pendência — perder a
            # distinção aqui destruiria essa régua. Em vez disso: cabeçalho virou 'Dias' (vale
            # nos dois casos, não promete só idade) e cada célula se rotula pelo próprio estado,
            # então a leitura errada exige ignorar a palavra na própria célula.
            if dias is None:
                ha_txt = "—"
            elif estado == "encerrada":
                ha_txt = "durou %d d" % dias
            else:
                ha_txt = "há %d d" % dias
            alarme = dias is not None and dias > 30 and estado != "encerrada"
            ha_cor = tickets_spec.COR_ESTADO["aberta"] if alarme else TEXT

            vals = (str(oc.get("Usina") or "—")[:24], valor_extra(oc), os_txt, causa_txt,
                    _fmt_dt(oc.get("Início da ocorrência")), ha_txt)
            cores = (TEXT, TEXT, os_cor, MUTED if causa in (None, "") else TEXT, TEXT, ha_cor)
            for c, (v, cr) in enumerate(zip(vals, cores), start=1):
                it = QTableWidgetItem(str(v))
                it.setForeground(_cor(cr))
                # tudo centralizado menos a Causa raiz (Levi, 30/08): ela é a única coluna de
                # texto corrido e de largura variável — centralizar faria cada linha começar
                # num ponto diferente, e o olho perde a coluna ao descer a lista.
                if c != 4:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if c == 4 and causa_txt != causa_completa:      # causa raiz truncada: o resto no hover
                    it.setToolTip(causa_completa)
                self.tab.setItem(r, c, it)
        self.tab.blockSignals(False)

    # ── seleção ──────────────────────────────────────────────────────────────────────────
    @slot_seguro
    def _sel_tabela(self):
        r = self.tab.currentRow()
        if 0 <= r < len(self._visiveis):
            self._selecionar(self._visiveis[r])

    def _selecionar(self, oc):
        self._sel = oc
        if oc is None:
            self._p_conteudo.setVisible(False)
            self._p_hint.setVisible(True)
            return
        self._p_conteudo.setVisible(True)
        self._p_hint.setVisible(False)

        estado = oc["_estado"]
        cor = tickets_spec.COR_ESTADO.get(estado, MUTED)
        num_os = str(oc.get("OS") or "").strip()
        status_os = str(oc.get("Status da OS") or "").strip()
        self._p_row.setText("linha %s" % oc.get("_row", "—"))
        if num_os:
            self._p_estado_topo.setText("·  OS %s está: %s" % (num_os, status_os or "—"))
            topo_cor = cor
        elif estado == "encerrada":
            # mesma razão do 'OS' neutro que _pinta_tabela já aplica na tabela: sem coluna OS
            # ainda, uma ocorrência encerrada foi fechada por Fim digitado à mão, nada a ver
            # com falta de atendimento -- 'SEM OS' em vermelho alarmaria por um caso já
            # resolvido. Medido em 29/08: 801 das 1.327 ocorrências das duas abas (60%) estão
            # encerradas -- esse era o caso comum, não a exceção, e o revisor pegou porque eu
            # só tinha testado com uma linha aberta.
            self._p_estado_topo.setText("·  %s" % tickets_spec.NOME_ESTADO[estado].upper())
            topo_cor = cor
        else:
            self._p_estado_topo.setText("·  SEM OS")
            topo_cor = tickets_spec.COR_ESTADO["aberta"]
        self._p_estado_topo.setStyleSheet(
            "color:%s;font-size:10px;font-weight:800;background:transparent;border:none;"
            "letter-spacing:1.2px;" % topo_cor)

        self._p_usina.setText(str(oc.get("Usina") or "—"))
        self._repintar_ident(oc)
        self._repintar_ciclo(estado)
        self._p_aviso.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:11px;}"
                                    % (_rgba(cor, 0.10), _rgba(cor, 0.45)))
        self._p_aviso_txt.setText(_TXT_AVISO.get(estado, ""))

        causa = oc.get("Causa raiz")
        self._p_causa.setText(str(causa) if causa not in (None, "") else "")
        resp = oc.get("Responsabilidade da Grid Co.?")
        self._p_resp.setText(str(resp) if resp not in (None, "") else "—")

        self._p_ini.setText(_fmt_dt(oc.get("Início da ocorrência")))
        fim = oc.get("Fim da ocorrência")
        self._p_fim.setText("em aberto" if fim in (None, "") else _fmt_dt(fim))
        horas = oc.get("_horas")
        self._p_indisp.setText("%.1f h" % horas if horas is not None else "—")

        coment = oc.get("Comentários gerais")
        self._p_coment.setPlainText(str(coment) if coment not in (None, "") else "")

    def _repintar_ident(self, oc):
        """ATIVO · SKID · CABINE. Em Trackers vêm direto da planilha (SKID) ou são fixos
        (Cabine — a cadeia do tracker nunca passa por lá, medido em tickets_ativo). Em Strings
        vêm do catálogo via _achar_inversor + skid_de/cabine_de."""
        _limpar_layout(self._ident_box)
        if self._aba == "Trackers":
            trk = oc.get("Nº do tracker / Identificação")
            skid = oc.get("Nº do SKID")
            campos = [("ATIVO", "Tracker %s" % trk if trk not in (None, "") else "—", GREEN, False),
                      ("SKID", str(skid) if skid not in (None, "") else "—", TEXT, False),
                      ("CABINE", "não se aplica a tracker", MUTED, True)]
        else:
            inv_nome = oc.get("Inversor")
            campos = [("ATIVO", str(inv_nome) if inv_nome not in (None, "") else "—", GREEN, False)]
            if not self._ativos_prontos:
                campos += [("SKID", "carregando catálogo…", MUTED, True),
                          ("CABINE", "carregando catálogo…", MUTED, True)]
            elif self._ativos_falhou:
                campos += [("SKID", "catálogo indisponível", MUTED, True),
                          ("CABINE", "catálogo indisponível", MUTED, True)]
            else:
                ativo = _achar_inversor(inv_nome, oc.get("Usina"), self._todos_ativos)
                if ativo is None:
                    campos += [("SKID", "não encontrado no catálogo", MUTED, True),
                              ("CABINE", "não encontrado no catálogo", MUTED, True)]
                else:
                    sk = tickets_ativo.skid_de(ativo, self._por_id)
                    cb = tickets_ativo.cabine_de(ativo, self._por_id)
                    campos += [("SKID", api._asset_short_name(sk) if sk else "não encontrado no catálogo",
                               TEXT if sk else MUTED, not bool(sk)),
                              ("CABINE", api._asset_short_name(cb) if cb else "não encontrado no catálogo",
                               TEXT if cb else MUTED, not bool(cb))]
        for rot, val, cor_v, ital in campos:
            c = QVBoxLayout()
            c.setSpacing(1)
            c.addWidget(_lbl(rot, MUTED, 9, 800, esp=1.1))
            c.addWidget(_lbl(val, cor_v, 12.5, 400 if ital else 700, ital=ital))
            w = QWidget()
            w.setLayout(c)
            self._ident_box.addWidget(w)
        self._ident_box.addStretch(1)

    def _repintar_ciclo(self, estado):
        """A barra de ciclo de vida — elemento PRINCIPAL do painel. Nesta fase só 'aberta' e
        'encerrada' acontecem de verdade (sem coluna OS); os 3 estados do meio ficam desenhados
        prontos para a fase 2, sem precisar redesenhar a tela quando ela chegar."""
        _limpar_layout(self._ciclo_box)
        chaves = [k for k, _, _ in tickets_spec.ESTADOS]
        idx_atual = chaves.index(estado) if estado in chaves else 0
        for i, (k, nome, cor) in enumerate(tickets_spec.ESTADOS):
            passou, agora = i < idx_atual, i == idx_atual
            c = cor if (passou or agora) else BORDER
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            ponto = QLabel("●" if (passou or agora) else "○")
            ponto.setStyleSheet("color:%s;font-size:%spx;background:transparent;border:none;"
                                % (c, 14 if agora else 10))
            ponto.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(ponto)
            col.addWidget(_lbl(nome, c if agora else MUTED, 8.5, 800 if agora else 600))
            w = QWidget()
            w.setLayout(col)
            self._ciclo_box.addWidget(w)
            if i < len(tickets_spec.ESTADOS) - 1:
                tr = QFrame()
                tr.setFixedHeight(2)
                tr.setStyleSheet("background:%s;border:none;margin-bottom:13px;"
                                 % (cor if passou else BORDER))
                self._ciclo_box.addWidget(tr, 1)

    def reiniciar(self):
        """Entrar de novo = filtros limpos (mesmo padrão de AtivosTab). Os dados já carregados
        continuam — reabrir a aba não bate na API de novo."""
        self._busca.blockSignals(True)
        self._busca.clear()
        self._busca.blockSignals(False)
        self._estados_filtro.clear()
        self._usina_filtro = ""
        self._repintar()
