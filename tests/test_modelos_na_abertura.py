# -*- coding: utf-8 -*-
"""O que o PCM salva no banco — os temas da Solicitação e os modelos da inspeção de chamado — chega ao app de mesa NA
ABERTURA.

O defeito (27/09/2026): o `temas_store.aplicar_no_spec` dizia "chamado uma vez na abertura do app" e nada o chamava fora
da tela de Temas. O PCM salvava um tema e as outras máquinas seguiam com os do código na Solicitação e na Fila. O
`chamado_modelos_store`, do mesmo dia, tinha o mesmo buraco: o os_web aplicava, a Inspeção do app de mesa não.

A janela é a REAL. Só a borda de fora é trocada: as linhas cruas das duas abas (`_linhas`, a única função que vai à rede
em cada store) e o `start` do ApiWorker, que deixa toda thread PARADA numa lista — o teste decide qual roda e quando. É
assim que se reproduz o banco respondendo antes de alguém abrir uma tela, e depois.

Dado SINTÉTICO: o oem é público."""
import copy
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip

import api
import chamado_insp_spec as ci
import chamado_modelos_store as cms
import solic_spec as sp
import temas_store as ts
import workers

MOTIVO_NOVO = "Motivo do tema de teste"


def _tema(n, chave, **kw):
    d = {"nome": chave, "motivo": "", "classif1": "", "tipo_os": "", "tipo_equipamento": "",
         "solicitacoes": 0, "arquivado": False, "subtarefas": []}
    d.update(kw)
    return {"row_number": n, "headers": ["chave", "valor"], "values": [chave, json.dumps(d, ensure_ascii=False)]}


def _modelo(n, chave, valor):
    return {"row_number": n, "headers": ["chave", "valor"], "values": [chave, json.dumps(valor, ensure_ascii=False)]}


# o que o PCM teria salvo: a Vegetação com outro nome, um tema que só o banco tem e um fornecedor novo de inversor
TEMAS_DO_BANCO = [
    _tema(2, "vegetacao", nome="Vegetação — nome do banco", motivo="Roçagem", solicitacoes=83,
          subtarefas=[{"desc": "Pergunta da vegetação no banco", "tipo": "texto", "anexo": False}]),
    _tema(3, "tema_teste_abertura", nome="Tema de teste da abertura", motivo=MOTIVO_NOVO, solicitacoes=5,
          subtarefas=[{"desc": "Pergunta do tema de teste", "tipo": "texto", "anexo": True}]),
]
MODELOS_DO_BANCO = [
    _modelo(2, "MARCA:Fornecedor Teste", {
        "subtarefas": [{"desc": "Pergunta do fornecedor de teste", "tipo": "texto", "obrig": True, "anexo": False,
                        "opcoes": [], "chave": "", "so_para": []}],
        "canal": "e-mail de teste", "atende": ["Inversor"], "arquivado": False,
        "versao": "2026-09-27T10:00:00-03:00", "por": "Teste"}),
]


@pytest.fixture(autouse=True)
def _temas_do_codigo():
    """`aplicar_no_spec` troca `sp.TEMAS` e `sp.POR_TEMA` NO LUGAR. Sem devolver o código, o tema de mentira de um teste
    apareceria na Solicitação do seguinte (os modelos de chamado, o conftest já devolve)."""
    t, p = copy.deepcopy(sp.TEMAS), copy.deepcopy(sp.POR_TEMA)
    yield
    sp.TEMAS.clear()
    sp.TEMAS.update(t)
    sp.POR_TEMA.clear()
    sp.POR_TEMA.update(p)


@pytest.fixture
def banco(monkeypatch):
    """As duas abas. Começam como o PCM teria deixado; o teste troca por uma exceção (banco fora) ou por [] (aba vazia)."""
    estado = {"temas": list(TEMAS_DO_BANCO), "chamado": list(MODELOS_DO_BANCO)}

    def _ler(qual):
        v = estado[qual]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(ts, "_linhas", lambda buscar=None: _ler("temas"))
    monkeypatch.setattr(ts, "_cache", None)
    monkeypatch.setattr(cms, "_linhas", lambda: _ler("chamado"))
    return estado


@pytest.fixture
def parados(monkeypatch, tmp_path):
    """Todo ApiWorker iniciado fica aqui, sem thread e sem rede. E o log de erro vai para um arquivo do teste: a queda de
    banco de mentira não pode sujar o %TEMP%\\criaros_erros.log que a equipe lê."""
    lista = []
    monkeypatch.setattr(workers.ApiWorker, "start", lambda self, *a: lista.append(self))
    monkeypatch.setattr(workers, "_LOG", str(tmp_path / "criaros_erros.log"))
    return lista


@pytest.fixture
def janela(qapp, monkeypatch, parados, banco):
    monkeypatch.setattr(api, "current_user", lambda: "")
    import app
    win = app.MainWindow()
    yield win
    workers.auth_bus.sessao_expirou.disconnect(win._sessao_expirou)   # janela de teste não abre login de ninguém
    # DESTRUIR AGORA, e não `deleteLater()`: sem laço de eventos o adiamento nunca roda, e o `deleteLater` ainda passa
    # a posse ao C++. As janelas ficavam vivas até a saída do processo e morriam DEPOIS do QApplication — em 4 de 7
    # rodadas da suíte o python caía ali, com todos os testes verdes (código 139).
    sip.delete(win)


def _banco_responde(parados):
    """A resposta do banco chega AGORA: roda, na thread do teste, o worker que a abertura deixou lendo o banco."""
    ws = [w for w in parados if getattr(w._fn, "__module__", "") == "modelos_banco"]
    assert ws, "a abertura do app não pediu a leitura do banco"
    for w in ws:
        parados.remove(w)
        w.run()


def _chaves(cb):
    return [cb.itemData(i) for i in range(cb.count())]


def _solicitacao(tema):
    return {"id_code": 9001, "usina": "Usina Teste", "ativo": "INV-01", "criado_por": "Supervisor Teste",
            "data": "2026-09-27 08:00:00", "status": "Pendente", "cor_status": "#01C0DD",
            "descricao_full": "texto do supervisor", "observacao": "relato\n\n" + sp.bloco({"tema": tema})}


# ── na abertura, com o banco no ar ────────────────────────────────────────────────────────────────────────────────
def test_na_abertura_a_solicitacao_e_a_fila_oferecem_os_temas_do_banco(janela, parados):
    _banco_responde(parados)
    for cb in (janela.sol.cb_tema, janela.solpcm.fila.cb_tema):
        assert _chaves(cb) == ["", "vegetacao", "tema_teste_abertura"]        # do maior volume para o menor
        assert cb.itemText(1) == "Vegetação — nome do banco"


def test_na_abertura_a_inspecao_passa_a_usar_o_fornecedor_do_banco(janela, parados):
    _banco_responde(parados)
    assert "Fornecedor Teste" in ci.marcas_para("Inversor")
    assert ci.subtarefas("Inversor", "Fornecedor Teste")[-1]["description"] == "Pergunta do fornecedor de teste"


# ── o banco fora do ar (ou a aba vazia) não muda nada ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("resposta", [ConnectionError("banco fora de teste"), []], ids=["fora", "vazio"])
def test_sem_banco_o_codigo_fica_exatamente_como_estava(janela, parados, banco, resposta):
    """Sem reaplicar a semente: `da_semente()` não guarda o `obrig`, e reaplicá-la tornaria obrigatória a subtarefa
    opcional da Vegetação — o código mudando por causa de uma queda de rede."""
    banco["temas"] = banco["chamado"] = resposta
    temas, passos = copy.deepcopy(sp.TEMAS), copy.deepcopy(sp.POR_TEMA)
    inspecao = ci.subtarefas("Inversor", "Huawei")
    _banco_responde(parados)
    assert sp.TEMAS == temas and sp.POR_TEMA == passos
    assert ci.subtarefas("Inversor", "Huawei") == inspecao
    assert _chaves(janela.sol.cb_tema) == [""] + [k for k, _ in sp.temas()]


def test_queda_do_banco_na_abertura_fica_no_log(janela, parados, banco, tmp_path):
    """"O PCM salvou e na minha máquina não mudou" começa pelo %TEMP%\\criaros_erros.log: sem a linha, a queda de rede na
    abertura seria invisível."""
    banco["temas"] = ConnectionError("banco fora de teste")
    _banco_responde(parados)
    assert "banco fora de teste" in (tmp_path / "criaros_erros.log").read_text(encoding="utf-8")


def test_temas_fora_do_ar_nao_seguram_os_modelos_de_chamado(janela, parados, banco):
    banco["temas"] = ConnectionError("banco fora de teste")
    _banco_responde(parados)
    assert "Fornecedor Teste" in ci.marcas_para("Inversor")


def test_modelos_de_chamado_fora_do_ar_nao_seguram_os_temas(janela, parados, banco):
    banco["chamado"] = ConnectionError("banco fora de teste")
    _banco_responde(parados)
    assert "tema_teste_abertura" in _chaves(janela.sol.cb_tema)


# ── a tela já estava aberta quando o banco respondeu ──────────────────────────────────────────────────────────────
def test_solicitacao_em_preenchimento_nao_perde_o_tema_nem_as_subtarefas(janela, parados):
    """Remontar o combo não pode desfazer o que o supervisor já fez: o `clear()` solto dispararia `_on_tema` e trocaria
    as subtarefas editadas pelas do tema."""
    sol = janela.sol
    sol.cb_tema.setCurrentIndex(sol.cb_tema.findData("vegetacao"))
    sol.editor_subs.adicionar()
    sol.editor_subs._linhas[-1].ed.setText("Subtarefa escrita pelo supervisor")
    _banco_responde(parados)
    assert sol.cb_tema.currentData() == "vegetacao"
    assert sol.editor_subs.itens()[-1]["desc"] == "Subtarefa escrita pelo supervisor"


def test_solicitacao_em_preenchimento_mostra_o_nome_novo_do_tema(janela, parados):
    """O rótulo do campo escuta o `currentIndexChanged`, que a remontagem silencia: sem avisá-lo, a tela mostraria o nome
    velho com o combo já no novo."""
    sol = janela.sol
    sol.cb_tema.setCurrentIndex(sol.cb_tema.findData("vegetacao"))
    _banco_responde(parados)
    assert sol.v_tema.lbl.text() == "Vegetação — nome do banco"


def test_tema_escolhido_e_arquivado_no_banco_vira_sem_tema_na_tela_inteira(janela, parados, banco):
    banco["temas"] = [TEMAS_DO_BANCO[1], _tema(2, "vegetacao", nome="Vegetação", solicitacoes=83, arquivado=True)]
    sol = janela.sol
    sol.cb_tema.setCurrentIndex(sol.cb_tema.findData("vegetacao"))
    _banco_responde(parados)
    assert sol.cb_tema.currentData() == ""
    assert "Sem tema" in sol.lbl_subs.text()        # e não o roteiro de um tema que ninguém pode mais escolher


def test_fila_aberta_antes_da_resposta_mostra_o_tema_que_so_o_banco_tem(janela, parados):
    """A solicitação nasceu NOUTRA máquina com um tema que o combo do código não tem: o `_selecionar` caiu em "sem tema"
    por falta de opção. Quando o banco responde, a Fila mostra o tema e o título no padrão dele."""
    tab = janela.solpcm
    tab.ir(tab.FILA)
    tab.fila.set_itens([_solicitacao("tema_teste_abertura")], [])
    assert (tab.fila.cb_tema.currentData() or "") == ""
    _banco_responde(parados)
    assert tab.fila.cb_tema.currentData() == "tema_teste_abertura"
    assert tab.fila.lbl_titulo.text() == "[Usina Teste][INV-01] - " + MOTIVO_NOVO


def test_sem_tema_escolhido_pelo_pcm_na_fila_nao_e_desfeito(janela, parados):
    """O tema da solicitação JÁ estava na lista e o PCM tirou: o "sem tema" é escolha dele, e a resposta do banco não o
    põe de volta."""
    tab = janela.solpcm
    tab.ir(tab.FILA)
    tab.fila.set_itens([_solicitacao("vegetacao")], [])
    tab.fila.cb_tema.setCurrentIndex(0)
    _banco_responde(parados)
    assert (tab.fila.cb_tema.currentData() or "") == ""


def _inspecao_com_o_ativo(janela):
    janela._mostrar_modo("insp")
    insp = janela._modo_inner["insp"]
    insp._set_assets([{"id": 71, "code": "T-INV-11", "description": "Inversor 1.1 Fornecedor Teste X1",
                       "cliente": "Cliente Teste", "usina": "Usina Teste", "tipo": "Inversor"}])
    for cb, txt in ((insp.cb_cli, "Cliente Teste"), (insp.cb_usi, "Usina Teste"), (insp.cb_tipo, "Inversor")):
        cb.setCurrentIndex(cb.findText(txt))
    insp.cb_ativo.setCurrentIndex(1)
    return insp


def test_inspecao_aberta_antes_da_resposta_passa_a_oferecer_o_fornecedor(janela, parados):
    insp = _inspecao_com_o_ativo(janela)
    assert insp.cb_marca.findText("Fornecedor Teste") < 0
    _banco_responde(parados)
    assert insp.cb_marca.currentText() == "Fornecedor Teste"          # já sugerido: a descrição do ativo diz a marca
    assert "Pergunta do fornecedor de teste" in insp.lb_subs.text()


def test_marca_escolhida_na_inspecao_antes_da_resposta_continua_escolhida(janela, parados):
    insp = _inspecao_com_o_ativo(janela)
    insp.cb_marca.setCurrentIndex(insp.cb_marca.findText("Huawei"))
    _banco_responde(parados)
    assert insp.cb_marca.currentText() == "Huawei"


# ── salvo na tela de Temas desta máquina ──────────────────────────────────────────────────────────────────────────
def test_tema_salvo_na_tela_de_temas_aparece_ao_voltar_ao_formulario_e_a_fila(qapp, monkeypatch, parados, banco):
    """O `_salvou` da tela de Temas aplica em memória, mas os dois combos tinham nascido antes — tema novo só aparecia
    depois de fechar e abrir o app, mesmo na máquina de quem salvou."""
    from steps.solic_pcm import SolicPcmTab
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    tab = SolicPcmTab()
    try:
        tab.temas._salvou({})
        tab.ir(tab.NOVA)
        assert "tema_teste_abertura" in _chaves(tab.nova.cb_tema)
        tab.ir(tab.FILA)
        assert "tema_teste_abertura" in _chaves(tab.fila.cb_tema)
    finally:
        sip.delete(tab)                          # pelo mesmo motivo da `janela`: não deixar para a saída do processo
