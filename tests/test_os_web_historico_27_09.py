# tests/test_os_web_historico_27_09.py
"""Histórico, lote de 27/09/2026 (Levi): "Buscar OS" curto (2), rótulos fora dos cards e grade alinhada (3), a busca por
texto colada na tabela (4), as visões sem repetir a busca (7) e o topo recolhível (8).

O 7 não vira "filtro da mesma lista" porque as visões são três buscas diferentes no Fracttal (criadas por mim,
atribuídas a mim, a equipe inteira) e a da equipe passa do teto de 2.000 em 30 dias — filtrar as outras a partir dela
perderia OS. O que se trava aqui: voltar a uma visão não vai ao Fracttal; o ↻ vai; o teto cortando é DITO; e a tela não
busca de novo, em 34 lotes, o que o servidor já mandou."""
import re

import pytest

import api
from os_web import criar_app
from os_web import rotas

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
LINHA = {"id": 501, "folio": 9812, "cliente": "Acme", "usina": "Alfa 2", "ativo": "Inversor 1", "tipo": "Inversor",
         "tipo_tarefa": "Religamento", "descricao": "INV 1 desligado", "criado_por": "Levi Maia", "etiquetas": [],
         "data": "2026-09-11T12:00:00", "event_date": "2026-09-11T11:00:00", "data_fim": "", "status_id": 1,
         "status": "Em Processo", "inicio": "2026-09-11T13:15:00", "gatilho": "Não agendada", "programada": "",
         "equipe": ""}


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    monkeypatch.setattr(api, "get_labels", lambda: [])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda: {"pessoas": [], "eu": 77})
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    rotas._MEMO.clear()
    # o nome curto do Ativo lê o catálogo do DISCO (21 mil ativos) para as frases de cada tipo: aqui, nenhum
    monkeypatch.setattr(api, "_read_asset_cache", lambda: [])


def _cli(email="eu@teste.invalid"):
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": email, "perfil": "ADMINISTRATOR"}
    return c


# ── 7. as visões sem repetir a busca ────────────────────────────────────────────────────────────
def test_voltar_a_uma_visao_nao_vai_ao_fracttal_e_o_atualizar_vai(monkeypatch):
    chamadas = []
    monkeypatch.setattr(api, "list_minhas_os", lambda modo="criadas", **k: chamadas.append(modo) or [dict(LINHA)])
    c = _cli()
    c.get("/os/historico?de=2026-09-01&ate=2026-09-12")
    c.get("/os/historico?modo=cos&de=2026-09-01&ate=2026-09-12")
    c.get("/os/historico?de=2026-09-01&ate=2026-09-12")                     # volta à 1ª: da memória
    assert chamadas == ["criadas", "criadas"]                                # geral e COS (a COS busca 'criadas' TODOS)
    c.get("/os/historico?de=2026-09-01&ate=2026-09-12&atualizar=1")          # o ↻
    assert len(chamadas) == 3


def test_a_memoria_e_por_pessoa(monkeypatch):
    """ "Criadas por MIM" depende de quem é o mim: a lista de um não pode servir o outro."""
    chamadas = []
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: chamadas.append(1) or [])
    _cli("eu@teste.invalid").get("/os/historico?de=2026-09-01&ate=2026-09-12")
    _cli("outra@teste.invalid").get("/os/historico?de=2026-09-01&ate=2026-09-12")
    assert len(chamadas) == 2


def test_erro_do_fracttal_nao_fica_guardado(monkeypatch):
    estado = {"n": 0}

    def lista(**k):
        estado["n"] += 1
        if estado["n"] == 1:
            raise api.FracttalError("fora do ar")
        return [dict(LINHA)]
    monkeypatch.setattr(api, "list_minhas_os", lista)
    c = _cli()
    assert "fora do ar" in c.get("/os/historico").get_data(as_text=True)
    assert "9812" in c.get("/os/historico").get_data(as_text=True)          # a 2ª tenta de novo


def test_o_teto_cortando_as_mais_antigas_e_dito(monkeypatch):
    def lista(info=None, **k):
        info.update(total=2314, cap=2000)
        return [dict(LINHA, id=i, folio=i) for i in range(2000)]
    monkeypatch.setattr(api, "list_minhas_os", lista)
    h = _cli().get("/os/historico?modo=cos").get_data(as_text=True)
    assert "O período tem 2314 OS e a tela carrega até 2000: as 314 mais antigas ficaram de fora." in h


def test_o_aviso_conta_o_que_chegou_e_nao_o_que_sobrou_da_busca(monkeypatch):
    """A conta é total − carregadas (antes da busca local): a busca por texto não pode inflar o número de cortadas, e o
    teto dito é o do servidor — a 1ª versão dizia "carrega até 46" quando a busca deixava 46 linhas na tela."""
    def lista(info=None, **k):
        info.update(total=2314, cap=2000)
        return [dict(LINHA, id=i, folio=i, usina="Alfa 2" if i < 46 else "Beta") for i in range(1999)]
    monkeypatch.setattr(api, "list_minhas_os", lista)
    h = _cli().get("/os/historico?modo=cos&busca=alfa").get_data(as_text=True)
    assert "O período tem 2314 OS e a tela carrega até 2000: as 315 mais antigas ficaram de fora." in h


def test_sem_corte_nao_ha_aviso(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda info=None, **k: info.update(total=1, cap=2000) or [dict(LINHA)])
    assert "ficaram de fora" not in _cli().get("/os/historico").get_data(as_text=True)
    # linha a menos do que o total, mas dentro do teto (uma OS sem forma), não é corte do teto
    monkeypatch.setattr(api, "list_minhas_os", lambda info=None, **k: info.update(total=3, cap=2000) or [dict(LINHA)])
    rotas._MEMO.clear()
    assert "ficaram de fora" not in _cli().get("/os/historico").get_data(as_text=True)


def test_a_linha_chega_completa_e_a_tela_nao_busca_o_meta_de_novo(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [dict(LINHA)])
    h = _cli().get("/os/historico?modo=cos").get_data(as_text=True)
    assert "11/09/2026 10:15" in h and "Não agendada" in h                   # início (Brasília) e gatilho na COS
    assert "/os/historico/meta" not in h                                     # os 34 lotes sequenciais saíram
    assert re.search(r'<input type="checkbox" value="Religamento"', h)       # o tipo de tarefa já vem na lista


def test_list_minhas_os_guarda_inicio_gatilho_e_o_total(monkeypatch):
    monkeypatch.setattr(api, "_current_user_ids", lambda: (10, 77))
    monkeypatch.setattr(api, "_rpc_call", lambda *a, **k: {"total": 1, "data": [{"id": 5}]})
    monkeypatch.setattr(api, "_shape_wo_row", lambda w: {"id": w["id"], "data": "2026-09-11T12:00:00"})
    monkeypatch.setattr(api, "_meta_tarefa_por_os", lambda ids: {5: {"tipo_tarefa": "Religamento", "inicio": "X",
                                                                     "gatilho": "Não agendada"}})
    info = {}
    out = api.list_minhas_os(info=info)
    assert out[0]["inicio"] == "X" and out[0]["gatilho"] == "Não agendada" and out[0]["tipo_tarefa"] == "Religamento"
    assert info == {"total": 1, "cap": api.HISTORICO_CAP}


# ── 2, 3, 4: a barra, a grade e a busca colada na tabela ────────────────────────────────────────
def test_buscar_os_curto(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [])
    h = _cli().get("/os/historico").get_data(as_text=True)
    assert 'placeholder="Buscar OS"' in h and "direto, ignora filtros\" inputmode" not in h


def test_rotulos_fora_de_todos_os_filtros_e_grade_de_4(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [dict(LINHA)])
    h = _cli().get("/os/historico").get_data(as_text=True)
    grade = h[h.index('<div class="hf-grade">'):h.index("</form>")]
    rotulos = re.findall(r'<span class="hf-lbl">([^<]+)</span>', grade)
    assert rotulos == ["Criado por", "Etiqueta", "Status", "Período", "Cliente", "Usina", "Tipo de ativo", "Tipo de tarefa"]
    assert '<summary><span class="os-lbl">' not in grade                    # nenhum rótulo DENTRO do card


def test_atribuidas_mantem_a_grade_sem_buraco(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [])
    h = _cli().get("/os/historico?modo=atribuidas").get_data(as_text=True)
    assert "Não se aplica nesta visão" in h and 'name="pessoa"' not in h


def test_a_busca_por_texto_fica_colada_na_tabela(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [dict(LINHA)])
    h = _cli().get("/os/historico").get_data(as_text=True)
    barra = h.index('<div class="hf-barra">')
    assert barra < h.index('id="busca_no"') < h.index('<table class="os-tbl os-hist"')
    assert 'form="f_hist"' in h[barra:h.index('<table class="os-tbl os-hist"')]     # continua valendo no formulário
    css = open(rotas._AQUI + r"\static\os.css", encoding="utf-8").read()
    assert ".hf-barra{display:flex;align-items:center;gap:12px;margin-bottom:4px}" in css


# ── 8. o topo recolhível ────────────────────────────────────────────────────────────────────────
def test_o_topo_recolhe_e_a_escolha_fica_guardada(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [])
    h = _cli().get("/os/historico").get_data(as_text=True)
    assert 'id="b_topo"' in h and 'localStorage.getItem("osTopoRecolhido")' in h
    # aplicado ANTES do cabeçalho, para a página não piscar com o topo aberto
    assert h.index('localStorage.getItem("osTopoRecolhido")') < h.index('<header class="os-header">')
    css = open(rotas._AQUI + r"\static\os.css", encoding="utf-8").read()
    assert "body.os-sem-topo .os-header,body.os-sem-topo .os-sep{display:none}" in css


# ── lote da tarde de 27/09: círculo de carga, filtros do servidor que valem na hora, card com ações, Ativo curto ──
def test_a_busca_conta_o_progresso_do_token(monkeypatch):
    """O navegador manda p=<token> e pergunta em /historico/progresso quanto já veio — quem conta é a própria busca."""
    def lista(progresso=None, **k):
        progresso(3, 12)
        return [dict(LINHA)]
    monkeypatch.setattr(api, "list_minhas_os", lista)
    c = _cli()
    c.get("/os/historico?p=tokenteste01")
    assert c.get("/os/historico/progresso?p=tokenteste01").get_json() == {"feito": 3, "total": 12, "conhecido": True}
    assert c.get("/os/historico/progresso?p=outro-token").get_json()["conhecido"] is False
    assert c.get("/os/historico/progresso?p=<script>").get_json()["conhecido"] is False        # token estranho não entra


def test_list_minhas_os_avisa_cada_pedido_ao_fracttal(monkeypatch):
    monkeypatch.setattr(api, "_current_user_ids", lambda: (10, 77))
    monkeypatch.setattr(api, "_rpc_call", lambda metodo, params: {"total": 450, "data": [{"id": params.get("start", 0) + 1}]}
                        if metodo == api.RPC_WO_LIST else {"data": []})
    monkeypatch.setattr(api, "_shape_wo_row", lambda w: {"id": w["id"], "data": "2026-09-11T12:00:00"})
    vistos = []
    api.list_minhas_os(progresso=lambda f, t: vistos.append((f, t)))
    # 3 páginas (200 + 200 + 50) + 4 lotes de meta estimados (450 / 130) = 7; o último aviso fecha em 100%
    assert vistos[0] == (1, 7) and vistos[-1] == (7, 7) and all(t == 7 for _, t in vistos)


def test_criado_por_etiqueta_e_periodo_buscam_na_hora(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [dict(LINHA)])
    h = _cli().get("/os/historico").get_data(as_text=True)
    assert '["pessoa", "etiqueta"].forEach' in h and 'input[name=de], input[name=ate]' in h
    assert "window.OsCarga.mostrar(t)" in h and '<script src="/os/static/carga.js" defer></script>' in h
    assert 'href="/os/historico" data-carga' in h                        # a aba também mostra o círculo


def test_o_card_do_historico_tem_as_acoes(monkeypatch):
    """Concluir, Cancelar e as outras ações moram no os_acoes.js — a página do Histórico nunca o incluía."""
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [dict(LINHA)])
    h = _cli().get("/os/historico").get_data(as_text=True)
    assert '<script src="/os/static/os_acoes.js"></script>' in h and 'addEventListener("os:alterada"' in h
    js = open(rotas._AQUI + r"\static\os_acoes.js", encoding="utf-8").read()
    assert js.count("alterou(d);") == 6                                  # as seis ações que mudam a OS avisam a lista


def test_a_coluna_ativo_mostra_o_nome_curto(monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: [dict(LINHA, ativo="Inversor 1.10 Sungrow SG125HV")])
    h = _cli().get("/os/historico").get_data(as_text=True)
    assert ('<td class="k-ativo" data-k="ativo" title="Inversor 1.10 Sungrow SG125HV" '
            'data-csv="Inversor 1.10 Sungrow SG125HV">Inversor 1.10</td>') in h
    css = open(rotas._AQUI + r"\static\os.css", encoding="utf-8").read()
    assert ".os-hist th.k-ativo,.os-hist td.k-ativo{text-align:center" in css
