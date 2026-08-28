"""As abas de ocorrência do workbook `tickets_performance`, declaradas.

Medido em 28/08: 15 das 23 colunas de Trackers e 15 das 18 de Strings indisp são IDÊNTICAS. Não
são duas coisas — é uma ocorrência com dois conjuntos de extras. Por isso a tela é uma só e a aba
seguinte (Desligamentos, Inv. com baixa performance) entra aqui como declaração, não como tela
nova."""

NUCLEO = [
    "Usina", "Código da usina", "Cliente", "UF", "Supervisor(a)", "Responsável",
    "Causa raiz", "Responsabilidade da Grid Co.?",
    "Início da ocorrência", "Início do chamado pela Grid Co.", "Fim da ocorrência",
    "Indisponibilidade (horas)", "Indisponibilidade da Grid Co. (horas)",
    "Comentários para os clientes", "Comentários gerais",
]

ABAS = {
    "Trackers": {
        "sheet_id": 123,
        "rotulo": "Trackers",
        "extras": ["Fonte", "Equipamento", "Status", "Nº do SKID",
                   "Quantidade de trackers parados", "Nº do tracker / Identificação",
                   "Inversor", "Plano de ação"],
    },
    "Strings": {
        "sheet_id": 128,
        "rotulo": "Strings indisp",
        "extras": ["Inversor", "Quantidade de strings no inversor",
                   "Quantidade de strings no afetadas"],
    },
}

# (chave, rótulo, cor). A ORDEM é o ciclo de vida; a tela desenha nesta ordem.
# `a_fechar` só aparece na fase de leitura: é a OS concluída cujo Fim ainda não foi gravado —
# exatamente o passivo que a fase de escrita vai resolver.
ESTADOS = [
    ("aberta",      "Aberta",         "#e05454"),
    ("com_os",      "OS criada",      "#eb8b57"),
    ("verificando", "Em verificação", "#4a9eff"),
    ("a_fechar",    "A fechar",       "#eb8b57"),
    ("encerrada",   "Encerrada",      "#3fb27f"),
]
COR_ESTADO = {k: c for k, _, c in ESTADOS}
NOME_ESTADO = {k: n for k, n, _ in ESTADOS}


def linha_para_dict(headers, values):
    """Casa o cabeçalho com os valores da linha.

    Duas tolerâncias necessárias: a API devolve listas de valores mais curtas quando as últimas
    células estão vazias, e a planilha tem a coluna A vazia (o cabeçalho começa em B), o que
    produz um nome de coluna em branco que não interessa a ninguém."""
    out = {}
    for i, nome in enumerate(headers or []):
        chave = str(nome or "").strip()
        if not chave:
            continue
        out[chave] = values[i] if i < len(values or []) else None
    return out


def estado_do_ticket(num_os, status_os, fim):
    """Onde a ocorrência está no ciclo de vida. Ver spec §5."""
    if fim not in (None, "", " "):
        return "encerrada"
    if not str(num_os or "").strip():
        return "aberta"
    s = str(status_os or "").strip().lower()
    if "verifica" in s:
        return "verificando"
    if "conclu" in s:
        return "a_fechar"
    return "com_os"
