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


@pytest.fixture(autouse=True)
def _chamados_sem_banco(monkeypatch):
    """Os stores dos chamados (27/09/2026) vão ao banco da Gridco — nenhum teste vai. A leitura devolve vazio e a escrita
    falha ALTO (quem quer testar escrita troca `gridco_abas._get`/`escrever` no próprio teste).

    E o modelo da inspeção volta ao CÓDIGO antes e depois de cada teste: `chamado_modelos_store.aplicar` mexe no pacote
    `chamado_garantia` em memória, e um teste que salva um fornecedor não pode mudar a inspeção do teste seguinte."""
    try:
        import chamado_modelos_store as cms
        import chamados_obs_store as cos
        import gridco_abas as ga
    except Exception:                                    # noqa: BLE001 — ambiente sem o pacote: nada a proteger
        yield
        return

    def _sem_rede(*a, **k):
        raise RuntimeError("teste sem rede: troque gridco_abas._get/escrever no próprio teste")
    monkeypatch.setattr(ga, "_get", _sem_rede)
    monkeypatch.setattr(ga, "escrever", _sem_rede)
    monkeypatch.setattr(cms, "_linhas", lambda: [])
    monkeypatch.setattr(cos, "_linhas", lambda: [])
    for mod in (cms, cos):
        mod.ABA._id = None
    cms._estado.update(banco=None, lido=0.0, proxima=0.0, erro="")
    cos._estado.update(lista=None, lido=0.0)
    cms.aplicar({})
    yield
    cms.aplicar({})
    cms._estado.update(banco=None, lido=0.0, proxima=0.0, erro="")
    cos._estado.update(lista=None, lido=0.0)


@pytest.fixture(autouse=True)
def _temas_sem_banco(monkeypatch):
    """O `temas_store` também vai ao banco, e desde 27/09/2026 a Solicitação do os_web relê os temas antes de cada rota
    (`temas_store.garantir`). Nenhum teste vai: a aba fica VAZIA, o que deixa valendo os temas do código. Quem testa o
    banco troca o `_linhas` no próprio teste — e a busca injetada (`carregar(buscar=...)`) segue funcionando."""
    try:
        import temas_store as ts
    except Exception:                                    # noqa: BLE001 — ambiente sem o módulo: nada a proteger
        yield
        return
    monkeypatch.setattr(ts, "_linhas", lambda buscar=None: buscar() if buscar else [])
    monkeypatch.setattr(ts, "_cache", None)
    ts._estado.update(proxima=0.0, erro="")
    yield
    ts._estado.update(proxima=0.0, erro="")
