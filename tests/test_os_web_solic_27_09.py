# tests/test_os_web_solic_27_09.py
"""A Nova solicitação, pedido do Levi de 27/09/2026:
1. sem os botões que levam à Fila do PCM (a fila e o histórico moram no setor PCM);
2. dá para digitar no tipo de ativo;
3. o tema segue o tipo de ativo — "se for inversor, só vai aparecer tema de inversores, se for trackers só trackers, se
   for ETM só ETM, se for nenhum então vai ficar sem tema mesmo";
4. o título sugerido é "[Ativo] - Motivo", com o nome de CADA ativo ao criar;
5. "Data sugerida ao PCM" vira "Data Programada (Sugestão)".
Os ativos e as descrições aqui são inventados — o repositório é público."""
import os

import pytest

import api
import solic_spec as sp
from os_web import criar_app, solic_web as sw, tradicional_web as trad

_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web")


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    monkeypatch.setattr(api, "get_request_types", lambda *a, **k: {})
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = "jwt-de-teste"
        s["conta"] = {"nome": "Pessoa Teste", "email": "pessoa.teste@exemplo.com", "perfil": "ADMINISTRATOR"}
    return c


# ── 3. o tema segue o tipo de ativo ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tema,tipos", [
    ("inversor_inspecao", ["Inversor"]), ("inversor_substituicao", ["Inversor"]), ("inversor_garantia", ["Inversor"]),
    ("tracker_reset_tcu", ["Estrutura Trackers"]), ("tracker_inject", ["Estrutura Trackers"]),
    ("tracker_motor", ["Estrutura Trackers"]), ("tracker_chamado", ["Estrutura Trackers"]),
    ("nobreak", ["NBRK"]), ("protecao_transformador", ["Transformador", "Cabine", "RELE", "DTRF", "DJMT"]),
    ("vegetacao", ["Usina"]),
])
def test_os_temas_do_codigo_tem_tipo(tema, tipos):
    assert sw.tipos_do_tema(tema) == tipos


def test_todo_tema_do_codigo_aparece_em_algum_tipo():
    """Tema sem tipo some da tela — nenhum dos que existem pode cair nisso sem alguém decidir."""
    assert all(sw.tipos_do_tema(k) for k in sp.TEMAS)


def test_o_tipo_de_equipamento_do_tema_manda(monkeypatch):
    """O PCM escolhe o tipo na tela de Temas: o que ele escolheu vale mais que a tabela."""
    monkeypatch.setitem(sp.TEMAS, "vegetacao", dict(sp.TEMAS["vegetacao"], tipo_equipamento="Infraestrutura Civil"))
    assert sw.tipos_do_tema("vegetacao") == ["Infraestrutura Civil"]


@pytest.mark.parametrize("chave,nome,tipos", [
    ("etm_limpeza", "ETM — limpeza dos sensores", ["Estação Meteorológica"]),
    ("sensor_x", "Estação meteorológica — calibração", ["Estação Meteorológica"]),
    ("novo_tracker", "Tracker — alinhamento", ["Estrutura Trackers"]),
    ("tcu_bateria", "Bateria da TCU", ["Estrutura Trackers"]),
    ("novo_inv", "Inversor — ventilação", ["Inversor"]),
    ("pintura", "Pintura da cerca", []),
])
def test_tema_novo_sem_tipo_vai_pelo_nome(monkeypatch, chave, nome, tipos):
    monkeypatch.setitem(sp.TEMAS, chave, {"nome": nome, "motivo": nome, "classif1": "", "tipo": "", "solicitacoes": 0})
    assert sw.tipos_do_tema(chave) == tipos


def test_a_tela_recebe_os_tipos_e_o_motivo_de_cada_tema():
    t = {x["chave"]: x for x in sw.temas_para_tela()}
    assert t["tracker_motor"]["tipos"] == ["Estrutura Trackers"] and t["tracker_motor"]["motivo"] == sp.motivo("tracker_motor")


# ── 4. o título "[Ativo] - Motivo" ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("asset,esperado", [
    ({"description": "Inversor 1.5 Marca X { TST100-INVR1.5 }", "tipo": "Inversor"}, "[Inversor 1.5] - Motivo"),
    ({"description": "Tracker 40.100 Marca Y Modelo-H250 V05", "tipo": "Estrutura Trackers"}, "[Tracker 40.100] - Motivo"),
    ({"description": "Cliente X - Usina Teste 1 - CE  Cidade  Estado Brasil", "tipo": "Usina",
      "usina": "Cliente X - Usina Teste 1 - CE"}, "[Usina Teste 1] - Motivo"),
    ({"description": "Nobreak 1      { TST100-NBRK1 }", "tipo": "NBRK"}, "[Nobreak 1] - Motivo"),
])
def test_a_marca_vira_o_nome_curto_de_cada_ativo(asset, esperado):
    assert sw.titulo_do_ativo("[Ativo] - Motivo", asset) == esperado


def test_titulo_sem_a_marca_fica_como_a_pessoa_escreveu():
    assert sw.titulo_do_ativo("Troca do cabo", {"description": "Inversor 1.5"}) == "Troca do cabo"


def test_a_cascata_manda_o_nome_curto_para_a_previa():
    """A prévia da tela tem de ser o MESMO nome que o servidor põe ao criar."""
    a = {"id": 1, "code": "TST100-INVR1.5", "label": "TST100-INVR1.5 — Inversor 1.5 Marca X", "tipo": "Inversor",
         "cliente": "C", "usina": "U", "description": "Inversor 1.5 Marca X { TST100-INVR1.5 }"}
    assert trad.ativos_de([a], "C", "U")[0]["curto"] == sw.nome_curto(a) == "Inversor 1.5"


def _escolhidos(monkeypatch, n):
    ativos = [{"code": "TST100-INVR1.%d" % i, "description": "Inversor 1.%d Marca X" % i, "tipo": "Inversor"}
              for i in range(1, n + 1)]
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: ativos)
    monkeypatch.setattr(api, "_read_asset_cache", lambda: ativos)
    chamadas = []
    monkeypatch.setattr(api, "create_solicitacoes_bulk", lambda assets, desc, c1, **k: chamadas.append(
        ([a["code"] for a in assets], desc)) or [{"code": a["code"], "ok": True, "id_code": 1} for a in assets])
    return [a["code"] for a in ativos], chamadas


def test_criar_com_a_marca_da_um_titulo_por_ativo(cli, monkeypatch):
    codes, chamadas = _escolhidos(monkeypatch, 2)
    r = cli.post("/os/api/solic/criar", json={"ativos": codes, "descricao": "[Ativo] - Troca de ventilador", "classif1": 7})
    assert r.status_code == 200
    assert chamadas == [(["TST100-INVR1.1"], "[Inversor 1.1] - Troca de ventilador"),
                        (["TST100-INVR1.2"], "[Inversor 1.2] - Troca de ventilador")]


def test_criar_sem_a_marca_segue_em_lote(cli, monkeypatch):
    codes, chamadas = _escolhidos(monkeypatch, 2)
    cli.post("/os/api/solic/criar", json={"ativos": codes, "descricao": "Troca de ventilador", "classif1": 7})
    assert chamadas == [(codes, "Troca de ventilador")]


# ── 1, 2, 4 e 5 na tela ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_da_nova_solicitacao(cli):
    h = cli.get("/os/solicitacao").get_data(as_text=True)
    assert 'href="/os/solicitacao/fila"' not in h and 'href="/os/solicitacao/historico"' not in h      # 1
    assert '<select id="cb_tipo" data-busca="1" disabled>' in h                                         # 2
    assert 'data-tipos="Estrutura Trackers"' in h and 'data-motivo="' in h                              # 3
    assert 'placeholder="[Ativo] - Motivo"' in h and 'id="hint_titulo"' in h                            # 4
    assert "Data Programada (Sugestão)" in h and "Data sugerida ao PCM" not in h                        # 5
    assert 'href="/os/"' in h                                                                            # a volta ao Início


@pytest.mark.parametrize("arq", ["solic_fila.html", "solic_hist.html"])
def test_a_fila_e_o_historico_sao_do_setor_pcm(arq):
    s = open(os.path.join(_WEB, "templates", arq), encoding="utf-8").read()
    assert 'href="/os/setor/pcm"' in s and 'href="/os/solicitacao"' not in s
    assert 'href="/os/solicitacao/fila"' in s and 'href="/os/solicitacao/historico"' in s
