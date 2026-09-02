"""O registro de áreas do launcher.

Existe porque a promessa feita à Engenharia — "você é dona de uma linha no app.py" — só é verdade
se card, título, descrição e ícone vierem do pacote da área. Quando alguma dessas pontas volta
para o `app.py`, o portão de fronteira do CI passa a reprovar PR legítimo e a área fica sem saída.
Ver docs/ambiente-compartilhado-engenharia.md, §6.3.
"""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # antes de importar app: ele carrega PyQt

import app

# Os 14 nomes que o `_ICO` tinha antes de existir área alguma. Repetidos aqui de propósito: é o
# que faz o teste de colisão falhar se uma área tentar usar um deles.
_ICONES_DO_APP = {
    "bolt", "stack", "calendar", "file", "copy", "arrow", "plus", "doc",
    "history", "clipboard", "headset", "searchcheck", "rack", "ticket",
}


def test_a_engenharia_esta_registrada_como_area():
    assert "eng" in [a.CHAVE for a in app.AREAS]


def test_o_icone_de_toda_area_entrou_no_dicionario_do_launcher():
    # Sem isto o card abre com o ícone `doc` e ninguém percebe: o `_icone()` ganhou fallback
    # justamente por causa da v135, então nome desconhecido não derruba mais o app — só troca o
    # desenho, em silêncio, e o erro fica só no log.
    for a in app.AREAS:
        assert a.ICONE in app._ICO, (
            "ícone '%s' da área '%s' não entrou no _ICO" % (a.ICONE, a.CHAVE))


def test_nenhuma_area_sobrescreve_icone_do_app():
    # `_ICO.update()` de uma área com nome repetido trocaria o desenho de um card do app sem aviso.
    for a in app.AREAS:
        colisoes = _ICONES_DO_APP & set(a.ICONES)
        assert not colisoes, "área '%s' redefine ícone do app: %s" % (a.CHAVE, colisoes)


def test_o_selo_de_analises_nao_volta_a_ser_achado_por_indice():
    # O selo "N atribuídas a você" já apontou para o card errado quando o Tickets entrou no meio
    # da lista, e o comentário no código avisava que aconteceria de novo. Agora é achado pelo
    # título. Este teste impede que a busca por índice volte num merge distraído — mesma ideia do
    # test_updater_canal.py, que tranca o canal de release dentro do repositório.
    fonte = os.path.join(os.path.dirname(app.__file__), "app.py")
    with open(fonte, encoding="utf-8") as f:
        txt = f.read()
    assert '_cards_por_titulo["Performance"]' in txt
    # O que se proíbe é a ATRIBUIÇÃO por índice, não a menção. O comentário ao lado do código cita
    # `_launcher_cards[2]` de propósito — é ele que conta por que a busca mudou. Um grep pela
    # string crua reprovava essa explicação e empurrava para apagá-la, que é o oposto do que este
    # repositório faz com o histórico de um erro.
    assert not re.search(r"_card_perf\s*=\s*self\._launcher_cards\[", txt)
