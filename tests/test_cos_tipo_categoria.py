"""O tipo de OS que cada categoria do COS abre.

O operador do COS reportou em 31/08: escolher "C · Comunicação" abria a OS como **religamento**.
Falha de comunicação não tem religamento nenhum — o técnico vai até lá inspecionar. A tela
sincronizava só no sentido tipo → categoria, então quem mexia na categoria ficava com o tipo no
padrão, que é Religamento.

O teste é do MAPA, não da tela: é a regra de negócio, e é ela que a interface tem de obedecer
nos dois sentidos. A ligação com os controles está provada à parte, dirigindo a tela real.
"""
import cos_spec as cs


def test_comunicacao_abre_inspecao_e_nunca_religamento():
    assert cs.TIPO_DA_CAT[cs.CAT_C] == cs.TIPO_INSPECAO
    assert "Religamento" not in cs.TIPO_DA_CAT[cs.CAT_C]


def test_protecao_e_inversor_abrem_religamento():
    assert cs.TIPO_DA_CAT[cs.CAT_A] == cs.TIPO_RELIGAMENTO
    assert cs.TIPO_DA_CAT[cs.CAT_B] == cs.TIPO_RELIGAMENTO


def test_toda_categoria_tem_tipo():
    # categoria nova sem tipo definido cairia num KeyError dentro de um slot — e slot decorado
    # que levanta exceção deixa o controle MUDO, sem erro na tela.
    assert set(cs.TIPO_DA_CAT) == set(cs.CATEGORIAS)


def test_a_acao_da_comunicacao_tambem_nao_e_religamento():
    # os dois andam juntos: tipo Inspeção com ação "Religamento Local" continuaria dizendo ao
    # técnico para religar.
    assert cs.ACAO_DEFAULT_CAT[cs.CAT_C] == cs.ACAO_INSPECAO
    assert cs.acao_texto(cs.CAT_C, remoto=False) == cs.ACAO_INSPECAO
    assert "Religamento" not in cs.acao_texto(cs.CAT_C, remoto=False)


def test_o_titulo_da_inspecao_nao_fala_em_religar():
    t = cs.motivo_titulo(cs.TIPO_INSPECAO, equipamento="Cabine")
    assert "Religamento" not in t
    assert t.lower().startswith("inspeção e normalização")
