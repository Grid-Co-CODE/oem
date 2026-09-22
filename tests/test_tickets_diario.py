"""O diário de edições — a cópia que o sync não alcança.

Nenhum teste bate na rede: `garantir_aba`, `registrar` e `ler` aceitam injeção. O que está sendo
provado aqui é a REGRA de aplicar por cima, que é onde mora o risco: aplicar na linha errada
seria corrigir a ocorrência do vizinho em silêncio.
"""
import datetime

import pytest

import tickets_diario as di


def _limpa_estado():
    """garantir_aba guarda o id resolvido e o registra na trava de escrita; sem limpar, um
    teste enxergaria a aba que o anterior criou."""
    import tickets_escrita as esc
    for sid in list(esc.SHEETS_LIBERADAS):
        if esc.SHEETS_LIBERADAS[sid].endswith(di.NOME_ABA):
            esc.SHEETS_LIBERADAS.pop(sid)
    di._SHEET_ID.clear()


def _oc(row, usina, skid, trk, **campos):
    d = {"_row": row, "Usina": usina, "Nº do SKID": skid, "Nº do tracker / Identificação": trk}
    d.update(campos)
    return d


def _reg(linha, imp, quando="2026-08-31 10:00:00", aba="Trackers", **campos):
    d = {"linha": linha, "impressao": imp, "quando": quando, "aba": aba, "quem": "levi"}
    for c in di.CAMPOS:
        d.setdefault(c, "")
    d.update(campos)
    return d


# ── impressão ──────────────────────────────────────────────────────────────────────────────
def test_impressao_ignora_caixa_e_espaco():
    # célula de planilha vem com espaço invisível o tempo todo; se isso mudasse a impressão, o
    # diário deixaria de reconhecer a própria linha que acabou de gravar.
    a = di.impressao("Trackers", _oc(9, "TIM100", "02", "129"))
    b = di.impressao("Trackers", _oc(9, "  tim100 ", " 02", "129  "))
    assert a == b


def test_impressao_nao_usa_data():
    # as duas datas são EDITÁVEIS na tela: se entrassem na impressão, corrigir o Início faria o
    # registro deixar de casar com a própria ocorrência que o gerou.
    x = _oc(9, "TIM100", "02", "129", **{"Início da ocorrência": "01/06/2025"})
    y = _oc(9, "TIM100", "02", "129", **{"Início da ocorrência": "15/07/2025"})
    assert di.impressao("Trackers", x) == di.impressao("Trackers", y)


def test_impressao_de_strings_usa_o_inversor():
    a = di.impressao("Strings", {"Usina": "MAB100", "Inversor": "INV-03"})
    b = di.impressao("Strings", {"Usina": "MAB100", "Inversor": "INV-04"})
    assert a != b


# ── aplicar ────────────────────────────────────────────────────────────────────────────────
def test_repoe_o_campo_que_o_sync_desfez():
    oc = _oc(9, "TIM100", "02", "129", **{"Causa raiz": ""})
    imp = di.impressao("Trackers", oc)
    placar = di.aplicar("Trackers", [oc], [_reg(9, imp, **{"Causa raiz": "NCU com problema"})])
    assert oc["Causa raiz"] == "NCU com problema"
    assert oc["_restaurado"] == ["Causa raiz"]
    assert placar == {"aplicados": 1, "campos": 1, "orfaos": 0}


def test_nao_marca_restaurado_quando_o_banco_ja_concorda():
    # o caso comum: o sync ainda não passou, o banco já tem o valor. Marcar "restaurado" aqui
    # encheria a tela de aviso para quem acabou de salvar.
    oc = _oc(9, "TIM100", "02", "129", **{"Causa raiz": "NCU com problema"})
    imp = di.impressao("Trackers", oc)
    placar = di.aplicar("Trackers", [oc], [_reg(9, imp, **{"Causa raiz": "NCU com problema"})])
    assert "_restaurado" not in oc
    assert placar["aplicados"] == 0


def test_ignora_registro_quando_a_linha_virou_outra_ocorrencia():
    # ALGUÉM APAGOU UMA LINHA NO EXCEL e tudo desceu: a linha 9 agora é de outra usina. Aplicar
    # ali escreveria a causa raiz de um tracker na ocorrência de outro, sem ninguém ver.
    oc = _oc(9, "MAB100", "01", "77", **{"Causa raiz": ""})
    velha = di.impressao("Trackers", _oc(9, "TIM100", "02", "129"))
    placar = di.aplicar("Trackers", [oc], [_reg(9, velha, **{"Causa raiz": "NCU com problema"})])
    assert oc["Causa raiz"] == ""
    assert placar["orfaos"] == 1


def test_registro_de_linha_que_sumiu_conta_como_orfao():
    placar = di.aplicar("Trackers", [], [_reg(9, "x|y", **{"Causa raiz": "algo"})])
    assert placar == {"aplicados": 0, "campos": 0, "orfaos": 1}


def test_vence_o_registro_mais_novo():
    oc = _oc(9, "TIM100", "02", "129", **{"Causa raiz": ""})
    imp = di.impressao("Trackers", oc)
    di.aplicar("Trackers", [oc], [
        _reg(9, imp, quando="2026-08-31 09:00:00", **{"Causa raiz": "antigo"}),
        _reg(9, imp, quando="2026-08-31 18:00:00", **{"Causa raiz": "novo"}),
    ])
    assert oc["Causa raiz"] == "novo"


def test_nao_mistura_as_duas_abas():
    # 'linha 9' existe nas duas abas e são ocorrências diferentes.
    oc = _oc(9, "TIM100", "02", "129", **{"Causa raiz": ""})
    imp = di.impressao("Trackers", oc)
    placar = di.aplicar("Trackers", [oc],
                        [_reg(9, imp, aba="Strings", **{"Causa raiz": "de outra aba"})])
    assert oc["Causa raiz"] == ""
    assert placar["aplicados"] == 0


def test_aplica_varios_campos_de_uma_vez():
    oc = _oc(9, "TIM100", "02", "129",
             **{"Causa raiz": "", "Fim da ocorrência": "", "Comentários gerais": ""})
    imp = di.impressao("Trackers", oc)
    placar = di.aplicar("Trackers", [oc], [_reg(9, imp, **{
        "Causa raiz": "NCU", "Fim da ocorrência": "20/08/2026 14:00",
        "Comentários gerais": "trocado"})])
    assert placar["campos"] == 3
    assert sorted(oc["_restaurado"]) == ["Causa raiz", "Comentários gerais", "Fim da ocorrência"]


def test_vazio_no_registro_NAO_apaga_o_que_o_banco_tem():
    """O registro do ticket que nasce com a OS (`tickets_nasce`) traz só OS, Status do ticket e
    Início do chamado — "" no resto. Até 22/09 esse "" era aplicado como valor: medido naquele dia,
    21 ocorrências perdiam na tela o Início, o comentário e até o Fim (10 de Strings, encerradas,
    voltavam a parecer abertas). O banco estava intacto; o Salvar seguinte é que gravaria o vazio."""
    oc = _oc(3179, "CLN100", "01", "12", **{
        "Início da ocorrência": "2026-09-15 08:00:00", "Fim da ocorrência": "2026-09-20 10:00:00",
        "Comentários gerais": "PV3 e PV4 com corrente nula em 15/09", "Causa raiz": "fusível"})
    imp = di.impressao("Trackers", oc)
    placar = di.aplicar("Trackers", [oc], [_reg(3179, imp, **{
        "OS": "13637", "Status do ticket": "OS Programada",
        "Início do chamado pela Grid Co.": "2026-09-15 12:46:01"})])
    assert oc["Início da ocorrência"] == "2026-09-15 08:00:00"
    assert oc["Fim da ocorrência"] == "2026-09-20 10:00:00"
    assert oc["Comentários gerais"] == "PV3 e PV4 com corrente nula em 15/09"
    assert oc["Causa raiz"] == "fusível"
    assert oc["OS"] == "13637" and oc["Status do ticket"] == "OS Programada"
    # só o Início do chamado é "restaurado" (é coluna da planilha); OS e Status moram só no diário
    assert oc["_restaurado"] == ["Início do chamado pela Grid Co."]
    assert placar == {"aplicados": 1, "campos": 1, "orfaos": 0}


def test_sem_registro_nenhum_nao_toca_em_nada():
    oc = _oc(9, "TIM100", "02", "129", **{"Causa raiz": "do banco"})
    assert di.aplicar("Trackers", [oc], []) == {"aplicados": 0, "campos": 0, "orfaos": 0}
    assert oc["Causa raiz"] == "do banco"


# ── criação da aba e registro ──────────────────────────────────────────────────────────────
def test_reaproveita_a_aba_existente_em_vez_de_criar_outra():
    _limpa_estado()
    chamou = []
    sid = di.garantir_aba(listar=lambda: [{"id": 401, "workbook_key": di.WORKBOOK,
                                           "sheet_name": di.NOME_ABA}],
                          criar=lambda c: chamou.append(c) or {"id": 999})
    assert sid == 401 and not chamou


def test_cria_a_aba_com_as_colunas_certas_quando_nao_existe():
    _limpa_estado()
    corpos = []
    sid = di.garantir_aba(listar=lambda: [],
                          criar=lambda c: corpos.append(c) or {"id": 402})
    assert sid == 402
    assert corpos[0]["sheet_name"] == di.NOME_ABA
    assert corpos[0]["headers"][:5] == ["quando", "quem", "aba", "linha", "impressao"]
    for c in di.CAMPOS:
        assert c in corpos[0]["headers"]


def test_nao_confunde_aba_de_mesmo_nome_em_outro_workbook():
    _limpa_estado()
    corpos = []
    di.garantir_aba(listar=lambda: [{"id": 77, "workbook_key": "bd_thopen",
                                     "sheet_name": di.NOME_ABA}],
                    criar=lambda c: corpos.append(c) or {"id": 403})
    assert corpos, "devia ter criado a aba no workbook certo"


def test_registrar_manda_quando_quem_e_impressao():
    enviados = []
    _limpa_estado()
    di.garantir_aba(listar=lambda: [{"id": 401, "workbook_key": di.WORKBOOK,
                                    "sheet_name": di.NOME_ABA}])
    oc = _oc(9, "TIM100", "02", "129")
    di.registrar("Trackers", oc, {"Causa raiz": "NCU"}, sheet_id=401,
                 agora=datetime.datetime(2026, 8, 31, 14, 30, 0),
                 enviar=lambda m, s, r, corpo: enviados.append((m, s, corpo)) or {"row_number": 2})
    metodo, sid, corpo = enviados[0]
    assert metodo == "POST" and sid == 401
    d = dict(zip(corpo["headers"], corpo["values"]))
    assert d["quando"] == "2026-08-31 14:30:00"
    assert d["linha"] == 9 and d["aba"] == "Trackers"
    assert d["impressao"] == di.impressao("Trackers", oc)
    assert d["Causa raiz"] == "NCU"


def test_registrar_grava_vazio_para_campo_apagado():
    # apagar a causa raiz é uma edição como outra qualquer, e o registro guarda o que foi salvo,
    # vazio inclusive — é o histórico de quem mudou o quê. Na LEITURA, desde 22/09, o vazio não é
    # reimposto (ver test_vazio_no_registro_NAO_apaga_o_que_o_banco_tem): o PUT já apagou a coluna.
    enviados = []
    _limpa_estado()
    di.garantir_aba(listar=lambda: [{"id": 401, "workbook_key": di.WORKBOOK,
                                    "sheet_name": di.NOME_ABA}])
    di.registrar("Trackers", _oc(9, "TIM100", "02", "129"),
                 {"Causa raiz": "", "Fim da ocorrência": "20/08/2026"}, sheet_id=401,
                 enviar=lambda m, s, r, c: enviados.append(c) or {"row_number": 3})
    d = dict(zip(enviados[0]["headers"], enviados[0]["values"]))
    assert d["Causa raiz"] == ""
    assert d["Fim da ocorrência"] == "20/08/2026"
