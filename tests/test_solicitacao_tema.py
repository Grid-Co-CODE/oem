"""A tela de solicitação com tema: o que a escolha do tema faz, e o que ela NÃO pode desfazer.

O caso que motiva o teste mais importante daqui: o supervisor escreve o título dele e depois
troca o tema. Se a tela regenerasse o título nessa hora, ela apagaria o trabalho dele sem avisar
— o pior tipo de automação. `_titulo_auto` existe só para isso, e é fácil de quebrar num refactor
porque nada na tela dá erro quando ele para de funcionar.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import solic_spec as sp
from steps.solicitacao import SolicitacaoTab


def _tela(qapp):
    return SolicitacaoTab()


def _idx_do_tema(t, chave):
    return next(i for i in range(t.cb_tema.count()) if t.cb_tema.itemData(i) == chave)


def test_o_combo_traz_sem_tema_mais_todos_os_temas(qapp):
    t = _tela(qapp)
    assert t.cb_tema.itemData(0) == ""           # "— sem tema —" primeiro
    assert t.cb_tema.count() == len(sp.TEMAS) + 1


def test_escolher_o_tema_preenche_o_titulo(qapp):
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "vegetacao"))
    assert t.desc.toPlainText().strip() == "Roçagem e supressão vegetal"


def test_titulo_escrito_a_mao_NAO_e_sobrescrito(qapp):
    """O teste que mais importa. Trocar o tema depois de digitar não pode apagar o texto."""
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "vegetacao"))
    t.desc.setPlainText("Roçada urgente no acesso da subestação")     # o supervisor digitou
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "nobreak"))             # e trocou o tema
    assert t.desc.toPlainText().strip() == "Roçada urgente no acesso da subestação"


def test_titulo_automatico_e_substituido_ao_trocar_de_tema(qapp):
    # O outro lado da mesma regra: enquanto o título é o que a tela gerou, ele acompanha o tema.
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "vegetacao"))
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "nobreak"))
    assert t.desc.toPlainText().strip() == "Inspeção de nobreak"


def test_limpar_volta_a_aceitar_titulo_automatico(qapp):
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "vegetacao"))
    t.desc.setPlainText("meu texto")
    t.reset()
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "nobreak"))
    assert t.desc.toPlainText().strip() == "Inspeção de nobreak"


def test_a_previa_mostra_todas_as_subtarefas_do_tema(qapp):
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "nobreak"))
    html = t.lbl_subs.text()
    esperado = sp.subtarefas("nobreak")
    assert ("<b>%d subtarefas</b>" % len(esperado)) in html
    for s in esperado:
        assert s["description"] in html, s["description"]


def test_a_previa_marca_o_anexo_obrigatorio(qapp):
    # É o que separa checklist de formulário decorativo — precisa estar visível ANTES de enviar.
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(_idx_do_tema(t, "vegetacao"))
    assert "anexo obrigatório" in t.lbl_subs.text()


def test_sem_tema_a_previa_explica_o_que_acontece(qapp):
    """Nove dos catorze temas ainda não têm checklist. A tela não pode ficar muda nesse caso —
    o supervisor precisa saber que a OS vai nascer só com a base, e mesmo assim poder enviar."""
    t = _tela(qapp)
    t.cb_tema.setCurrentIndex(0)
    txt = t.lbl_subs.text()
    assert "Sem tema" in txt and "base" in txt


def test_a_tela_tem_os_campos_da_sugestao_para_o_PCM(qapp):
    t = _tela(qapp)
    assert t.cb_tecnico is not None and t.data_prev is not None
    # data pretendida nasce à frente da de hoje: sugerir o passado não faz sentido
    assert t.data_prev.dateTime() > t.data.dateTime()
