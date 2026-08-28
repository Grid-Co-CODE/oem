"""Fixtures e caminho de import dos testes.

Fica na RAIZ de propósito: o pytest insere o diretório de cada conftest.py no sys.path, e daqui
dá para apontar `os_creator/` sem instalar nada.

APPEND, nunca insert(0), pelo mesmo motivo documentado em os_creator/api.py: a raiz do
repositório não pode ganhar precedência sobre a pasta do app."""
import os
import sys

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.join(_RAIZ, "os_creator")
if _APP not in sys.path:
    sys.path.insert(0, _APP)          # aqui insert(0) é correto: queremos o os_creator na frente
