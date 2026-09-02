"""Os temas de solicitação e as subtarefas que cada um leva para a OS.

O que estes testes protegem, e por quê: o `solic_spec` decide o que a OS vai PEDIR ao técnico.
Um erro aqui não quebra nada — ele cria a OS com a pergunta errada, o técnico responde o que foi
perguntado, e o dado errado entra no sistema do cliente. É a mesma classe de falha que o
`CLAUDE.md` da área descreve: o grave não é o que quebra, é o que funciona e grava errado.
"""
import pytest

import solic_spec as S


def test_todo_tema_com_metadado_tem_subtarefa_e_vice_versa():
    # Um tema declarado em TEMAS mas sem bloco em POR_TEMA apareceria na tela e criaria OS sem
    # checklist — o problema que este módulo existe para acabar.
    assert set(S.TEMAS) == set(S.POR_TEMA)


def test_os_quatro_temas_medidos_estao_declarados():
    for t in ("vegetacao", "nobreak", "protecao_transformador"):
        assert S.existe(t)
    # Tracker foi QUEBRADO em três: as 13 subtarefas recorrentes eram três procedimentos
    # distintos no mesmo ativo. Juntá-los faria a OS de troca de motor perguntar sobre inject.
    for t in ("tracker_reset_tcu", "tracker_inject", "tracker_motor"):
        assert S.existe(t)


def test_a_base_entra_em_todo_tema():
    for tema in S.POR_TEMA:
        descs = [s["description"] for s in S.subtarefas(tema)]
        assert "Descreva a atividade realizada" in descs, tema
        assert any("Registro fotográfico" in d for d in descs), tema


def test_a_base_vem_no_FIM_nao_no_comeco():
    """Ordem importa: o técnico executa o serviço e só então descreve o que fez.

    No chamado a base abre a lista porque lá se descreve o PROBLEMA; aqui se descreve o que foi
    FEITO. Inverter faria o app pedir o relato antes do trabalho."""
    subs = [s["description"] for s in S.subtarefas("nobreak")]
    assert subs[-3:] == [s["desc"] for s in S.BASE]


def test_nao_ha_subtarefa_repetida_em_tema_nenhum():
    for tema in S.POR_TEMA:
        descs = [s["description"].strip().lower() for s in S.subtarefas(tema)]
        assert len(descs) == len(set(descs)), tema


def test_todo_tema_exige_ao_menos_uma_evidencia_com_anexo():
    # Sem anexo obrigatório a foto vira "depois eu mando" e a OS fecha sem prova — foi o que
    # motivou a mesma regra no chamado de garantia.
    for tema in S.POR_TEMA:
        assert any(s["attachments_required"] for s in S.subtarefas(tema)), tema


def test_tipos_de_campo_sao_os_ids_reais_da_conta():
    # Os ids foram sondados ao vivo na conta 4987. Mandar um id inexistente não dá erro: o Fracttal
    # aceita e a subtarefa nasce como texto, perdendo a validação de número e de sim/não.
    validos = set(S.TIPO_ID.values())
    for tema in S.POR_TEMA:
        for s in S.subtarefas(tema):
            assert s["id_task_form_item_type"] in validos, (tema, s["description"])


def test_lista_sempre_traz_opcoes():
    # tipo "lista" (7) sem `dropdown_options` vira menu vazio na mão do técnico.
    for tema in S.POR_TEMA:
        for s in S.subtarefas(tema):
            if s["id_task_form_item_type"] == S.TIPO_ID["lista"]:
                assert s.get("dropdown_options"), (tema, s["description"])


def test_seguranca_vem_antes_da_medicao_na_protecao():
    """Intervenção em alta tensão: autorização do COS, EPI e LOTO precedem qualquer medição.

    Não é estética de lista — é a ordem em que o técnico tem de agir, e a OS é o que ele segue."""
    descs = [s["description"].lower() for s in S.subtarefas("protecao_transformador")]
    i_cos = next(i for i, d in enumerate(descs) if "cos" in d)
    i_loto = next(i for i, d in enumerate(descs) if "loto" in d)
    i_oleo = next(i for i, d in enumerate(descs) if "óleo" in d)
    assert i_cos < i_loto < i_oleo


def test_vegetacao_mede_antes_e_depois():
    """O que distingue dano preexistente de dano causado pela roçagem — a pergunta que a
    empreiteira faz depois e que hoje ninguém consegue responder."""
    descs = [s["description"].lower() for s in S.subtarefas("vegetacao")]
    assert any("antes do início da supressão" in d for d in descs)
    assert any("após a supressão" in d for d in descs)
    assert any("novos ou agravados" in d for d in descs)


def test_tema_desconhecido_falha_alto():
    # Silenciar aqui criaria OS sem subtarefa nenhuma, que é indistinguível do estado atual.
    with pytest.raises(KeyError):
        S.subtarefas("tema_que_nao_existe")


def test_a_classificacao_sugerida_sai_do_tema():
    c = S.classificacao("vegetacao")
    assert c["classif1"] == "Não Para o Ativo"
    assert c["dominio"] == 77
    # Tracker usa a régua de SEVERIDADE, não a binária — é o retrato da mistura que existe hoje
    # no campo obrigatório, e o motivo de o default vir do tema e não do menu.
    assert S.classificacao("tracker_reset_tcu")["classif1"].startswith("Leve")


def test_titulo_no_padrao_das_OS():
    assert S.titulo("Brodowski", "Tracker 12", "tracker_motor") == \
        "[Brodowski][Tracker 12] - Troca de motor"
    # sem ativo ainda produz título utilizável — não pode devolver "[] - motivo"
    assert S.titulo("Brodowski", "", "tracker_motor") == "[Brodowski] - Troca de motor"


def test_temas_saem_ordenados_por_volume():
    ordem = [k for k, _ in S.temas()]
    assert ordem[0].startswith("tracker"), ordem     # 312 solicitações
    assert ordem[-1] == "nobreak", ordem             # 50, o menor dos quatro


# ── o bloco da sugestão do supervisor ────────────────────────────────────────
def test_o_bloco_carrega_tema_tecnico_e_data():
    b = S.bloco({"tema": "tracker_motor", "tecnico": "João Vieira", "data": "05/09/2026"})
    assert b.startswith(S.MARCADOR)
    assert "Técnico sugerido: João Vieira" in b
    assert "Data pretendida: 05/09/2026" in b


def test_bloco_vazio_nao_polui_a_observacao():
    # Sem sugestão nenhuma, o bloco não deve existir — um "[PCM]" sozinho na observação é ruído
    # que a pessoa lê no Fracttal e não entende.
    assert S.bloco({}) == ""
    assert S.bloco({"tecnico": "  "}) == ""


def test_ida_e_volta_do_bloco():
    d = {"tema": "vegetacao", "tecnico": "Danuth Fernandes", "data": "10/09/2026"}
    assert S.parse(S.bloco(d)) == d


def test_parse_tolera_acento_e_caixa_no_rotulo():
    """Quem edita a observação no Fracttal web digita como quiser. Um acento perdido não pode
    fazer a fila do PCM esquecer o tema da solicitação."""
    t = "[PCM]\nTEMA: nobreak\ntecnico sugerido: Fred\nDATA PRETENDIDA: 09/09/2026"
    assert S.parse(t) == {"tema": "nobreak", "tecnico": "Fred", "data": "09/09/2026"}


def test_parse_sem_bloco_devolve_vazio():
    assert S.parse("Tracker travado desde ontem") == {}
    assert S.parse("") == {}
    assert S.parse(None) == {}


def test_o_relato_do_supervisor_vem_antes_do_bloco():
    # Quem abre a solicitação no Fracttal quer ler o relato, não o metadado.
    obs = S.observacao_com_bloco("Tracker 12 travado desde ontem.",
                                 {"tema": "tracker_motor", "tecnico": "João"})
    assert obs.index("Tracker 12 travado") < obs.index(S.MARCADOR)


def test_reenviar_nao_duplica_o_bloco():
    """Empilhar dois [PCM] faria o parse ficar com o PRIMEIRO — que é o velho. A sugestão
    corrigida pelo supervisor seria silenciosamente ignorada."""
    obs1 = S.observacao_com_bloco("relato", {"tema": "vegetacao", "tecnico": "Ana"})
    obs2 = S.observacao_com_bloco(obs1, {"tema": "nobreak", "tecnico": "Bruno"})
    assert obs2.count(S.MARCADOR) == 1
    assert S.parse(obs2) == {"tema": "nobreak", "tecnico": "Bruno"}
    assert obs2.startswith("relato")


def test_observacao_sem_sugestao_fica_intacta():
    assert S.observacao_com_bloco("só o relato", {}) == "só o relato"


def test_titulo_limpa_o_codigo_e_os_espacos_do_nome_do_ativo():
    """A descrição do ativo vem com o código embutido e espaçamento de largura fixa.

    Achado na solicitação de teste 3534, criada de verdade: o título saiu
    "[Cabine 1][Chave Seccionadora 1      { TESTE100-CHSC1 }] - Inspeção de nobreak".
    Compilar e passar nos testes não tinha pego — só criar a solicitação pegou."""
    t = S.titulo("Cabine 1", "Chave Seccionadora 1      { TESTE100-CHSC1 }", "nobreak")
    assert t == "[Cabine 1][Chave Seccionadora 1] - Inspeção de nobreak"


def test_titulo_sem_usina_nem_ativo_ainda_e_utilizavel():
    assert S.titulo("", "", "nobreak") == "Inspeção de nobreak"
    assert S.titulo("  ", "{ SO-CODIGO }", "nobreak") == "Inspeção de nobreak"
