"""As subtarefas que o app acrescenta ao plano de tracker.

Sugestão da equipe (Levi, 31/08): o técnico muitas vezes não comenta, e depois ninguém sabe se o
tracker voltou a operar nem qual era a causa raiz. O plano do Fracttal pergunta se ele ESTÁ
parado, não como a atividade TERMINOU.

O item novo é clonado da FORMA de um item que veio do plano — a estrutura do form item tem 20
campos e montá-la do zero seria adivinhar quais o RPC exige. Os testes abaixo protegem justamente
isso: a forma, a ordem e a não-duplicação.
"""
import api


def _item(desc, tipo=1, ordem=1):
    """Um form item com as MESMAS chaves que o Fracttal devolve (medido no plano 20614611)."""
    return {"id": 72090786 + ordem, "id_company": 4987, "id_task": 20614611,
            "id_task_form_item_type": tipo, "id_unit": None, "description": desc,
            "is_changed": False, "task_form_item_type_description": "TEXT" if tipo == 1 else "BOOLEAN",
            "unit_description": None, "units_code": None,
            "task_form_item_group_description": None, "id_task_form_item_group": None,
            "order_number": ordem, "id_group_task": 350648, "is_configured": True,
            "is_required": True, "task_description": "[Grid Co.] - Verificação de Tracker Parado",
            "iterations": {}, "attachments_required": True, "dropdown_options": None}


def _plano_tracker(subs=None):
    return {"id_task": 20614611, "description": "[Grid Co.] - Verificação de Tracker Parado",
            "subtasks": subs if subs is not None else
            [_item("O tracker encontra-se parado?", 2, 1), _item("Reset realizado?", 2, 2)]}


def test_acrescenta_as_duas_perguntas_no_fim():
    novo = api.com_subtarefas_extra(_plano_tracker())
    descs = [s["description"] for s in novo["subtasks"]]
    assert descs[:2] == ["O tracker encontra-se parado?", "Reset realizado?"]
    assert "O tracker voltou a operar ao final da atividade?" in descs[2:]
    assert any("causa raiz" in d.lower() for d in descs[2:])


def test_o_item_novo_tem_as_mesmas_chaves_do_plano():
    # é isto que impede o RPC de recusar: campo faltando vira erro na criação da OS, não aqui.
    plano = _plano_tracker()
    novo = api.com_subtarefas_extra(plano)
    assert set(novo["subtasks"][-1]) == set(plano["subtasks"][0])


def test_a_pergunta_de_voltar_a_operar_e_sim_nao():
    novo = api.com_subtarefas_extra(_plano_tracker())
    item = next(s for s in novo["subtasks"] if s["description"].startswith("O tracker voltou"))
    assert item["id_task_form_item_type"] == 2
    assert item["task_form_item_type_description"] == "BOOLEAN"


def test_a_causa_raiz_e_texto_livre():
    novo = api.com_subtarefas_extra(_plano_tracker())
    item = next(s for s in novo["subtasks"] if "causa raiz" in s["description"].lower())
    assert item["id_task_form_item_type"] == 1


def test_nenhuma_extra_exige_anexo():
    # as do plano exigem foto; exigir foto para responder "voltou a operar?" travaria o
    # fechamento da OS por um motivo que não é do negócio.
    novo = api.com_subtarefas_extra(_plano_tracker())
    for s in novo["subtasks"][2:]:
        assert s["attachments_required"] is False
        assert s["is_required"] is True          # responder, sim, é obrigatório


def test_ordem_continua_a_do_plano():
    novo = api.com_subtarefas_extra(_plano_tracker())
    assert [s["order_number"] for s in novo["subtasks"]] == [1, 2, 3, 4]


def test_nao_duplica_o_que_o_plano_ja_pergunta():
    # se um dia a pergunta entrar no plano do Fracttal, a OS não pode sair com ela duas vezes.
    plano = _plano_tracker([_item("O tracker encontra-se parado?", 2, 1),
                            _item("O tracker voltou a operar ao final da atividade?", 2, 2)])
    novo = api.com_subtarefas_extra(plano)
    descs = [s["description"] for s in novo["subtasks"]]
    assert descs.count("O tracker voltou a operar ao final da atividade?") == 1
    assert len(novo["subtasks"]) == 3          # só a causa raiz entrou


def test_nao_mexe_em_plano_de_outro_tipo():
    outro = {"id_task": 1, "description": "[Grid Co.] - Inspeção Geral do Inversor",
             "subtasks": [_item("Conferir conexões")]}
    assert api.com_subtarefas_extra(outro) is outro


def test_nao_muta_o_plano_original():
    # o plano fica em CACHE por id_task: mutar somaria as extras de novo a cada OS do lote, e um
    # lote de 30 trackers sairia com 60 perguntas repetidas.
    plano = _plano_tracker()
    antes = len(plano["subtasks"])
    api.com_subtarefas_extra(plano)
    api.com_subtarefas_extra(plano)
    assert len(plano["subtasks"]) == antes


def test_plano_sem_subtarefa_nenhuma_passa_intacto():
    # sem um item para clonar, inventar a estrutura seria adivinhação — melhor não mexer.
    vazio = {"id_task": 2, "description": "[Grid Co.] - Verificação de Tracker Parado",
             "subtasks": []}
    assert api.com_subtarefas_extra(vazio) is vazio


# ── a rede de segurança ────────────────────────────────────────────────────────────────────
def test_desfaz_as_extras_e_devolve_o_plano_original():
    plano = _plano_tracker()
    com = api.com_subtarefas_extra(plano)
    assert api.tem_subtarefas_extra(com) is True
    sem = api.sem_subtarefas_extra(com)
    assert [s["description"] for s in sem["subtasks"]] == [s["description"] for s in plano["subtasks"]]
    assert api.tem_subtarefas_extra(sem) is False


def test_plano_sem_extras_passa_intacto_pelo_desfazer():
    plano = _plano_tracker()
    assert api.sem_subtarefas_extra(plano) is plano
    assert api.tem_subtarefas_extra(plano) is False


def test_o_item_novo_nao_leva_chave_de_controle_para_o_rpc():
    # a marca de "isto foi o app que acrescentou" fica no PLANO, não no item: o que vai para o
    # Fracttal é a lista de subtarefas, e campo desconhecido ali é risco de recusa.
    novo = api.com_subtarefas_extra(_plano_tracker())
    for s in novo["subtasks"]:
        assert not any(k.startswith("_") for k in s)
