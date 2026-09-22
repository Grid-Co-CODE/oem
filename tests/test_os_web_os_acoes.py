# tests/test_os_web_os_acoes.py
"""As AÇÕES do card de detalhe da OS, na web (os_web/rotas_os_acoes.py): trocar responsável, editar etiquetas, editar a
observação, Concluir OS, Cancelar OS, Fluxo e os anexos com download. Cada escrita chama a MESMA função do `api.py` que o
desktop chama, com os MESMOS argumentos (steps/os_detalhe.py, steps/cancelar_os.py); a validação devolve 400 com a frase
do app e nada chega ao Fracttal. A API é um dublê que grava o que recebeu."""
import os

import pytest

import api
from os_web import criar_app, os_acoes_web

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
_STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web", "static")


def _det(**muda):
    d = {"folio": 9812, "descricao": "[Inversor 2.18] - Recomposição de String", "tipo": "Corretiva", "classif": "Elétrica / Strings",
         "criticidade": "Alto", "event_date": "2026-09-12T01:10:00", "data_fim": None, "responsavel": "Luiz Silva",
         "criado_por": "Levi Maia", "solicitacao": None, "os_pai": "", "os_pai_id": None,
         "notas": "Strings Ipv10 e Ipv17 com corrente nula, verificar e normalizar",
         "subtarefas": [{"descricao": "Medir tensão das strings", "feito": True, "tipo": "Número", "resposta": "612", "id_tarefa": 1},
                        {"descricao": "Foto da string normalizada", "feito": False, "tipo": "Texto", "resposta": "", "id_tarefa": 1}],
         "tarefas": [{"id": 1, "titulo": "[Inversor 2.18] - Recomposição de String", "ativo": "Inversor 2.18", "tipo": "Corretiva",
                      "classif": "Elétrica", "criticidade": "Alto", "programada": "2026-09-12T08:00:00", "inicio": "", "fim": "",
                      "duracao": "5400", "gatilho": "Sem agendamento", "nota": ""}],
         "etiquetas": [{"id": 4660, "nome": "PERFORMANCE", "cor": "#8fce3f"}], "code": "TNB200-INVR2.18", "ativo": "Inversor 2.18",
         "cancel_motivo": "", "cancel_nota": ""}
    d.update(muda)
    return d


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det() if wid == 501 else {})
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


# ── o card: os controles vivos, com os textos do app ───────────────────────────────────────────────────
def test_o_card_habilita_os_controles_do_app(cli):
    html = cli.get("/os/os/501?parcial=1&status=Em+Processo").get_data(as_text=True)
    assert "Disponível no OS Creator instalado" not in html                      # o aviso de 'só no app' saiu
    for acao in ("responsavel", "etiquetas", "nota-editar", "nota-salvar", "nota-cancelar", "concluir", "cancelar", "fluxo",
                 "anexos-sub", "anexos-os"):
        assert 'data-acao="%s"' % acao in html, acao
    # os rótulos do app, iguais (steps/os_detalhe.py)
    for txt in (">trocar<", ">editar<", ">Editar<", ">Salvar<", ">Cancelar<", "Concluir OS", "Cancelar OS", ">Fluxo", "Clonar esta OS",
                "Abrir chamado", "Observação da OS…", "Atribuir esta OS a outra pessoa",
                "Fecha a OS no Fracttal (irreversível — precisa de permissão na sua conta)",
                "Cancela a OS no Fracttal (precisa de permissão na sua conta)"):
        assert txt in html, txt
    # Clonar e Abrir chamado são telas de outros pacotes: viram links pelo número da OS
    assert 'href="/os/clonar?folio=9812"' in html and 'href="/os/chamados/abrir?folio=9812"' in html
    # o card sabe quem é (o JS recarrega o fragmento por aqui) e a etiqueta leva o id (o seletor nasce marcado)
    assert 'data-wid="501"' in html and 'data-folio="9812"' in html and 'data-status="Em Processo"' in html
    assert 'data-id="4660"' in html
    assert 'data-msg' in html                                                      # onde a mensagem de cada ação aparece


def test_os_dialogos_do_app_vem_no_fragmento_como_templates(cli):
    """Cada QDialog do desktop vira um <template> no card, com o MESMO texto, que o JS clona por cima do card."""
    html = cli.get("/os/os/501?parcial=1&status=Em+Processo").get_data(as_text=True)
    for nome in ("responsavel", "etiquetas", "concluir", "cancelar", "fluxo", "anexos"):
        assert 'data-dlg="%s"' % nome in html, nome
    # TrocarResponsavelDialog
    assert "Trocar o responsável da OS 9812" in html and "Hoje está com <b>Luiz Silva</b>." in html and ">Atribuir<" in html
    assert "carregando o pessoal…" in html
    # _EtiquetasDialog
    assert "Etiquetas da OS 9812" in html and "carregando etiquetas…" in html
    # _ConcluirDialog: título, subtítulo, % pelas subtarefas (1 de 2 = 50%), aviso de pendentes/irreversível
    assert "Concluir a OS 9812?" in html and "A OS será marcada como concluída e fechada no Fracttal." in html
    assert "Conclusão da OS" in html and ">50%<" in html and "1 de 2 subtarefas concluídas" in html
    assert "ficarão registradas como <b>pendentes</b>. Esta ação é <b>irreversível</b>!" in html
    # CancelarOSDialog
    assert "Cancelar a OS 9812" in html and "Tipo: <b>Cancelar OS</b>" in html and "a autorização é a do seu usuário no Fracttal" in html
    assert "Motivo do cancelamento" in html and "carregando motivos…" in html and "Confirmar cancelamento" in html and ">Voltar<" in html
    # FluxoDialog
    assert "Fluxo da OS 9812" in html and "carregando o fluxo…" in html


def test_concluir_avisa_antes_quando_a_tarefa_esta_sem_data_de_fim(cli, monkeypatch):
    """Lado 'antes' do double check (Levi, 03/08, OS 10509): a tarefa sem `fim` acende o aviso vermelho no diálogo."""
    html = cli.get("/os/os/501?parcial=1").get_data(as_text=True)                  # a tarefa do _det() tem fim ""
    assert "Esta OS vai fechar <b>sem data de fim da tarefa</b>" in html
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(tarefas=[{"id": 1, "titulo": "T", "fim": "2026-09-12T10:00:00"}]))
    # O NEGATIVO PRECISA SER A FRASE INTEIRA. Com o trecho solto "sem data de fim" o teste passou
    # a falhar sozinho quando o card ganhou o rótulo "OS ainda sem data de fim" — outro lugar,
    # outro assunto, e o aviso vermelho do diálogo continuava certinho (21/09).
    html = cli.get("/os/os/501?parcial=1").get_data(as_text=True)
    assert "vai fechar <b>sem data de fim da tarefa</b>" not in html
    assert "desta OS vão fechar <b>sem data de fim</b>" not in html
    # várias sem fim: conta e lista até 3
    tarefas = [{"id": i, "titulo": "Tarefa %d" % i, "fim": ""} for i in range(1, 6)]
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(tarefas=tarefas))
    html = cli.get("/os/os/501?parcial=1").get_data(as_text=True)
    assert "<b>5 tarefas</b> desta OS vão fechar <b>sem data de fim</b>" in html and "Tarefa 1; Tarefa 2; Tarefa 3 e mais 2" in html


def test_concluir_sem_subtarefas_mostra_100_e_o_texto_do_app(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(subtarefas=[]))
    html = cli.get("/os/os/501?parcial=1").get_data(as_text=True)
    assert ">100%<" in html and "OS sem subtarefas" in html


def test_editar_nota_segue_as_duas_recusas_do_app(cli, monkeypatch):
    """`_nota_pode_editar` (steps/os_detalhe.py): OS concluída/cancelada e OS de várias tarefas não editam — o botão nasce
    desabilitado com o motivo no title, como o tooltip do app."""
    html = cli.get("/os/os/501?parcial=1&status=Em+Processo").get_data(as_text=True)
    assert 'data-acao="nota-editar" title="Editar a observação desta OS"' in html
    html = cli.get("/os/os/501?parcial=1&status=Conclu%C3%ADda").get_data(as_text=True)
    assert 'data-acao="nota-editar" disabled title="OS concluída — o Fracttal não aceita mais editar a observação."' in html
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(cancel_motivo="Duplicada"))
    html = cli.get("/os/os/501?parcial=1").get_data(as_text=True)                  # sem status na URL: o cancelamento entrega
    assert "OS cancelada — o Fracttal não aceita mais editar a observação." in html
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(tarefas=[{"id": i} for i in range(3)]))
    html = cli.get("/os/os/501?parcial=1&status=Em+Processo").get_data(as_text=True)
    assert "Esta OS tem 3 tarefas, e cada uma tem a sua observação. A edição por aqui só é segura em OS de uma tarefa — use o Fracttal." in html


def test_pagina_cheia_carrega_o_js_e_o_css_do_pacote(cli):
    html = cli.get("/os/os/501").get_data(as_text=True)
    assert "/os/static/os_acoes.js" in html and "/os/static/os_acoes.css" in html
    # o fragmento do card leva o CSS junto (o Histórico o injeta numa página que não o conhece)
    assert "/os/static/os_acoes.css" in cli.get("/os/os/501?parcial=1").get_data(as_text=True)
    assert cli.get("/os/static/os_acoes.js").status_code == 200 and cli.get("/os/static/os_acoes.css").status_code == 200


# ── escritas: a função do api e os argumentos do desktop ──────────────────────────────────────────────
def test_trocar_responsavel_chama_mudar_responsavel_como_o_desktop(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "mudar_responsavel", lambda *a, **k: visto.update(args=a, kw=k) or {"ok": True, "raw": {}})
    r = cli.post("/os/api/os/501/responsavel", json={"id_personnel": 1414413, "name": "Levi Maia", "folio": 9812})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert visto == {"args": (501, 1414413), "kw": {}}       # os_detalhe.py:331 — ApiWorker(api.mudar_responsavel, self._wo, p["id_personnel"])
    assert r.get_json()["mensagem"] == "OS 9812 agora está com Levi Maia."
    visto.clear()
    r = cli.post("/os/api/os/501/responsavel", json={})
    assert r.status_code == 400 and r.get_json()["erro"] == "escolha a pessoa." and not visto        # nada chega à API
    monkeypatch.setattr(api, "mudar_responsavel", lambda *a: {"ok": False, "erro": "não consegui trocar o responsável"})
    r = cli.post("/os/api/os/501/responsavel", json={"id_personnel": 5})
    assert r.status_code == 400 and r.get_json()["erro"] == "não consegui trocar o responsável"


def test_etiquetas_get_traz_catalogo_e_as_da_os(cli, monkeypatch):
    monkeypatch.setattr(api, "get_labels", lambda: [{"id": 4660, "description": "PERFORMANCE", "color": "8fce3f"},
                                                    {"id": 12, "description": "CHAMADOS", "color": None},
                                                    {"id": 13, "description": "  ", "color": "#000000"}])
    j = cli.get("/os/api/os/501/etiquetas?atuais=4660,12").get_json()
    assert [l["id"] for l in j["catalogo"]] == [4660, 12]                      # a sem descrição não entra (como o filtro do app)
    assert j["catalogo"][0]["color"] == "#8fce3f" and j["catalogo"][1]["color"] == "#A6A6A6"   # _cor_hex: normaliza, cinza no fallback
    assert j["atuais"] == [4660, 12]
    assert cli.get("/os/api/os/501/etiquetas").get_json()["atuais"] == [4660]  # sem a lista do card, lê a OS


def test_etiquetas_post_chama_apply_labels_com_o_conjunto_inteiro(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "apply_labels", lambda *a: visto.update(args=a) or {"ok": True, "raw": {}})
    r = cli.post("/os/api/os/501/etiquetas", json={"ids": [4660, "12"]})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert visto["args"] == (501, [4660, 12])                # os_detalhe.py:420 — ApiWorker(api.apply_labels, self._wo, ids); labels_sync SUBSTITUI o conjunto
    visto.clear()
    r = cli.post("/os/api/os/501/etiquetas", json={"ids": []})
    assert r.status_code == 400 and r.get_json()["erro"] == "Marque ao menos uma etiqueta (ou Cancelar)." and not visto
    monkeypatch.setattr(api, "apply_labels", lambda *a: {"ok": False, "erro": "sem id_work_order ou id_labels"})
    assert cli.post("/os/api/os/501/etiquetas", json={"ids": [1]}).status_code == 400


def test_editar_nota_chama_editar_nota_os_aparada_e_respeita_as_recusas(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "editar_nota_os", lambda *a: visto.update(args=a) or {"ok": True, "nota": a[1]})
    r = cli.post("/os/api/os/501/nota", json={"nota": "  texto novo  ", "status": "Em Processo"})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "nota": "texto novo"}
    assert visto["args"] == (501, "texto novo")               # os_detalhe.py:1361 — ApiWorker(api.editar_nota_os, self._wo, novo) com novo = texto.strip()
    # OS de várias tarefas: a recusa do app, e NADA chega à API (sobrescrever a observação da tarefa errada é pior que não editar)
    visto.clear()
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(tarefas=[{"id": 1}, {"id": 2}]))
    r = cli.post("/os/api/os/501/nota", json={"nota": "x"})
    assert r.status_code == 400 and "Esta OS tem 2 tarefas" in r.get_json()["erro"] and not visto
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det(cancel_motivo="Duplicada"))
    r = cli.post("/os/api/os/501/nota", json={"nota": "x"})
    assert r.status_code == 400 and "cancelada" in r.get_json()["erro"] and not visto
    # o Fracttal recusou (OS concluída) → a mensagem do api, em 400
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: _det())
    monkeypatch.setattr(api, "editar_nota_os", lambda *a: {"ok": False, "erro": "Esta OS já está concluída — o Fracttal não aceita mais editar a observação dela."})
    r = cli.post("/os/api/os/501/nota", json={"nota": "x"})
    assert r.status_code == 400 and "já está concluída" in r.get_json()["erro"]


def test_concluir_chama_concluir_os_checado_e_reconfere_a_data_de_fim(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "concluir_os_checado", lambda *a: visto.update(args=a) or {"ok": True, "raw": {}, "data_fim": {"ok": True, "total": 1, "sem_fim": []}})
    r = cli.post("/os/api/os/501/concluir", json={"folio": 9812})
    assert r.status_code == 200 and visto["args"] == (501,)   # os_detalhe.py:896 — ApiWorker(api.concluir_os_checado, self._wo): irreversível, 2 passos dentro do api
    assert r.get_json()["mensagem"] == "A OS 9812 foi concluída." and r.get_json()["aviso"] is False
    # 2º lado do double check: fechou SEM data de fim → o aviso do app, com a contagem
    monkeypatch.setattr(api, "concluir_os_checado", lambda *a: {"ok": True, "data_fim": {"ok": False, "total": 3, "sem_fim": ["A", "B"]}})
    j = cli.post("/os/api/os/501/concluir", json={"folio": 9812}).get_json()
    assert j["aviso"] is True and j["mensagem"].startswith("A OS 9812 foi concluída, mas 2 das 3 tarefas ficou SEM data de fim.")
    assert "cronômetro de execução" in j["mensagem"]
    monkeypatch.setattr(api, "concluir_os_checado", lambda *a: {"ok": True, "data_fim": {"ok": False, "total": 1, "sem_fim": ["A"]}})
    assert "mas a tarefa ficou SEM data de fim" in cli.post("/os/api/os/501/concluir", json={}).get_json()["mensagem"]
    # recusa em dict ({'ok': False, 'msg'}) → 400 com a frase; FracttalError → 502 JSON pelo errorhandler
    monkeypatch.setattr(api, "concluir_os_checado", lambda *a: {"ok": False, "msg": "Não foi possível fechar a OS."})
    r = cli.post("/os/api/os/501/concluir", json={})
    assert r.status_code == 400 and r.get_json()["erro"] == "Não foi possível fechar a OS."
    def _boom(*a):
        raise api.FracttalError("Não foi possível mudar o status da OS (sua conta tem permissão p/ fechar OS?).")
    monkeypatch.setattr(api, "concluir_os_checado", _boom)
    r = cli.post("/os/api/os/501/concluir", json={})
    assert r.status_code == 502 and "permissão" in r.get_json()["erro"]


def test_cancelar_chama_cancel_os_com_motivo_e_observacao_como_o_desktop(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "cancel_os", lambda *a, **k: visto.update(args=a, kw=k) or {"ok": True, "raw": {}})
    r = cli.post("/os/api/os/501/cancelar", json={"id_status_custom": 7, "note": "  OS duplicada  ", "folio": 9812})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "mensagem": "OS 9812 cancelada com sucesso."}
    assert visto == {"args": (501, 7, "OS duplicada"), "kw": {}}   # cancelar_os.py:77 — ApiWorker(api.cancel_os, self._wo, idm, self.obs.toPlainText().strip())
    visto.clear()
    r = cli.post("/os/api/os/501/cancelar", json={"note": "sem motivo"})
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o motivo do cancelamento." and not visto
    def _recusa(*a, **k):
        raise api.FracttalError("Cancelamento recusado pelo Fracttal (sua conta tem permissão p/ cancelar OS?).")
    monkeypatch.setattr(api, "cancel_os", _recusa)
    r = cli.post("/os/api/os/501/cancelar", json={"id_status_custom": 7})
    assert r.status_code == 502 and "recusado" in r.get_json()["erro"]


def test_cancel_motivos_vem_do_api(cli, monkeypatch):
    monkeypatch.setattr(api, "get_cancel_motivos", lambda: [{"id": 7, "description": "Duplicada"}, {"id": 9, "description": "Erro de cadastro"}])
    assert cli.get("/os/api/os/501/cancel-motivos").get_json() == {"motivos": [{"id": 7, "description": "Duplicada"}, {"id": 9, "description": "Erro de cadastro"}]}


# ── leituras: fluxo e anexos ───────────────────────────────────────────────────────────────────────────
def test_fluxo_chama_fluxo_da_os_sem_historico_do_ativo_e_pinta_a_cadeia(cli, monkeypatch):
    visto = {}
    fx = {"atual": {"id": 501, "folio": "9812"},
          "cadeia": [{"id": 400, "folio": "9786", "descricao": "[Inversor 2.18] - Inspeção Geral do Inversor", "tipo_tarefa": "Preventiva",
                      "status": "Concluída", "status_id": 3, "event_date": "2026-09-01T12:00:00", "criacao": ""},
                     {"id": 501, "folio": "9812", "descricao": "[Inversor 2.18] - Recomposição de String", "tipo_tarefa": "Corretiva",
                      "status": "Em Processo", "status_id": 1, "event_date": "", "criacao": "2026-09-12T01:12:00"}],
          "ativo": {"id_item": 1, "nome": "Thopen - Tanabi 2 - SP", "code": "TNB200", "usina": "Thopen - Tanabi 2 - SP", "cliente": "Thopen"},
          "historico": [], "aviso": ""}
    monkeypatch.setattr(api, "fluxo_da_os", lambda *a: visto.update(args=a) or fx)
    j = cli.get("/os/api/os/501/fluxo").get_json()
    assert visto["args"] == (501, 0)                           # os_fluxo.py:139 — ApiWorker(api.fluxo_da_os, self._wo, 0): sem o histórico do ativo
    assert j["subtitulo"] == "Thopen - Tanabi 2 - SP"          # deduplica nome/usina/cliente (o nome já contém o cliente)
    assert [n["folio"] for n in j["cadeia"]] == ["9786", "9812"] and j["cadeia"][1]["atual"] is True and j["cadeia"][0]["atual"] is False
    assert j["cadeia"][0]["cor"] == "#3fb27f" and j["cadeia"][1]["cor"] == "#4a9eff"       # COR_STATUS do os_fluxo.py
    assert j["cadeia"][0]["data"] == "01/09/2026" and j["cadeia"][1]["data"] == "11/09/2026"  # event_date, ou a criação; Brasília
    assert j["cadeia"][0]["href"] == "/os/os/400?status=Conclu%C3%ADda"
    assert j["vazio"] is False
    monkeypatch.setattr(api, "fluxo_da_os", lambda *a: {**fx, "cadeia": fx["cadeia"][1:]})
    assert cli.get("/os/api/os/501/fluxo").get_json()["vazio"] is True             # "Esta OS não tem outra ligada a ela"


def test_anexos_lista_separa_imagens_documentos_e_notas_e_deduplica_como_o_card(cli, monkeypatch):
    subs = [{"url": "https://s3/a.jpg?X-Amz=1", "thumb": None, "descricao": "Foto da string  ·  a.jpg", "nome": "a.jpg", "value": ".ot/x/a.jpg",
             "subtarefa": "Foto da string", "is_image": True, "is_text": False},
            {"url": "https://s3/laudo.pdf?X-Amz=1", "thumb": None, "descricao": "Laudo", "nome": "laudo.pdf", "value": ".ot/x/laudo.pdf",
             "subtarefa": "Laudo", "is_image": False, "is_text": False},
            {"url": None, "thumb": None, "descricao": "Medição  ·  612 V no barramento", "nome": "612 V no barramento", "value": "",
             "subtarefa": "Medição", "is_image": False, "is_text": True}]
    oss = [{"value": ".ot/x/a.jpg", "nome": "a.jpg", "user": "Levi Maia", "url": "https://s3/a.jpg?X-Amz=2", "is_image": True, "is_text": False, "desc": ""},
           {"value": ".ot/y/print.png", "nome": "print.png", "user": "Levi Maia", "url": "https://s3/print.png", "is_image": True, "is_text": False, "desc": "print"},
           {"value": ".ot/y/relatorio.zip", "nome": "relatorio.zip", "user": "Ana", "url": "https://s3/relatorio.zip", "is_image": False, "is_text": False, "desc": ""},
           {"value": "", "nome": "observação do PCM", "user": "Ana", "url": None, "is_image": False, "is_text": True, "desc": "observação do PCM"}]
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: subs)
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: oss)
    j = cli.get("/os/api/os/501/anexos-lista").get_json()
    sub, os_ = j["sub"], j["os"]
    assert [x["tipo"] for x in sub["itens"]] == ["imagem", "documento", "nota"] and sub["n"] == 3
    assert sub["itens"][0]["legenda"] == "Foto da string  ·  a.jpg" and sub["itens"][0]["url"].startswith("https://s3/a.jpg")
    assert sub["itens"][0]["baixar"] == "/os/api/os/501/anexo?value=.ot%2Fx%2Fa.jpg&nome=a.jpg"    # renova a URL ao clicar
    assert sub["itens"][1]["ext"] == "PDF" and sub["itens"][1]["quem"] == "Laudo"
    assert sub["itens"][2]["texto"] == "Medição  ·  612 V no barramento"
    # da OS sai o a.jpg (já é anexo de subtarefa) — a mesma régua do `_recount`/os_anexos_contagem
    assert [x["nome"] for x in os_["itens"]] == ["print.png", "relatorio.zip", "observação do PCM"] and os_["n"] == 3
    assert os_["itens"][0]["legenda"] == "print.png  ·  Levi Maia" and os_["itens"][1]["ext"] == "ZIP" and os_["itens"][1]["quem"] == "Ana"
    assert os_["itens"][2]["tipo"] == "nota" and os_["itens"][2]["texto"] == "observação do PCM"
    assert j["n"] == {"sub": 3, "os": 3}


def test_baixar_anexo_renova_a_url_no_fracttal_e_devolve_os_bytes(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "s3_get_url", lambda name: visto.update(name=name) or "https://s3/novo?X-Amz=3")
    monkeypatch.setattr(api, "baixar_imagem", lambda url: visto.update(url=url) or b"%PDF-1.4 conteudo")
    r = cli.get("/os/api/os/501/anexo?value=.ot%2Fx%2Flaudo.pdf&nome=laudo%20final.pdf")
    assert r.status_code == 200 and r.data == b"%PDF-1.4 conteudo"
    assert visto == {"name": ".ot/x/laudo.pdf", "url": "https://s3/novo?X-Amz=3"}      # documentos.py: a URL pré-assinada EXPIRA; reabrir renova
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert 'filename="laudo final.pdf"' in r.headers["Content-Disposition"] and "attachment" in r.headers["Content-Disposition"]
    assert cli.get("/os/api/os/501/anexo").status_code == 400
    monkeypatch.setattr(api, "s3_get_url", lambda name: None)
    r = cli.get("/os/api/os/501/anexo?value=.ot%2Fx%2Fsumiu.pdf")
    assert r.status_code == 404 and "renovar" in r.get_json()["erro"]


def test_sem_sessao_a_api_devolve_401_json():
    app = criar_app(segredo="teste", testing=True)
    r = app.test_client().post("/os/api/os/501/cancelar", json={"id_status_custom": 7})
    assert r.status_code == 401 and r.get_json()["login"] is True


# ── regras puras (os_acoes_web) ────────────────────────────────────────────────────────────────────────
def test_regra_da_nota_e_a_do_card_do_app():
    assert os_acoes_web.nota_pode_editar(1, 1) == (True, "Editar a observação desta OS")
    assert os_acoes_web.nota_pode_editar(2, 1)[0]                                   # Em Verificação ainda aceita
    assert os_acoes_web.nota_pode_editar(3, 1) == (False, "OS concluída — o Fracttal não aceita mais editar a observação.")
    assert os_acoes_web.nota_pode_editar(4, 1)[1].startswith("OS cancelada")
    assert "3 tarefas" in os_acoes_web.nota_pode_editar(1, 3)[1] and "Fracttal" in os_acoes_web.nota_pode_editar(1, 3)[1]
    assert os_acoes_web.status_id_de("Concluída", {}) == 3 and os_acoes_web.status_id_de("", {"cancel_nota": "x"}) == 4
    assert os_acoes_web.status_id_de("", {}) is None


def _sem_comentario(linha: str) -> str:
    """A linha sem o comentário `//` do fim. O `://` de uma URL não conta como começo de comentário."""
    i = 0
    while True:
        i = linha.find("//", i)
        if i < 0:
            return linha
        if i == 0 or linha[i - 1] != ":":
            return linha[:i]
        i += 2


def test_js_e_css_trazem_as_confirmacoes_e_avisos_do_app():
    js = open(os.path.join(_STATIC, "os_acoes.js"), encoding="utf-8").read()
    # "carregando o fluxo…" saiu DESTA lista porque migrou para o template: o diálogo é montado
    # pelo servidor, então o aviso já nasce na tela, sem depender do JS chegar. A frase continua
    # exigida — logo abaixo, no arquivo em que ela passou a viver (21/09).
    for txt in ("Confirma o cancelamento da OS", "Isto muda o status dela no Fracttal.", "gravando no Fracttal…", "cancelando no Fracttal…",
                "Esta OS não tem outra ligada a ela — nem como pai, nem como filha.", "escolha a pessoa.",
                "Marque ao menos uma etiqueta (ou Cancelar).", "Escolha o motivo do cancelamento.", "salvando…", "concluindo…",
                "Sem anexos nas subtarefas.", "Sem anexos nesta OS.", "arquivo(s)", "nota(s) de texto", "parcial=1"):
        assert txt in js, txt
    # SÓ NO CÓDIGO: o arquivo tem um comentário que CITA `alert()` para explicar a regra, e a
    # busca crua acusava o próprio comentário. Erro vai para a .os-resultado, nunca em alert().
    for linha in js.splitlines():
        assert "alert(" not in _sem_comentario(linha), linha.strip()[:70]
    tpl = open(os.path.join(os.path.dirname(_STATIC), "templates", "os_detalhe_conteudo.html"),
               encoding="utf-8").read()
    assert "carregando o fluxo…" in tpl, "o aviso de carregamento do fluxo sumiu da tela"
    css = open(os.path.join(_STATIC, "os_acoes.css"), encoding="utf-8").read()
    assert ".acoes-fundo" in css and "z-index:80" in css                             # o diálogo fica ACIMA do card do Histórico (z 60)
