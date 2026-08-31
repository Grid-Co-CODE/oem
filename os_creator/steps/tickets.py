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

from PyQt6.QtCore import Qt, QTimer, QDate, QTime
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QLineEdit,
                             QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
                             QAbstractItemView, QScrollArea, QTextEdit, QSizePolicy,
                             QComboBox, QAbstractScrollArea, QMenu, QCalendarWidget,
                             QStyledItemDelegate, QStyleOptionViewItem,
                             QTimeEdit)

import api
import tickets_api
import tickets_ativo
import tickets_calc
import tickets_diario
import tickets_escrita
import tickets_spec
from steps import lupa_os
from steps.ui import BG, CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED
from workers import ApiWorker, slot_seguro

# perto do que a aba Ativos já usa (LIMITE_TABELA=400): Trackers tem 2.781 linhas na planilha,
# e desenhar todas de uma vez é custo de layout sem ganho — quem quer uma usina específica usa
# a busca ou o filtro de usina à esquerda.
_LIMITE_TABELA = 400

# Cores escolhidas pelo Levi em 31/08 para a tabela.
_REALCE = "#A27D3F"      # a linha clicada, inteira
_GRADE = "#3D61A6"       # as linhas da grade
_TINTA_REALCE = "#141824"  # o texto sobre o dourado; ver _pintar_selecao
_COR_ORIGINAL = 260        # papel do item onde a cor "de verdade" da célula fica guardada

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
def _so_numero(v):
    """'02' -> '2'. A planilha guarda a cabine com zero à esquerda; é formatação de quem
    digitou, não parte do número (Levi, 31/08). Texto que não for número passa inteiro — há
    cabine escrita como '1A' e cortar o zero de '01A' quebraria o nome."""
    t = str(v or "").strip()
    if not t:
        return "—"
    return str(int(t)) if t.isdigit() else t


# Colunas que mudam com a aba. DUAS colunas em Trackers desde 31/08: Cabine e Tracker vinham
# grudadas num "02 / 93" que não dava para ordenar nem ler em coluna.
_EXTRA_COL = {
    # "Cabine", não "Skid": mesmo vocabulário do painel desde 31/08 — ver _repintar_ident.
    "Trackers": [("Cabine", lambda oc: _so_numero(oc.get("Nº do SKID"))),
                 ("Tracker", lambda oc: str(oc.get("Nº do tracker / Identificação") or "—"))],
    "Strings": [("Inversor", lambda oc: str(oc.get("Inversor") or "—"))],
}

# a ordem das colunas da tabela; as extras entram depois da Usina
_FIXAS_ANTES = ["", "Usina"]
_FIXAS_DEPOIS = ["OS", "Causa raiz", "Início da ocorrência", "Período"]


def colunas_da_aba(aba):
    """Nomes das colunas, na ordem. Trackers tem 8 (Cabine E Tracker), Strings tem 7."""
    return _FIXAS_ANTES + [r for r, _ in _EXTRA_COL[aba]] + _FIXAS_DEPOIS


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


def _ativos_da_usina(usina_ticket, todos):
    """Todos os ativos do catálogo que pertencem à usina citada no ticket.

    Mesmo casamento em dois passos do `_achar_inversor`, e pela mesma razão: a coluna 'Usina' é
    MISTA — a maioria traz o código ('TIM100'), 24% trazem o nome de exibição ('Demerval Lobao').
    Tenta o código, que é preciso quando existe, e só cai para o nome quando o escopo por código
    vier vazio."""
    un = api._norm_txt(usina_ticket)
    if not un or not todos:
        return []
    por_codigo = [a for a in todos if _codigo_bate_usina(api._norm_txt(a.get("code")), un)]
    if por_codigo:
        return por_codigo
    return [a for a in todos if _nomes_de_usina_batem(un, api._norm_txt(a.get("usina")))]


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

    RECURSIVO: `_pinta_estados` põe LAYOUTS dentro de layouts (a barra segmentada monta cada
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


def _abrir_popup(pop, ancora):
    """Mostra o popup colado na âncora e SEMPRE dentro da tela.

    Os dois jeitos de errar isto apareceram na verificação de 31/08. O calendário do 'Fim da
    ocorrência' nasce abaixo do campo, que fica no pé do painel: metade dele — inclusive os
    botões usar/limpar — caía fora do monitor. E o histórico de comentários abria a partir de um
    botão que estava ROLADO PARA FORA da área visível, então ia para uma coordenada fora da
    tela: o popup existia, não levantava erro nenhum e ninguém via.

    Não cabendo abaixo, abre acima; não cabendo dos dois lados, encosta na borda."""
    pop.adjustSize()
    tela = QApplication.primaryScreen().availableGeometry()
    canto = ancora.mapToGlobal(ancora.rect().bottomLeft())
    x = min(max(tela.left() + 8, canto.x()), max(tela.left() + 8, tela.right() - pop.width() - 8))
    y = canto.y() + 2
    if y + pop.height() > tela.bottom() - 8:
        acima = ancora.mapToGlobal(ancora.rect().topLeft()).y() - pop.height() - 2
        if acima >= tela.top() + 8:
            y = acima
    # TRAVA FINAL, e é ela que garante o resultado: abrir "acima" só resolve quando a âncora
    # está na tela. O botão de histórico vive DENTRO da área de rolagem do painel e pode estar
    # rolado para fora da vista — aí tanto o abaixo quanto o acima caem fora do monitor.
    # Medido em 31/08: sem esta linha o popup nascia 46px além da borda de baixo.
    y = max(tela.top() + 8, min(y, tela.bottom() - pop.height() - 8))
    pop.move(x, y)
    pop.show()


def _menu(dono):
    """QMenu no tema da tela. O padrão do Qt vem CLARO — no navy vira um retângulo branco no
    meio da tela. A folha precisa ser repetida em cada submenu: estilo de QMenu não desce
    sozinho para o menu filho."""
    m = QMenu(dono)
    m.setStyleSheet(
        "QMenu{background:%s;border:1px solid %s;border-radius:10px;padding:6px;}"
        "QMenu::item{color:%s;padding:7px 30px 7px 14px;border-radius:7px;font-size:12px;}"
        "QMenu::item:selected{background:%s;color:%s;}"
        "QMenu::separator{height:1px;background:%s;margin:5px 8px;}"
        % (CARD, BORDER, TEXT, GREEN, GREEN_INK, BORDER))
    return m


def _qss_barra():
    """Botão da barra do topo: mesma caixa dos campos, para alinhar com os segmentos de estado
    e com a busca. Sem padding vertical — ele entraria POR FORA da altura fixa."""
    return ("QPushButton{background:%s;border:1px solid %s;border-radius:10px;"
            "padding:0px 12px;min-height:0px;color:%s;font-size:12px;font-weight:700;"
            "text-align:left;}"
            "QPushButton:hover{border-color:%s;}" % (INPUT, BORDER, TEXT, GREEN))


def _qss_campo(cor_texto=MUTED):
    # Fundo SEMPRE o INPUT (Levi, 28/08): um fundo mais escuro que o card vira buraco na tela.
    # Nesta fase TODO campo é somente-leitura — a cor do texto (MUTED, o padrão aqui) é o único
    # sinal disso, nunca o fundo (senão o campo para de parecer um campo). A busca do cabeçalho
    # é a exceção: é o único campo que a pessoa de fato usa, e passa cor_texto=TEXT.
    # min-height:0 — sem isso o Qt impõe uma altura mínima de conteúdo (42px medidos) que
    # nem setFixedHeight vence, e o campo fica com o dobro da altura pedida.
    return ("background:%s;border:1px solid %s;border-radius:9px;padding:0px 10px;min-height:0px;"
            "color:%s;font-size:12.5px;" % (INPUT, BORDER, cor_texto))


def _campo(ph="", editavel=False):
    """Campo do painel. `editavel` muda três coisas ao mesmo tempo, de propósito: deixa digitar,
    acende o texto (MUTED lê como desligado) e fixa a altura dos botões da barra — o Levi pediu
    o mesmo tamanho dos segmentos de estado (31/08). A altura precisa vir por `max-height` na
    folha: o mínimo de conteúdo do QLineEdit sobrevive a setFixedHeight."""
    e = QLineEdit()
    e.setReadOnly(not editavel)
    if ph:
        e.setPlaceholderText(ph)
    if editavel:
        e.setStyleSheet("QLineEdit{%s min-height:%dpx;max-height:%dpx;}"
                        "QLineEdit:focus{border-color:%s;}"
                        % (_qss_campo(TEXT), _ALTURA_QSS, _ALTURA_QSS, GREEN))
    else:
        e.setStyleSheet("QLineEdit{%s}" % _qss_campo())
    return e


class _CampoData(QLineEdit):
    """Campo de data com calendário — e que continua sendo um campo de texto.

    Herda de QLineEdit de propósito, em vez de virar um QDateTimeEdit: o QDateTimeEdit NÃO SABE
    ficar vazio, e vazio aqui tem significado — 'Fim da ocorrência' em branco é o que define a
    ocorrência como aberta. Ele também obrigaria a digitar no formato dele. Assim o texto livre
    continua valendo (inclusive as grafias antigas da planilha) e o calendário é um atalho."""

    def __init__(self, ph=""):
        super().__init__()
        if ph:
            self.setPlaceholderText(ph)
        self.setStyleSheet("QLineEdit{%s min-height:%dpx;max-height:%dpx;padding-right:26px;}"
                           "QLineEdit:focus{border-color:%s;}"
                           % (_qss_campo(TEXT), _ALTURA_QSS, _ALTURA_QSS, GREEN))
        self._b = QPushButton("▾", self)
        self._b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b.setFixedSize(22, _ALTURA_QSS - 6)
        self._b.setStyleSheet("QPushButton{background:transparent;border:none;color:%s;"
                              "font-size:12px;font-weight:800;padding:0px;}"
                              "QPushButton:hover{color:%s;}" % (MUTED, GREEN))
        self._b.clicked.connect(self._abrir)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._b.move(self.width() - self._b.width() - 4, (self.height() - self._b.height()) // 2)

    @slot_seguro
    def _abrir(self, *_):
        pop = QFrame(self, Qt.WindowType.Popup)
        pop.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:11px;}"
                          % (CARD, BORDER))
        v = QVBoxLayout(pop)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        cal = QCalendarWidget()
        cal.setGridVisible(False)
        cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        cal.setStyleSheet(
            "QCalendarWidget QWidget{background:%s;color:%s;}"
            "QCalendarWidget QAbstractItemView{background:%s;color:%s;selection-background-color:%s;"
            "selection-color:%s;outline:0;}"
            "QCalendarWidget QAbstractItemView:disabled{color:%s;}"
            "QCalendarWidget QToolButton{background:transparent;color:%s;border:none;"
            "font-size:12px;font-weight:700;padding:4px 8px;}"
            "QCalendarWidget QToolButton:hover{color:%s;}"
            "QCalendarWidget QMenu{background:%s;color:%s;}"
            "QCalendarWidget QSpinBox{background:%s;color:%s;border:1px solid %s;}"
            % (CARD, TEXT, CARD, TEXT, GREEN, GREEN_INK, MUTED, TEXT, GREEN, CARD, TEXT,
               INPUT, TEXT, BORDER))
        atual = tickets_calc._para_dt(self.text())
        if atual is not None:
            cal.setSelectedDate(QDate(atual.year, atual.month, atual.day))
        v.addWidget(cal)

        linha = QHBoxLayout()
        linha.setSpacing(8)
        linha.addWidget(_lbl("hora", MUTED, 10.5, 700))
        hora = QTimeEdit()
        hora.setDisplayFormat("HH:mm")
        hora.setTime(QTime(atual.hour, atual.minute) if atual is not None else QTime(0, 0))
        hora.setStyleSheet("QTimeEdit{background:%s;border:1px solid %s;border-radius:8px;"
                           "color:%s;font-size:12px;padding:2px 6px;min-height:0px;}"
                           % (INPUT, BORDER, TEXT))
        linha.addWidget(hora)
        linha.addStretch(1)
        b_limpar = QPushButton("limpar")
        b_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        b_limpar.setStyleSheet("QPushButton{background:transparent;border:none;color:%s;"
                               "font-size:11px;font-weight:700;}"
                               "QPushButton:hover{color:%s;}" % (MUTED, GREEN))
        b_ok = QPushButton("usar")
        b_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ok.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:8px;"
                           "padding:5px 14px;font-size:11px;font-weight:800;}"
                           % (GREEN, GREEN_INK))
        linha.addWidget(b_limpar)
        linha.addWidget(b_ok)
        v.addLayout(linha)

        def usar():
            d, h = cal.selectedDate(), hora.time()
            self.setText("%02d/%02d/%04d %02d:%02d" % (d.day(), d.month(), d.year(),
                                                       h.hour(), h.minute()))
            # setText NÃO dispara textEdited (só a digitação dispara), e sem isto o Salvar
            # continuaria apagado depois de escolher a data no calendário.
            self.textEdited.emit(self.text())
            pop.close()

        def limpar():
            self.setText("")
            self.textEdited.emit("")
            pop.close()

        b_ok.clicked.connect(lambda *_: usar())
        b_limpar.clicked.connect(lambda *_: limpar())
        cal.activated.connect(lambda *_: usar())          # duplo clique no dia já resolve
        _abrir_popup(pop, self)


# ── comentários datados (Levi, 31/08) ──────────────────────────────────────────────────────
# A coluna 'Comentários gerais' vira um LOG: uma linha por comentário, com data e autor. O que
# já estava lá entra como bloco único e SEM autor — não dá para inventar quem escreveu.
_COMENTARIO = re.compile(r"^(\d{2}/\d{2}/\d{4} \d{2}:\d{2})\s+—\s+([^:]{1,40}):\s*(.*)$")


def comentarios_de(texto):
    """[(quando, quem, texto)]. Entrada antiga vem como (None, None, bloco inteiro)."""
    linhas = str(texto or "").replace("\r", "").split("\n")
    entradas, antigo = [], []
    for l in linhas:
        m = _COMENTARIO.match(l.strip())
        if m:
            entradas.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
        elif l.strip() and not entradas:
            antigo.append(l.strip())          # antes do primeiro marcador: histórico sem autor
        elif l.strip():
            # continuação de um comentário de várias linhas
            q, w, t = entradas[-1]
            entradas[-1] = (q, w, (t + "\n" + l.strip()).strip())
    if antigo:
        entradas.insert(0, (None, None, "\n".join(antigo)))
    return entradas


def para_iso(texto):
    """'20/08/2026 14:03' → '2026-08-20 14:03:00'. Devolve o texto cru se não for data.

    A coluna guarda ISO (conferido no dado real), mas a tela mostra e aceita dd/mm/aaaa. Gravar
    do jeito que foi digitado deixaria a mesma coluna com dois formatos — o nosso parser aguenta,
    quem lê a planilha e quem ordena por data, não."""
    d = tickets_calc._para_dt(texto)
    return d.strftime("%Y-%m-%d %H:%M:%S") if d is not None else str(texto or "").strip()


def acrescentar_comentario(texto_atual, novo, quem, agora=None):
    """Devolve a coluna com o comentário novo no fim, datado e assinado."""
    novo = (novo or "").strip()
    if not novo:
        return texto_atual or ""
    carimbo = (agora or datetime.now()).strftime("%d/%m/%Y %H:%M")
    linha = "%s — %s: %s" % (carimbo, quem, novo)
    atual = str(texto_atual or "").rstrip()
    return (atual + "\n" + linha) if atual else linha


def _combo(opcoes):
    """Campo de escolha, na mesma caixa e altura do _campo editável."""
    c = QComboBox()
    c.addItems(opcoes)
    c.setCursor(Qt.CursorShape.PointingHandCursor)
    c.setStyleSheet(
        "QComboBox{background:%s;border:1px solid %s;border-radius:9px;padding:0px 10px;"
        "min-height:%dpx;max-height:%dpx;color:%s;font-size:12.5px;}"
        "QComboBox:hover{border-color:%s;}"
        "QComboBox::drop-down{border:none;width:22px;}"
        # o Qt não desenha seta neste tema — sem isto o campo parece texto e ninguém descobre
        # que é uma escolha. Triângulo feito com bordas, que é o que o QSS aceita no subcontrole.
        "QComboBox::down-arrow{width:0px;height:0px;margin-right:7px;"
        "border-left:4px solid transparent;border-right:4px solid transparent;"
        "border-top:5px solid %s;}"
        "QComboBox QAbstractItemView{background:%s;color:%s;border:1px solid %s;"
        "selection-background-color:%s;selection-color:%s;outline:0;}"
        % (INPUT, BORDER, _ALTURA_QSS, _ALTURA_QSS, TEXT, GREEN, GREEN, CARD, TEXT, BORDER,
           GREEN, GREEN_INK))
    return c


def _rotulado(rotulo, widget, dica=None, cor_dica=GREEN):
    """Rótulo do campo. A dica entra no MESMO texto, separada por travessão e no mesmo cinza
    (Levi, 31/08): pintada e solta ao lado, ela competia com o rótulo em vez de completá-lo."""
    w = QWidget()
    w.setStyleSheet("background:%s;" % CARD)      # ver a nota do QScrollArea em _coluna_painel
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    t = QHBoxLayout()
    t.setSpacing(7)
    t.addWidget(_lbl("%s - %s" % (rotulo, dica) if dica else rotulo, MUTED, 10.5, 700))
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


# altura dos controles da barra do topo. Levi, 31/08: "reduza o tamanho em 50%%". Precisa ser
# FIXA em cada um: o QSS global do app (app.py:50) poe padding:9px em QPushButton e
# padding:7px nos campos, e isso entra na altura mesmo quando o estilo local pede menos.
_ALTURA_BARRA = 31      # altura VISÍVEL na tela (Levi, 31/08: metade dos 58 anteriores, e os
                        # campos do painel "do mesmo tamanho dos botões de aberto/encerrada").
_ALTURA_QSS = _ALTURA_BARRA - 2   # a folha de estilo mede o CONTEÚDO: a borda de 1px de cada
                        # lado entra por fora. Pedir 31 no QSS dá 33 na tela.
                        #
                        # E a folha precisa dizer min-height E max-height, os dois: `min-height:0`
                        # sozinho derruba o mínimo que setFixedHeight tinha posto, e o layout
                        # espreme o campo quando o painel fica apertado — medido em 31/08, os
                        # campos do painel nasceram com 21px pedindo 29. Sem nenhum min-height,
                        # o Qt impõe 42 e nem a altura fixa vence. Só a dupla resolve.


class _RealceDaLinha(QStyledItemDelegate):
    """Pinta o fundo da linha escolhida — e só isso.

    Existe porque `item.setBackground()` não pinta nada quando a tabela tem folha de estilo: com
    QSS na view, o Qt ignora o BackgroundRole do modelo. E a seleção nativa está desligada de
    propósito (ver a nota em `setSelectionMode`), porque o estilo desenhava uma barra na aresta
    de cada célula e repintava o texto, apagando a cor de estado da tarja."""

    def __init__(self, dono):
        super().__init__(dono)
        self._dono = dono

    def updateEditorGeometry(self, editor, option, index):
        """O editor OCUPA A CÉLULA INTEIRA (Levi, 31/08: "pega só metade para baixo da linha").
        Sozinho, o Qt dá ao editor o tamanho que ele pede e o encosta embaixo; aqui a geometria
        é imposta depois, então nem a altura mínima do QLineEdit nem o padding do QSS global
        conseguem encolhê-lo."""
        editor.setGeometry(option.rect.adjusted(2, 2, -2, -2))

    def paint(self, painter, option, index):
        if index.row() != getattr(self._dono, "_linha_sel", -1):
            super().paint(painter, option, index)
            return
        painter.fillRect(option.rect, QColor(_REALCE))
        super().paint(painter, option, index)


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
        # O NÚMERO EM VERDE (Levi, 31/08). O texto de um QPushButton é de uma cor só — ele não
        # aceita rich text —, então o rótulo e a contagem viram dois QLabel dentro do próprio
        # botão. `WA_TransparentForMouseEvents` é o que mantém o clique funcionando: sem isso o
        # rótulo engole o clique e o filtro para de responder no meio do botão.
        lb = QHBoxLayout(b)
        lb.setContentsMargins(16, 0, 16, 0)
        lb.setSpacing(9)
        lb.addStretch(1)
        for texto, cor_txt, peso in ((rotulo, TEXT if ligado else MUTED, 700),
                                     (str(n), GREEN, 800)):
            q = QLabel(texto)
            q.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            q.setStyleSheet("color:%s;background:transparent;border:none;font-size:12px;"
                            "font-weight:%d;" % (cor_txt, peso))
            lb.addWidget(q)
        lb.addStretch(1)
        # cantos só nas pontas, para o conjunto ler como UM bloco
        e = "10px" if primeiro else "0"
        d = "10px" if ultimo else "0"
        b.setStyleSheet(
            "QPushButton{color:%s;background:transparent;border:none;"
            "border-top:2px solid transparent;"
            "border-top-left-radius:%s;border-bottom-left-radius:%s;"
            "border-top-right-radius:%s;border-bottom-right-radius:%s;"
            "padding:0px 16px;font-size:12px;font-weight:700;text-align:center;}"
            "QPushButton:hover{color:%s;}"
            "QPushButton:checked{color:%s;background:%s;border-top:2px solid %s;}"
            % (MUTED, e, e, d, d, TEXT, cor, _rgba(cor, 0.13), cor))
        # o botão vai DENTRO do quadro, que tem 1px de borda em cima e embaixo: com a altura
        # cheia aqui o controle fecharia em 33 e ficaria 2px mais alto que a busca e que os
        # campos do painel — justamente o alinhamento que o Levi pediu.
        b.setFixedHeight(_ALTURA_QSS)
        # O BOTÃO PRECISA CABER O QUE ESTÁ DENTRO DELE (Levi, 31/08: "ficaram comprimidos"). Com
        # os rótulos dentro de um layout, o sizeHint do QPushButton continua sendo o do seu
        # TEXTO — que está vazio —, então o Qt achava que 30px bastavam e os nomes saíam
        # cortados ("Aberta" virou "Al"). A largura mínima vem do layout, que é quem sabe.
        b.setMinimumWidth(lb.sizeHint().width())
        b.clicked.connect(lambda _c=False, k=chave: ao_clicar(k))
        return b


# Barra de rolagem: sem isto o Qt desenha a do Windows, cinza-claro (#EFEFEF), que grita no
# meio do navy — foi o "plano de fundo mais claro" que o Levi apontou em 30/08 depois de eu
# ter consertado o escuro. Fina, sem setas, e só a alça visível.
_QSS_SCROLLBAR = """
QScrollBar:vertical{background:transparent;width:9px;margin:0;}
QScrollBar::handle:vertical{background:%s;border-radius:4px;min-height:30px;}
QScrollBar::handle:vertical:hover{background:%s;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;border:none;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}
QScrollBar:horizontal{background:transparent;height:9px;margin:0;}
QScrollBar::handle:horizontal{background:%s;border-radius:4px;min-width:30px;}
QScrollBar::handle:horizontal:hover{background:%s;}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;border:none;}
QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:transparent;}
QScrollBar::corner{background:transparent;}
/* A ARMADILHA: dar setStyleSheet num widget liga o fundo estilizado nele. Sem uma regra de cor
   para o PRÓPRIO widget, o Qt pinta o cinza padrão do sistema (#EFEFEF) — um sexto da tela ficou
   cinza-claro no meio do navy assim que eu acrescentei o estilo das barras. Toda folha de
   estilo aplicada num container precisa dizer a cor do container. */
TicketsTab{background:%s;}
QAbstractScrollArea{background:%s;}
QTableWidget{background:%s;}
QTableWidget QWidget{background:%s;}
""" % (BORDER, MUTED, BORDER, MUTED, BG, CARD, CARD, CARD)


def _carregar_aba(sheet_id):
    """As ocorrências E o diário, na mesma thread do worker.

    O diário é opcional de propósito: aba ainda não criada, token ausente, API fora do ar — nada
    disso pode impedir a tela de ABRIR. Sem ele a tela mostra o que o banco tem, que é o
    comportamento de antes; com ele, mostra também o que o app gravou e o sync desfez."""
    linhas = tickets_api.listar_linhas(sheet_id)
    try:
        diario = tickets_diario.ler()
    except Exception as e:                       # noqa: BLE001 — ver a docstring
        print("[tickets] diário indisponível (%s: %s)" % (type(e).__name__, str(e)[:120]))
        diario = []
    return linhas, diario


class TicketsTab(QWidget):
    """Catálogo de ocorrências: lista + painel. Leitura."""
    _selfnav = True          # o wrapper do app NÃO põe a barra de Voltar — o daqui é o único

    def __init__(self, on_voltar=None):
        super().__init__()
        self._on_voltar = on_voltar
        self._aba = "Trackers"
        self._ocs, self._sel = [], None
        self._visiveis = []
        # (coluna, descendente). None = a ordem padrão de `ordenar_ocorrencias`: o que precisa de
        # atenção primeiro. Clicar num cabeçalho troca; clicar de novo inverte; o terceiro clique
        # devolve o padrão, para ninguém ficar preso numa ordem que não quis.
        self._ordem = None
        self._estados_filtro = set()      # vazio = todos os estados
        self._usina_filtro = ""
        self._todos_ativos, self._por_id = [], {}
        self._ativos_prontos = False
        self._ativos_falhou = False
        self._w = self._wa = None
        # edicao (fase 2): _populando cala os sinais enquanto a tela preenche os campos;
        # _sujo é o que acende o Salvar e avisa que há coisa digitada sem gravar.
        self._populando = False
        self._sujo = False
        self.setStyleSheet(_QSS_SCROLLBAR)
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
        # sub-layout SÓ dos segmentos: `_pinta_estados` limpa este, não a barra inteira. Antes
        # o combo morava no mesmo layout e era DESTRUÍDO a cada repintura — ficava órfão,
        # desalinhado e cortado pelo card de baixo.
        self._seg_box = QHBoxLayout()
        self._seg_box.setSpacing(0)
        self._tiles_box.addLayout(self._seg_box)
        # A usina virou BOTÃO com menu, não mais um combo (Levi, 31/08): 63 usinas numa lista
        # única é rolagem sem fim. O menu abre por CLIENTE e só então mostra as usinas dele —
        # dois cliques em vez de caçar na lista.
        self._b_usina = QPushButton("Todas as usinas")
        self._b_usina.setFixedWidth(250)
        self._b_usina.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_usina.setStyleSheet(_qss_barra())
        # ALTURA depois da folha de estilo: o QSS global do app (app.py:42) põe padding nos
        # campos, e o padding entra na altura. Altura fixa antes do stylesheet não segura —
        # medido: pedi 38 e o controle nasceu com 58, desalinhado dos chips ao lado.
        self._b_usina.setFixedHeight(_ALTURA_BARRA)
        self._b_usina.clicked.connect(self._menu_usinas)
        self._tiles_box.addWidget(self._b_usina)
        self._tiles_box.addStretch(1)
        # A BUSCA MORA AQUI, não no cabeçalho (Levi, 31/08: "na mesma LINHA dos botões de
        # aberta, encerrada"). Fica fora do _seg_box de propósito: aquele é limpo a cada
        # repintura e levaria o campo junto, apagando o que a pessoa digitou.
        self._tiles_box.addWidget(self._campo_busca())
        raiz.addLayout(self._tiles_box)

        # DUAS colunas desde o redesenho de 30/08 (direção "tabela protagonista"): a coluna de
        # usinas virou um seletor na barra do topo e devolveu a largura para a tabela, que é o
        # que a pessoa de fato lê. Antes eram três caixas disputando espaço numa tela pequena.
        corpo = QHBoxLayout()
        corpo.setSpacing(16)
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
        # O TÍTULO É O SELETOR DE FONTE (Levi, 31/08). Antes eram dois chips ao lado do título
        # dizendo a mesma coisa que ele; agora o nome da aba faz parte da frase — "Tickets de
        # Trackers" — no verde da Grid e com a seta avisando que dá para trocar. Sai um controle
        # da barra e o título passa a dizer o que a tela está mostrando.
        lt = QHBoxLayout()
        lt.setSpacing(9)
        lt.addWidget(_lbl("Tickets de", TEXT, 20, 800))
        self._b_fonte = QPushButton()
        self._b_fonte.setCursor(Qt.CursorShape.PointingHandCursor)
        # mesma fonte e mesmo tamanho de "Tickets", só a cor muda — é uma palavra do título que
        # por acaso é clicável, não um botão colado no título.
        self._b_fonte.setStyleSheet(
            "QPushButton{background:transparent;border:none;padding:0px;text-align:left;"
            "color:%s;font-size:20px;font-weight:800;}"
            "QPushButton:hover{color:%s;}" % (GREEN, TEXT))
        self._b_fonte.clicked.connect(self._menu_fonte)
        lt.addWidget(self._b_fonte)
        lt.addStretch(1)
        cx.addLayout(lt)
        self._sub = _lbl("carregando ocorrências…", MUTED, 12)
        self._sub.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        cx.addWidget(self._sub)
        cab.addLayout(cx)
        cab.addStretch(1)
        self._pinta_fonte()
        return cab

    def _campo_busca(self):
        self._busca = QLineEdit()
        self._busca.setPlaceholderText("usina, cabine, tracker/inversor, causa…")
        # max-height na própria folha de estilo: o mínimo de conteúdo do QLineEdit sobrevive a
        # setFixedHeight e a setMinimumHeight(0) — só o QSS o vence (medido: 42 nos dois casos).
        self._busca.setStyleSheet("QLineEdit{%s min-height:%dpx;max-height:%dpx;}"
                                  % (_qss_campo(TEXT), _ALTURA_QSS, _ALTURA_QSS))
        self._busca.setFixedWidth(320)
        # zerar o mínimo ANTES da altura fixa: o QLineEdit guarda um mínimo de conteúdo próprio,
        # e setFixedHeight sozinho não desce abaixo dele (medido: pedia 29 e ficava em 42).
        self._t_busca = QTimer(self)
        self._t_busca.setSingleShot(True)
        self._t_busca.setInterval(220)
        self._t_busca.timeout.connect(self._repintar)
        self._busca.textChanged.connect(lambda *_: self._t_busca.start())
        return self._busca

    def _pinta_fonte(self):
        self._b_fonte.setText("%s  ▾" % self._aba)

    @slot_seguro
    def _menu_fonte(self, *_):
        m = _menu(self)
        for nome in tickets_spec.ABAS:
            a = m.addAction(nome)
            a.setCheckable(True)
            a.setChecked(nome == self._aba)
            a.triggered.connect(lambda _c=False, n=nome: self._trocar_aba(n))
        m.exec(self._b_fonte.mapToGlobal(self._b_fonte.rect().bottomLeft()))

    @slot_seguro
    def _menu_usinas(self, *_):
        """Drill-down cliente → usina (Levi, 31/08). Cliente vem do próprio ticket (é uma das
        15 colunas do núcleo), então não custa consulta nenhuma."""
        m = _menu(self)
        a = m.addAction("Todas as usinas")
        a.setCheckable(True)
        a.setChecked(not self._usina_filtro)
        a.triggered.connect(lambda _c=False: self._trocar_usina(""))
        m.addSeparator()
        por_cliente = {}
        for o in self._ocs:
            cli = str(o.get("Cliente") or "").strip() or "sem cliente informado"
            u = str(o.get("Usina") or "—")
            por_cliente.setdefault(cli, {})
            por_cliente[cli][u] = por_cliente[cli].get(u, 0) + 1
        # "sem cliente informado" por último: é falta de cadastro, não um cliente.
        for cli in sorted(por_cliente, key=lambda c: (c == "sem cliente informado",
                                                      api._norm_txt(c))):
            usinas = por_cliente[cli]
            sub = m.addMenu("%s   %d" % (cli, sum(usinas.values())))
            sub.setStyleSheet(m.styleSheet())     # estilo de QMenu não desce para o submenu
            for u, qtd in sorted(usinas.items(), key=lambda x: -x[1]):
                ac = sub.addAction("%s   %d" % (u, qtd))
                ac.setCheckable(True)
                ac.setChecked(u == self._usina_filtro)
                ac.triggered.connect(lambda _c=False, n=u: self._trocar_usina(n))
        m.exec(self._b_usina.mapToGlobal(self._b_usina.rect().bottomLeft()))

    def _coluna_lista(self):
        p = _Painel()
        topo = QHBoxLayout()
        topo.addWidget(_secao("OCORRÊNCIAS"))
        topo.addStretch(1)
        p.v.addLayout(topo)

        self.tab = QTableWidget(0, len(colunas_da_aba(self._aba)))
        # os nomes vêm de `colunas_da_aba`: a lista fixa que estava aqui ficou para trás quando
        # Trackers ganhou Cabine e Tracker separadas, e mostrava rótulos que não existiam mais
        # até a primeira repintura.
        self.tab.setHorizontalHeaderLabels(colunas_da_aba(self._aba))
        self.tab.verticalHeader().setVisible(False)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # SEM SELEÇÃO DO QT (Levi, 31/08: "não quero que mude a cor à esquerda" e "esse laranja
        # em cada célula é feião"). Provado por experimento: com a seleção ligada o estilo
        # desenha uma barra na aresta esquerda de cada célula e repinta o texto da linha, o que
        # apagava a cor de estado da tarja. Nenhuma regra de folha derruba isso. Quem marca a
        # linha é o `_pintar_selecao`, com o verde da Grid, e as cores de cada célula ficam.
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._linha_sel = -1
        self.tab.setItemDelegate(_RealceDaLinha(self))
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # duplo clique (ou F2) abre a edição, e só na coluna da Causa raiz — ver a nota em
        # _pinta_tabela. Clique simples continua só selecionando.
        self.tab.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                 | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tab.itemChanged.connect(self._causa_editada)
        self.tab.setShowGrid(False)
        # outline:0 + item:focus (custou tempo antes): sem isso o retângulo de foco da célula
        # clicada desenha uma borda por dentro do item e espreme o texto.
        self.tab.setStyleSheet(
            # CARD, não `transparent`: viewport transparente cai na cor BASE da paleta do sistema,
            # que é CLARA (#EFEFEF) — a tabela inteira ficava cinza dentro do navy. Só aparece
            # dentro da MainWindow, porque é ela quem instala a paleta; a tela isolada não
            # reproduzia, e foi por isso que passou em dois testes meus.
            "QTableWidget{background:%s;border:none;color:%s;font-size:12.5px;outline:0;"
            "gridline-color:%s;}"
            "QTableWidget QWidget{background:%s;}"
            # cabeçalho QUADRADO e sem fio lateral (Levi, 31/08): só o fio de baixo, para dar
            # a impressão de divisão sem desenhar uma caixa. O QHeaderView precisa da regra
            # própria — estilizar só ::section deixa o canto arredondado do widget aparecendo.
            "QHeaderView{background:%s;border:none;border-radius:0;}"
            "QHeaderView::section{background:%s;color:%s;border:none;border-radius:0;"
            "border-bottom:1px solid %s;padding:5px 4px;font-size:10px;font-weight:800;}"
            # O EDITOR DA CÉLULA (Levi, 31/08): ao dar duplo clique na causa raiz, a caixa de
            # digitar nascia mais alta que a linha e escorregava para baixo, invadindo a linha
            # seguinte. O culpado é o QSS global do app, que põe padding e altura mínima em todo
            # QLineEdit — o delegate dimensiona o editor pelo retângulo da célula, mas o mínimo
            # do widget vence e o excedente transborda.
            # A altura é FIXA e menor que a linha: só `min-height:0` fazia o editor encolher até
            # a altura do texto (11px medidos) e cortar as letras de baixo. 18px de conteúdo mais
            # as duas bordas cabem com folga na linha de 30px, e o delegate centraliza.
            "QTableWidget QLineEdit{background:%s;color:%s;border:1px solid %s;border-radius:5px;"
            "padding:0px 5px;margin:0px;min-height:0px;font-size:12.5px;}"
            "QTableWidget::item{padding:9px 4px;}"
            "QTableWidget::item:focus{border:none;outline:none;}"
            # A SELEÇÃO É PINTADA POR NÓS (Levi, 31/08: "não quero que mude a cor à esquerda" e
            # "esse laranja é feião, testa a cor grid"). Aqui o estilo é anulado: transparente
            # nos dois lugares. Quem pinta é o `_pintar_selecao`, item a item — assim o texto de
            # cada célula mantém a sua cor (SEM OS em vermelho, dias em alarme) e a tarja mantém
            # a cor do estado. Deixar com o estilo repintava tudo com a cor de seleção do QSS
            # global do app, e sobravam riscos nas divisas das células.
            "QTableWidget{selection-background-color:transparent;}"
            "QTableWidget::item:selected{background:transparent;border:none;}"
            % (CARD, TEXT, _GRADE, CARD, CARD, CARD, MUTED, BORDER, INPUT, TEXT, GREEN))
        self.tab.cellClicked.connect(self._sel_tabela)
        self.tab.horizontalHeader().setSectionsClickable(True)
        self.tab.horizontalHeader().sectionClicked.connect(self._ordenar_por)
        self.tab.setColumnWidth(0, 14)
        self.tab.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # QUEM ESTICA É A CAUSA RAIZ (col. 4), não a usina. Estava ao contrário: a usina esticava
        # e deixava um vão enorme entre a tarja e o texto, enquanto a causa raiz — que é o texto
        # LONGO e de largura variável — pedia todo o espaço que precisasse em ResizeToContents e
        # empurrava o painel da direita para FORA da tela. Medido em 1536px: o layout exigia
        # 1782px e o painel ficava cortado pela borda.
        cab = self.tab.horizontalHeader()
        self._ajustar_larguras()
        # GRADE (Levi, 31/08). Os riscos que apareciam antes na linha clicada não eram a grade
        # — eram o estilo desenhando a seleção nativa, que já está desligada. Com ela fora do
        # caminho, a grade pode voltar, e no azul que ele escolheu.
        self.tab.setShowGrid(True)
        self.tab.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        p.v.addWidget(self.tab, 1)
        self._rodape = _lbl("—", MUTED, 11.5)
        p.v.addWidget(self._rodape)
        return p

    def _coluna_painel(self):
        p = _Painel(400)          # 452 não cabia com a tabela em 1366px de notebook
        self._p_conteudo = QWidget()
        # A COR DO CARD, EXPLÍCITA — mesma armadilha do QScrollArea mais abaixo, e o Levi
        # apontou de novo em 31/08 ao clicar numa linha. Medido varrendo uma coluna de pixels da
        # tela renderizada: os widgets de dentro (rótulos, identificação, aviso, área de
        # rolagem) pintam #121A2B cada um por conta própria, mas os VÃOS do layout entre eles
        # mostravam #090D18, a cor da JANELA — porque este QWidget não pintava nada. Lia como
        # faixas escuras atravessando o painel.
        self._p_conteudo.setStyleSheet("background:%s;" % CARD)
        cv = QVBoxLayout(self._p_conteudo)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(12)

        # o título da seção CARREGA o estado (Levi, 28/08) — em vez de "OCORRÊNCIA" seco e
        # repetir a informação numa caixa abaixo.
        # O CICLO VIRA UMA FITA no topo (Levi, 30/08: "poderia ficar lá em cima em vez de ocupar
        # espaço"). Antes era uma linha inteira de bolinhas com rótulo embaixo — uns 40px numa
        # coluna que já não cabia. Os rótulos não fazem falta: o estado atual já está escrito no
        # cabeçalho, ao lado de "OCORRÊNCIA".
        self._ciclo_box = QHBoxLayout()
        self._ciclo_box.setContentsMargins(0, 0, 0, 0)
        self._ciclo_box.setSpacing(3)
        cv.addLayout(self._ciclo_box)

        topo = QHBoxLayout()
        topo.addWidget(_secao("OCORRÊNCIA"))
        self._p_estado_topo = _lbl("", tickets_spec.COR_ESTADO["aberta"], 10, 800, esp=1.2)
        topo.addWidget(self._p_estado_topo)
        topo.addStretch(1)
        self._p_row = _lbl("", MUTED, 10, ital=True)
        topo.addWidget(self._p_row)
        # o caminho de VOLTA para a visão geral. Sem ele, depois do primeiro clique numa linha a
        # pessoa nunca mais veria o panorama — a tabela não tem como "desselecionar".
        b_geral = QPushButton("visão geral  ✕")
        b_geral.setCursor(Qt.CursorShape.PointingHandCursor)
        b_geral.setStyleSheet("QPushButton{background:transparent;color:%s;border:none;"
                              "font-size:10px;font-weight:800;padding:0 0 0 10px;}"
                              "QPushButton:hover{color:%s;}" % (MUTED, GREEN))
        b_geral.clicked.connect(self._voltar_geral)
        topo.addWidget(b_geral)
        cv.addLayout(topo)

        self._p_usina = _lbl("—", TEXT, 17, 800)
        self._p_usina.setWordWrap(True)
        cv.addWidget(self._p_usina)

        self._ident_box = QHBoxLayout()
        self._ident_box.setSpacing(14)
        cv.addLayout(self._ident_box)


        self._p_aviso = QFrame()
        avv = QVBoxLayout(self._p_aviso)
        avv.setContentsMargins(13, 10, 13, 10)
        avv.setSpacing(3)
        self._p_aviso_txt = _lbl("", MUTED, 11)
        self._p_aviso_txt.setWordWrap(True)
        avv.addWidget(self._p_aviso_txt)
        # O AVISO É CLICÁVEL quando não há OS (Levi, 31/08): a mensagem dizia que faltava
        # vincular e não oferecia caminho nenhum para fazer isso. Agora ela é o caminho.
        self._p_aviso_acao = _lbl("", GREEN, 10.5, 800)
        avv.addWidget(self._p_aviso_acao)
        self._p_aviso.mousePressEvent = lambda e: (self._vincular_os()
                                                   if self._pode_vincular() else None)
        cv.addWidget(self._p_aviso)

        # A COR DO CARD, EXPLÍCITA, em todos os níveis. `transparent` NÃO resolve: com folha de
        # estilo no QFrame pai, o QWidget interno do QScrollArea acaba pintando a cor de JANELA
        # (#0B1020), que é mais ESCURA que o card (#121A2B) — é o retângulo escuro dentro do
        # painel que o Levi apontou três vezes. Pintar a cor certa acaba com a dúvida.
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:%s;border:none;}"
                         "QScrollArea > QWidget > QWidget{background:%s;}" % (CARD, CARD))
        sc.viewport().setStyleSheet("background:%s;" % CARD)
        dentro = QWidget()
        dentro.setStyleSheet("background:%s;" % CARD)
        v = QVBoxLayout(dentro)
        v.setContentsMargins(0, 2, 8, 0)
        v.setSpacing(13)

        # Cliente, UF, Supervisor e Responsável SAÍRAM (Levi, 28/08): vêm do catálogo, não mudam
        # e não são decisão de ninguém nesta tela.
        v.addWidget(_secao("CAUSA RAIZ", tickets_spec.COR_ESTADO["verificando"]))
        self._p_causa = _campo(ph="aguardando técnico", editavel=True)
        v.addWidget(_rotulado("Causa raiz", self._p_causa, dica="só o técnico",
                              cor_dica=tickets_spec.COR_ESTADO["verificando"]))
        # escolha, não texto livre: a régua da indisponibilidade da Grid Co. tem exatamente
        # três casos (Sim = tudo, Parcial = menos 6 h, resto = zero) e digitar "sim " ou "SIM"
        # cai fora dela em silêncio, zerando a hora de quem preencheu.
        self._p_resp = _combo(["", "Sim", "Parcial", "Não"])
        v.addWidget(_rotulado("Responsabilidade da Grid Co.?", self._p_resp))

        v.addWidget(_regua())
        v.addWidget(_secao("PRAZOS"))
        self._p_ini = _CampoData(ph="dd/mm/aaaa hh:mm")
        v.addWidget(_rotulado("Início da ocorrência", self._p_ini, dica="data e hora"))
        self._p_fim = _CampoData(ph="em aberto")
        v.addWidget(_rotulado("Fim da ocorrência", self._p_fim))
        # este NÃO abre: é calculado pela janela solar a partir das duas datas acima. Campo
        # calculado que aceita digitação vira número que ninguém sabe de onde veio.
        self._p_indisp = _campo()
        v.addWidget(_rotulado("Indisponibilidade", self._p_indisp,
                              dica="período solar (06 a 18h)"))

        v.addWidget(_regua())
        # COMENTÁRIOS vira um log (Levi, 31/08): o campo nasce VAZIO, para escrever o próximo, e
        # o que já foi dito fica atrás do botão de histórico. Antes o campo trazia tudo junto e
        # editar um comentário antigo era o caminho natural — o que apaga o registro de alguém.
        topo_c = QHBoxLayout()
        topo_c.setSpacing(8)
        topo_c.addWidget(_secao("COMENTÁRIOS"))
        self._b_hist = QPushButton("histórico")
        self._b_hist.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_hist.setStyleSheet("QPushButton{background:transparent;border:none;color:%s;"
                                   "font-size:10px;font-weight:800;padding:0px;}"
                                   "QPushButton:hover{color:%s;}"
                                   "QPushButton:disabled{color:%s;}" % (GREEN, TEXT, BORDER))
        self._b_hist.clicked.connect(self._ver_comentarios)
        topo_c.addWidget(self._b_hist)
        topo_c.addStretch(1)
        v.addLayout(topo_c)
        self._p_coment = QTextEdit()
        self._p_coment.setFixedHeight(56)
        self._p_coment.setPlaceholderText("escreva um comentário novo…")
        self._p_coment.setStyleSheet("QTextEdit{%s}QTextEdit:focus{border-color:%s;}"
                                     % (_qss_campo(TEXT), GREEN))
        v.addWidget(self._p_coment)

        v.addWidget(_regua())
        acao = QHBoxLayout()
        acao.setSpacing(10)
        self._p_estado_edicao = _lbl("", MUTED, 10.5)
        self._p_estado_edicao.setWordWrap(True)
        acao.addWidget(self._p_estado_edicao, 1)
        self._b_salvar = QPushButton("Salvar")
        self._b_salvar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_salvar.setFixedHeight(_ALTURA_BARRA)
        # min-height E max-height, os dois: com `min-height:0` o layout do painel espremia o
        # botão para 16px quando a coluna ficava apertada (medido em 31/08).
        self._b_salvar.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:none;border-radius:9px;"
            "padding:0px 18px;min-height:%dpx;max-height:%dpx;font-size:12px;font-weight:800;}"
            "QPushButton:disabled{background:%s;color:%s;}"
            % (GREEN, GREEN_INK, _ALTURA_BARRA, _ALTURA_BARRA, INPUT, MUTED))
        self._b_salvar.clicked.connect(self._salvar)
        acao.addWidget(self._b_salvar)
        v.addLayout(acao)
        v.addStretch(1)

        # marcar sujo em cada campo: é o que acende o Salvar e o que permite avisar antes de a
        # troca de linha jogar fora o que foi digitado.
        for w in (self._p_causa, self._p_ini, self._p_fim):
            w.textEdited.connect(self._marcar_sujo)
        self._p_resp.activated.connect(self._marcar_sujo)
        self._p_coment.textChanged.connect(self._marcar_sujo)
        sc.setWidget(dentro)
        cv.addWidget(sc, 1)

        p.v.addWidget(self._p_conteudo, 1)

        # SEGUNDO ESTADO do painel (redesenho de 30/08): sem linha selecionada ele não fica
        # vazio dizendo "selecione algo" — mostra onde estão as ocorrências e por quais causas.
        # É a pergunta que a pessoa tem ao ABRIR a tela, antes de saber em que linha clicar.
        self._p_geral = QWidget()
        # a cor do CARD, explicita — sem isto o QWidget pinta a cor de JANELA, mais escura, e
        # vira um retangulo escuro dentro do painel. Ja consertado antes; a linha se perdeu
        # quando refiz este bloco no redesenho de 30/08.
        self._p_geral.setStyleSheet("background:%s;" % CARD)
        gv = QVBoxLayout(self._p_geral)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.setSpacing(12)
        gv.addWidget(_secao("VISÃO GERAL"))
        self._g_titulo = _lbl("—", TEXT, 15, 800)
        self._g_titulo.setWordWrap(True)
        gv.addWidget(self._g_titulo)
        self._g_sub = _lbl("", MUTED, 11.5)
        self._g_sub.setWordWrap(True)
        gv.addWidget(self._g_sub)
        gv.addWidget(_regua())
        gv.addWidget(_secao("ONDE ESTÃO"))
        self._g_usinas = QVBoxLayout()
        self._g_usinas.setSpacing(5)
        gv.addLayout(self._g_usinas)
        gv.addWidget(_regua())
        gv.addWidget(_secao("CAUSAS MAIS FREQUENTES"))
        self._g_causas = QVBoxLayout()
        self._g_causas.setSpacing(5)
        gv.addLayout(self._g_causas)
        gv.addStretch(1)
        p.v.addWidget(self._p_geral, 1)
        return p

    def _barra_geral(self, rot, qtd, total, cor):
        """Linha da visão geral: nome, barrinha proporcional e contagem. A barra existe porque
        uma lista de números sem escala não responde 'onde está concentrado' num relance."""
        w = QWidget()
        w.setStyleSheet("background:%s;" % CARD)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(9)
        nome = _lbl(str(rot)[:26], TEXT, 11.5)
        nome.setFixedWidth(150)
        h.addWidget(nome)
        trilho = QFrame()
        trilho.setFixedHeight(5)
        trilho.setStyleSheet("background:%s;border:none;border-radius:3px;" % INPUT)
        tv = QHBoxLayout(trilho)
        tv.setContentsMargins(0, 0, 0, 0)
        cheio = QFrame()
        cheio.setStyleSheet("background:%s;border:none;border-radius:3px;" % cor)
        tv.addWidget(cheio, max(1, int(100 * qtd / max(total, 1))))
        tv.addStretch(max(1, 100 - int(100 * qtd / max(total, 1))))
        h.addWidget(trilho, 1)
        n = _lbl(str(qtd), MUTED, 11)
        n.setFixedWidth(34)
        n.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(n)
        return w

    def _pinta_geral(self):
        """Preenche a visão geral com o que está FILTRADO agora, não com o universo — assim ela
        responde à busca e ao seletor de usina em vez de mostrar sempre o mesmo."""
        _limpar_layout(self._g_usinas)
        _limpar_layout(self._g_causas)
        todas = getattr(self, "_filtradas", self._visiveis)
        base = [o for o in todas if o["_estado"] != "encerrada"] or todas
        usinas, causas = {}, {}
        for o in base:
            u = str(o.get("Usina") or "—")
            usinas[u] = usinas.get(u, 0) + 1
            c = str(o.get("Causa raiz") or "").strip() or "sem causa registrada"
            causas[c] = causas.get(c, 0) + 1
        abertas = [o for o in todas if o["_estado"] != "encerrada"]
        antigas = sum(1 for o in abertas if (o.get("_dias") or 0) > 30)
        sem_os = sum(1 for o in abertas if not str(o.get("OS") or "").strip())
        self._g_titulo.setText("%s %s em %d %s"
                               % (f"{len(abertas):,}".replace(",", "."),
                                  "ocorrência aberta" if len(abertas) == 1 else "ocorrências abertas",
                                  len(usinas), "usina" if len(usinas) == 1 else "usinas"))
        # "N sem OS" só informa quando N difere do total: nesta fase a coluna OS não existe
        # (spec §8), então TODA aberta está sem OS e repetir o número seria ruído.
        partes = []
        if sem_os and sem_os != len(abertas):
            partes.append("%d sem OS vinculada" % sem_os)
        partes.append("%d %s há mais de 30 dias"
                      % (antigas, "aberta" if antigas == 1 else "abertas"))
        self._g_sub.setText(" · ".join(partes))
        topo = max((n for _, n in usinas.items()), default=1)
        for u, q in sorted(usinas.items(), key=lambda x: -x[1])[:7]:
            self._g_usinas.addWidget(self._barra_geral(u, q, topo,
                                                       tickets_spec.COR_ESTADO["aberta"]))
        topo_c = max((n for _, n in causas.items()), default=1)
        for c, q in sorted(causas.items(), key=lambda x: -x[1])[:6]:
            self._g_causas.addWidget(self._barra_geral(c, q, topo_c, MUTED))

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
        self._w = ApiWorker(_carregar_aba, sheet_id)
        self._w.ok.connect(lambda par, a=aba_pedida: self._ocs_chegaram(par, a))
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
    def _ocs_chegaram(self, par, aba_pedida):
        self._w = None
        if aba_pedida != self._aba:
            return           # resposta de uma troca de aba já abandonada — descarta
        linhas, diario = par
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
        # o DIÁRIO por cima do que veio do banco: se o sync desfez uma edição do app, aqui ela
        # volta. Ver tickets_diario — a aba dele não existe no .xlsx, então o sync não a alcança.
        self._placar_diario = tickets_diario.aplicar(aba_pedida, ocs, diario)
        for row in ocs:
            if row.get("_restaurado"):
                ini, fim = row.get("Início da ocorrência"), row.get("Fim da ocorrência")
                row["_estado"] = tickets_spec.estado_do_ticket(row.get("OS"),
                                                               row.get("Status da OS"), fim)
                row["_dias"] = _dias_desde(ini, fim)
                row["_horas"] = tickets_calc.indisponibilidade_horas(ini, fim)
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
        # se já tinha uma ocorrência de Strings selecionada, o campo Cabine que estava
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
        self._pinta_fonte()
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

    # colunas ordenáveis: índice na tabela → função que extrai a chave. A tarja (0) fica de
    # fora por não ter conteúdo, e a OS (3) porque é constante enquanto a coluna não existir.
    # A chave é uma TUPLA (tem_valor, valor). Assim a linha SEM dado vai para o fim nos DOIS
    # sentidos, em vez de virar "a mais recente" ao inverter — e são muitas: 251 das 513
    # ocorrências abertas de trackers não têm data de início (limitação conhecida, 30/08).
    # por NOME e não por índice: desde que Trackers ganhou Cabine e Tracker separadas, a mesma
    # coluna está em posições diferentes nas duas abas.
    _ORDENAVEL = {
        "Usina": lambda o: (1, api._norm_txt(o.get("Usina") or "")),
        "Cabine": lambda o: ((1, int(str(o.get("Nº do SKID") or "").strip()))
                             if str(o.get("Nº do SKID") or "").strip().isdigit()
                             else (0, 0)),
        "Tracker": lambda o: ((1, int(t)) if (t := str(
            o.get("Nº do tracker / Identificação") or "").strip()).isdigit() else (0, 0)),
        "Inversor": lambda o: (1, api._norm_txt(o.get("Inversor") or "")),
        "Causa raiz": lambda o: (1 if str(o.get("Causa raiz") or "").strip() else 0,
                                 api._norm_txt(o.get("Causa raiz") or "")),
        "Início da ocorrência": lambda o: (
            (1, d) if (d := tickets_calc._para_dt(o.get("Início da ocorrência")))
            else (0, datetime.min)),
        "Período": lambda o: ((1, o["_dias"]) if o.get("_dias") is not None else (0, -1)),
    }
    _DESC_POR_PADRAO = ("Início da ocorrência", "Período")

    @slot_seguro
    def _ordenar_por(self, col):
        nomes = colunas_da_aba(self._aba)
        nome = nomes[col] if 0 <= col < len(nomes) else ""
        if nome not in self._ORDENAVEL:
            return
        col = nome
        padrao_desc = nome in self._DESC_POR_PADRAO   # data e dias começam do maior p/ o menor
        if self._ordem is None or self._ordem[0] != col:
            self._ordem = (col, padrao_desc)
        elif self._ordem[1] == padrao_desc:
            self._ordem = (col, not padrao_desc)
        else:
            self._ordem = None               # terceiro clique: volta ao padrão
        self._repintar()

    # `*_` obrigatório: `clicked` do Qt manda um bool. Sem ele o slot levanta TypeError, o
    # @slot_seguro engole (é para isso que ele existe) e o botão fica MUDO — foi o que o Levi
    # viu em 31/08 no "✕ visão geral". Um slot ligado a clicked SEMPRE aceita o argumento.
    @slot_seguro
    def _voltar_geral(self, *_):
        self._pintar_selecao(-1)
        self._selecionar(None)

    # ── edição (fase 2) ──────────────────────────────────────────────────────────────────
    # Os campos abrem, mas a gravação ainda esbarra no pipeline: enquanto a planilha subir as
    # abas Trackers e Strings com replace=true, o que fosse gravado aqui sumiria no próximo
    # sync, em silêncio. Por isso a trava é de CÓDIGO (tickets_escrita.SHEETS_LIBERADAS) e o
    # erro diz o motivo, em vez de o Salvar falhar com uma mensagem genérica de rede.
    _CAMPOS_EDITAVEIS = ("Causa raiz", "Responsabilidade da Grid Co.?",
                         "Início da ocorrência", "Início do chamado pela Grid Co.",
                         "Fim da ocorrência", "Comentários gerais")

    def _pode_vincular(self):
        """Só faz sentido oferecer vínculo em ocorrência SEM OS e ainda aberta. Encerrada já
        acabou; com OS, o caminho é o próprio número no cabeçalho."""
        oc = self._sel or {}
        return bool(oc) and not str(oc.get("OS") or "").strip() and oc.get("_estado") != "encerrada"

    @slot_seguro
    def _vincular_os(self, *_):
        """Escolher a OS do Fracttal e prendê-la à ocorrência (Levi, 31/08: "quero ao clicar na
        mensagem conseguir escolher").

        O número fica no DIÁRIO, não na planilha: as duas abas não têm coluna de OS, e criar uma
        não resolveria enquanto o pipeline subir o .xlsx — o sync encolhe a aba de volta.

        Junto vai o 'Início do chamado pela Grid Co.' com a data de CRIAÇÃO da OS. Essa coluna
        existe na planilha e é o que o Levi chama de "data que a Grid notificou": a notificação é
        a abertura da OS, então preencher à mão seria redigitar o que o Fracttal já sabe. Só
        preenche se estiver vazia — data já registrada por alguém não é sobrescrita."""
        if self._sel is None:
            return
        pop = QFrame(self, Qt.WindowType.Popup)
        pop.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:12px;}"
                          % (CARD, BORDER))
        pop.setFixedWidth(400)
        v = QVBoxLayout(pop)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(9)
        v.addWidget(_secao("VINCULAR OS"))
        linha_busca = QHBoxLayout()
        linha_busca.setSpacing(8)
        busca = QLineEdit()
        busca.setPlaceholderText("número da OS")
        busca.setStyleSheet("QLineEdit{%s min-height:%dpx;max-height:%dpx;}"
                            "QLineEdit:focus{border-color:%s;}"
                            % (_qss_campo(TEXT), _ALTURA_QSS, _ALTURA_QSS, GREEN))
        linha_busca.addWidget(busca, 1)
        # A LUPA (Levi, 31/08): quem não sabe o número precisa de um jeito de PROCURAR, e o
        # campo acima só serve para quem já sabe. Abre o card grande sobre o app.
        b_lupa = QPushButton("⌕")
        b_lupa.setCursor(Qt.CursorShape.PointingHandCursor)
        b_lupa.setToolTip("procurar as OS deste ativo ou da usina")
        b_lupa.setFixedWidth(38)
        b_lupa.setFixedHeight(_ALTURA_BARRA)
        b_lupa.setStyleSheet("QPushButton{background:%s;color:%s;border:none;border-radius:9px;"
                             "font-size:16px;font-weight:800;min-height:0px;}"
                             % (GREEN, GREEN_INK))
        b_lupa.clicked.connect(lambda *_: (pop.close(), self._abrir_lupa()))
        linha_busca.addWidget(b_lupa)
        v.addLayout(linha_busca)
        aviso = _lbl("digite o número e tecle Enter, ou use a lupa para procurar", MUTED, 10.5)
        aviso.setWordWrap(True)
        v.addWidget(aviso)
        lista = QVBoxLayout()
        lista.setSpacing(4)
        v.addLayout(lista)
        v.addStretch(1)

        def escolher(os_achada):
            oc = self._sel
            folio = str(os_achada.get("folio") or "").strip()
            oc["OS"] = folio
            # a data vem de OUTRA consulta de propósito: o RPC da busca devolve 7 campos e
            # NENHUM é a data de criação — o que ele traz é `date_maintenance`, a data do
            # serviço. Medido em 31/08 na OS 9208: criada em 09/07, serviço em 04/07. Cinco
            # dias de diferença numa coluna que existe para dizer QUANDO A GRID AVISOU.
            criada = ""
            try:
                w = api.os_por_folio(folio) or {}
                criada = para_iso(api.fmt_data_br(w.get("creation_date")))
            except Exception as e:                   # noqa: BLE001 — a OS já foi vinculada
                print("[tickets] sem data de criação da OS %s (%s)" % (folio, str(e)[:80]))
            if criada and not str(oc.get("Início do chamado pela Grid Co.") or "").strip():
                oc["Início do chamado pela Grid Co."] = criada
            oc["_estado"] = tickets_spec.estado_do_ticket(oc.get("OS"), oc.get("Status da OS"),
                                                          oc.get("Fim da ocorrência"))
            pop.close()
            self._sujo = True
            self._selecionar(oc)      # repinta o painel com a OS já no cabeçalho
            self._sujo = True         # _selecionar zera; a escolha ainda não foi gravada
            self._pinta_edicao()
            self._repintar()

        def procurar():
            termo = busca.text().strip()
            if not termo:
                return
            _limpar_layout(lista)
            aviso.setText("procurando…")
            # síncrono e curto de propósito: é um popup modal-ish, com um filtro por número, e
            # um worker aqui traria o risco de a resposta chegar com o popup já fechado.
            try:
                achadas = api.buscar_os_pai(termo, limit=12)
            except Exception as e:                       # noqa: BLE001
                aviso.setText("não consegui procurar: %s" % str(e)[:90])
                return
            if not achadas:
                aviso.setText("nenhuma OS com esse número")
                return
            aviso.setText("%d encontrada(s) — clique para vincular" % len(achadas))
            for o in achadas:
                # a descrição deste RPC costuma ser o próprio número; o que ajuda a escolher
                # é a data e quem está com ela.
                detalhe = "  ·  ".join(x for x in (o.get("data"), o.get("responsavel"),
                                                   (o.get("descricao") or "")[:30]) if x)
                b = QPushButton("OS %s      %s" % (o.get("folio"), detalhe))
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet("QPushButton{background:%s;color:%s;border:1px solid %s;"
                                "border-radius:8px;padding:6px 10px;font-size:11.5px;"
                                "text-align:left;}"
                                "QPushButton:hover{border-color:%s;color:%s;}"
                                % (INPUT, TEXT, BORDER, GREEN, GREEN))
                b.clicked.connect(lambda _c=False, x=o: escolher(x))
                lista.addWidget(b)
            pop.adjustSize()

        busca.returnPressed.connect(procurar)
        # sem altura mínima: com ela o card nascia com um vão vazio embaixo da dica, antes de
        # existir resultado nenhum (Levi, 31/08). Ele cresce sozinho quando a lista aparece.
        _abrir_popup(pop, self._p_aviso)
        busca.setFocus()

    @slot_seguro
    def _abrir_lupa(self, *_):
        """O card grande com as OS do ativo — e da usina inteira, se a pessoa quiser.

        O ativo do Fracttal sai do mesmo caminho que o painel usa para mostrar SKID/Cabine: em
        Strings, o inversor resolvido no catálogo; em Trackers não há ativo cadastrado por
        tracker, então lá a lupa já abre na usina."""
        oc = self._sel
        if oc is None:
            return
        usina = str(oc.get("Usina") or "")
        ativo = {}
        if self._aba == "Strings" and self._ativos_prontos and not self._ativos_falhou:
            ativo = _achar_inversor(oc.get("Inversor"), usina, self._todos_ativos) or {}
        dlg = lupa_os.LupaOS(self, ativo, usina,
                             _ativos_da_usina(usina, self._todos_ativos), self._os_escolhida)
        dlg.exec()

    def _os_escolhida(self, os_):
        """A lupa devolveu uma OS. Reaproveita o mesmo caminho do vínculo por número — inclusive
        o 'Início do chamado pela Grid Co.', que sai da data de criação da OS."""
        oc = self._sel
        if oc is None:
            return
        oc["OS"] = str(os_.get("folio") or "").strip()
        criada = para_iso(api.fmt_data_br(os_.get("aberta")))
        if criada and not str(oc.get("Início do chamado pela Grid Co.") or "").strip():
            oc["Início do chamado pela Grid Co."] = criada
        oc["_estado"] = tickets_spec.estado_do_ticket(oc.get("OS"), oc.get("Status da OS"),
                                                      oc.get("Fim da ocorrência"))
        self._selecionar(oc)
        self._sujo = True
        self._pinta_edicao()
        self._repintar()

    @slot_seguro
    def _ver_comentarios(self, *_):
        """O histórico da ocorrência, um por linha. Entrada anterior a 31/08 aparece sem autor —
        a coluna era texto corrido e não dá para inventar quem escreveu."""
        hist = comentarios_de((self._sel or {}).get("Comentários gerais"))
        if not hist:
            return
        pop = QFrame(self, Qt.WindowType.Popup)
        pop.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:11px;}"
                          % (CARD, BORDER))
        v = QVBoxLayout(pop)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(9)
        v.addWidget(_secao("HISTÓRICO DE COMENTÁRIOS"))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:%s;border:none;}"
                         "QScrollArea > QWidget > QWidget{background:%s;}" % (CARD, CARD))
        sc.viewport().setStyleSheet("background:%s;" % CARD)
        dentro = QWidget()
        dentro.setStyleSheet("background:%s;" % CARD)
        dv = QVBoxLayout(dentro)
        dv.setContentsMargins(0, 0, 8, 0)
        dv.setSpacing(11)
        for quando, autor, texto in hist:
            bloco = QVBoxLayout()
            bloco.setSpacing(2)
            if quando:
                bloco.addWidget(_lbl("%s  ·  %s" % (quando, autor), GREEN, 10, 800))
            else:
                bloco.addWidget(_lbl("antes do histórico datado", MUTED, 10, 800, ital=True))
            t = _lbl(texto, TEXT, 12)
            t.setWordWrap(True)
            bloco.addWidget(t)
            w = QWidget()
            w.setStyleSheet("background:%s;" % CARD)
            w.setLayout(bloco)
            dv.addWidget(w)
        dv.addStretch(1)
        sc.setWidget(dentro)
        v.addWidget(sc)
        pop.setFixedWidth(380)
        pop.setFixedHeight(min(420, 90 + 62 * len(hist)))
        _abrir_popup(pop, self._b_hist)

    @slot_seguro
    def _marcar_sujo(self, *_):
        if self._populando or self._sel is None:
            return
        self._sujo = True
        self._pinta_edicao()

    def _pinta_edicao(self):
        self._b_salvar.setEnabled(self._sujo and self._sel is not None)
        if self._sujo:
            self._aviso_edicao("alterações não salvas", tickets_spec.COR_ESTADO["aberta"])
            return
        # o diário repôs algo que o sync tinha desfeito: isso PRECISA aparecer. Corrigir em
        # silêncio é a mesma classe de erro que ele existe para evitar — a pessoa tem de saber
        # que o que está na tela não é o que o banco devolveu.
        repostos = (self._sel or {}).get("_restaurado")
        if repostos:
            self._aviso_edicao("%s: reposto pelo app (o sync da planilha tinha desfeito)"
                               % ", ".join(repostos), tickets_spec.COR_ESTADO["verificando"])
        else:
            self._p_estado_edicao.setText("")

    def _digitado(self):
        """O que está nos campos agora, na grafia das colunas da planilha.

        Comentário é ACRÉSCIMO, não substituição: o campo traz só o texto novo, e aqui ele vira
        mais uma linha datada e assinada no fim da coluna. Mandar o campo direto apagaria todo o
        histórico a cada salvamento."""
        return {"Causa raiz": self._p_causa.text().strip(),
                "Responsabilidade da Grid Co.?": self._p_resp.currentText().strip(),
                "Início da ocorrência": para_iso(self._p_ini.text()),
                "Fim da ocorrência": para_iso(self._p_fim.text()),
                "Comentários gerais": acrescentar_comentario(
                    (self._sel or {}).get("Comentários gerais"),
                    self._p_coment.toPlainText(), tickets_diario.quem()),
                # estes dois não têm campo na tela: vêm do vínculo com a OS. Precisam entrar
                # aqui mesmo assim — é o que o diário grava, e o que o PUT manda para a coluna
                # 'Início do chamado', que existe na planilha ('OS' não existe e é ignorada).
                "OS": str((self._sel or {}).get("OS") or "").strip(),
                "Início do chamado pela Grid Co.":
                    para_iso((self._sel or {}).get("Início do chamado pela Grid Co."))}

    def _aviso_edicao(self, texto, cor):
        self._p_estado_edicao.setText(texto)
        self._p_estado_edicao.setStyleSheet(
            "color:%s;font-size:10.5px;background:transparent;border:none;" % cor)

    @slot_seguro
    def _salvar(self, *_):
        oc = self._sel
        if oc is None or not self._sujo:
            return
        sheet_id = tickets_spec.ABAS[self._aba]["sheet_id"]
        cab = tickets_api.cabecalho_de(sheet_id)
        if not cab:
            self._aviso_edicao("não sei a ordem das colunas desta aba — recarregue a tela antes "
                               "de salvar", tickets_spec.COR_ESTADO["aberta"])
            return
        # a linha INTEIRA volta, não só o que mudou: o PUT da API substitui a linha, e mandar
        # apenas os campos editados apagaria as outras 10 colunas.
        dados = {c: oc.get(c) for c in cab if str(c or "").strip()}
        dados.update(self._digitado())
        base = {c: oc.get(c) for c in self._CAMPOS_EDITAVEIS}
        self._b_salvar.setEnabled(False)
        self._aviso_edicao("salvando…", MUTED)
        try:
            tickets_escrita.gravar_linha(sheet_id, oc.get("_row"), dados, cab, base=base)
        except tickets_escrita.EscritaBloqueada:
            # a mensagem da exceção é para o log; na tela vale o que a pessoa pode fazer a
            # respeito. O id da aba e o replace=true não ajudam quem está tentando salvar.
            self._aviso_edicao("ainda não dá para gravar: a planilha do OneDrive continua "
                               "sobrescrevendo esta aba a cada sync, e o que você digitou "
                               "sumiria. Falta o corte no pipeline.",
                               tickets_spec.COR_ESTADO["aberta"])
            self._b_salvar.setEnabled(True)
        except tickets_escrita.ConflitoDeEdicao as e:
            # alguém mexeu na linha enquanto esta tela estava aberta. Não gravo por cima: o
            # trabalho do outro sumiria sem ninguém perceber.
            self._aviso_edicao("outra pessoa alterou %s nesta linha — recarregue antes de salvar"
                               % ", ".join(e.campos), tickets_spec.COR_ESTADO["aberta"])
            self._b_salvar.setEnabled(True)
        except Exception as e:                                   # rede, 401, 500…
            self._aviso_edicao("não consegui salvar: %s" % str(e)[:120],
                               tickets_spec.COR_ESTADO["aberta"])
            self._b_salvar.setEnabled(True)
        else:
            digitado = self._digitado()
            oc.update(digitado)
            self._sujo = False
            self._recalcular(oc)
            # O DIÁRIO, depois da gravação e nunca antes: registrar o que não entrou no banco
            # faria a tela repor, na abertura seguinte, um valor que ninguém chegou a salvar.
            # Falhar aqui não desfaz nada — a linha real já está gravada, só o seguro contra o
            # sync é que não ficou. Por isso a mensagem muda em vez de virar erro.
            protegido = True
            try:
                tickets_diario.registrar(self._aba, oc, digitado)
            except Exception as e:               # noqa: BLE001
                protegido = False
                print("[tickets] não registrei no diário (%s: %s)"
                      % (type(e).__name__, str(e)[:140]))
            if protegido:
                self._aviso_edicao("salvo", GREEN)
            elif sheet_id in tickets_escrita.SHEETS_QUE_O_SYNC_SOBRESCREVE:
                # sem o diário, "salvo" seco seria meia verdade: gravou sim, e o sync desta aba
                # pode desfazer. É a diferença entre um dado que voltou atrás e um dado que
                # sumiu sem explicação.
                self._aviso_edicao("salvo — mas fora do diário: a planilha do OneDrive pode "
                                   "desfazer no próximo sync",
                                   tickets_spec.COR_ESTADO["verificando"])
            else:
                self._aviso_edicao("salvo", GREEN)
            self._repintar()

    def _recalcular(self, oc):
        """Depois de gravar, a indisponibilidade e o estado precisam sair das datas NOVAS —
        senão a linha continua dizendo 'em aberto' com o Fim já preenchido."""
        ini, fim = oc.get("Início da ocorrência"), oc.get("Fim da ocorrência")
        oc["_estado"] = tickets_spec.estado_do_ticket(oc.get("OS"), oc.get("Status da OS"), fim)
        oc["_dias"] = _dias_desde(ini, fim)
        oc["_horas"] = tickets_calc.indisponibilidade_horas(ini, fim)

    @slot_seguro
    def _trocar_usina(self, nome):
        self._usina_filtro = nome or ""
        self._repintar()

    # ── repintura ────────────────────────────────────────────────────────────────────────
    # ligado direto ao timeout do QTimer da busca (_t_busca) além de ser chamado pelos 3 slots
    # acima — é o coração da tela. Ver o comentário de _trocar_aba: sem @slot_seguro, uma
    # exceção aqui é a janela sumindo sem mensagem, não um traceback no log.
    @slot_seguro
    def _repintar(self):
        termo = api._norm_txt(self._busca.text())
        extratores = [f for _, f in _EXTRA_COL[self._aba]]

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
            campos = [oc.get("Usina"), oc.get("Causa raiz")] + [f(oc) for f in extratores]
            texto = api._norm_txt(" ".join(str(c) for c in campos if c not in (None, "")))
            return termo in texto

        passou = [o for o in self._ocs if _passa(o)]
        if self._ordem is None:
            filtradas = ordenar_ocorrencias(passou)
        else:
            col, desc = self._ordem
            chave = self._ORDENAVEL[col]
            # ordena o VALOR no sentido pedido, mas mantém quem não tem dado sempre por último
            filtradas = sorted(passou, key=lambda o: chave(o)[1], reverse=desc)
            filtradas.sort(key=lambda o: -chave(o)[0])
        total = len(filtradas)
        # a TABELA corta em 400 por desempenho, mas a visão geral conta o filtro INTEIRO —
        # senão ela diria "400 ocorrências" para sempre, que é o teto da tabela e não o dado.
        self._filtradas = filtradas
        self._visiveis = filtradas[:_LIMITE_TABELA]

        self._pinta_estados()
        self._pinta_tabela()
        extra = total - _LIMITE_TABELA
        self._rodape.setText("%s ocorrências" % f"{total:,}".replace(",", ".")
                             + (" · mostrando as %d primeiras, refine a busca" % _LIMITE_TABELA
                                if extra > 0 else ""))
        # NÃO auto-seleciona mais (redesenho de 30/08): a visão geral é o primeiro estado do
        # painel, e ela responde "onde estão as abertas" antes de a pessoa saber em que clicar.
        self._pintar_selecao(-1)
        self._selecionar(None)

    def _pinta_estados(self):
        """A barra segmentada do topo: filtro de estado E contagem, num controle só.

        Antes eram DUAS coisas dizendo o mesmo: uma faixa de tiles com os números e, na coluna
        da esquerda, uma pilha de pílulas para filtrar por estado. Os números eram os mesmos e a
        pilha comia a altura que a lista de usinas precisava (Levi, 30/08). Fundidos aqui, logo
        depois dos botões de Trackers/Strings, que é onde ele pediu."""
        _limpar_layout(self._seg_box)
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
        self._seg_box.addWidget(_Segmentado(itens, self._chip_estado))
        self._pinta_seletor_usina()

    def _pinta_seletor_usina(self):
        """A usina saiu da coluna e virou seletor aqui: 63 opções não cabiam numa lista fixa, e
        a coluna que as segurava comia a largura da tabela. O rótulo diz o filtro em vigor —
        sem o número de usinas, que o Levi tirou em 31/08 por não decidir nada."""
        if not self._usina_filtro:
            self._b_usina.setText("Todas as usinas")
            return
        qtd = sum(1 for o in self._ocs if o.get("Usina") == self._usina_filtro)
        self._b_usina.setText("%s   %d" % (self._usina_filtro[:26], qtd))

    def _ajustar_larguras(self):
        """QUEM ESTICA É A CAUSA RAIZ, onde quer que ela esteja: é a única coluna de texto longo
        e de largura variável. Em ResizeToContents ela pedia todo o espaço que precisasse e
        empurrava o painel da direita para FORA da tela (medido em 1536px). Por nome, e não por
        índice, porque Trackers e Strings têm quantidades de colunas diferentes desde 31/08."""
        cab = self.tab.horizontalHeader()
        nomes = colunas_da_aba(self._aba)
        for i, nome in enumerate(nomes):
            cab.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if nome == "Causa raiz"
                                     else QHeaderView.ResizeMode.ResizeToContents)
        self.tab.setColumnWidth(0, 14)

    def _pinta_tabela(self):
        rot = list(colunas_da_aba(self._aba))
        if self._ordem is not None:          # a seta diz por onde está ordenado, e em que sentido
            col, desc = self._ordem
            if col in rot:
                rot[rot.index(col)] += ("  ▼" if desc else "  ▲")
        if self.tab.columnCount() != len(rot):
            self.tab.setColumnCount(len(rot))
            self._ajustar_larguras()          # colunas novas nascem sem modo de redimensionar
        self.tab.setHorizontalHeaderLabels(rot)
        self.tab.blockSignals(True)
        self.tab.clearContents()          # descarta também os widgets de célula da tarja
        self.tab.setRowCount(0)
        self.tab.setRowCount(len(self._visiveis))
        for r, oc in enumerate(self._visiveis):
            estado = oc["_estado"]
            cor_estado = tickets_spec.COR_ESTADO.get(estado, MUTED)
            tarja = QTableWidgetItem("▐")
            # A COR EXPLICADA NO HOVER (Levi, 31/08). A tarja dizia o estado só por cor, e cor
            # sozinha não se explica: o mesmo texto que o painel usa vira a dica aqui, então
            # quem passa o mouse descobre sem precisar clicar na linha.
            tarja.setToolTip("%s — %s" % (tickets_spec.NOME_ESTADO.get(estado, estado),
                                          _TXT_AVISO.get(estado, "")))
            # a cor da tarja é A INFORMAÇÃO: sem isto o azul de seleção a substitui e a linha
            # escolhida some da leitura por estado (Levi, 31/08).
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
                os_txt, os_cor = "Sem OS", tickets_spec.COR_ESTADO["aberta"]

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
            # "X dias", seco (Levi, 31/08). O "há"/"durou" saiu: a coluna passou a se chamar
            # Período, e é o nome dela que diz o que o número é — em ocorrência aberta, quanto
            # tempo já corre; em encerrada, quanto durou.
            ha_txt = "—" if dias is None else ("%d dia" % dias if dias == 1 else "%d dias" % dias)
            alarme = dias is not None and dias > 30 and estado != "encerrada"
            ha_cor = tickets_spec.COR_ESTADO["aberta"] if alarme else TEXT

            extras = [f(oc) for _, f in _EXTRA_COL[self._aba]]
            vals = ([str(oc.get("Usina") or "—")[:24]] + extras
                    + [os_txt, causa_txt, _fmt_dt(oc.get("Início da ocorrência")), ha_txt])
            cores = ([TEXT] + [TEXT] * len(extras)
                     + [os_cor, MUTED if causa in (None, "") else TEXT, TEXT, ha_cor])
            i_causa = colunas_da_aba(self._aba).index("Causa raiz")
            for c, (v, cr) in enumerate(zip(vals, cores), start=1):
                it = QTableWidgetItem(str(v))
                it.setForeground(_cor(cr))
                # a cor "de verdade" da célula fica guardada: na linha marcada o texto vira
                # escuro para se ler sobre o dourado, e ao sair da marcação ela volta.
                it.setData(_COR_ORIGINAL, cr)
                # tudo centralizado menos a Causa raiz (Levi, 30/08): ela é a única coluna de
                # texto corrido e de largura variável — centralizar faria cada linha começar
                # num ponto diferente, e o olho perde a coluna ao descer a lista.
                if c != i_causa:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if c == i_causa:
                    # EDITÁVEL NA PRÓPRIA TABELA (Levi, 31/08). Só esta coluna: as outras ou são
                    # calculadas ou vêm da planilha. E o texto INTEIRO vai para a edição, não o
                    # truncado — senão salvar de dentro da tabela cortaria a causa raiz em 40
                    # caracteres sem ninguém pedir.
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                    it.setData(Qt.ItemDataRole.EditRole,
                               "" if causa in (None, "") else str(causa))
                    if causa_txt != causa_completa:            # o resto no hover
                        it.setToolTip(causa_completa)
                else:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tab.setItem(r, c, it)
        # a repintura recria os itens: sem isto a linha marcada perderia o realce a cada busca,
        # filtro ou ordenação, e a pessoa não saberia mais qual estava aberta no painel.
        self._pintar_selecao(getattr(self, "_linha_sel", -1))
        self.tab.blockSignals(False)

    @slot_seguro
    def _causa_editada(self, item):
        """Causa raiz digitada direto na tabela: grava na hora.

        Deixar pendente de um clique em Salvar no painel seria pior que não ter a edição — a
        pessoa digitaria numa linha, clicaria na próxima e perderia o que escreveu sem aviso.
        `_pinta_tabela` roda com os sinais bloqueados, então aqui só chega edição de gente."""
        if item is None or item.column() != colunas_da_aba(self._aba).index("Causa raiz"):
            return
        r = item.row()
        if not (0 <= r < len(self._visiveis)):
            return
        oc = self._visiveis[r]
        novo = item.text().strip()
        if novo == "aguardando técnico":          # o texto de placeholder da célula vazia
            novo = ""
        if novo == str(oc.get("Causa raiz") or "").strip():
            return
        self._sel_tabela(r)
        self._p_causa.setText(novo)
        self._sujo = True
        self._pinta_edicao()
        self._salvar()

    # ── seleção ──────────────────────────────────────────────────────────────────────────
    _FUNDO_SEL = _rgba(GREEN, 0.16)

    def _pintar_selecao(self, linha):
        """Marca a linha escolhida: o fundo quem pinta é o `_RealceDaLinha`; aqui vai só o texto.

        SOBRE O DOURADO O TEXTO ESCURECE. As cores das células (Sem OS em vermelho, o alarme da
        coluna Período) foram escolhidas para o fundo navy e somem sobre #A27D3F. A TARJA fica
        de fora: a cor dela é a informação, e o Levi pediu explicitamente que não mude ao
        clicar. Trocar a paleta no delegate não resolve — com folha de estilo na tabela, quem
        decide a cor do texto é o estilo, não a paleta da opção."""
        anterior = getattr(self, "_linha_sel", -1)
        self._linha_sel = linha
        for r in (anterior, linha):
            if not (0 <= r < self.tab.rowCount()):
                continue
            for c in range(1, self.tab.columnCount()):     # a coluna 0 é a tarja: não se mexe
                it = self.tab.item(r, c)
                if it is None:
                    continue
                original = it.data(_COR_ORIGINAL) or TEXT
                it.setForeground(_cor(_TINTA_REALCE if r == linha else original))
        self.tab.viewport().update()

    @slot_seguro
    def _sel_tabela(self, r=-1, _c=0):
        self._pintar_selecao(r)
        if 0 <= r < len(self._visiveis):
            self._linha_sel = r
            self._selecionar(self._visiveis[r])

    def _selecionar(self, oc):
        self._sel = oc
        if oc is None:
            self._p_conteudo.setVisible(False)
            self._sujo = False
            self._pinta_edicao()
            self._pinta_geral()
            self._p_geral.setVisible(True)
            return
        self._p_conteudo.setVisible(True)
        self._p_geral.setVisible(False)

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
        pode = self._pode_vincular()
        self._p_aviso_acao.setText("clique para escolher a OS  ›" if pode else "")
        self._p_aviso.setCursor(Qt.CursorShape.PointingHandCursor if pode
                                else Qt.CursorShape.ArrowCursor)

        # `_populando` cala os sinais de edição: setText/setPlainText disparam os mesmos sinais
        # que a digitação, e sem a trava toda linha clicada nasceria "com alterações não salvas".
        self._populando = True
        try:
            causa = oc.get("Causa raiz")
            self._p_causa.setText(str(causa) if causa not in (None, "") else "")
            resp = str(oc.get("Responsabilidade da Grid Co.?") or "").strip()
            # valor fora das três opções (grafia antiga na planilha) entra como opção extra em
            # vez de sumir: apagar calado o que já estava gravado é pior que mostrar o estranho.
            if resp and self._p_resp.findText(resp) < 0:
                self._p_resp.addItem(resp)
            self._p_resp.setCurrentText(resp)

            self._p_ini.setText(_fmt_dt(oc.get("Início da ocorrência")))
            fim = oc.get("Fim da ocorrência")
            self._p_fim.setText("" if fim in (None, "") else _fmt_dt(fim))
            horas = oc.get("_horas")
            self._p_indisp.setText("%.1f h" % horas if horas is not None else "—")

            # o campo é para o comentário NOVO; o que já existe fica no histórico
            self._p_coment.setPlainText("")
            hist = comentarios_de(oc.get("Comentários gerais"))
            # SEM HISTÓRICO, O BOTÃO SOME (Levi, 31/08: "não está dando a opção de digitar"). Um
            # botão apagado escrito "sem histórico" ao lado do título lê como "aqui não dá para
            # comentar" — e dava: o campo logo abaixo sempre esteve aberto. Sem o botão, o que
            # sobra é o campo com o convite para escrever.
            self._b_hist.setVisible(bool(hist))
            self._b_hist.setText("histórico  %d" % len(hist) if hist else "")
        finally:
            self._populando = False
        self._sujo = False
        self._pinta_edicao()

    def _repintar_ident(self, oc):
        """ATIVO · CABINE.

        UM campo só desde 31/08 (Levi): "Skid e Cabine é a mesma coisa". Eram dois porque o
        catálogo do Fracttal tem os dois níveis, mas na boca de quem opera é o mesmo lugar
        físico. A régua que ele deu: se só existe skid, o número do skid VAI no campo Cabine;
        se existem os dois, vale a cabine. Em Trackers a planilha só traz o skid — e a cadeia
        do tracker nunca passa por uma cabine (medido em tickets_ativo), então lá é sempre o
        skid que aparece."""
        _limpar_layout(self._ident_box)
        if self._aba == "Trackers":
            trk = oc.get("Nº do tracker / Identificação")
            skid = oc.get("Nº do SKID")
            campos = [("ATIVO", "Tracker %s" % trk if trk not in (None, "") else "—", GREEN, False),
                      ("CABINE", str(skid) if skid not in (None, "") else "—", TEXT, False)]
        else:
            inv_nome = oc.get("Inversor")
            campos = [("ATIVO", str(inv_nome) if inv_nome not in (None, "") else "—", GREEN, False)]
            if not self._ativos_prontos:
                campos += [("CABINE", "carregando catálogo…", MUTED, True)]
            elif self._ativos_falhou:
                campos += [("CABINE", "catálogo indisponível", MUTED, True)]
            else:
                ativo = _achar_inversor(inv_nome, oc.get("Usina"), self._todos_ativos)
                if ativo is None:
                    campos += [("CABINE", "não encontrado no catálogo", MUTED, True)]
                else:
                    # a cabine manda; sem ela, o skid ocupa o lugar (a régua do Levi)
                    lugar = (tickets_ativo.cabine_de(ativo, self._por_id)
                             or tickets_ativo.skid_de(ativo, self._por_id))
                    campos += [("CABINE",
                                api._asset_short_name(lugar) if lugar
                                else "não encontrado no catálogo",
                                TEXT if lugar else MUTED, not bool(lugar))]
        for rot, val, cor_v, ital in campos:
            c = QVBoxLayout()
            c.setSpacing(1)
            c.addWidget(_lbl(rot, MUTED, 9, 800, esp=1.1))
            c.addWidget(_lbl(val, cor_v, 12.5, 400 if ital else 700, ital=ital))
            w = QWidget()
            w.setStyleSheet("background:%s;" % CARD)
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
            seg = QFrame()
            seg.setFixedHeight(4)
            # até a etapa atual, colorido; daí em diante, o cinza da borda. A leitura é de
            # progresso, e o nome do estado já vem escrito logo abaixo, no cabeçalho.
            seg.setStyleSheet("background:%s;border:none;border-radius:2px;"
                              % (cor if i <= idx_atual else BORDER))
            seg.setToolTip(nome)
            self._ciclo_box.addWidget(seg, 1)
    def reiniciar(self):
        """Entrar de novo = filtros limpos (mesmo padrão de AtivosTab). Os dados já carregados
        continuam — reabrir a aba não bate na API de novo."""
        self._busca.blockSignals(True)
        self._busca.clear()
        self._busca.blockSignals(False)
        self._estados_filtro.clear()
        self._usina_filtro = ""
        self._sujo = False
        self._repintar()
