# tests/test_os_web_acomp.py
"""Acompanhamento de chamados (27/09/2026): o quadro das OS de acompanhamento (a OS 3 do chamado de garantia) e a tela
de cada uma — ticket na subtarefa, observação no banco, finalizar pelo Concluir do card.

A nota abaixo é SINTÉTICA, no formato que o servidor do App monta (ver app-campo-docs/notas-e-os-administrativa.html):
o repositório é público e não leva dado real."""
import datetime as dt
import os

import pytest

import api
import chamados_obs_store as cos
from os_web import acomp_web as aw
from os_web import criar_app, rotas

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
HOJE = dt.datetime(2026, 9, 27, 10, 0)
# a equipe de chamados vem do .env (o repositório é público: nome e id de gente não entram no código nem aqui)
EQUIPE_ID, EQUIPE_NOME = 900001, "Analista Teste"
NOTA = """[CHAMADO] Acompanhamento — STI · Estrutura Trackers
OS de campo: 9101 · Inspeção: 9102 · Ativo: TST100-ETKR1.100
Data da falha: 10/09/2026 13:28 · Menos de 7 dias: Sim

Campos do formulário do fabricante (coletados na inspeção):
  problema: Bateria baixa no tracker de teste
  acoes: Medida a tensão do painel
  serial: SN-TESTE-0001
  mac: AA00BB11CC22
Demais respostas:
  Causa da falha: Desgaste natural
  Localização na planta: fileira, posição e nº dos trackers afetados: Tracker 1
  TCU liga / energiza?: Sim"""


def _linha(i, folio, status=1, nota=NOTA, data="2026-09-20T12:00:00", data_fim="", resp_id=EQUIPE_ID,
           resp=EQUIPE_NOME, cliente="Cliente Teste", marca_titulo="STI"):
    return {"id": i, "folio": str(folio), "cliente": cliente, "usina": "Usina Teste 1", "ativo": "Tracker 1.100 TST",
            "tipo": "Estrutura Trackers", "tipo_tarefa": "Administrativa", "note": nota,
            "descricao": "[Tracker 1.100 TST] - Acompanhamento de chamado %s" % marca_titulo, "status_id": status,
            "status": api.WO_STATUS.get(status), "data": data, "data_fim": data_fim, "atribuido_a": resp,
            "id_atribuido": resp_id}


# ── a nota lida de volta ──────────────────────────────────────────────────────────────────────────────────────
def test_a_nota_volta_em_partes():
    n = aw.ler_nota("texto antes que não é do bloco\n" + NOTA)
    assert (n["marca"], n["tipo"]) == ("STI", "Estrutura Trackers")
    assert (n["os_campo"], n["inspecao"], n["ativo"]) == ("9101", "9102", "TST100-ETKR1.100")
    assert n["data_falha"] == "10/09/2026 13:28" and n["menos7_nota"] is True
    assert [c["chave"] for c in n["campos"]] == ["problema", "acoes", "serial", "mac"]
    assert n["campos"][2] == {"chave": "serial", "rotulo": "Nº de série", "valor": "SN-TESTE-0001", "mono": True}
    # a pergunta que tem ':' dentro fica inteira — partir no primeiro ':' cortaria "Localização na planta"
    loc = [d for d in n["demais"] if d["pergunta"].startswith("Localização")][0]
    assert loc == {"pergunta": "Localização na planta: fileira, posição e nº dos trackers afetados", "resposta": "Tracker 1"}


def test_nota_sem_o_bloco_nao_inventa():
    n = aw.ler_nota("OS criada à mão, sem o bloco do App")
    assert n["marca"] == "" and n["campos"] == [] and n["demais"] == []


def test_so_a_os_de_acompanhamento_entra():
    assert aw.eh_os3(_linha(1, 1))
    assert aw.eh_os3(dict(_linha(1, 1), note=""))                       # sem nota: título + Administrativa
    assert not aw.eh_os3(dict(_linha(1, 1), note="", tipo_tarefa="Corretiva"))
    assert not aw.eh_os3({"note": "OS antiga com a etiqueta CHAMADOS", "descricao": "Troca de TCU", "tipo_tarefa": "Corretiva"})


def test_menos_de_7_dias_e_recalculado():
    assert aw.menos_7d("10/09/2026 13:28", HOJE) == {"sim": False, "dias": 16}
    assert aw.menos_7d("24/09/2026 13:28", HOJE) == {"sim": True, "dias": 2}
    assert aw.menos_7d("", HOJE) == {"sim": None, "dias": None}


def test_a_coluna_sai_da_propria_os():
    assert aw.coluna(1, "") == "chegou" and aw.coluna(1, "TK-1") == "ticket"
    assert aw.coluna(2, "") == "fim" and aw.coluna(3, "TK-1") == "fim" and aw.coluna(4, "TK-1") == ""


# ── o card ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_card_diz_ha_quanto_tempo_e_de_quem():
    c = aw.cartao(_linha(1, 9103, data="2026-09-18T12:00:00"), "", "", HOJE)
    assert c["col"] == "chegou" and c["tempo"] == "chegou há 9 dias" and c["urg"] == "r"
    assert c["chegou"] == "18/09/2026 09:00" and c["marca"] == "STI" and c["code"] == "TST100-ETKR1.100"
    assert c["da_equipe"] is True
    outro = aw.cartao(_linha(1, 9103, resp_id=900002, resp="Técnico  Teste"), "", "", HOJE)
    assert outro["da_equipe"] is False and outro["responsavel"] == "Técnico Teste"


def test_com_ticket_a_regua_e_a_da_cobranca():
    c = aw.cartao(_linha(1, 9103, data="2026-09-01T12:00:00"), "TK-9", "2026-09-26T09:00:00-03:00", HOJE)
    assert c["col"] == "ticket" and c["ticket"] == "TK-9" and c["tempo"] == "há 1 dia sem atualização" and c["urg"] == "m"
    assert aw.cartao(_linha(1, 9103), "TK-9", "2026-09-27T08:00:00-03:00", HOJE)["urg"] == "g"      # atualizado hoje
    assert aw.cartao(_linha(1, 9103, data="2026-09-01T12:00:00"), "TK-9", "", HOJE)["urg"] == "r"   # 26 dias sem nada


def test_finalizada_sem_data_de_fim_usa_a_data_da_tela():
    c = aw.cartao(_linha(1, 9103, status=3), "TK-9", "", HOJE, finalizado="2026-09-26T11:30:00-03:00")
    assert c["col"] == "fim" and c["tempo"] == "em 26/09"


def test_o_ticket_nao_lido_e_dito():
    assert aw.cartao(_linha(1, 9103), None, "", HOJE)["ticket_nao_lido"] is True


def test_o_quadro_ordena_conta_e_separa():
    linhas = [_linha(1, 9201, data="2026-09-25T12:00:00"), _linha(2, 9202, data="2026-09-10T12:00:00"),
              _linha(3, 9203), _linha(4, 9204, status=3, data_fim="2026-09-26T14:30:00"),
              _linha(5, 9205, status=4), _linha(6, 9206, status=3, data="2026-03-01T12:00:00", data_fim="2026-04-01T12:00:00"),
              _linha(7, 9207, resp_id=900002, resp="Técnico", cliente="Outro Cliente"),
              {"id": 8, "folio": "9208", "note": "OS antiga", "descricao": "Troca", "tipo_tarefa": "Corretiva", "status_id": 1}]
    q = aw.montar_quadro(linhas, {3: "TK-3"}, {}, HOJE)
    assert [c["folio"] for c in q["colunas"]["chegou"]] == ["9202", "9207", "9201"]     # a mais parada primeiro
    assert [c["folio"] for c in q["colunas"]["ticket"]] == ["9203"]
    assert [c["folio"] for c in q["colunas"]["fim"]] == ["9204"]
    assert (q["canceladas"], q["antigas"], q["fora"], q["total"]) == (1, 1, 1, 5)
    assert q["opcoes"]["cliente"] == ["Cliente Teste", "Outro Cliente"] and q["opcoes"]["marca"] == ["STI"]


def test_so_le_o_ticket_de_quem_vai_para_a_tela():
    assert aw.precisa_ticket(_linha(1, 1, status=1), HOJE) and aw.precisa_ticket(_linha(1, 1, status=2), HOJE)
    assert aw.precisa_ticket(_linha(1, 1, status=3, data_fim="2026-09-20T12:00:00"), HOJE)
    assert not aw.precisa_ticket(_linha(1, 1, status=3, data_fim="2026-03-20T12:00:00"), HOJE)
    assert not aw.precisa_ticket(_linha(1, 1, status=4), HOJE)


def test_linha_do_tempo_da_mais_nova_para_a_chegada():
    c = aw.cartao(_linha(1, 9103), "", "", HOJE)
    obs = [{"quando": "2026-09-26T09:12:00-03:00", "tipo": "ticket", "texto": "Ticket registrado: TK-1", "quem": "Analista"},
           {"quando": "2026-09-26T09:15:00-03:00", "tipo": "obs", "texto": "Aberto no portal", "quem": "Analista"}]
    tl = aw.linha_do_tempo(c, obs)
    assert [e["texto"] for e in tl][:2] == ["Aberto no portal", "Ticket registrado: TK-1"]
    assert tl[-1]["texto"].startswith("Chegou: a OS 9103") and tl[-1]["d"] == "20/09"
    assert [e["novo"] for e in tl] == [True, False, False] and tl[1]["ev"] is True
    assert aw.linha_do_tempo(c, [])[0]["novo"] is False                 # só a chegada: nada acende


def test_no_empate_de_segundo_a_gravada_depois_fica_em_cima():
    c = aw.cartao(_linha(1, 9103), "", "", HOJE)
    mesmo = "2026-09-27T02:13:00-03:00"
    obs = [{"quando": mesmo, "tipo": "ticket", "texto": "Ticket registrado: TK-1", "quem": "S"},
           {"quando": mesmo, "tipo": "finalizado", "texto": "Chamado finalizado", "quem": "S"}]
    assert [e["texto"] for e in aw.linha_do_tempo(c, obs)][:2] == ["Chamado finalizado", "Ticket registrado: TK-1"]


def test_outros_chamados_do_ativo_e_da_mesma_os_de_campo():
    a = aw.cartao(_linha(1, 9301), "", "", HOJE)
    b = aw.cartao(_linha(2, 9302), "", "", HOJE)                                       # mesmo ativo e mesma OS 1
    c = aw.cartao(_linha(3, 9303, nota=NOTA.replace("TST100-ETKR1.100", "TST100-ETKR2.100")), "", "", HOJE)
    d = aw.cartao(_linha(4, 9304, nota=NOTA.replace("9101", "9999").replace("TST100-ETKR1.100", "X")), "", "", HOJE)
    o = aw.outros(a, [a, b, c, d])
    assert [x["folio"] for x in o["ativo"]] == ["9302"] and [x["folio"] for x in o["campo"]] == ["9303"]


def test_o_ticket_de_varias_os_casa_pelo_texto(monkeypatch):
    def rpc(metodo, params):
        assert metodo == api.RPC_WO_FORMIT
        if params["id_work_order"] == 3:
            raise api.FracttalError("recusou")
        itens = {1: [{"description": "Nº do ticket ou protocolo aberto no fabricante", "value": " TK-1 ", "id_task_form_item_type": 1}],
                 2: [{"description": "Outra coisa", "value": "x", "id_task_form_item_type": 1}]}
        return {"data": itens.get(params["id_work_order"], [])}
    monkeypatch.setattr(api, "_rpc_call", rpc)
    assert api.tickets_os3_em_massa([1, 2, 3, 1]) == {1: "TK-1", 2: "", 3: None}


# ── as rotas ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    rotas._MEMO.clear()
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_ID", str(EQUIPE_ID))
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_NOME", EQUIPE_NOME)
    monkeypatch.setattr(aw, "agora_brt", lambda: HOJE)
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})


@pytest.fixture
def cli():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "analista@teste.invalid", "perfil": "ADMINISTRATOR"}
    return c


def _det(folio="9103", resposta="", com_item=True):
    item = {"descricao": "Nº do ticket ou protocolo aberto no fabricante", "resposta": resposta, "id_tarefa": 555,
            "id_form_item": 777, "tipo_id": 1, "feito": bool(resposta), "tipo": "Texto"}
    return {"folio": folio, "notas": NOTA, "subtarefas": [item] if com_item else [], "code": "TST100-ETKR1.100",
            "ativo": "Tracker 1.100 TST", "descricao": "[Tracker 1.100 TST] - Acompanhamento de chamado STI"}


def test_o_card_de_chamados_abre_as_tres_portas(cli):
    h = cli.get("/os/chamados").get_data(as_text=True)
    for href in ("/os/chamados/inspecao", "/os/chamados/acompanhamento", "/os/chamados/fornecedores"):
        assert 'href="%s"' % href in h
    assert "em-breve/chamados" not in h and "Controle de fornecedores" in h


def test_o_quadro_com_as_tres_colunas_e_a_memoria(cli, monkeypatch):
    chamadas = []
    monkeypatch.setattr(api, "list_chamados", lambda **k: chamadas.append(k) or
                        [_linha(1, 9103), _linha(2, 9104), _linha(3, 9105, status=3, data_fim="2026-09-26T12:00:00")])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {2: "TK-2"})
    h = cli.get("/os/chamados/acompanhamento").get_data(as_text=True)
    chegou = h[h.index('data-col="chegou"'):h.index('data-col="ticket"')]
    ticket = h[h.index('data-col="ticket"'):h.index('data-col="fim"')]
    assert "/os/chamados/acompanhamento/9103" in chegou and "<em data-n>1</em>" in chegou
    assert "/os/chamados/acompanhamento/9104" in ticket and "TK-2" in ticket
    assert "/os/chamados/acompanhamento/9105" in h[h.index('data-col="fim"'):]
    assert '<div class="lbl">Sem ticket</div><div class="linha"><span class="val r">1</span>' in h
    assert 'title="chegou há 7 dias"' in h and '<span class="tag u-a">7 dias</span>' in h
    cli.get("/os/chamados/acompanhamento")
    assert len(chamadas) == 1                                             # da memória
    cli.get("/os/chamados/acompanhamento?atualizar=1")
    assert len(chamadas) == 2


def test_o_quadro_avisa_quem_esta_fora_da_equipe(cli, monkeypatch):
    monkeypatch.setattr(api, "list_chamados", lambda **k: [_linha(1, 9103, resp_id=900002, resp="Técnico Teste")])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    h = cli.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert "no nome de Técnico Teste" in h
    assert "<b>1 de 1</b> OS de acompanhamento estão no nome de outra pessoa, não da equipe de chamados (Analista Teste)" in h



def test_sem_a_equipe_no_env_ninguem_e_de_fora(cli, monkeypatch):
    """Sem OS_WEB_CHAMADO_RESP_ID/NOME, o quadro não sabe quem é a equipe: acusar todas as OS seria alarme falso."""
    monkeypatch.delenv("OS_WEB_CHAMADO_RESP_ID")
    monkeypatch.delenv("OS_WEB_CHAMADO_RESP_NOME")
    assert aw.equipe() == (0, "") and aw.da_equipe(_linha(1, 9103, resp_id=900002, resp="Técnico Teste"))
    monkeypatch.setattr(api, "list_chamados", lambda **k: [_linha(1, 9103, resp_id=900002, resp="Técnico Teste")])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    h = cli.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert "no nome de outra pessoa" not in h and "no nome de Técnico Teste" not in h


def test_a_equipe_pelo_nome_quando_a_linha_nao_traz_o_id():
    assert aw.da_equipe(_linha(1, 9103, resp_id="", resp="analista  teste"))
    assert not aw.da_equipe(_linha(1, 9103, resp_id="", resp="Outra Pessoa"))

def test_o_quadro_sai_mesmo_sem_o_banco_das_observacoes(cli, monkeypatch):
    monkeypatch.setattr(api, "list_chamados", lambda **k: [_linha(1, 9103)])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    monkeypatch.setattr(cos, "_linhas", lambda: (_ for _ in ()).throw(ConnectionError("banco fora")))
    h = cli.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert "/os/chamados/acompanhamento/9103" in h and "Não consegui ler as observações" in h


def test_a_tela_do_chamado(cli, monkeypatch):
    monkeypatch.setattr(api, "list_chamados", lambda **k: [_linha(1, 9103), _linha(2, 9104)])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det())
    h = cli.get("/os/chamados/acompanhamento/9103").get_data(as_text=True)
    assert 'data-folio="9103"' in h and 'data-wid="1"' in h
    assert "SN-TESTE-0001" in h and 'data-copia="SN-TESTE-0001"' in h and "Copiar tudo" in h
    assert 'href="/os/os/folio/9101"' in h and 'href="/os/os/folio/9102"' in h           # a cadeia
    assert "Não · 16 dias" in h and 'a nota diz "Sim"' in h                                 # recalculado
    assert "Portal STI" in h                                                                # como abrir (chamado_spec.CANAL)
    assert "/os/chamados/acompanhamento/9104" in h                                          # outro chamado do ativo
    assert "Chegou: a OS 9103 nasceu sozinha no fechamento da inspeção 9102." in h



def test_as_respostas_do_tecnico_recolhem_ate_o_titulo(cli, monkeypatch):
    """Levi, 27/09: "dê para reduzir essa parte, com um botão esconde e deixa só o título". O botão fica no cabeçalho,
    com o Copiar tudo — que continua valendo com a tabela escondida —, e a escolha volta antes da 1ª pintura."""
    monkeypatch.setattr(api, "list_chamados", lambda **k: [_linha(1, 9103)])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det())
    h = cli.get("/os/chamados/acompanhamento/9103").get_data(as_text=True)
    for bloco, corpo in (("campos", "corpo_campos"), ("demais", "corpo_demais")):
        ini = h.index('data-recolhe="%s"' % bloco)
        assert h.index('aria-controls="%s"' % corpo, ini) < h.index('id="%s"' % corpo, ini)     # botão no cabeçalho
        assert 'aria-expanded="true"' in h[ini:h.index('id="%s"' % corpo, ini)]
    campos = h[h.index('data-recolhe="campos"'):h.index('id="corpo_campos"')]
    assert "Copiar tudo" in campos and "Esconder" in campos and "Mostrar" in campos
    assert "SN-TESTE-0001" in h[h.index('id="corpo_campos"'):h.index('data-recolhe="demais"')]   # a tabela no corpo
    assert 'localStorage.getItem("acomp.recolhe."' in h                                         # antes da pintura
    js = open(os.path.join(os.path.dirname(rotas.__file__), "static", "acomp.js"), encoding="utf-8").read()
    assert '"acomp.recolhe." + bloco.dataset.recolhe' in js                                      # a mesma chave

def test_gravar_o_ticket_vai_na_subtarefa_e_anota(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det())
    gravou, anotou = [], []
    monkeypatch.setattr(api, "salvar_subtarefas", lambda wid, tid, v: gravou.append((wid, tid, v)) or {"ok": True, "n": 1})
    monkeypatch.setattr(cos, "adicionar", lambda *a, **k: anotou.append((a, k)) or {})
    rotas._MEMO[("acomp", "x")] = (0, "velho")
    j = cli.post("/os/api/acomp/9103/ticket", json={"ticket": "  TK  77 ", "wid": 1}).get_json()
    assert j["ok"] and j["ticket"] == "TK 77" and j["aviso"] == ""
    assert gravou == [(1, 555, [{"id_form_item": 777, "valor": "TK 77", "tipo": 1}])]
    assert anotou[0][0] == (9103, "Ticket registrado: TK 77", "ticket")
    assert anotou[0][1]["quem"] == "Analista Teste" and anotou[0][1]["ativo"] == "TST100-ETKR1.100"
    assert ("acomp", "x") not in rotas._MEMO                                 # o quadro relê na próxima


def test_trocar_o_ticket_anota_de_onde_para_onde(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(resposta="TK-1"))
    monkeypatch.setattr(api, "salvar_subtarefas", lambda *a: {"ok": True})
    anotou = []
    monkeypatch.setattr(cos, "adicionar", lambda *a, **k: anotou.append(a) or {})
    cli.post("/os/api/acomp/9103/ticket", json={"ticket": "TK-2", "wid": 1})
    assert anotou[0][1] == "Ticket alterado: TK-1 → TK-2"


def test_o_mesmo_ticket_nao_regrava(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(resposta="TK-1"))
    monkeypatch.setattr(api, "salvar_subtarefas", lambda *a: pytest.fail("não devia gravar"))
    assert cli.post("/os/api/acomp/9103/ticket", json={"ticket": "TK-1", "wid": 1}).get_json()["ok"]


def test_id_de_outra_os_nao_grava(cli, monkeypatch):
    """O id veio do navegador: se ele não for o desta OS, nada é gravado (senão o ticket iria para outro chamado)."""
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(folio="5555"))
    monkeypatch.setattr(api, "salvar_subtarefas", lambda *a: pytest.fail("não devia gravar"))
    r = cli.post("/os/api/acomp/9103/ticket", json={"ticket": "TK-1", "wid": 1})
    assert r.status_code == 404


def test_os_sem_a_subtarefa_do_ticket(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(com_item=False))
    r = cli.post("/os/api/acomp/9103/ticket", json={"ticket": "TK-1", "wid": 1})
    assert r.status_code == 400 and "não tem a subtarefa" in r.get_json()["erro"]


def test_ticket_vazio(cli):
    assert cli.post("/os/api/acomp/9103/ticket", json={"ticket": "  ", "wid": 1}).status_code == 400


def test_ticket_gravado_e_anotacao_que_falha_vira_aviso(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det())
    monkeypatch.setattr(api, "salvar_subtarefas", lambda *a: {"ok": True})
    monkeypatch.setattr(cos, "adicionar", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("banco fora")))
    j = cli.post("/os/api/acomp/9103/ticket", json={"ticket": "TK-1", "wid": 1}).get_json()
    assert j["ok"] and "anotação automática não entrou" in j["aviso"]


def test_salvar_observacao(cli, monkeypatch):
    anotou = []
    monkeypatch.setattr(cos, "adicionar", lambda *a, **k: anotou.append((a, k)) or
                        {"quando": "2026-09-27T10:32:00-03:00", "tipo": "obs", "texto": a[1], "quem": k["quem"]})
    j = cli.post("/os/api/acomp/9103/obs", json={"texto": "A Huawei pediu o log", "ativo": "TST100-ETKR1.100"}).get_json()
    assert anotou[0][0] == (9103, "A Huawei pediu o log", "obs") and anotou[0][1]["email"] == "analista@teste.invalid"
    assert j["entrada"]["d"] == "27/09" and j["entrada"]["autor"] == "Analista Teste · 27/09 10:32" and j["entrada"]["novo"]


def test_observacao_vazia_e_sem_credencial(cli, monkeypatch):
    assert cli.post("/os/api/acomp/9103/obs", json={"texto": " "}).status_code == 400
    import gridco_abas as ga
    monkeypatch.setattr(cos, "adicionar", lambda *a, **k: (_ for _ in ()).throw(ga.SemCredencial("sem token")))
    assert cli.post("/os/api/acomp/9103/obs", json={"texto": "x"}).status_code == 403


def test_finalizar_e_o_concluir_do_card(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(resposta="TK-1"))
    concluiu, anotou = [], []
    monkeypatch.setattr(api, "concluir_os_checado", lambda wid: concluiu.append(wid) or
                        {"ok": True, "data_fim": {"sem_fim": [555], "total": 1}})
    monkeypatch.setattr(cos, "adicionar", lambda *a, **k: anotou.append(a) or {})
    j = cli.post("/os/api/acomp/9103/finalizar", json={"wid": 1}).get_json()
    assert concluiu == [1] and anotou[0][1:3] == ("Chamado finalizado", "finalizado")
    assert j["mensagem"] == "Chamado finalizado: a OS 9103 foi concluída no Fracttal."
    assert "data de fim vazia" in j["aviso"]                                   # dito com calma: é o esperado aqui


def test_finalizar_recusado_pelo_fracttal(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det())
    monkeypatch.setattr(api, "concluir_os_checado", lambda wid: {"ok": False, "msg": "tarefa pendente"})
    r = cli.post("/os/api/acomp/9103/finalizar", json={"wid": 1})
    assert r.status_code == 400 and r.get_json()["erro"] == "tarefa pendente"


def test_o_em_breve_antigo_cai_no_quadro(cli):
    r = cli.get("/os/em-breve/chamados")
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/chamados/acompanhamento")
