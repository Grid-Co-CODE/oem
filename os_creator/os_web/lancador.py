# os_creator/os_web/lancador.py
"""O lançador da aba Criar OS e as abas, como no `app.py` do desktop — MESMOS textos, MESMA ordem, MESMOS ícones.

Os textos moram aqui de novo (e não são importados do `app.py`) porque aquele módulo é Qt: importá-lo num servidor web
carregaria o PyQt6 inteiro só para ler nove strings. `tests/test_os_web_fidelidade.py` lê o código-fonte do app e
falha se um lado mudar sem o outro."""
from __future__ import annotations
from markupsafe import Markup

# (chave, icone, titulo, subtitulo, destino). Ativos em 1º (Levi, 06/08): consulta é a porta de entrada. As áreas
# (Engenharia) entram DEPOIS dos cards do app, sempre — a grade não muda para quem já usa.
CARDS = [
    {"chave": "ativos", "icone": "rack", "titulo": "Ativos", "sub": "Todo o catálogo do Fracttal — busca, histórico e atalhos", "href": "/os/em-breve/ativos"},
    {"chave": "perf", "icone": "bolt", "titulo": "Performance", "sub": "Inversores, Strings, Trackers e ETM", "href": "/os/performance"},
    {"chave": "cos", "icone": "stack", "titulo": "COS", "sub": "Ocorrência de desligamento, religamento e inspeção", "href": "/os/em-breve/cos"},
    {"chave": "pcm", "icone": "calendar", "titulo": "PCM", "sub": "OS planejada por família de plano, vários ativos", "href": "/os/em-breve/pcm"},
    {"chave": "chamados", "icone": "headset", "titulo": "Chamados", "sub": "Nova OS ligada a uma OS pai, com a etiqueta CHAMADOS", "href": "/os/em-breve/chamados"},
    {"chave": "insp", "icone": "searchcheck", "titulo": "Inspeção de chamados", "sub": "OS de teste que fundamenta o chamado — subtarefas por ativo e marca", "href": "/os/em-breve/insp"},
    {"chave": "tradicional", "icone": "file", "titulo": "Tradicional", "sub": "Criar OS do zero, passo a passo", "href": "/os/em-breve/tradicional"},
    {"chave": "clonar", "icone": "copy", "titulo": "Clonar OS", "sub": "Duplicar uma OS existente pelo número", "href": "/os/em-breve/clonar"},
    {"chave": "eng", "icone": "etm", "titulo": "Engenharia", "sub": "OS de ETM e as análises da Engenharia", "href": "/os/em-breve/eng"},
]

# as abas do app, na ordem (a de Solicitação / PCM ainda mora só no app)
ABAS = [
    {"chave": "criar", "titulo": "Criar OS", "icone": "plus", "href": "/os/"},
    {"chave": "solic", "titulo": "Solicitação / PCM", "icone": None, "href": "/os/em-breve/solic"},
    {"chave": "hist", "titulo": "Históricos de OS", "icone": "history", "href": "/os/historico"},
]

# O que cada card/aba faz no app e ainda não faz na web (a página "em breve" explica com estas palavras).
NO_APP = {
    "ativos": ("Ativos", "o catálogo inteiro do Fracttal, com busca, histórico do ativo e atalhos para criar OS"),
    "cos": ("COS", "a OS de ocorrência: desligamento, religamento e inspeção, com as regras de proteção do COS"),
    "pcm": ("PCM", "a OS planejada por família de plano, para vários ativos de uma vez"),
    "chamados": ("Chamados", "a OS nova ligada a uma OS pai, com a etiqueta CHAMADOS"),
    "insp": ("Inspeção de chamados", "a OS de teste que fundamenta o chamado, com subtarefas por ativo e marca"),
    "tradicional": ("Tradicional", "o passo a passo de criar uma OS do zero"),
    "clonar": ("Clonar OS", "duplicar uma OS existente pelo número"),
    "eng": ("Engenharia", "as OS de ETM e as análises da Engenharia"),
    "solic": ("Solicitação / PCM", "o painel de solicitações, o formulário, a fila do PCM e o histórico"),
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
