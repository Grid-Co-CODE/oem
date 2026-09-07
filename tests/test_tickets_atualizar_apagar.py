# -*- coding: utf-8 -*-
"""Os quatro pedidos do Levi de 07/09 na tela de Tickets.

O que cada bloco tranca:

- **Atualizar** devolve o que a pessoa estava olhando. Um botão que recarrega jogando fora filtro
  e linha aberta é pior que não ter botão: obriga a remontar a visão a cada clique.
- **Renomear usina** lê a aba UMA vez. Era uma releitura por linha, a 0,40s cada — 58 segundos só
  conferindo as 147 ocorrências de "Irecê 2", e a tela parada dizendo "corrigindo…". Foi isso que
  ele viu como "não está mudando o nome novo da usina".
- **Apagar** exige as DUAS confirmações. Recusar qualquer uma delas não pode chegar na API: isto
  não tem desfazer em lugar nenhum.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import steps.tickets as tk
import tickets_escrita
from PyQt6.QtWidgets import QMessageBox

_SIM = QMessageBox.StandardButton.Yes
_NAO = QMessageBox.StandardButton.No


def _oc(row, usina="Irece 2", **extra):
    d = {"_row": row, "Usina": usina, "Causa raiz": "Problema TCU", "Status do ticket": "",
         "Nº do SKID": "1", "Nº do tracker / Identificação": str(row), "OS": "",
         "Início da ocorrência": "2025-05-24 00:00:00", "Fim da ocorrência": "",
         "_estado": "aberta", "_dias": 100, "_ativo_ok": True, "_usina_ok": False}
    d.update(extra)
    return d


# ── renomear a usina: UMA leitura da aba, e não uma por linha ──────────────────────────────
@pytest.fixture
def espiao(monkeypatch):
    """Conta as viagens à API sem fazer nenhuma."""
    reg = {"listas": 0, "puts": [], "leituras": 0}

    def listar(sheet_id, buscar=None):
        reg["listas"] += 1
        return [{"_row": i, "Usina": "Irece 2"} for i in range(1, 200)]

    def gravar(sheet_id, row_number, dados, headers, base=None, enviar=None, ler=None):
        if base is not None:
            reg["leituras"] += 1
            (ler or (lambda *_: {}))(sheet_id, row_number)
        reg["puts"].append((row_number, dados.get("Usina")))
        return {}

    monkeypatch.setattr(tk.tickets_api, "listar_linhas", listar)
    monkeypatch.setattr(tk.tickets_api, "cabecalho_de", lambda sid: ["Usina", "Causa raiz"])
    monkeypatch.setattr(tk.tickets_escrita, "gravar_linha", gravar)
    return reg


def test_renomear_le_a_aba_uma_vez_so(espiao):
    """A conta que motivou a mudança: 147 linhas custavam 147 releituras."""
    ocs = [_oc(i) for i in range(1, 148)]
    tk._renomear_usina("Trackers", ocs, "IRC200")
    assert espiao["listas"] == 1, "leu a aba %d vezes" % espiao["listas"]
    assert len(espiao["puts"]) == 147


def test_renomear_grava_o_codigo_em_todas(espiao):
    ocs = [_oc(i) for i in range(1, 6)]
    corrigidas, falhas = tk._renomear_usina("Trackers", ocs, "IRC200")
    assert falhas == []
    assert len(corrigidas) == 5
    assert {c for _, c in espiao["puts"]} == {"IRC200"}


def test_renomear_continua_conferindo_conflito(espiao):
    """A leitura única não pode ter enfraquecido a conferência — ela só mudou de fonte."""
    ocs = [_oc(1)]
    tk._renomear_usina("Trackers", ocs, "IRC200")
    assert espiao["leituras"] == 1, "gravou sem conferir se alguém mexeu na linha"


def test_renomear_avisa_o_avanco(espiao):
    passos = []
    tk._renomear_usina("Trackers", [_oc(i) for i in range(1, 5)], "IRC200",
                       progresso=lambda i, n: passos.append((i, n)))
    assert passos == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_uma_linha_que_falha_nao_derruba_as_outras(monkeypatch, espiao):
    def gravar(sheet_id, row_number, dados, headers, base=None, enviar=None, ler=None):
        if row_number == 2:
            raise RuntimeError("boom")
        espiao["puts"].append((row_number, dados.get("Usina")))
        return {}
    monkeypatch.setattr(tk.tickets_escrita, "gravar_linha", gravar)
    corrigidas, falhas = tk._renomear_usina("Trackers", [_oc(i) for i in (1, 2, 3)], "IRC200")
    assert len(corrigidas) == 2 and len(falhas) == 1
    assert falhas[0][0]["_row"] == 2


# ── apagar: as DUAS confirmações ───────────────────────────────────────────────────────────
class _TelaFalsa:
    """O bastante de `TicketsTab` para o caminho do apagar. Instanciar a tela inteira puxaria a
    rede (ocorrências e catálogo do Fracttal) por um teste que é sobre decisão, não sobre pintura.
    """
    _apagar_ocorrencia = tk.TicketsTab._apagar_ocorrencia.__wrapped__

    def __init__(self, oc):
        self._sel = oc
        self._aba = "Trackers"
        self.enviados = []
        self.avisos = []

    def _aviso_edicao(self, txt, cor):
        self.avisos.append(txt)

    def _apagou(self, *_):
        pass

    def _apagar_falhou(self, *_):
        pass


@pytest.fixture
def tela(monkeypatch):
    t = _TelaFalsa(_oc(42))

    class _Worker:
        def __init__(self, fn, *a):
            t.enviados.append((fn, a))
            self.ok = self.erro = type("S", (), {"connect": lambda *_: None})()

        def start(self):
            pass

    monkeypatch.setattr(tk, "ApiWorker", _Worker)
    t._b_apagar = t._b_salvar = type("B", (), {"setEnabled": lambda *_: None})()
    return t


def _respostas(monkeypatch, question, warning):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: question))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warning))


def test_apagar_pede_as_duas_e_so_entao_manda(tela, monkeypatch):
    _respostas(monkeypatch, _SIM, _SIM)
    tela._apagar_ocorrencia()
    assert len(tela.enviados) == 1
    fn, args = tela.enviados[0]
    assert fn is tickets_escrita.apagar_linha
    assert args[1] == 42, "mandou apagar a linha errada"


def test_recusar_a_primeira_nao_apaga(tela, monkeypatch):
    _respostas(monkeypatch, _NAO, _SIM)
    tela._apagar_ocorrencia()
    assert tela.enviados == []


def test_recusar_a_SEGUNDA_nao_apaga(tela, monkeypatch):
    """A que importa. Uma segunda pergunta que não é olhada só atrasa o mesmo engano."""
    _respostas(monkeypatch, _SIM, _NAO)
    tela._apagar_ocorrencia()
    assert tela.enviados == []


def test_sem_ocorrencia_aberta_nao_pergunta_nada(tela, monkeypatch):
    perguntou = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: perguntou.append(1) or _SIM))
    tela._sel = None
    tela._apagar_ocorrencia()
    assert perguntou == [] and tela.enviados == []


# ── Atualizar: devolve o que a pessoa estava olhando ───────────────────────────────────────
@pytest.fixture
def aba(qapp, monkeypatch):
    """A tela de verdade, sem rede: `_carregar` some e a busca responde na hora.

    Aqui precisa ser a tela inteira — o que se está trancando é justamente a conversa entre
    `_atualizar`, `_ocs_chegaram` e `_repintar`, e um dublê testaria o dublê."""
    monkeypatch.setattr(tk.TicketsTab, "_carregar", lambda self: None)
    t = tk.TicketsTab()
    t._ativos_prontos = True
    t._todos_ativos = []
    banco = [_oc(i, usina="TIM100" if i % 2 else "Irece 2") for i in range(1, 9)]

    def busca(self=t):
        self._ocs_chegaram((list(banco), []), self._aba)

    monkeypatch.setattr(t, "_buscar_ocorrencias", busca)
    busca()
    yield t, banco
    t.deleteLater()


def test_atualizar_mantem_o_filtro_de_usina_e_de_estado(aba):
    t, _ = aba
    t._usina_filtro = "TIM100"
    t._estados_filtro = {"aberta"}
    t._atualizar()
    assert t._usina_filtro == "TIM100", "o filtro de usina se perdeu no Atualizar"
    assert t._estados_filtro == {"aberta"}


def test_abrir_a_tela_continua_zerando_os_filtros(aba):
    """A preservação é do Atualizar, não de toda carga: trocar de aba tem de vir limpo."""
    t, _ = aba
    t._usina_filtro = "TIM100"
    t._buscar_ocorrencias()          # sem passar pelo _atualizar
    assert t._usina_filtro == ""


def test_atualizar_reabre_a_mesma_ocorrencia(aba):
    t, banco = aba
    alvo = t._visiveis[2]
    t._sel_tabela(2, -1)
    assert t._sel is not None
    t._atualizar()
    assert t._sel is not None, "o painel fechou sozinho no Atualizar"
    assert t._sel.get("_row") == alvo.get("_row")


def test_atualizar_nao_reabre_a_linha_errada_quando_ela_some(aba, monkeypatch):
    """Reabrir por posição traria a ocorrência do vizinho — a mesma classe de erro do diário."""
    t, banco = aba
    t._sel_tabela(0, -1)
    sumida = t._sel.get("_row")
    restante = [o for o in banco if o.get("_row") != sumida]
    monkeypatch.setattr(t, "_buscar_ocorrencias",
                        lambda: t._ocs_chegaram((restante, []), t._aba))
    t._atualizar()
    assert t._sel is None, "reabriu alguma linha no lugar da que foi apagada"


def test_atualizar_solta_o_botao_mesmo_quando_a_busca_falha(aba):
    t, _ = aba
    t._atualizar()
    t._falhou("sem rede")
    assert t._b_atualizar.isEnabled(), "uma falha de rede trancaria o botão para sempre"


def test_atualizar_ignora_o_clique_repetido_durante_a_busca(aba, monkeypatch):
    t, _ = aba
    vezes = []
    monkeypatch.setattr(t, "_buscar_ocorrencias", lambda: vezes.append(1))
    t._w = object()                 # como se uma busca estivesse em curso
    t._atualizar()
    assert vezes == []


# ── a escrita em si ────────────────────────────────────────────────────────────────────────
def test_apagar_respeita_a_trava_de_aba_liberada():
    """A mesma trava do gravar. Sem ela, um sheet_id errado apagaria linha de outra planilha."""
    with pytest.raises(tickets_escrita.EscritaBloqueada):
        tickets_escrita.apagar_linha(999999, 1, enviar=lambda *a: {})


def test_apagar_usa_DELETE_na_linha_pedida():
    vistos = []
    tickets_escrita.apagar_linha(123, 77, enviar=lambda *a: vistos.append(a) or {})
    assert vistos == [("DELETE", 123, 77, None)]
