"""Fixtures e caminho de import dos testes.

Fica na RAIZ de propósito: o pytest insere o diretório de cada conftest.py no sys.path, e daqui
dá para apontar `os_creator/` sem instalar nada.

É o INVERSO do `api.py`: lá a raiz entra depois de `os_creator/`, então basta anexá-la. Aqui
o pytest já põe a raiz na frente sozinho, então é o `os_creator/` que precisa do `insert(0)`
para continuar ganhando. A regra que ambos cumprem é a mesma — `os_creator` vence a raiz —,
o que muda é de onde cada um parte."""
import os
import sys

import pytest

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.join(_RAIZ, "os_creator")
if _APP not in sys.path:
    sys.path.insert(0, _APP)          # aqui insert(0) é correto: queremos o os_creator na frente


@pytest.fixture(scope="session")
def qapp():
    """QApplication única para os testes que instanciam widget.

    `scope="session"` não é otimização: o Qt não admite duas QApplication no mesmo processo, e
    criar a segunda aborta o interpretador sem traceback nenhum — o teste "some" em vez de falhar.

    A plataforma offscreen é fixada aqui, e não só no workflow, para o teste passar igual na
    máquina de quem escreveu — que tem tela e, sem isto, abriria janela de verdade no meio da suíte.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
