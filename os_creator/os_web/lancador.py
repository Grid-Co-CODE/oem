# os_creator/os_web/lancador.py
"""A tela inicial da web, as páginas de setor e as abas do topo.

ATÉ 27/09/2026 a web copiava o lançador do `app.py` — nove cards do mesmo peso, na ordem do app. Nesse dia o Levi pediu
outra estrutura ("parece que todo campo carrega o mesmo peso", e o PCM aparecia duas vezes: a aba "Solicitação / PCM"
e o card): primeiro CONSULTAR (Ativos, Histórico), depois os SETORES (Performance, COS, PCM, Chamados, Engenharia, mais
o jeito tradicional de criar OS) e por fim as SOLICITAÇÕES (a nova solicitação ao PCM e o Clonar OS). O PCM virou um
setor com três partes: a clonagem de planos (Handover, MPS, MPA…), a fila e o histórico das solicitações.

O app de mesa segue com a grade dele. `tests/test_os_web_fidelidade.py` lê o código-fonte do app (sem Qt) e confere
que TODO card dele tem porta aqui (`DO_APP`), com o mesmo ícone — mudar um lado sem o outro ainda acusa."""
from __future__ import annotations
from urllib.parse import urlencode

from markupsafe import Markup

SUB_CHAMADOS = "Os chamados de garantia: da OS de teste ao ticket no fornecedor."

# "em_breve" = a rota que a tela vai ter na web. Enquanto ela não existir, a porta aparece APAGADA ("no app de mesa") e
# o card leva à página que explica; no dia em que a rota nascer, a porta vira link sozinha (`portas_vivas`). A PcmTab
# (a clonagem de planos) já tem a especificação pronta em tests/test_os_web_pcm.py, para /os/pcm — por isso o setor
# PCM mora em /os/setor/pcm, e não lá.
CONSULTA = [
    {"chave": "ativos", "icone": "rack", "titulo": "Ativos", "href": "/os/ativos",
     "sub": "Todo o catálogo do Fracttal: a busca, o histórico de cada ativo e os atalhos para criar a OS dele."},
    {"chave": "hist", "icone": "history", "titulo": "Histórico de OS", "href": "/os/historico",
     "sub": "As suas, as da equipe e as do COS, com filtro por período, etiqueta, status e quem criou.",
     "portas": [{"rotulo": "Histórico geral", "href": "/os/historico?modo=criadas"},
                {"rotulo": "Atribuídas a mim", "href": "/os/historico?modo=atribuidas"},
                {"rotulo": "Visão COS", "href": "/os/historico?modo=cos"}]},
]

# o rótulo curto de cada plano da Performance no card do setor (o título inteiro não cabe numa pílula)
CURTO_PERF = {"Geração e ETM": "Geração e ETM", "Inspeção Geral do Inversor": "Inversor",
              "Recomposição de String": "String", "Verificação de Tracker Parado": "Tracker parado"}


def _portas_perf() -> list:
    from . import perf_web
    return ([{"rotulo": CURTO_PERF.get(p["titulo"], p["titulo"]), "href": "/os/performance/criar?" + urlencode({"frase": p["frase"]})}
             for p in perf_web.PLANOS] + [{"rotulo": "Tickets", "href": "/os/tickets"}])


SETORES = [
    {"chave": "perf", "icone": "bolt", "titulo": "Performance", "href": "/os/performance",
     "sub": "Inversores, strings, trackers e ETM: as OS de análise da equipe.", "portas": _portas_perf()},
    {"chave": "cos", "icone": "stack", "titulo": "COS", "href": "/os/em-breve/cos", "em_breve": "/os/cos",
     "sub": "Ocorrência de desligamento, religamento e inspeção, com as regras de proteção.",
     "portas": [{"rotulo": "Desligamento"}, {"rotulo": "Religamento"}, {"rotulo": "Inspeção"}]},
    {"chave": "pcm", "icone": "calendar", "titulo": "PCM", "href": "/os/setor/pcm",
     "sub": "As OS pelos planos do Fracttal e as solicitações que chegam ao PCM.",
     "portas": [{"rotulo": "Planos: Handover, MPS, MPA", "em_breve": "/os/pcm"},
                {"rotulo": "Fila do PCM", "href": "/os/solicitacao/fila"},
                {"rotulo": "Histórico de solicitações", "href": "/os/solicitacao/historico"}]},
    {"chave": "chamados", "icone": "headset", "titulo": "Chamados", "href": "/os/chamados", "sub": SUB_CHAMADOS,
     "portas": [{"rotulo": "Inspeção", "href": "/os/chamados/inspecao"},
                {"rotulo": "Acompanhamento", "href": "/os/chamados/acompanhamento"},
                {"rotulo": "Fornecedores", "href": "/os/chamados/fornecedores"}]},
    {"chave": "eng", "icone": "etm", "titulo": "Engenharia", "href": "/os/engenharia", "etiqueta": "em construção",
     "sub": "As OS de ETM e as análises da Engenharia."},
]

TRADICIONAL = {"chave": "tradicional", "icone": "file", "titulo": "Criar OS do zero", "rotulo": "Tradicional",
               "href": "/os/tradicional", "sub": "sem setor, passo a passo: ativo, tipo, tarefas e responsável"}

SOLICITACOES = [
    {"chave": "solic", "icone": "clipboard", "titulo": "Nova solicitação", "href": "/os/solicitacao",
     "sub": "Pedir uma OS ao PCM: o ativo, o tema, o técnico e a data sugeridos."},
    {"chave": "clonar", "icone": "copy", "titulo": "Clonar OS", "href": "/os/clonar",
     "sub": "Duplicar uma OS existente pelo número, com as tarefas e o responsável."},
]

# todas as portas da tela inicial numa lista só (o "em breve" e os testes percorrem esta)
CARDS = CONSULTA + SETORES + [TRADICIONAL] + SOLICITACOES

# card do app de mesa → a porta dele aqui. Os dois cards de chamados do app ("Chamados" e "Inspeção de chamados") são
# UM setor na web, com a inspeção dentro.
DO_APP = {"Ativos": "ativos", "Performance": "perf", "COS": "cos", "PCM": "pcm", "Chamados": "chamados",
          "Inspeção de chamados": "chamados", "Tradicional": "tradicional", "Clonar OS": "clonar", "Engenharia": "eng"}

# As partes de cada setor que tem página própria (o molde é o do Chamados): o PCM separado como o Levi pediu —
# "clonagem de Handover, MPS, MPA etc. - fila de PCM - histórico de solicitações".
PORTAS_SETOR = {
    "pcm": {"titulo": "PCM", "icone": "calendar",
            "sub": "Planejamento e controle da manutenção: as OS pelos planos, a fila das solicitações e o histórico delas.",
            "portas": [
                {"icone": "calendar", "titulo": "Clonagem de planos", "em_breve": "/os/pcm",
                 "sub": "Handover, MPS, MPA e as outras famílias: uma OS com várias tarefas a partir dos planos do Fracttal. "
                        "Marque os ativos, escolha a família e cada ativo vira uma tarefa, com o plano e as subtarefas dele.",
                 "chips": ["Handover", "MPM", "MPA", "MPS", "MPQ", "MPW", "MPT"]},
                {"icone": "listchecks", "titulo": "Fila do PCM", "href": "/os/solicitacao/fila",
                 "sub": "As solicitações esperando o PCM: aprovar e virar OS, devolver para refazer ou pôr uma observação.",
                 "rodape": "Pendentes, aprovadas e recusadas"},
                {"icone": "history", "titulo": "Histórico de solicitações", "href": "/os/solicitacao/historico",
                 "sub": "Todas as solicitações, inclusive as devolvidas para refazer, com a OS que cada uma virou.",
                 "rodape": "Busca por nº, usina, ativo e status"},
            ]},
    "chamados": {"titulo": "Chamados", "icone": "headset",
                 "sub": "O chamado de garantia nasce de uma OS de teste: primeiro a inspeção em campo, com o que o fornecedor "
                        "exige; quando o técnico fecha a inspeção, a OS de acompanhamento chega para a equipe de chamados.",
                 "portas": [
                     {"icone": "searchcheck", "titulo": "Inspeção de chamados", "href": "/os/chamados/inspecao",
                      "sub": "A OS de teste que fundamenta o chamado, com as subtarefas por ativo e fornecedor.",
                      "rodape": "OS de teste"},
                     {"icone": "headset", "titulo": "Acompanhamento de chamados", "href": "/os/chamados/acompanhamento",
                      "sub": "As OS que chegaram, as com ticket aberto no fornecedor e as finalizadas, com as observações de cada uma.",
                      "rodape": "Equipe de chamados"},
                     {"icone": "listchecks", "titulo": "Controle de fornecedores", "href": "/os/chamados/fornecedores",
                      "sub": "As subtarefas padrão que cada fornecedor exige, por tipo de ativo: inversor, tracker e o resto.",
                      "rodape": "Modelos"},
                 ]},
}


def portas_vivas(itens, existe) -> list:
    """As portas com o link resolvido: a que espera uma tela (`em_breve`) vira link no dia em que a rota existir;
    antes disso fica sem link e marcada `fora` (apagada, "no app de mesa"). `existe(rota) -> bool`."""
    out = []
    for p in itens or []:
        p = dict(p)
        if p.get("em_breve"):
            if existe(p["em_breve"]):
                p["href"] = p["em_breve"]
            else:
                p["fora"] = True
                p.setdefault("href", None)
        out.append(p)
    return out


def saudacao(hora: int) -> str:
    """Bom dia até meio-dia, boa tarde até as 18h, boa noite depois — pela hora de BRASÍLIA (o servidor pode estar
    em UTC)."""
    return "Bom dia" if 5 <= hora < 12 else ("Boa tarde" if 12 <= hora < 18 else "Boa noite")


# as abas do topo (27/09: a "Solicitação / PCM" saiu — a nova solicitação mora em Solicitações e a fila e o histórico,
# no setor PCM). A chave "criar" continua sendo a do Início: é ela que as telas passam para acender a aba.
ABAS = [
    {"chave": "criar", "titulo": "Início", "icone": "home", "href": "/os/"},
    {"chave": "hist", "titulo": "Histórico de OS", "icone": "history", "href": "/os/historico"},
]

# O que cada card/aba faz no app e ainda não faz na web (a página "em breve" explica com estas palavras).
NO_APP = {
    "cos": ("COS", "a OS de ocorrência: desligamento, religamento e inspeção, com as regras de proteção do COS"),
    "pcm": ("PCM", "a OS planejada por família de plano, para vários ativos de uma vez"),
    "tickets": ("Tickets", "as ocorrências de trackers e strings da Gridco Performance API"),
}

# Ícones de linha (SVG), os MESMOS paths do `_ICO` do app.py (+ o "etm" da área de Engenharia).
ICONES = {
    "bolt":     '<path d="M13 3 4 14h7l-1 7 9-11h-7z"/>',
    "stack":    '<path d="M12 4 3 9l9 5 9-5-9-5z"/><path d="M3 14l9 5 9-5"/>',
    "calendar": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9h16"/><path d="M8 3v4"/><path d="M16 3v4"/>',
    "file":     '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6"/><path d="M9 15h6"/>',
    "copy":     '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "arrow":    '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "plus":     '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M12 9v6"/><path d="M9 12h6"/>',
    "doc":      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
    "history":  '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 4v4h4"/><path d="M12 8v4l3 2"/>',
    "clipboard": '<rect x="6" y="4" width="12" height="16" rx="2"/><path d="M9 4h6v3H9z"/><path d="M9 12h6"/><path d="M9 16h4"/>',
    "headset":  '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="13" width="4" height="7" rx="1.5"/><rect x="17" y="13" width="4" height="7" rx="1.5"/><path d="M20 18v1a3 3 0 0 1-3 3h-3"/>',
    "searchcheck": '<path d="m8 11 2 2 4-4"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
    "rack":     '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/>'
                '<path d="M7 7.5h.01"/><path d="M7 16.5h.01"/>',
    "ticket":   '<path d="M2 9a3 3 0 1 0 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 1 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/>'
                '<path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/>',
    "etm":      '<path d="M12 21V10"/><path d="M8 21h8"/><circle cx="12" cy="7" r="3"/>'
                '<path d="M5 7a7 7 0 0 1 2-4.9"/><path d="M19 7a7 7 0 0 0-2-4.9"/>',
    # os da tela de Performance (steps/ui.py::_LUCIDE, só os que os cards de plano usam)
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "zap":      '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "alert":    '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "list":     '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
    "search":   '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
    # os do detalhe da OS (steps/os_detalhe.py: relogio da duracao, pessoas, anexos verde/azul, fluxo)
    "clock":    '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "user":     '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "userplus": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6"/><path d="M22 11h-6"/>',
    "camera":   '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
    "monitor":  '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    "branch":   '<path d="M6 3v12"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    # o botão de recolher o topo e a porta Controle de fornecedores (só da web)
    "chevup":   '<path d="m18 15-6-6-6 6"/>',
    # a aba Início (27/09/2026: a aba deixou de ser "Criar OS" — a tela inicial consulta, cria e pede)
    "home":     '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
    "listchecks": '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
}
ICONE_PADRAO = "doc"


def svg(nome: str) -> str:
    """Só o miolo (paths) do ícone — é o que o teste de fidelidade compara com o `_ICO` do app."""
    return ICONES.get(nome) or ICONES[ICONE_PADRAO]


def icone(nome: str, cor: str = "#8fce3f", size: int = 24) -> Markup:
    """A tag <svg> completa, no mesmo molde do `_SVG` do app (stroke 2, pontas arredondadas)."""
    return Markup('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="%d" height="%d" fill="none" stroke="%s" '
                  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
                  % (size, size, cor, svg(nome)))


def iniciais(nome: str) -> str:
    """'Levi Maia' → 'LM' (primeiro + último nome), como o avatar do app; sem nome → '?'."""
    partes = [p for p in (nome or "").split() if p]
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def texto_selo(n) -> str:
    """'N atribuídas a você' do card Performance; zero = sem selo (sem ruído), igual ao app."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return "1 atribuída a você" if n == 1 else f"{n} atribuídas a você"
