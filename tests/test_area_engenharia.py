"""O descritor da área da Engenharia: o que o launcher lê para montar o card.

Existe porque o contrato entre o app e a área é ESTE arquivo, não o `app.py`. Se um campo sumir
ou trocar de nome, o card some da grade sem erro nenhum — o launcher só não acha o que iterar, e
o app abre normalmente com um card a menos. Ver docs/ambiente-compartilhado-engenharia.md, §6.3.
"""
import steps.engenharia as area


def test_o_descritor_tem_os_campos_que_o_launcher_le():
    assert area.CHAVE == "eng"
    assert area.TITULO == "Engenharia"
    assert area.DESCRICAO.strip()
    assert area.ICONE


def test_o_icone_citado_existe_no_proprio_pacote():
    # a área nunca toca no `_ICO` do app.py — `steps/CLAUDE.md` documenta que existem DOIS
    # dicionários de ícone e que trocar um pelo outro levanta KeyError. Ela traz o próprio, e
    # quem confere que o nome citado existe é este teste, antes de qualquer merge.
    assert area.ICONE in area.ICONES
    assert area.ICONES[area.ICONE].strip().startswith("<")


def test_a_tela_abre(qapp):
    tela = area.abrir(on_voltar=lambda: None)
    assert tela is not None


def test_a_tela_nao_desenha_o_proprio_voltar(qapp):
    # sem `_selfnav`, quem desenha o "← Voltar" é o `_wrap_modo` do app.py. Se a tela desenhasse
    # outro, ficariam DOIS Voltar na mesma tela — o caso que `steps/CLAUDE.md` documenta.
    tela = area.abrir(on_voltar=lambda: None)
    assert not getattr(tela, "_selfnav", False)
