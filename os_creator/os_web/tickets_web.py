# os_creator/os_web/tickets_web.py
"""A tela de Tickets na web — PURO: sem Flask, sem PyQt, sem rede.

O DADO JÁ ERA PORTÁTIL. Das 3.611 linhas de Tickets no desktop, cinco módulos já eram puros e
são usados aqui SEM CÓPIA: `tickets_api` (leitura), `tickets_escrita` (escrita), `tickets_spec`
(abas e ciclo de vida), `tickets_calc` (datas e horas) e `tickets_diario` (o que o sync desfez).
O que estava preso ao Qt era só a apresentação — e é ela que este módulo porta.

As constantes abaixo são cópia do `steps/tickets.py`, pelo mesmo motivo do `lancador.py`: aquele
módulo importa PyQt6 no topo e um servidor web não pode carregá-lo para ler dez listas.
`tests/test_os_web_tickets_tela.py` lê o código-fonte do app e falha se um lado mudar sem o outro.
"""
from __future__ import annotations
import datetime as dt

import collections
import re

import tickets_calc
import tickets_spec

# ── as colunas da tabela (steps/tickets.py) ──────────────────────────────────────────────────
# "Resumo incidente" é o NOME DA COLUNA (Levi, 31/08); o dado continua sendo a coluna
# 'Causa raiz' da planilha — por isso o de-para em CAMPO_DA_COLUNA.
ROTULO_CAUSA = "Resumo incidente"
COL_ATIVO = "Ativo vinculado"
COL_STATUS = "Status"
FIXAS_ANTES = ["Usina"]
FIXAS_DEPOIS = [COL_ATIVO, "OS", COL_STATUS, ROTULO_CAUSA, "Início da ocorrência", "Período"]

# Colunas que mudam com a aba. DUAS em Trackers desde 31/08: Cabine e Tracker vinham grudadas num
# "02 / 93" que não dava para ordenar nem ler em coluna.
EXTRA_COL = {"Trackers": ["Cabine", "Tracker"], "Strings": ["Inversor"]}

# Coluna da tabela → campo da planilha. O que não está aqui NÃO é editável.
CAMPO_DA_COLUNA = {
    "Cabine": "Nº do SKID",
    "Tracker": "Nº do tracker / Identificação",
    "Inversor": "Inversor",
    "OS": "OS",
    # "Status do ticket", nunca "Status": a aba Trackers já tem uma coluna com esse nome
    # ("Parado"/"Em conformidade") e escrever por cima dela apaga o filtro que separa ocorrência
    # de check periódico.
    COL_STATUS: "Status do ticket",
    ROTULO_CAUSA: "Causa raiz",
}

# Os status do ticket (lista do Levi, 31/08). Vazio no começo: enquanto ninguém disser em que pé
# está, dizer "Triagem" seria inventar andamento.
STATUS = ["", "Triagem", "OS Pendente", "OS Programada", "OS em Verificação", "Validação da OS",
          "Aguardando Cliente", "Aguardando Concessionária", "Aguardando Condições da Planta",
          "Aguardando Fabricante", "Aguardando Programação da OS", "Em Análise de Performance",
          "Em Análise da Engenharia", "Reavaliação de Performance", "Concluído"]

# O que o painel deixa editar — os mesmos do `TicketsTab._CAMPOS_EDITAVEIS`, mais os dois que a
# tabela do app edita direto na célula (OS e Status do ticket).
CAMPOS_EDITAVEIS = ("Causa raiz", "Responsabilidade da Grid Co.?",
                    "Início da ocorrência", "Início do chamado pela Grid Co.",
                    "Fim da ocorrência", "Comentários gerais")
CAMPOS_TABELA = ("OS", "Status do ticket")
EDITAVEIS = CAMPOS_EDITAVEIS + CAMPOS_TABELA

ALARME_DIAS = 30            # acima disto a ocorrência aberta fica vermelha, como no app

# O que a TELA escreve no cabeçalho, quando difere do nome interno (Levi, 22/09: "mude a coluna
# 'Estado' para 'Status'"). A coluna do ciclo de vida passa a se chamar "Status" — e a que já se
# chamava "Status" vira "Status do ticket", que é o nome real do campo na planilha; sem isso a
# tabela teria duas colunas "Status" lado a lado. O nome interno (`COL_STATUS`) não muda: ele é o
# do app de mesa, e o teste de fidelidade o compara com o de lá.
ROTULO_COLUNA = {COL_STATUS: "Status do ticket"}
ROTULO_ESTADO = "Status"

# ── agrupamento por usina (Levi, 22/09) ──────────────────────────────────────────────────────
# A coluna de quantidade é o que a pessoa quer ver no cabeçalho do grupo: não "quantas linhas",
# e sim QUANTOS EQUIPAMENTOS estão parados. Uma ocorrência pode valer 6 trackers.
COL_QTD = {"Trackers": "Quantidade de trackers parados",
           "Strings": "Quantidade de strings no afetadas"}
ROTULO_QTD = {"Trackers": "trackers parados", "Strings": "strings zeradas"}
SEM_CLIENTE = "(sem cliente)"


def qtd_de(oc: dict, aba: str) -> int:
    """Quantos equipamentos esta ocorrência representa. Vazio ou ilegível = 1.

    1 e não 0: a ocorrência existe, então há pelo menos um equipamento parado. Zero faria uma
    usina com a coluna em branco parecer saudável — e 109 das 3.180 linhas de Trackers estão em
    branco (medido em 22/09)."""
    v = str((oc or {}).get(COL_QTD.get(aba, "")) or "").strip()
    if not v:
        return 1
    try:
        n = int(float(v.replace(",", ".")))
    except ValueError:
        return 1
    return n if n > 0 else 1


def mapa_clientes(ocs: list) -> dict:
    """{usina: cliente} a partir das linhas que TÊM o campo preenchido.

    Sai da PRÓPRIA planilha, e não do catálogo de ativos, porque a coluna "Usina" daqui é o código
    ("TIM100", "PRM100") ou o nome curto ("Barretos") — nunca o "Cliente - Usina - UF" do
    cadastro. Conferido em 22/09: o prefixo casa com o cliente em 0 de 1.167 linhas, e o catálogo
    reconhece 2 de 279 códigos órfãos. Cruzar com ele daria a impressão de funcionar e erraria.

    Medido: nenhuma usina aparece com DOIS clientes diferentes (0 ambíguas em 50), então preencher
    o vazio pelo que a mesma usina diz em outra linha é seguro."""
    por = {}
    for o in (ocs or []):
        u = str((o or {}).get("Usina") or "").strip()
        c = str((o or {}).get("Cliente") or "").strip()
        if u and c:
            por.setdefault(u, c)
    return por


def preencher_cliente(ocs: list) -> list:
    """Põe `_cliente` em toda ocorrência: o campo, o da mesma usina, ou "(sem cliente)".

    O grupo "(sem cliente)" é EXPLÍCITO de propósito. São 279 ocorrências (19% da aba Trackers) em
    usinas que não têm o campo em lugar nenhum — Barretos, PRM100, PRM200. Um filtro de cliente
    que simplesmente não as mostrasse faria 19% do passivo sumir da tela sem ninguém perceber."""
    por = mapa_clientes(ocs)
    for o in (ocs or []):
        c = str((o or {}).get("Cliente") or "").strip()
        o["_cliente"] = c or por.get(str(o.get("Usina") or "").strip()) or SEM_CLIENTE
    return ocs


def clientes_de(ocs: list) -> list:
    """Os clientes para o dropdown, em ordem; "(sem cliente)" por último, se existir."""
    vistos = sorted({o.get("_cliente") for o in (ocs or []) if o.get("_cliente") and o["_cliente"] != SEM_CLIENTE},
                    key=lambda x: x.lower())
    if any(o.get("_cliente") == SEM_CLIENTE for o in (ocs or [])):
        vistos.append(SEM_CLIENTE)
    return vistos


def usinas_de(ocs: list, cliente: str = "") -> list:
    """As usinas para o dropdown — só as do cliente escolhido, quando há um."""
    return sorted({str(o.get("Usina") or "").strip() for o in (ocs or [])
                   if str(o.get("Usina") or "").strip() and (not cliente or o.get("_cliente") == cliente)},
                  key=lambda x: x.lower())


def agrupar(ocs: list, aba: str) -> list:
    """As ocorrências agrupadas por usina, cada grupo com a conta que o cabeçalho mostra.

    → [{usina, cliente, n, n_abertas, qtd, itens}], da usina com MAIS equipamentos parados para a
    com menos. A ordem é essa porque o drill-down existe para achar onde doer mais; alfabética
    obrigaria a abrir uma por uma para descobrir.

    `qtd` conta só as NÃO ENCERRADAS: "parado" é estado de agora. Somar as encerradas junto diria
    que uma usina resolvida há seis meses ainda tem 40 trackers parados."""
    por = {}
    for o in (ocs or []):
        u = str((o or {}).get("Usina") or "").strip() or "(sem usina)"
        g = por.setdefault(u, {"usina": u, "cliente": o.get("_cliente") or SEM_CLIENTE,
                               "n": 0, "n_abertas": 0, "qtd": 0, "itens": []})
        g["itens"].append(o)
        g["n"] += 1
        if o.get("_estado") != "encerrada":
            g["n_abertas"] += 1
            g["qtd"] += qtd_de(o, aba)
    grupos = list(por.values())
    for g in grupos:
        g["itens"] = ordenar(g["itens"])
    grupos.sort(key=lambda g: (-g["qtd"], -g["n_abertas"], g["usina"].lower()))
    return grupos


def colunas_da_aba(aba: str) -> list:
    """Nomes das colunas, na ordem. Trackers tem 8 (Cabine E Tracker), Strings tem 7."""
    return FIXAS_ANTES + list(EXTRA_COL.get(aba) or []) + FIXAS_DEPOIS


def so_numero(v) -> str:
    """'02' -> '2'. A planilha guarda a cabine com zero à esquerda; é formatação de quem digitou,
    não parte do número (Levi, 31/08). Texto que não for número passa inteiro — há cabine escrita
    como '1A' e cortar o zero de '01A' quebraria o nome."""
    t = str(v or "").strip()
    if not t:
        return "—"
    return str(int(t)) if t.isdigit() else t


def fmt_dt(v, com_hora: bool = True) -> str:
    d = tickets_calc._para_dt(v)
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def para_input(v) -> str:
    """A data no formato do <input type=datetime-local>. '' quando não dá para ler."""
    d = tickets_calc._para_dt(v)
    return d.strftime("%Y-%m-%dT%H:%M") if d is not None else ""


def dias_desde(ini, fim=None, agora=None):
    """Dias entre o Início e o Fim (ou até agora, se ainda aberta). None quando não dá para
    calcular — mesma régua do `indisponibilidade_horas`: número plausível e errado é pior que
    traço na tela."""
    a = tickets_calc._para_dt(ini)
    if a is None:
        return None
    b = tickets_calc._para_dt(fim) or (agora or dt.datetime.now())
    if b < a:
        return None
    return (b - a).days


def periodo_txt(dias) -> str:
    """O Período em UNIDADE QUE SE LÊ: dia até 60, depois mês, depois ano.

    O CORTE EM 60 DIAS, e não em 30: 30 é o limiar do alarme vermelho. Se a unidade virasse mês
    exatamente ali, "31 dias" viraria "1 mês" no mesmo ponto em que a linha fica vermelha, e quem
    varre a lista perderia a noção de quanto passou do limite.

    ARREDONDA PARA BAIXO, sempre: "1 ano" com 470 dias é menos errado que "1 ano e 4 meses" dando
    a entender precisão que a origem não tem."""
    if dias is None or dias < 0:
        return "—"
    if dias < 60:
        return "1 dia" if dias == 1 else "%d dias" % dias
    # UMA escada só, em meses. Contar o ano à parte (`dias // 365`) criava um degrau feio: 364
    # dias saía "12 meses" e 365 saía "1 ano", os dois na mesma tela.
    meses = dias // 30
    if meses < 12:
        return "1 mês" if meses == 1 else "%d meses" % meses
    anos, resto = divmod(meses, 12)
    if not resto:
        return "1 ano" if anos == 1 else "%d anos" % anos
    return "%d ano%s e %d m%s" % (anos, "" if anos == 1 else "s", resto, "ês" if resto == 1 else "eses")


def eh_conformidade(row: dict) -> bool:
    """'Em conformidade' NÃO é ocorrência: é o check periódico dizendo que o tracker está bem.

    Medido em 28/08 sobre 999 linhas: 734 são 'Em conformidade' (418 delas até sem Fim). Sem este
    filtro a régua 'Sem OS' contaria ~654 em vez das 236 ocorrências reais — número plausível e
    completamente errado. A coluna Status só existe em Trackers; em Strings nunca dispara."""
    return str((row or {}).get("Status") or "").strip().lower() == "em conformidade"


def montar(linhas: list, agora=None) -> tuple:
    """(ocorrências, ocultas) — as linhas da planilha viram ocorrências com estado, dias e horas.

    As ESCONDIDAS ficam guardadas: elas não são ocorrência e não entram na tabela, mas o nome da
    usina nelas é o mesmo nome da planilha, e uma correção que ignore isso fica pela metade."""
    ocs, ocultas = [], []
    for row in (linhas or []):
        if not isinstance(row, dict):
            continue
        if eh_conformidade(row):
            ocultas.append(row)
            continue
        ini, fim = row.get("Início da ocorrência"), row.get("Fim da ocorrência")
        row["_estado"] = tickets_spec.estado_do_ticket(row.get("OS"), row.get("Status da OS"), fim)
        row["_dias"] = dias_desde(ini, fim, agora)
        row["_horas"] = tickets_calc.indisponibilidade_horas(ini, fim)
        ocs.append(row)
    return ocs, ocultas


def recalcular(ocs: list, agora=None) -> list:
    """Estado, dias e horas de novo, DEPOIS do diário.

    O `montar` roda antes de o diário entrar, e o diário muda justamente o que decide o estado: a
    OS e o Fim. Sem recalcular, a ocorrência com OS vinculada seguia "Aberta" no contador e no
    painel, com o número da OS na coluna ao lado (medido em 22/09: 6 em Trackers, 5 em Strings).
    O app de mesa recalcula só as linhas com campo restaurado, e a OS nunca é "restaurada" (não
    tem coluna); aqui recalcula todas, que custa nada perto da leitura da aba."""
    for row in (ocs or []):
        ini, fim = row.get("Início da ocorrência"), row.get("Fim da ocorrência")
        row["_estado"] = tickets_spec.estado_do_ticket(row.get("OS"), row.get("Status da OS"), fim)
        row["_dias"] = dias_desde(ini, fim, agora)
        row["_horas"] = tickets_calc.indisponibilidade_horas(ini, fim)
    return ocs


def celula(oc: dict, coluna: str, aba: str) -> str:
    """O texto de uma célula da tabela, na régua do app."""
    if coluna == "Cabine":
        return so_numero(oc.get("Nº do SKID"))
    if coluna == "Tracker":
        return str(oc.get("Nº do tracker / Identificação") or "—")
    if coluna == "Inversor":
        return str(oc.get("Inversor") or "—")
    if coluna == "Período":
        return periodo_txt(oc.get("_dias"))
    if coluna == "Início da ocorrência":
        return fmt_dt(oc.get("Início da ocorrência"))
    if coluna == COL_ATIVO:
        return str(oc.get("Ativo") or "—")
    if coluna == "OS":
        # "Sem OS" e não um traço: a ausência de OS é o estado que a tela existe para caçar
        return str(oc.get("OS") or "").strip() or "Sem OS"
    campo = CAMPO_DA_COLUNA.get(coluna, coluna)
    return str(oc.get(campo) or "—")


def alarme(oc: dict) -> bool:
    """Aberta há mais de 30 dias — o vermelho da coluna Período."""
    if (oc or {}).get("_estado") == "encerrada":
        return False
    return (oc.get("_dias") or 0) > ALARME_DIAS


def placar(ocs: list) -> dict:
    """Quantas ocorrências em cada estado do ciclo de vida, na ordem do `tickets_spec.ESTADOS`."""
    por = {k: 0 for k, _r, _c in tickets_spec.ESTADOS}
    for o in (ocs or []):
        k = (o or {}).get("_estado")
        if k in por:
            por[k] += 1
    return por


def filtrar(ocs: list, estado: str = "", busca: str = "", so_alarme: bool = False,
            cliente: str = "", usina: str = "") -> list:
    """Cliente + usina + estado + texto + o filtro 'abertas há mais de 30 dias'. A busca varre tudo
    que é texto da linha: quem procura uma ocorrência sabe o inversor OU a usina OU o número da
    OS, não a coluna certa."""
    q = (busca or "").strip().lower()
    out = []
    for o in (ocs or []):
        if cliente and o.get("_cliente") != cliente:
            continue
        if usina and str(o.get("Usina") or "").strip() != usina:
            continue
        if estado and o.get("_estado") != estado:
            continue
        if so_alarme and not alarme(o):
            continue
        if q and q not in " ".join(str(v) for k, v in o.items()
                                   if not str(k).startswith("_") and v is not None).lower():
            continue
        out.append(o)
    return out


def ordenar(ocs: list) -> list:
    """Mais antiga primeiro DENTRO das abertas, e as encerradas por último.

    É a ordem de quem vai trabalhar a fila: o que está aberto há mais tempo é o que mais custa, e
    o encerrado só interessa como consulta."""
    def chave(o):
        encerrada = 1 if o.get("_estado") == "encerrada" else 0
        dias = o.get("_dias")
        return (encerrada, -(dias if dias is not None else -1))
    return sorted(ocs or [], key=chave)


ERRO_ABA = "Aba de tickets desconhecida: %s"
ERRO_SEM_LINHA = "Ocorrência sem número de linha — recarregue a lista."
ERRO_NADA_MUDOU = "Nada mudou nesta ocorrência."
ERRO_CAMPO = "Campo que esta tela não edita: %s"


DATAS = ("Início da ocorrência", "Início do chamado pela Grid Co.", "Fim da ocorrência")
# Os campos que a planilha NÃO tem como coluna: vivem só no diário (tickets_diario.CAMPOS_SEM_COLUNA).
# Mandá-los no PUT não adianta (o `para_valores` só escreve o que está no cabeçalho), e conferir
# conflito neles contra a linha da planilha compararia com o vazio.
SO_DIARIO = frozenset({"OS", "Ativo", "Status do ticket"})


def para_iso(v) -> str:
    """'21/09/2026 14:30' ou '2026-09-21T14:30' → '2026-09-21 14:30:00' (steps/tickets.py::para_iso).

    A coluna guarda ISO, conferido no dado real. Gravar do jeito que o navegador manda deixaria a
    mesma coluna com dois formatos — o nosso parser aguenta; quem ordena a planilha por data, não."""
    d = tickets_calc._para_dt(v)
    return d.strftime("%Y-%m-%d %H:%M:%S") if d is not None else str(v or "").strip()


def _norm(campo: str, v) -> str:
    """O valor na forma em que dá para comparar: data por instante (ao minuto), resto por texto.

    Sem isto a data que ninguém tocou parecia mudada — o painel devolve "2026-09-21T14:30" e a
    planilha guarda "2026-09-21 14:30:00"."""
    if campo in DATAS:
        d = tickets_calc._para_dt(v)
        return d.strftime("%Y-%m-%d %H:%M") if d is not None else str(v or "").strip()
    return str(v or "").strip()


def validar_edicao(aba: str, atual: dict, valores: dict, originais: dict = None) -> tuple:
    """(mudou, erro) — o que a PESSOA mudou, e só isso.

    "Mudou" é contra o que ela VIU ao abrir o painel (`originais`), não contra o banco de agora:
    se outra pessoa mexeu na linha nesse meio-tempo, o painel ainda mostra o valor velho, e
    comparar com o banco faria esse valor velho parecer uma edição — que sobrescreveria o outro.
    Sem `originais` (chamada antiga), cai no `atual`, que é o comportamento de antes.

    As datas mudadas saem em ISO; os outros campos, aparados."""
    if aba not in tickets_spec.ABAS:
        return {}, ERRO_ABA % aba
    if not (atual or {}).get("_row"):
        return {}, ERRO_SEM_LINHA
    base = originais if originais is not None else (atual or {})
    mudou = {}
    for campo, novo in (valores or {}).items():
        if campo not in EDITAVEIS:
            return {}, ERRO_CAMPO % campo
        if _norm(campo, novo) != _norm(campo, base.get(campo)):
            mudou[campo] = para_iso(novo) if (campo in DATAS and str(novo or "").strip()) \
                else str(novo or "").strip()
    if not mudou:
        return {}, ERRO_NADA_MUDOU
    return mudou, ""


def conflitos(atual: dict, originais: dict, mudou: dict) -> list:
    """Os campos que a pessoa mudou E que alguém MAIS mudou desde que ela abriu o painel.

    Só esses. Campo que o outro mudou e esta pessoa não tocou não é conflito — é a edição dele,
    e ela fica (a linha inteira volta com o valor ATUAL do banco, não com o que o painel viu)."""
    if originais is None:
        return []
    return [c for c in (mudou or {}) if _norm(c, (atual or {}).get(c)) != _norm(c, originais.get(c))]


def linha_inteira(atual: dict, mudou: dict, cabecalho: list) -> dict:
    """A LINHA INTEIRA para o PUT, com o que mudou por cima.

    INTEIRA porque o PUT da API substitui a linha, e o `para_valores` põe "" em toda coluna
    ausente: mandar só o que mudou apagaria Usina, Cliente, Supervisor e as datas. É o defeito que
    a primeira versão desta tela tinha (22/09) — e que o app nunca teve (steps/tickets.py::_salvar).
    As colunas vêm do cabeçalho da aba; campo que só existe no diário não entra."""
    cab = [c for c in (cabecalho or []) if str(c or "").strip()]
    linha = {c: (atual or {}).get(c) for c in cab}
    for c, v in (mudou or {}).items():
        if c in linha:
            linha[c] = v
    return linha


def retrato_para_diario(atual: dict, mudou: dict, campos) -> dict:
    """O registro do diário: TODOS os campos como ficaram, não só o que mudou.

    É o que o app de mesa grava (`steps/tickets.py::_digitado`), e o motivo é a leitura: dos
    registros de uma linha só o MAIS NOVO vale. Um registro com só a Causa raiz faria a OS vinculada
    antes sumir da tela, porque a OS não tem coluna na planilha e mora apenas no diário. `atual` já
    vem com o diário aplicado, então o que ele carrega é o que a pessoa via."""
    retrato = {}
    for c in (campos or []):
        v = (atual or {}).get(c)
        v = "" if v is None else str(v).strip()
        retrato[c] = para_iso(v) if (c in DATAS and v) else v
    retrato.update(mudou or {})
    return retrato


def muda_a_planilha(mudou: dict, cabecalho: list) -> bool:
    """Se algum campo mudado é coluna de verdade. OS e Status do ticket sozinhos vão só ao diário —
    regravar a linha inteira por eles seria um PUT à toa, com a janela de conflito que ele abre."""
    cab = set(cabecalho or [])
    return any(c in cab and c not in SO_DIARIO for c in (mudou or {}))


def mensagem_salvo(dados: dict, oc: dict) -> str:
    n = len(dados or {})
    quais = ", ".join(sorted(dados or {}))
    return ("%d campo%s gravado%s na ocorrência da linha %s: %s."
            % (n, "" if n == 1 else "s", "" if n == 1 else "s", (oc or {}).get("_row"), quais))


# ── EXCLUIR (steps/tickets.py::_apagar_ocorrencia) ───────────────────────────────────────────
# DUAS perguntas, e cada uma faz um trabalho (Levi, 07/09). A primeira mostra QUAL ocorrência vai
# sumir, para pegar o clique na linha errada. A segunda diz o que ninguém vê: que apagar alcança
# todo mundo que lê esse banco. Se as duas dissessem a mesma coisa, a segunda seria clicada no
# automático.
APAGAR_QUAL = "Apagar esta ocorrência da aba %s?\n\n%s\n%s\nlinha %s do banco"
APAGAR_ALCANCE = ("Não tem desfazer.\n\nA linha sai da Gridco Performance API — some para todo "
                  "mundo que lê esse banco, não só desta tela. O diário do app guarda edição, não "
                  "linha apagada, e o sync da planilha não repõe mais estas abas.\n\nApagar mesmo?")
ERRO_LINHA_MUDOU = ("Esta linha do banco não é mais a mesma ocorrência que o painel mostrava — "
                    "alguém apagou ou reordenou linhas nesse meio-tempo. Nada foi apagado; "
                    "recarregue a tela.")


def identificacao(aba: str, oc: dict) -> str:
    """"TIM100 · 2 · 93" — a usina e as colunas extras da aba, como o app monta."""
    partes = [str((oc or {}).get("Usina") or "").strip()]
    partes += [celula(oc, c, aba) for c in EXTRA_COL.get(aba, [])]
    return " · ".join(p for p in partes if p and p != "—")


# ── VINCULAR OS (steps/tickets.py::_vincular_os / _status_ao_vincular) ───────────────────────
def pode_vincular(oc: dict) -> bool:
    """Só em ocorrência SEM OS e ainda aberta. Encerrada já acabou; com OS, o caminho é o número."""
    return bool(oc) and not str(oc.get("OS") or "").strip() and oc.get("_estado") != "encerrada"


def status_ao_vincular(status_atual, status_da_os) -> str:
    """O "Status do ticket" padrão ao vincular: 'OS em Verificação' se o técnico já fechou a OS,
    'OS Programada' se não. SÓ preenche vazio — status escolhido à mão não é sobrescrito."""
    if str(status_atual or "").strip():
        return str(status_atual).strip()
    st = str(status_da_os or "").lower()
    return "OS em Verificação" if ("verifica" in st or "conclu" in st) else "OS Programada"


def numero_da_os(v) -> str:
    """O número da OS de uma célula que alguém digitou: "13801", "OS 13801", "13801/13802".
    '' quando não há número — aí a célula não vira link para uma OS que não existe."""
    m = re.search(r"\d{3,}", str(v or ""))
    return m.group(0) if m else ""


# ── TROCAR A USINA (porte de steps/lupa_usinas.py — o módulo importa PyQt6 no topo) ──────────
_UF = re.compile(r"^[A-Z]{2}$")
SEG_POR_LINHA = 0.4          # custo medido de um PUT na Gridco Performance API (07/09)
LOTE_USINA = 20              # linhas por requisição: cada lote cabe em ~10 s e a tela mostra o avanço
PERGUNTA_USINA = ("“%s” não existe no cadastro do Fracttal — e não existe em nenhuma das %d "
                  "linhas desta aba que repetem esse nome%s.\n\nTrocar as %d por “%s”?\n\n"
                  "Leva cerca de %d segundo(s).")
DETALHE_CHECKS = " (%d ocorrência(s) e %d linha(s) de check periódico, que a tela não lista)"


def _nt(t) -> str:
    import api
    return api._norm_txt(t)


def nome_curto(cliente, nome) -> str:
    """"Axis - Petrolina 3 - PE" → "Petrolina 3". É ESTE que vai para a planilha.

    Conservador de propósito: só tira o começo se ele for exatamente o cliente, e só tira o fim se
    for sigla de estado. Encurtar errado faria a linha casar com a usina errada."""
    nome = str(nome or "").strip()
    cliente = str(cliente or "").strip()
    partes = [p.strip() for p in nome.split(" - ")]
    if len(partes) >= 2 and cliente and partes[0].casefold() == cliente.casefold():
        partes = partes[1:]
    if len(partes) >= 2 and _UF.match(partes[-1]):
        partes = partes[:-1]
    return " - ".join(partes) or nome


def _desempatar(usinas: list) -> None:
    """Nome curto que serve para DUAS usinas volta a ser o nome COMPLETO do cadastro.

    Medido em 08/09: "Linhares 1" existe na Axis e na Thopen. Gravar o curto deixaria a linha
    apontando para dois clientes. Vale para nome CONTIDO em outro, porque o casamento é por trecho."""
    empatados = [u for u in usinas
                 if any(o is not u and (_nt(u["curto"]) == _nt(o["curto"]) or _nt(u["curto"]) in _nt(o["curto"]))
                        for o in usinas)]
    for u in empatados:
        u["curto"] = u["nome"]


def usinas_do_catalogo(ativos: list) -> list:
    """[{cliente, nome, curto, codigo, n}] — uma entrada por usina do Fracttal, na ordem de cliente."""
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
        out.append({"cliente": cli or "sem cliente", "nome": nome, "curto": nome_curto(cli, nome),
                    "codigo": cods.most_common(1)[0][0], "n": len(lst)})
    _desempatar(out)
    return sorted(out, key=lambda u: (_nt(u["cliente"]), _nt(u["nome"])))


def escopo_da_usina(ocs: list, ocultas: list, antigo: str) -> dict:
    """Quais linhas mudam ao trocar a usina "antigo" — as ocorrências E as escondidas.

    As escondidas contam porque o nome errado é da PLANILHA, não da linha: PEIII virou PTL300 em 13
    linhas e a 14ª, 'Em conformidade', ficou para trás (08/09). Dizer quantas ANTES de mexer é o
    que torna aceitável uma escolha de dois cliques que reescreve 147 linhas."""
    alvo = str(antigo or "").strip()
    a = [o.get("_row") for o in (ocs or []) if str(o.get("Usina") or "").strip() == alvo and o.get("_row")]
    b = [o.get("_row") for o in (ocultas or []) if str(o.get("Usina") or "").strip() == alvo and o.get("_row")]
    linhas = a + b
    return {"linhas": linhas, "n_ocs": len(a), "n_checks": len(b),
            "segundos": max(1, round(len(linhas) * SEG_POR_LINHA))}


def pergunta_usina(antigo: str, novo: str, esc: dict) -> str:
    n = len(esc.get("linhas") or [])
    detalhe = DETALHE_CHECKS % (esc["n_ocs"], esc["n_checks"]) if esc.get("n_checks") else ""
    return PERGUNTA_USINA % (antigo, n, detalhe, n, novo, esc.get("segundos") or 1)
