"""Descritor da área de Engenharia — o que o launcher do `app.py` lê para montar o card.

A área é dona desta pasta inteira. O `app.py` a registra com UMA linha e nunca precisa ser tocado
de novo: título, descrição e ícone moram aqui. É isso que permite ao portão de fronteira do CI ser
uma regra só ("o PR de fork cabe em steps/engenharia/"), sem exceção que se possa alargar.

Ver `CLAUDE.md` ao lado (a fronteira) e `docs/ambiente-compartilhado-engenharia.md` (o arranjo).
"""

CHAVE = "eng"                      # identifica a página da área dentro do stack do launcher
TITULO = "Engenharia"
DESCRICAO = "OS de ETM e as análises da Engenharia"

# O ícone mora AQUI, e não no `_ICO` do app.py, de propósito: `steps/CLAUDE.md` documenta que
# existem dois dicionários de ícone e que ler o nome de um para usar no outro levanta KeyError.
# A área nunca precisa saber disso — o launcher funde `ICONES` no dicionário dele ao registrar.
ICONE = "etm"
ICONES = {
    # estação meteorológica: mastro, sensor no topo e as duas hastes da medição
    "etm": '<path d="M12 21V10"/><path d="M8 21h8"/><circle cx="12" cy="7" r="3"/>'
           '<path d="M5 7a7 7 0 0 1 2-4.9"/><path d="M19 7a7 7 0 0 0-2-4.9"/>',
}


def abrir(on_voltar):
    """Cria a tela da área.

    O import é adiado para dentro da função porque o launcher lê este módulo no arranque só para
    montar o card — carregar a tela inteira ali atrasaria a abertura do app por uma tela que talvez
    ninguém clique. É o mesmo padrão do `_mostrar_modo`, onde cada `from steps.X import Y` vive
    dentro do ramo, e não no topo do arquivo.
    """
    from steps.engenharia.tela import EngenhariaTab
    return EngenhariaTab(on_voltar=on_voltar)
