# -*- coding: utf-8 -*-
"""Tipo de tarefa e Classificação 1 e 2 DA OS, na Fila do PCM (16/09).

São DUAS listas diferentes com o mesmo nome no Fracttal, e a confusão custou uma rodada:
`requests.types_1_list` classifica a SOLICITAÇÃO — é onde vive "Não Para o Ativo", que o tema
sugere — e `tasks.tasks_types_list` classifica a OS, com "Programada" / "Não Programada". Estes
campos são os DA OS: o padrão é "Programada" (é o que o PCM está fazendo ao aprovar) e a
Classificação 2 é a disciplina, que o tema traz no campo `tipo`.

O par "Programada / Elétrica" é o mesmo que o app já grava nas OS de análise e de ETM — conferido
por Levi nas OS 10445/10444/10383 e 10478."""
import pytest

import solic_spec as sp

TEMA = "nobreak"                       # tema cujo `tipo` (disciplina) é "Elétrica"
TIPOS = ["Corretiva", "Preventiva", "Religamento Remoto"]
C1 = ["Programada", "Não Programada"]                  # catálogo da OS, não o da solicitação
C2 = ["Elétrica", "Mecânica", "Civil"]


def _listas():
    return {"tipos": [{"description": d, "id": i} for i, d in enumerate(TIPOS, 1)],
            "c1": [{"description": d, "id": i} for i, d in enumerate(C1, 1)],
            "c2": [{"description": d, "id": i} for i, d in enumerate(C2, 1)]}


def _solicitacao(tema=TEMA, code=3620):
    return {"id_code": code, "usina": "Santa Maria do Pará 1", "ativo": "Inversor 5.2",
            "criado_por": "Laura Aguiar", "data": "2026-09-12 10:00:00", "status": "Pendente",
            "cor_status": "#01C0DD", "descricao_full": "Ventoinhas inoperantes",
            "observacao": "relato\n\n" + sp.bloco({"tema": tema})}


@pytest.fixture
def fila(qapp):
    from steps.solic_pcm import _Fila
    f = _Fila(lambda: None)
    f.set_tipos_classif(_listas())
    f.resize(1600, 950)
    f.show()
    qapp.processEvents()
    f.set_itens([_solicitacao()], [])
    qapp.processEvents()
    return f


def test_a_os_nasce_programada(fila):
    """Aprovar É programar: a OS sai do PCM com data marcada."""
    assert fila.cb_c1.currentText() == "Programada"
    assert fila.classificacoes()[0] == "Programada"


def test_a_disciplina_do_tema_vai_para_a_classificacao_2(fila):
    """O campo `tipo` do tema é disciplina ("Elétrica", "Limpeza e Conservação") — Classificação
    2 da OS. Não confundir com Tipo de tarefa (Corretiva/Preventiva/Religamento)."""
    assert sp.classificacao(TEMA)["tipo"] == "Elétrica", "o corpo de teste mudou de tema"
    assert fila.classificacoes()[1] == "Elétrica"


def test_a_classificacao_da_solicitacao_nao_entra_na_da_os(fila):
    """O erro que isto fecha: "Não Para o Ativo" classifica a SOLICITAÇÃO e estava sendo posto
    no campo da OS. As duas listas têm o mesmo nome e catálogos diferentes."""
    da_solicitacao = sp.classificacao(TEMA)["classif1"]
    assert da_solicitacao, "o corpo de teste precisa de um tema que classifique a solicitação"
    assert fila.cb_c1.currentText() != da_solicitacao


def test_a_sugestao_nao_atropela_a_escolha_de_quem_aprova(fila):
    """O PCM conhece o caso; o padrão é só um bom ponto de partida."""
    fila.cb_c1.setCurrentIndex(fila.cb_c1.findText("Não Programada"))
    fila._pintar_subs()                       # roda a cada mexida no tema/subtarefas
    assert fila.cb_c1.currentText() == "Não Programada"


def test_trocar_de_solicitacao_volta_para_o_padrao(fila, qapp):
    """Aprovar avança para a próxima: a classificação escolhida na anterior não pode seguir
    colada na seguinte, como já valia para a OS pai."""
    fila.cb_c1.setCurrentIndex(fila.cb_c1.findText("Não Programada"))
    fila.cb_c2.setCurrentIndex(fila.cb_c2.findText("Civil"))
    fila._selecionar(_solicitacao(code=3621))
    qapp.processEvents()
    assert fila.cb_c1.currentText() == "Programada"
    assert fila.classificacoes()[1] == "Elétrica"


def test_sem_as_listas_carregadas_a_os_nasce_sem_classificacao(qapp):
    """As listas vêm do Fracttal e podem não ter chegado. Vazio é vazio — melhor OS sem
    classificação que com a errada."""
    from steps.solic_pcm import _Fila
    f = _Fila(lambda: None)
    f.set_itens([_solicitacao()], [])
    qapp.processEvents()
    assert f.classificacoes() == ("", "")


def test_a_classificacao_vai_para_a_criacao_da_os(monkeypatch):
    """Ter o campo na tela não basta: o valor precisa chegar ao `clonar_os`, que resolve o id no
    catálogo vivo e monta o payload."""
    import api
    visto = {}
    monkeypatch.setattr(api, "_solicitacao_row", lambda *a, **k: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda *a, **k: None)
    monkeypatch.setattr(api, "clonar_os",
                        lambda tarefas, *a, **k: visto.update(tarefas[0]) or {"ok": True})
    api.aprovar_solicitacao({"id": 1}, "titulo", [], "3620", 7, "Fulano",
                            classif=("Programada", "Elétrica"))
    assert visto.get("classif_1") == "Programada"
    assert visto.get("classif_2") == "Elétrica"


def test_sem_classificacao_a_chamada_continua_valida(monkeypatch):
    """Quem não escolheu nada manda vazio, e o `_classif_ids` simplesmente não acha nome nenhum."""
    import api
    visto = {}
    monkeypatch.setattr(api, "_solicitacao_row", lambda *a, **k: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda *a, **k: None)
    monkeypatch.setattr(api, "clonar_os",
                        lambda tarefas, *a, **k: visto.update(tarefas[0]) or {"ok": True})
    api.aprovar_solicitacao({"id": 1}, "titulo", [], "3620", 7, "Fulano")
    assert visto.get("classif_1") == "" and visto.get("classif_2") == ""


def test_o_tipo_de_tarefa_nasce_no_padrao_de_sempre(fila):
    """O campo existe para quem precisa de Religamento ou Preventiva — não para obrigar uma
    escolha nova. Sem mexer, a OS continua nascendo Corretiva, como sempre nasceu."""
    assert fila.tipo_tarefa() == "Corretiva"


def test_o_tipo_escolhido_vai_para_a_criacao(fila, monkeypatch):
    import api
    visto = {}
    monkeypatch.setattr(api, "_solicitacao_row", lambda *a, **k: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda *a, **k: None)
    monkeypatch.setattr(api, "clonar_os",
                        lambda tarefas, *a, **k: visto.update(tarefas[0]) or {"ok": True})
    fila.cb_tipo.setCurrentIndex(fila.cb_tipo.findText("Religamento Remoto"))
    api.aprovar_solicitacao({"id": 1}, "titulo", [], "3620", 7, "Fulano",
                            tipo=fila.tipo_tarefa())
    assert visto.get("tipo") == "Religamento Remoto"


def test_os_seis_campos_sao_linhas_do_mesmo_estilo(fila):
    """Tipo e as duas classificações entraram como LINHAS, junto de Técnico/Data/Etiquetas —
    seis combos emoldurados ocupavam meio cartão (Levi, 16/09)."""
    for cb in (fila.cb_tipo, fila.cb_c1, fila.cb_c2):
        assert cb.objectName() == "etqInline", "o campo saiu do estilo das linhas de cima"
    y = [w.mapTo(fila, w.rect().topLeft()).y()
         for w in (fila.ed_tecnico, fila.ed_data, fila.etiquetas,
                   fila.cb_tipo, fila.cb_c1, fila.cb_c2)]
    assert y == sorted(y), "a ordem das linhas mudou: %s" % (y,)
    x = {w.mapTo(fila, w.rect().topLeft()).x()
         for w in (fila.ed_tecnico, fila.cb_tipo, fila.cb_c1, fila.cb_c2)}
    assert len(x) == 1, "os valores não estão na mesma coluna: %s" % (x,)
