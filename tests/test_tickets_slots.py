"""Todo slot ligado a `clicked` tem de aceitar o bool que o Qt manda.

Não é preciosismo: o `@slot_seguro` captura a exceção e segue (é para isso que ele existe), então
o sintoma de um slot com assinatura errada NÃO é um traceback — é o botão não fazer nada. Foi
assim que o "✕ visão geral" ficou mudo entre 30 e 31/08, e ninguém percebeu porque a tela
continuava funcionando em tudo o mais.

SÓ VALE PARA SLOT DECORADO. Sem decorador o PyQt inspeciona a assinatura e corta o argumento
sozinho — por isso a maioria dos botões do app funciona com `def _x(self)`. Com o decorador, o
que o PyQt inspeciona é o wrapper (`*a, **k`), que aceita tudo e repassa o bool adiante.

O teste lê o código-fonte em vez de instanciar a tela: montar a `TicketsTab` exige QApplication e
rede, e o que está sendo verificado é estático.
"""
import inspect
import io
import os
import re

ARQS = ["tickets.py", "performance.py", "historico.py", "ativos.py", "varias_os.py"]


def _fonte(nome):
    import steps
    caminho = os.path.join(os.path.dirname(inspect.getfile(steps)), nome)
    if not os.path.exists(caminho):
        return None
    return io.open(caminho, encoding="utf-8").read()


def test_slots_de_clicked_aceitam_o_argumento():
    problemas = []
    for arq in ARQS:
        s = _fonte(arq)
        if s is None:
            continue
        for metodo in sorted(set(re.findall(r"clicked\.connect\(self\.(\w+)\)", s))):
            d = re.search(r"(@slot_seguro\s+)?def %s\(self([^)]*)\)" % re.escape(metodo), s)
            if d is None:
                continue          # slot herdado ou vindo de fora do arquivo
            if d.group(1) and not d.group(2).strip():
                problemas.append("%s.%s" % (arq, metodo))
    assert not problemas, (
        "estes slots estão ligados a clicked mas não aceitam o bool do Qt — o botão fica mudo "
        "porque o @slot_seguro engole o TypeError: %s" % ", ".join(problemas))
