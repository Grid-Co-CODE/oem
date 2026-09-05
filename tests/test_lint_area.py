# -*- coding: utf-8 -*-
"""O portão de layout da área da Engenharia.

Ele existe porque `steps/engenharia/CLAUDE.md` prometia TRÊS conferências no CI e havia duas —
a pasta e os testes. A que faltava era justo esta, a que torna verdadeira a frase que sustenta o
arranjo: a Engenharia é dona do conteúdo, a casa segura o layout.

Testar o portão importa tanto quanto tê-lo: um lint que para de detectar não avisa que parou.
"""
import importlib.util
import io
import os

import pytest

_CAM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    ".github", "lint_area.py")


@pytest.fixture(scope="module")
def lint():
    spec = importlib.util.spec_from_file_location("lint_area", _CAM)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_pega_cor_escrita_a_mao(lint):
    assert lint._HEX.search('COR = "#1a2b3c"')
    assert lint._HEX.search("borda:#ABC;")
    assert lint._HEX.findall('a "#0B1020" b "#fff"') == ["#0B1020", "#fff"]


def test_nao_confunde_comentario_nem_numero_com_cor(lint):
    assert not lint._HEX.search("# comentário comum")
    assert not lint._HEX.search("linha 42, item #7")
    assert not lint._HEX.search("qtd #12345")          # 5 dígitos não é cor


def test_pega_emoji(lint):
    assert lint._emoji("\U0001F525")      # FIRE
    assert lint._emoji("⚠")          # sinal de aviso


def test_NAO_reprova_a_pontuacao_que_a_interface_usa(lint):
    """`·` separa campo em toda a interface e `°` aparece em temperatura. Se o portão pegasse
    esses, a régua viraria uma chateação e alguém desligaria o portão inteiro."""
    for ch in "·°—–…“”≥≤×":
        assert not lint._emoji(ch), "reprovou %r, que é pontuação e não figura" % ch


def test_a_pasta_da_area_esta_limpa_hoje(lint):
    """A régua só se paga porque a pasta nasceu limpa. Se este teste falhar, alguém escreveu cor
    à mão no repositório e o portão do CI vai reprovar o próximo PR da Engenharia."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cwd = os.getcwd()
    try:
        os.chdir(raiz)
        assert lint.main() == 0
    finally:
        os.chdir(cwd)


def test_a_mensagem_cita_NOMES_e_nao_hex(lint, tmp_path, monkeypatch, capsys):
    """Se o erro dissesse "use #0B1020", o agente obedeceria ao TEXTO e escreveria o hex de novo
    — exatamente o que o portão quer impedir. Ver docs/ambiente-compartilhado-engenharia.md §3.4.

    O teste lê a mensagem que sai de verdade, e não o código-fonte dela: a primeira versão deste
    teste procurava "BG" no corpo da função e falhou, porque os nomes vêm da constante `NOMES`.
    O que precisa estar certo é o que a pessoa lê."""
    area = tmp_path / "os_creator" / "steps" / "engenharia"
    area.mkdir(parents=True)
    (area / "tela.py").write_text('COR = "#1a2b3c"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert lint.main() == 1
    saida = capsys.readouterr().out
    linhas_da_dica = [l for l in saida.splitlines() if not l.startswith("::error")]
    dica = "\n".join(linhas_da_dica)
    for nome in ("BG", "CARD", "GREEN", "TEXT", "MUTED"):
        assert nome in dica, "a mensagem não cita %s" % nome
    assert not lint._HEX.search(dica), "a mensagem do portão cita um hex — o agente vai copiá-lo"
    assert "steps/ui.py" in dica, "a mensagem não diz de ONDE tirar a cor"
