"""COS: marcar ativos de mais de uma usina do mesmo cliente (Levi, 02/09).

O desligamento raramente respeita a fronteira da usina — uma ocorrência na distribuidora derruba
várias plantas do mesmo cliente de uma vez. Até aqui o COS obrigava a refazer a tela usina por
usina, porque trocar a usina ZERAVA a seleção.

O teste dirige a TELA REAL, não um mapa de regras: o que estava travando era a interface, e o
risco que ela introduz é o de ativo marcado que some da lista mas continua marcado — criando OS
que ninguém revisou. Metade dos casos abaixo é sobre exatamente isso.

O catálogo é sintético para a prova não depender do que o Fracttal tem hoje.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import steps.varias_os as vo


def _ativo(i, usina, cliente, tipo="Inversor"):
    return {"id": i, "code": "C%d" % i, "label": "Inversor %d" % i,
            "usina": usina, "cliente": cliente, "tipo": tipo}


# duas usinas do MESMO cliente + uma de outro — o "de outro" é o que prova que o modo é por cliente
ALTAIR = "Thopen - Altair 1 - SP"
BARRETOS = "Thopen - Barretos 1 - SP"
PHARMA = "Copel - Pharma II - PR"
CATALOGO = [_ativo(1, ALTAIR, "Thopen"), _ativo(2, ALTAIR, "Thopen"),
            _ativo(3, BARRETOS, "Thopen"), _ativo(4, PHARMA, "Copel")]


@pytest.fixture
def cos(qapp, monkeypatch):
    """A tela real, com catálogo sintético e sem rede.

    `ApiWorker` vira no-op porque o construtor dispara threads de verdade (responsável, tipos): num
    teste elas ou batem na API ou morrem junto com o objeto, e o processo aborta sem traceback."""
    monkeypatch.setattr(vo.api, "load_assets_cached", lambda *a, **k: list(CATALOGO))
    monkeypatch.setattr(vo, "ApiWorker", lambda *a, **k: type(
        "W", (), {"ok": type("S", (), {"connect": lambda *_: None})(),
                  "erro": type("S", (), {"connect": lambda *_: None})(),
                  "start": lambda self: None})())
    w = vo.VariasOSsDialog()
    yield w
    w.deleteLater()


def _escolher(w, cliente, usina):
    w.cb_cli.setCurrentIndex(w.cb_cli.findText(cliente))
    w.cb_usi.setCurrentIndex(w.cb_usi.findText(usina))


def _ids(w):
    return {a["id"] for a in w._cands()}


# ── o comportamento antigo não pode ter mudado ────────────────────────────────────────────────
def test_desligado_a_tabela_mostra_so_a_usina_escolhida(cos):
    _escolher(cos, "Thopen", ALTAIR)
    assert _ids(cos) == {1, 2}


def test_desligado_trocar_de_usina_continua_zerando_a_selecao(cos):
    # a regra antiga existe por um motivo: sem o modo ligado, misturar usinas seria acidente.
    _escolher(cos, "Thopen", ALTAIR)
    cos._checked = {1, 2}
    cos.cb_usi.setCurrentIndex(cos.cb_usi.findText(BARRETOS))
    assert cos._checked == set()


# ── o modo novo ───────────────────────────────────────────────────────────────────────────────
def test_ligado_lista_as_usinas_todas_do_cliente(cos):
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    assert _ids(cos) == {1, 2, 3}          # Altair + Barretos


def test_ligado_nao_vaza_ativo_de_outro_cliente(cos):
    # o modo é "várias usinas DO CLIENTE": trazer a Copel junto criaria OS para quem não pediu.
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    assert 4 not in _ids(cos)


def test_ligado_a_selecao_sobrevive_a_troca_de_usina(cos):
    # é o ponto do pedido: marcar em Altair, ir para Barretos e continuar com Altair marcado.
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    cos._checked = {1}
    cos.cb_usi.setCurrentIndex(cos.cb_usi.findText(BARRETOS))
    assert 1 in cos._checked


def test_a_linha_diz_de_que_usina_e_o_ativo(cos):
    # com várias usinas juntas, 'Inversor 1' aparece repetido; sem a usina no rótulo a escolha
    # vira adivinhação.
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    rotulos = [cos.tbl.item(r, 0).text() for r in range(cos.tbl.rowCount())]
    assert any("Barretos" in r for r in rotulos)
    assert any("Altair" in r for r in rotulos)


# ── as travas: marcado tem de ser sempre um subconjunto do que dá para ver ────────────────────
def test_desligar_o_modo_poda_o_que_saiu_da_tela(cos):
    # sem podar, o ativo de Barretos sumiria da lista e continuaria marcado — e viraria uma OS que
    # a pessoa não revisou.
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    cos._checked = {1, 3}
    cos.chk_multi_usi.setChecked(False)
    assert cos._checked == {1}


def test_trocar_de_cliente_poda_a_selecao(cos):
    # com o modo ligado o escopo é o cliente, então trocar de cliente troca a lista inteira. Sem a
    # poda, os ativos da Thopen ficariam marcados e invisíveis, e virariam OS na conta da Copel.
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    cos._checked = {1, 3}
    cos.cb_cli.setCurrentIndex(cos.cb_cli.findText("Copel"))
    assert cos._checked == set()


def test_com_cliente_escolhido_a_usina_de_outro_nem_aparece(cos):
    # é o que torna impossível misturar clientes sem querer: o combo de usina já vem filtrado.
    _escolher(cos, "Thopen", ALTAIR)
    assert cos.cb_usi.findText(PHARMA) < 0
    assert cos.cb_usi.findText(BARRETOS) >= 0


def test_sem_cliente_o_marcador_fica_desligado(cos):
    # o modo é "as usinas DESTE cliente" — sem cliente ele não teria escopo nenhum.
    assert cos.cb_cli.currentIndex() == 0
    assert not cos.chk_multi_usi.isEnabled()


def test_no_modo_mesmo_ativo_o_marcador_se_desliga(cos):
    # ali só um ativo é marcado por vez; espalhar por usinas não significaria nada.
    _escolher(cos, "Thopen", ALTAIR)
    cos.chk_multi_usi.setChecked(True)
    cos._on_modo(1)
    assert not cos.chk_multi_usi.isChecked()
    assert not cos.chk_multi_usi.isEnabled()
