# tests/test_os_web_tickets_grupos.py
"""Tickets agrupados por usina, com filtro de cliente e drill-down (Levi, 22/09/2026).

"gostaria de um filtro para cliente e usina / ao escolher o cliente os trackers/strings ficam
agrupados por usina e aí eu vou clicando e vai expandindo o drill down. Nesse agrupamento vai ter
a contagem de trackers parados ou strings zeradas."

O que estes testes seguram é o que foi MEDIDO na planilha real em 22/09, e que decidiu o desenho:

· a coluna "Usina" daqui é o código ("TIM100") ou o nome curto ("Barretos"), nunca o
  "Cliente - Usina - UF" do cadastro — o prefixo casa com o cliente em 0 de 1.167 linhas;
· 293 ocorrências não têm Cliente, e só 14 são recuperáveis pela própria planilha. As outras 279
  (19% da aba) vão para um grupo explícito, nunca somem atrás do filtro;
· nenhuma usina aparece com dois clientes diferentes (0 ambíguas em 50), o que torna seguro
  preencher o vazio pelo que a mesma usina diz em outra linha.
"""
import datetime as dt

import pytest

from os_web import tickets_web as tw

AGORA = dt.datetime(2026, 9, 22, 12, 0)


def _oc(row, usina, cliente="", qtd=None, fim="", ini="2026-09-01 08:00", aba="Trackers"):
    d = {"_row": row, "Usina": usina, "Cliente": cliente, "Status": "Parado",
         "Início da ocorrência": ini, "Fim da ocorrência": fim}
    if qtd is not None:
        d[tw.COL_QTD[aba]] = qtd
    return d


def _montar(linhas, aba="Trackers"):
    ocs, _ = tw.montar(linhas, agora=AGORA)
    tw.preencher_cliente(ocs)
    return ocs


# ── a contagem: EQUIPAMENTOS, não linhas ─────────────────────────────────────────────────────
def test_qtd_conta_equipamentos_e_nao_ocorrencias():
    """Uma ocorrência pode valer 6 trackers. O cabeçalho do grupo mostra 6, não 1 — é o número
    que a pessoa veio ver."""
    ocs = _montar([_oc(1, "Tupi", "2C", qtd=6), _oc(2, "Tupi", "2C", qtd=3)])
    g = tw.agrupar(ocs, "Trackers")[0]
    assert g["qtd"] == 9 and g["n"] == 2


def test_quantidade_vazia_vale_UM_e_nao_zero():
    """A ocorrência existe, então há pelo menos um equipamento parado. Zero faria uma usina com a
    coluna em branco parecer saudável — e 109 das 3.180 linhas de Trackers estão em branco."""
    assert tw.qtd_de({}, "Trackers") == 1
    assert tw.qtd_de({tw.COL_QTD["Trackers"]: ""}, "Trackers") == 1
    assert tw.qtd_de({tw.COL_QTD["Trackers"]: "abc"}, "Trackers") == 1
    assert tw.qtd_de({tw.COL_QTD["Trackers"]: 0}, "Trackers") == 1
    assert tw.qtd_de({tw.COL_QTD["Trackers"]: "4"}, "Trackers") == 4
    assert tw.qtd_de({tw.COL_QTD["Trackers"]: "4,0"}, "Trackers") == 4    # planilha manda vírgula


def test_qtd_ignora_as_encerradas():
    """"Parado" é estado de agora. Somar as encerradas diria que uma usina resolvida há seis meses
    ainda tem 40 trackers parados."""
    ocs = _montar([_oc(1, "Tupi", "2C", qtd=5),
                   _oc(2, "Tupi", "2C", qtd=40, fim="2026-03-01 08:00")])
    g = tw.agrupar(ocs, "Trackers")[0]
    assert g["qtd"] == 5 and g["n"] == 2 and g["n_abertas"] == 1


def test_strings_usa_a_coluna_de_strings_afetadas():
    ocs = _montar([_oc(1, "Barretos", "Thopen", qtd=7, aba="Strings")], aba="Strings")
    g = tw.agrupar(ocs, "Strings")[0]
    assert g["qtd"] == 7
    assert tw.ROTULO_QTD["Strings"] == "strings zeradas"


# ── o cliente ────────────────────────────────────────────────────────────────────────────────
def test_cliente_vazio_e_preenchido_pela_MESMA_usina():
    """Seguro porque nenhuma usina aparece com dois clientes (0 ambíguas em 50, medido)."""
    ocs = _montar([_oc(1, "TIM100", "Athon"), _oc(2, "TIM100", "")])
    assert [o["_cliente"] for o in ocs] == ["Athon", "Athon"]


def test_usina_sem_cliente_em_lugar_nenhum_vira_grupo_explicito():
    """279 ocorrências (19% da aba) estão nessa situação — Barretos, PRM100, PRM200. Um filtro que
    simplesmente não as mostrasse faria 19% do passivo sumir da tela."""
    ocs = _montar([_oc(1, "Barretos", ""), _oc(2, "Barretos", "")])
    assert all(o["_cliente"] == tw.SEM_CLIENTE for o in ocs)
    assert tw.clientes_de(ocs) == [tw.SEM_CLIENTE]


def test_sem_cliente_vai_por_ULTIMO_no_dropdown():
    ocs = _montar([_oc(1, "TIM100", "Athon"), _oc(2, "Barretos", ""), _oc(3, "X", "2C")])
    assert tw.clientes_de(ocs) == ["2C", "Athon", tw.SEM_CLIENTE]


def test_o_prefixo_da_usina_NAO_e_usado_como_cliente():
    """Medido: o prefixo casa com o cliente em 0 de 1.167 linhas, porque a coluna "Usina" daqui é
    código ou nome curto. Usá-lo daria a impressão de funcionar e erraria."""
    ocs = _montar([_oc(1, "Athon - Timon 1 - MA", "")])
    assert ocs[0]["_cliente"] == tw.SEM_CLIENTE       # e NÃO "Athon"


# ── os filtros ───────────────────────────────────────────────────────────────────────────────
def test_filtro_de_cliente_e_de_usina():
    ocs = _montar([_oc(1, "TIM100", "Athon"), _oc(2, "MAB200", "Athon"), _oc(3, "Tupi", "2C")])
    assert [o["_row"] for o in tw.filtrar(ocs, cliente="Athon")] == [1, 2]
    assert [o["_row"] for o in tw.filtrar(ocs, usina="Tupi")] == [3]
    assert [o["_row"] for o in tw.filtrar(ocs, cliente="Athon", usina="TIM100")] == [1]
    # cliente e usina que não se cruzam devolvem vazio, e não a lista inteira
    assert tw.filtrar(ocs, cliente="2C", usina="TIM100") == []


def test_usinas_do_dropdown_seguem_o_cliente():
    ocs = _montar([_oc(1, "TIM100", "Athon"), _oc(2, "MAB200", "Athon"), _oc(3, "Tupi", "2C")])
    assert tw.usinas_de(ocs, "Athon") == ["MAB200", "TIM100"]
    assert tw.usinas_de(ocs, "2C") == ["Tupi"]
    assert tw.usinas_de(ocs, "") == ["MAB200", "TIM100", "Tupi"]


def test_filtros_se_combinam_com_estado_e_alarme():
    ocs = _montar([_oc(1, "TIM100", "Athon", ini="2026-06-01 08:00"),          # 113 dias
                   _oc(2, "TIM100", "Athon", ini="2026-09-21 08:00"),          # 1 dia
                   _oc(3, "TIM100", "Athon", fim="2026-09-10 08:00")])         # encerrada
    assert [o["_row"] for o in tw.filtrar(ocs, cliente="Athon", so_alarme=True)] == [1]
    assert [o["_row"] for o in tw.filtrar(ocs, cliente="Athon", estado="encerrada")] == [3]


# ── a ordem dos grupos ───────────────────────────────────────────────────────────────────────
def test_grupos_vem_do_pior_para_o_melhor():
    """O drill-down existe para achar onde dói mais; alfabética obrigaria a abrir uma por uma."""
    ocs = _montar([_oc(1, "Aaa", "X", qtd=2), _oc(2, "Zzz", "X", qtd=50), _oc(3, "Mmm", "X", qtd=9)])
    assert [g["usina"] for g in tw.agrupar(ocs, "Trackers")] == ["Zzz", "Mmm", "Aaa"]


def test_empate_de_qtd_desempata_por_abertas_e_depois_por_nome():
    ocs = _montar([_oc(1, "Bbb", "X", qtd=5), _oc(2, "Aaa", "X", qtd=5)])
    assert [g["usina"] for g in tw.agrupar(ocs, "Trackers")] == ["Aaa", "Bbb"]


def test_grupo_leva_o_cliente_e_as_ocorrencias_ordenadas():
    ocs = _montar([_oc(1, "TIM100", "Athon", ini="2026-09-20 08:00"),
                   _oc(2, "TIM100", "Athon", ini="2026-06-01 08:00")])
    g = tw.agrupar(ocs, "Trackers")[0]
    assert g["cliente"] == "Athon"
    assert [o["_row"] for o in g["itens"]] == [2, 1]        # a mais antiga aberta primeiro


def test_usina_vazia_nao_some_do_agrupamento():
    ocs = _montar([_oc(1, "", "Athon")])
    assert tw.agrupar(ocs, "Trackers")[0]["usina"] == "(sem usina)"


# ── as DUAS abas, simetricamente ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("aba, rotulo, coluna", [
    ("Trackers", "trackers parados", "Quantidade de trackers parados"),
    ("Strings", "strings zeradas", "Quantidade de strings no afetadas"),
])
def test_o_agrupamento_vale_para_as_duas_abas(aba, rotulo, coluna):
    """Levi pediu o agrupamento primeiro em Trackers e depois "o mesmo na aba de strings" — e ele
    ja valia, porque `agrupar` recebe a aba em vez de supor uma. Este teste existe para que
    continue assim: fixar "Trackers" em qualquer um dos tres mapas quebra a Strings em silencio,
    e o sintoma seria a aba mostrar "trackers parados" contando a coluna errada."""
    assert tw.COL_QTD[aba] == coluna
    assert tw.ROTULO_QTD[aba] == rotulo
    ocs = _montar([_oc(1, "Usina X", "Cliente Y", qtd=4, aba=aba)], aba=aba)
    g = tw.agrupar(ocs, aba)[0]
    assert g["qtd"] == 4 and g["usina"] == "Usina X" and g["cliente"] == "Cliente Y"


def test_as_duas_abas_tem_conjuntos_de_coluna_DIFERENTES():
    """Trackers tem Cabine e Tracker; Strings tem Inversor. Se o agrupamento tivesse fixado uma
    aba, a outra mostraria coluna vazia."""
    assert "Tracker" in tw.colunas_da_aba("Trackers") and "Inversor" not in tw.colunas_da_aba("Trackers")
    assert "Inversor" in tw.colunas_da_aba("Strings") and "Tracker" not in tw.colunas_da_aba("Strings")


def test_nenhuma_aba_e_fixada_no_codigo_da_tela():
    """A rota e o template tem de passar a aba adiante, nunca escolher uma."""
    import os
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "os_creator", "os_web")
    with open(os.path.join(base, "rotas_tickets.py"), encoding="utf-8") as f:
        rota = f.read()
    assert "tw.agrupar(itens, aba)" in rota
    assert "tw.ROTULO_QTD.get(aba" in rota
    assert 'tw.ROTULO_QTD["Trackers"]' not in rota      # nada de aba fixa
    with open(os.path.join(base, "templates", "tickets.html"), encoding="utf-8") as f:
        h = f.read()
    assert "{{ rotulo_qtd }}" in h and "trackers parados" not in h


# ── a tela ───────────────────────────────────────────────────────────────────────────────────
def test_o_template_esconde_as_linhas_e_abre_por_grupo():
    import os
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "os_creator", "os_web", "templates", "tickets.html")
    with open(p, encoding="utf-8") as f:
        h = f.read()
    import re
    linha = re.search(r'<tr[^>]*class="tk-l tk-f"[^>]*>', h).group(0)
    assert 'data-g="{{ gi }}"' in linha and linha.rstrip(">").endswith("hidden")   # nasce fechada
    assert 'tr.tk-f[data-g="' in h                                 # o clique abre só o grupo dele
    assert "loop.parent" not in h                                  # isso é Django, não Jinja2
    # com UMA usina só, deixar fechada seria um clique à toa
    assert "if (gs.length === 1) alternar(gs[0]);" in h
