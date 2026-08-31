"""Escrita na Gridco Performance API — a trava de aba e o conflito de edição.

Nenhum teste aqui toca a rede: `gravar_linha`/`criar_linha` aceitam um `enviar` injetável e
`ler_linha` um `buscar`. É de propósito — teste de escrita que bate na API de verdade acabaria
gravando lixo numa planilha real no dia em que alguém rodasse a suíte distraído.
"""
import pytest

import tickets_escrita as esc

CABECALHO = ["Usina", "Nº do SKID", "Causa raiz", "Fim da ocorrência", "Nº OS"]
LIBERADA = 374                      # a aba de teste
PRODUCAO = 123                      # Trackers de verdade — ainda alimentada pelo pipeline


def _enviar_falso(registro):
    def enviar(metodo, sheet_id, row_number, corpo):
        registro.append((metodo, sheet_id, row_number, corpo))
        return {"row_number": row_number or 1}
    return enviar


# ── a trava ────────────────────────────────────────────────────────────────────────────────
def test_recusa_gravar_em_aba_de_producao():
    # enquanto o pipeline subir o .xlsx com replace=true, gravar na aba real é perder o dado no
    # sync seguinte, em silêncio. A trava é de código para não depender de ninguém lembrar.
    with pytest.raises(esc.EscritaBloqueada):
        esc.gravar_linha(PRODUCAO, 5, {"Usina": "TIM200"}, CABECALHO, enviar=lambda *a: None)


def test_recusa_criar_em_aba_de_producao():
    with pytest.raises(esc.EscritaBloqueada):
        esc.criar_linha(PRODUCAO, {"Usina": "TIM200"}, CABECALHO, enviar=lambda *a: None)


def test_aceita_a_aba_liberada():
    reg = []
    esc.criar_linha(LIBERADA, {"Usina": "TIM200"}, CABECALHO, enviar=_enviar_falso(reg))
    assert reg and reg[0][1] == LIBERADA


# ── montagem do corpo ──────────────────────────────────────────────────────────────────────
def test_valores_saem_na_ordem_do_cabecalho():
    v = esc.para_valores({"Causa raiz": "Tracker sem TCU", "Usina": "TIM200"}, CABECALHO)
    assert v == ["TIM200", "", "Tracker sem TCU", "", ""]


def test_none_vira_vazio_nao_o_texto_none():
    # None chega no banco como a palavra 'None' em alguns caminhos, e célula com o texto "None"
    # é pior que célula vazia: parece dado.
    v = esc.para_valores({"Usina": None, "Nº OS": None}, CABECALHO)
    assert v[0] == "" and v[4] == ""


def test_coluna_desconhecida_e_ignorada():
    v = esc.para_valores({"Coluna Que Nao Existe": "x", "Usina": "TIM200"}, CABECALHO)
    assert v == ["TIM200", "", "", "", ""]


# ── conflito de edição ─────────────────────────────────────────────────────────────────────
def test_grava_quando_ninguem_mexeu():
    reg = []
    base = {"Causa raiz": "", "Fim da ocorrência": ""}
    esc.gravar_linha(LIBERADA, 7, {"Usina": "TIM200", "Causa raiz": "Tracker sem TCU"},
                     CABECALHO, base=base, enviar=_enviar_falso(reg),
                     ler=lambda sid, rn: {"Causa raiz": "", "Fim da ocorrência": ""})
    assert reg[0][0] == "PUT" and reg[0][2] == 7


def test_recusa_quando_a_linha_mudou_no_banco():
    # o outro analista preencheu a causa raiz enquanto esta tela estava aberta. Gravar por cima
    # apagaria o trabalho dele sem ninguém perceber.
    with pytest.raises(esc.ConflitoDeEdicao) as e:
        esc.gravar_linha(LIBERADA, 7, {"Causa raiz": "Tracker sem TCU"}, CABECALHO,
                         base={"Causa raiz": ""}, enviar=lambda *a: None,
                         ler=lambda sid, rn: {"Causa raiz": "Falha no motor"})
    assert "Causa raiz" in e.value.campos
    assert e.value.campos["Causa raiz"] == ("", "Falha no motor")


def test_espaco_em_volta_nao_conta_como_mudanca():
    # célula de planilha vem com espaço invisível o tempo todo; tratar isso como edição de
    # outra pessoa faria a tela recusar salvar sem motivo.
    reg = []
    esc.gravar_linha(LIBERADA, 7, {"Causa raiz": "Tracker sem TCU"}, CABECALHO,
                     base={"Causa raiz": "Tracker sem TCU"}, enviar=_enviar_falso(reg),
                     ler=lambda sid, rn: {"Causa raiz": "  Tracker sem TCU  "})
    assert reg, "deveria ter gravado: só mudou espaço em volta"


def test_sem_base_nao_confere_nada():
    # criação de linha nova e gravação forçada não têm com o que comparar
    reg = []
    esc.gravar_linha(LIBERADA, 7, {"Usina": "TIM200"}, CABECALHO, enviar=_enviar_falso(reg))
    assert reg
