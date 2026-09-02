"""Portão 2 do CI: o layout da área da Engenharia.

A área é dona do conteúdo; a casa segura o layout. Na prática isso é uma regra só — cor sai por
nome importado de `steps/ui.py`, nunca por hexadecimal escrito à mão.

POR QUE VALE SÓ PARA `steps/engenharia/`: o resto do `steps/` tem 223 literais hexadecimais em 88
cores distintas (medido em 31/08/2026). A mesma regra aplicada ao repositório inteiro reprovaria
tudo e seria desligada na primeira semana. A pasta nova começa limpa e não acumula a dívida.

POR QUE "NOME, NUNCA HEX": o `CLAUDE.md` da raiz manda um valor de navy e o `steps/ui.py` usa
outro. Quem escreve hex à mão escolhe entre dois valores em conflito, e a tela sai fora do tema
sem ninguém notar. Nome não tem esse problema — resolve para o que o código usa de fato.
"""
import os
import re

import steps.engenharia as area

_PASTA = os.path.dirname(area.__file__)
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# pictogramas e dingbats. A faixa de SETAS fica de fora de propósito: o app usa "← Voltar", e
# incluí-la reprovaria código correto.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-⛿✀-➿️]")


def _fontes():
    """Todo .py da pasta da área."""
    for raiz, _dirs, arquivos in os.walk(_PASTA):
        if "__pycache__" in raiz:
            continue
        for nome in sorted(arquivos):
            if nome.endswith(".py"):
                yield os.path.join(raiz, nome)


def _ocorrencias(padrao):
    achados = []
    for caminho in _fontes():
        with open(caminho, encoding="utf-8") as f:
            for n, linha in enumerate(f, 1):
                if padrao.search(linha):
                    achados.append("%s:%d: %s" % (os.path.basename(caminho), n, linha.strip()))
    return achados


def test_a_area_tem_pelo_menos_um_arquivo_para_conferir():
    # sem isto, apagar a pasta por engano deixaria os dois testes abaixo passando com zero
    # arquivo lido — portão aberto que parece fechado.
    assert list(_fontes()), "nenhum .py encontrado em %s" % _PASTA


def test_nenhuma_cor_escrita_a_mao_na_area():
    achados = _ocorrencias(_HEX)
    assert not achados, (
        "cor escrita à mão na área da Engenharia. Importe o nome de steps/ui.py "
        "(BG, CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED):\n" + "\n".join(achados))


def test_sem_emoji_na_area():
    achados = _ocorrencias(_EMOJI)
    assert not achados, (
        "emoji na área da Engenharia; severidade se comunica por cor:\n" + "\n".join(achados))


def test_a_regra_pega_o_que_deve_pegar():
    """O lint precisa FALHAR quando deve.

    Sem este teste, um erro na expressão regular deixa o portão aberto e todo mundo acha que está
    protegido — que é exatamente o modo de falha que este arranjo inteiro existe para evitar.
    """
    assert _HEX.search("color:#0B1020;")
    assert _HEX.search('"#fff"')
    assert not _HEX.search("color:{TEXT}")          # f-string com nome: é o jeito certo
    assert not _HEX.search("# comentário comum")
    assert _EMOJI.search("pronto \U0001F600")
    assert not _EMOJI.search("← Voltar")            # seta não é emoji: o app usa isso no wrap


def test_o_documento_da_area_nao_cita_hexadecimal():
    """A régua escrita para a Engenharia cita NOME, nunca hex.

    Se o documento trouxer o navy do `CLAUDE.md` da raiz e o código usar o do `steps/ui.py`, o
    agente obedece ao documento — é o que ele lê primeiro — e a tela sai fora do tema. O texto
    perde a autoridade sobre cor e a devolve ao `steps/ui.py`, que é quem manda.
    """
    caminho = os.path.join(_PASTA, "CLAUDE.md")
    with open(caminho, encoding="utf-8") as f:
        achados = ["%d: %s" % (n, l.strip()) for n, l in enumerate(f, 1) if _HEX.search(l)]
    assert not achados, (
        "o CLAUDE.md da área cita cor em hexadecimal; cite o NOME do steps/ui.py:\n"
        + "\n".join(achados))
