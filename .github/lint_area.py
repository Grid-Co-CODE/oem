# -*- coding: utf-8 -*-
"""O portão de layout da área: nada de cor escrita à mão, nada de emoji.

POR QUE ELE EXISTE. O `steps/engenharia/CLAUDE.md` prometia três conferências no CI e só havia
duas — a pasta e os testes. Esta era a que faltava, e é justamente a que sustenta o arranjo: a
Engenharia é dona do CONTEÚDO da tela, e a casa segura o LAYOUT. Sem ela, o agente escreve
`#1a2b3c` e nada avisa; com ela, o PR reprova antes de qualquer pessoa perder tempo.

Documento de origem alertou para o defeito exato: "a pessoa vai confiar num guarda-corpo
ausente" — `docs/ambiente-compartilhado-engenharia.md` §3.1.

POR QUE SÓ NA PASTA DA ÁREA. Um lint de cor global reprovaria o repositório inteiro: são 223
literais hex e 88 cores distintas em `steps/*.py`, contra os 8 nomes que o `ui.py` exporta
(§3.4 do mesmo documento). A pasta da área é nova e começa limpa — verificado nesta data, zero
hex e zero emoji. Aqui a régua se paga; no resto, seria só ruído.

POR QUE A MENSAGEM CITA NOMES E NÃO HEX. Se o erro dissesse "use #0B1020", o agente obedeceria ao
texto e escreveria o hex de novo, que é exatamente o que se quer impedir. Ele cita `BG`, `CARD`,
`GREEN` — os nomes que o `ui.py` exporta.
"""
import io
import os
import re
import sys
import unicodedata

PASTA = os.path.join("os_creator", "steps", "engenharia")
NOMES = ("BG", "CARD", "INPUT", "BORDER", "GREEN", "GREEN_INK", "TEXT", "MUTED")

# `#RRGGBB` ou `#RGB`. O `\b` no fim evita casar o começo de um hash de commit dentro de um
# comentário; a âncora do início evita casar o `#` de comentário comum.
_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def _emoji(ch):
    """Pictograma de verdade, e não qualquer símbolo.

    A categoria `So` sozinha pegaria `°` (grau) e `·` (o separador que a interface inteira usa),
    e a régua viraria uma chateação. O corte em U+2500 deixa passar a pontuação técnica e barra
    o que é figura."""
    return ord(ch) > 0x2500 and unicodedata.category(ch) == "So"


def main():
    if not os.path.isdir(PASTA):
        print("pasta da área não existe; nada a conferir")
        return 0
    faltas = []
    for raiz, _, arqs in os.walk(PASTA):
        if "__pycache__" in raiz:
            continue
        for a in sorted(arqs):
            if not a.endswith(".py"):
                continue
            cam = os.path.join(raiz, a)
            for i, linha in enumerate(io.open(cam, encoding="utf-8"), 1):
                for m in _HEX.finditer(linha):
                    faltas.append((cam, i, "cor escrita à mão: %s" % m.group(0)))
                for ch in linha:
                    if _emoji(ch):
                        # imprime o CODIGO, e nao o caractere: o console do Windows e cp1252 e
                        # estoura com UnicodeEncodeError ao ecoar o emoji — o portao reprovava
                        # com traceback em vez de mensagem. O nome tambem diz melhor qual e.
                        faltas.append((cam, i, "emoji U+%04X (%s)" % (
                            ord(ch), unicodedata.name(ch, "sem nome"))))
    if not faltas:
        print("OK: nenhuma cor escrita à mão e nenhum emoji em %s" % PASTA)
        return 0
    for cam, i, o_que in faltas:
        print("::error file=%s,line=%d::%s" % (cam.replace(os.sep, "/"), i, o_que))
    print("")
    print("A cor sai de steps/ui.py, pelo NOME — %s." % ", ".join(NOMES))
    print("`from steps.ui import CARD, TEXT` e use a constante; não copie o valor.")
    print("Assim, o dia em que o tema mudar, esta tela muda junto.")
    print("")
    print("Emoji não entra na interface: severidade se comunica por COR, e o padrão está em")
    print("CLAUDE.md da raiz. Ícone vem de `icone_pix()`, em steps/ui.py.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
