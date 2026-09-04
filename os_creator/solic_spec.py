"""Temas de solicitação de serviço e as SUBTAREFAS que cada um leva para a OS.

PURO: sem PyQt e sem rede — só dados e strings, como o `cos_spec.py` e o `chamado_garantia/spec.py`.

Para que serve
──────────────
Hoje a solicitação nasce como texto livre e a OS nasce sem checklist. Medido em 02/09/2026 sobre
as **2.500 solicitações** de 05/02 a 02/09 e **414 OS** criadas a partir delas:

  - a descrição é TÍTULO, não relato (mediana de 45 caracteres) e **163 textos se repetem
    literalmente, cobrindo 613 solicitações (24,5%)** — a padronização já acontece, na mão;
  - só 33,2% dos títulos seguem o padrão `[Usina][Ativo] - Motivo` que as OS já usam;
  - nas OS, as duas "subtarefas" mais comuns são `Descreva a atividade realizada` (43%) e
    `Procedimento` (37%): campo em branco com nome, não passo;
  - a **Classificação 1** (obrigatória) mistura três coisas — escala binária Para/Não Para o Ativo
    (39,7%), escala de severidade Grave/Moderado/Leve/Mínimo (51,6%) e valores fora de escala como
    "Elétrica" e "TESTE AUTOMAÇÃO" (8,6%). O campo não é comparável entre solicitações.

Escolher o TEMA resolve os quatro de uma vez: o título sai no padrão, a classificação desce junto,
e a OS nasce com as subtarefas certas — sem depender de ninguém lembrar.

De onde vem cada subtarefa
──────────────────────────
**Não foram inventadas.** Saíram das OS reais, contando só o que aparece em 3 ou mais OS da
amostra e descontando os rótulos genéricos. O percentual em cada bloco é a adoção medida — é ele
que diz o que já era prática e o que ainda não pegou.

Estes quatro temas entram primeiro porque são os únicos com conteúdo real. Os outros nove
(String/CC, Comunicação, Chamado de garantia, Inversor ×2, Módulo FV, ETM, Firmware, Civil) somam
25,8% do volume e têm ZERO subtarefa recorrente: as deles precisam ser ESCRITAS por quem executa,
não inferidas de dado que não existe. Entram aqui um a um, no mesmo formato.

Espelha o `chamado_garantia/spec.py`
────────────────────────────────────
Mesma composição em camadas (base + específico + dedup) e o MESMO formato de saída, para cair no
`api._rpc_subtasks` sem tradução. A diferença é o eixo: lá o específico é a MARCA (o fabricante
cobra o que quer), aqui é o TEMA (o serviço é que manda).
"""

# apelido → id_task_form_item_type do Fracttal. Sondados ao vivo na conta 4987; ver a nota no
# `chamado_garantia/spec.py`. NÃO existe tipo Data nesta conta (o id 3 é Número), então data/hora
# vai como texto, com o formato dentro da própria pergunta.
TIPO_ID = {
    "texto":  1,
    "longo":  1,    # a conta não tem texto longo separado
    "num":    3,
    "simnao": 2,    # Sim / Não / N/A
    "verif":  4,    # Aprovado / Alerta / Falhou
    "lista":  7,    # precisa de `opcoes`
}


def _s(desc, tipo="texto", obrig=True, anexo=False, opcoes=None):
    """Uma subtarefa. `anexo=True` EXIGE arquivo.

    O anexo obrigatório é o que separa checklist de formulário decorativo: sem ele a evidência
    fotográfica vira "depois eu mando", e a OS fecha sem prova. É a mesma regra do chamado."""
    return {"desc": desc, "tipo": tipo, "obrig": obrig, "anexo": anexo, "opcoes": opcoes}


# ── BASE: vale para todo tema ────────────────────────────────────────────────
# Os três itens abaixo são os únicos que recorrem ATRAVÉS dos temas na amostra: descrição da
# atividade (43% das 414 OS), registro fotográfico (aparece em Nobreak 27%, Tracker 10% e
# Proteção 10% com redações diferentes) e pendência (Vegetação 27%, Coleta 17%).
# Ficam aqui em vez de repetidos em cada tema justamente porque a redação divergia entre eles.
BASE = [
    _s("Descreva a atividade realizada", "longo"),
    _s("Registro fotográfico da atividade", "texto", anexo=True),
    _s("Ficou alguma pendência? Se sim, descreva", "longo", obrig=False),
]


# ── POR TEMA ─────────────────────────────────────────────────────────────────
POR_TEMA = {
    # 83 solicitações · 30 OS amostradas · o tema mais maduro que existe hoje: 19 subtarefas
    # recorrentes e só 43% das OS caindo em rótulo genérico. Tem antes/depois e contagem — foi
    # escrito por alguém que pensou no serviço, e é o melhor modelo dos quatro.
    "vegetacao": [
        _s("Coloque a data e hora da inspeção inicial (dd/mm/aaaa hh:mm)"),
        _s("Os módulos foram inspecionados antes do início da supressão?", "simnao"),        # 40%
        _s("As caixas de passagem foram localizadas e inspecionadas antes da supressão?",
           "simnao"),                                                                        # 40%
        _s("Foi informada à equipe de supressão a localização das caixas de passagem?",
           "simnao"),                                                                        # 43%
        _s("Verificar danos em outros itens pré-roçada (string box, cabos, inversores)",
           "longo", obrig=False),                                                            # 10%
        _s("Atividade de roçagem realizada com sucesso?", "simnao"),                          # 43%
        _s("Os módulos foram inspecionados novamente após a supressão?", "simnao"),           # 43%
        _s("As caixas de passagem foram reavaliadas após a supressão?", "simnao"),            # 43%
        # As quatro contagens abaixo são o que distingue dano PREEXISTENTE de dano CAUSADO pela
        # roçagem — a pergunta que a empreiteira faz depois, e que hoje ninguém consegue responder.
        _s("Quantos módulos estavam com danos?", "num"),                                      # 30%
        _s("Quantos módulos apresentaram danos novos ou agravados?", "num", anexo=True),      # 30%
        _s("Quantas caixas de passagem foram identificadas com danos?", "num"),               # 30%
        _s("Quantas caixas de passagem tiveram danos novos ou agravados?", "num", anexo=True),  # 30%
    ],

    # 50 solicitações · 30 OS · 7 subtarefas, todas a 27% — um procedimento coerente, escrito de
    # uma vez só. É medição elétrica, então tudo é número com faixa, não "verificado sim/não".
    "nobreak": [
        _s("Realizar inspeção visual externa do gabinete (integridade física, superaquecimento)",
           "verif"),
        _s("Status dos LEDs e do display frontal — registre código de erro ou alarme", "texto"),
        _s("Tensão de saída CA medida, em V (127 ou 220 conforme projeto)", "num"),
        _s("Tensão de saída SEM alimentação CA, em V", "num"),
        _s("Teste de autonomia: desenergizar a entrada CA e validar se a comunicação se mantém",
           "simnao"),
        _s("Tempo de duração da bateria no teste de descarga, em minutos", "num"),
        _s("Evidência fotográfica do display, conexões internas e status", "texto", anexo=True),
    ],

    # 227 solicitações · 30 OS · 7 subtarefas a 10% — um único procedimento, de coleta de óleo de
    # transformador, que não se espalhou. Os três primeiros itens são de SEGURANÇA e vêm antes de
    # qualquer medição de propósito: é intervenção em alta tensão.
    "protecao_transformador": [
        _s("Solicitar autorização do COS antes de iniciar a intervenção na cabine", "simnao"),
        _s("Utilizar EPIs completos para alta tensão, incluindo luvas isolantes", "simnao"),
        _s("Realizar bloqueio e etiquetagem (LOTO) dos dispositivos de seccionamento", "simnao"),
        _s("Executar teste de ausência de tensão nos bornes e na carcaça", "simnao"),
        _s("Realizar a coleta de óleo conforme procedimento de amostragem", "verif"),
        _s("Avaliar base e estrutura de suporte (afundamento, desalinhamento, corrosão)", "verif"),
        _s("Registrar fotos do estado geral, dos pontos de coleta e da identificação", "texto",
           anexo=True),
    ],

    # ── Tracker: TRÊS temas, não um ──────────────────────────────────────────
    # As 13 subtarefas recorrentes do tema Tracker não são um checklist só: lendo os textos, são
    # três procedimentos distintos que caem no mesmo ativo. Juntá-los num tema só faria a OS de
    # troca de motor nascer perguntando sobre inject, e vice-versa.
    # E a hipótese de que tracker seria majoritariamente chamado de garantia NÃO se confirmou:
    # só 19% das 312 mencionam chamado/garantia/fabricante, e apenas 4% na descrição.
    "tracker_reset_tcu": [
        _s("Verificar alarmes ativos e status de comunicação na TCU antes da intervenção", "longo"),
        _s("Executar o procedimento de reset na placa de controle", "simnao"),
        _s("Testar a movimentação nos modos manual e automático após a reinicialização", "verif"),
        _s("Validar sincronismo, alinhamento e ausência de falhas no supervisório", "verif"),
        _s("Registrar fotos, parâmetros de operação e evidência de liberação", "texto", anexo=True),
    ],
    "tracker_inject": [
        _s("Acionar a STI para realizar o inject na TCU", "simnao"),
        _s("Acompanhar o processo e registrar as mensagens/status apresentados", "longo"),
        _s("Verificar se o tracker funcionou corretamente após o inject", "verif"),
        _s("Registrar relatório fotográfico do teste realizado", "texto", anexo=True),
    ],
    "tracker_motor": [
        _s("Realizar a instalação do motor no tracker", "simnao"),
        _s("Verificar fixação mecânica e conexões elétricas do motor instalado", "verif"),
        _s("Verificar funcionamento (movimento de rotação e seguimento solar)", "verif"),
        _s("Registrar relatório fotográfico da instalação e do teste", "texto", anexo=True),
    ],
}


# Ponto de extensão, VAZIO de propósito. No chamado, a camada extra é a MARCA, porque o fabricante
# cobra o que quer. Aqui a evidência das 414 OS não mostrou nenhuma subtarefa que varie por tipo de
# ativo DENTRO de um mesmo tema — então não há o que preencher ainda. A camada fica declarada para
# quando aparecer (ex.: proteção em cabine × em skid), e não para ser adivinhada agora.
POR_TIPO_ATIVO = {}


# ── Metadados do tema ────────────────────────────────────────────────────────
# `classif1` e `tipo` são a MAIORIA MEDIDA nas 2.500, com o percentual de domínio ao lado. Onde o
# domínio é baixo, o default vai mudar a classificação de boa parte do histórico — isso é o
# objetivo, mas precisa ser dito ao time, não aplicado em silêncio.
TEMAS = {
    "vegetacao": {
        "nome": "Vegetação — roçagem e supressão",
        "motivo": "Roçagem e supressão vegetal",
        "classif1": "Não Para o Ativo", "dominio": 77,
        "tipo": "Limpeza e Conservação", "solicitacoes": 83,
    },
    "nobreak": {
        "nome": "Nobreak e sistemas auxiliares",
        "motivo": "Inspeção de nobreak",
        "classif1": "Não Para o Ativo", "dominio": 50,
        "tipo": "Elétrica", "solicitacoes": 50,
    },
    "protecao_transformador": {
        "nome": "Proteção — transformador e cabine",
        "motivo": "Intervenção em transformador",
        "classif1": "Não Para o Ativo", "dominio": 34,
        "tipo": "Elétrica", "solicitacoes": 227,
    },
    "tracker_reset_tcu": {
        "nome": "Tracker — reset da TCU",
        "motivo": "Reset da TCU",
        "classif1": "Leve (Não Parou o Ativo, mas Afetou a Eficiência)", "dominio": 51,
        "tipo": "", "solicitacoes": 312,
    },
    "tracker_inject": {
        "nome": "Tracker — inject na TCU",
        "motivo": "Inject na TCU",
        "classif1": "Leve (Não Parou o Ativo, mas Afetou a Eficiência)", "dominio": 51,
        "tipo": "", "solicitacoes": 312,
    },
    "tracker_motor": {
        "nome": "Tracker — troca de motor",
        "motivo": "Troca de motor",
        "classif1": "Leve (Não Parou o Ativo, mas Afetou a Eficiência)", "dominio": 51,
        "tipo": "", "solicitacoes": 312,
    },
}


def temas() -> list:
    """[(chave, nome)] na ordem em que devem aparecer na tela — do maior volume para o menor."""
    return [(k, TEMAS[k]["nome"])
            for k in sorted(TEMAS, key=lambda k: (-TEMAS[k]["solicitacoes"], TEMAS[k]["nome"]))]


def existe(tema) -> bool:
    return tema in POR_TEMA


def subtarefas(tema: str, tipo_ativo: str = "") -> list:
    """Subtarefas do tema → lista pronta para `api._rpc_subtasks`.

    Ordem: específico do tema → específico do tipo de ativo → BASE. A base fica no FIM de
    propósito: "descreva a atividade" e a foto são o fechamento do serviço, e no chamado elas
    abrem porque lá o que se descreve é o problema, não o que foi feito.

    Subtarefa repetida entra uma vez só — a camada do ativo pode reforçar algo que o tema já pede,
    e duas linhas iguais na OS só confundem o técnico."""
    if tema not in POR_TEMA:
        raise KeyError("tema desconhecido: %r (conhecidos: %s)"
                       % (tema, ", ".join(sorted(POR_TEMA))))
    blocos = POR_TEMA[tema] + POR_TIPO_ATIVO.get((tipo_ativo or "").strip(), []) + BASE
    out, vistos = [], set()
    for s in blocos:
        chave = s["desc"].strip().lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        item = {"description": s["desc"],
                "id_task_form_item_type": TIPO_ID.get(s["tipo"], 1),
                "is_required": bool(s["obrig"]),
                "attachments_required": bool(s["anexo"])}
        if s["opcoes"]:
            item["dropdown_options"] = [{"description": o} for o in s["opcoes"]]
        out.append(item)
    return out


def subtarefas_base() -> list:
    """Só a BASE, para a solicitação SEM tema.

    Nove dos catorze temas ainda não têm checklist escrito. Se a fila do PCM travasse neles, ele
    voltaria para o Fracttal — e aí a OS nasce sem subtarefa nenhuma. Com a base, nasce com três:
    pior que o ideal, melhor que hoje."""
    return [{"description": s["desc"],
             "id_task_form_item_type": TIPO_ID.get(s["tipo"], 1),
             "is_required": bool(s["obrig"]),
             "attachments_required": bool(s["anexo"])} for s in BASE]


def classificacao(tema: str) -> dict:
    """Classificação sugerida pelo tema → {'classif1','tipo','dominio'}.

    É o que conserta o campo obrigatório sem pedir disciplina a ninguém: em vez de a pessoa
    escolher entre duas escalas que convivem no mesmo menu, o tema já desce com a resposta."""
    t = TEMAS.get(tema) or {}
    return {"classif1": t.get("classif1", ""), "tipo": t.get("tipo", ""),
            "dominio": t.get("dominio")}



# ── Inversor e tracker (03/09/2026) ──────────────────────────────────────────
# DE ONDE VEIO CADA LINHA: colhida das OS que ja existem, nao escrita por mim. Foram lidas 220
# solicitacoes de inversor que viraram OS (295 subtarefas distintas, fora as genericas) e 90 de
# tracker (71 distintas). O que eu fiz foi agrupar e ordenar; o texto e o tipo de campo saem de
# la — inclusive o vocabulario de seguranca (LOTO, descarga de capacitores) e de medicao
# (termografia, MC4, polaridade), que ninguem de fora da operacao escreveria assim.
#
# POR QUE INVERSOR NAO TINHA TEMA ATE HOJE: porque o corpus tambem nao tinha procedimento. As
# duas subtarefas mais comuns das OS de inversor sao "Procedimento" (46 de 90) e "Descreva a
# atividade realizada" (46 de 90) — campo em branco com nome. Todo o resto aparece UMA vez: cada
# tecnico escreveu o seu. E exatamente o buraco que estes temas fecham.
POR_TEMA["inversor_inspecao"] = [
    _s("Confirmar bloqueio e etiquetagem (LOTO) do inversor antes de iniciar", "verif", anexo=True),
    _s("Aguardar o tempo de descarga dos capacitores internos conforme manual do fabricante", "verif"),
    _s("Abrir tampas e inspecionar conexões da placa DC (aperto, oxidação, sinais de calor)", "verif"),
    _s("Comparar temperatura do inversor com a ambiente (termômetro IV / câmera térmica)", "verif"),
    _s("Temperatura medida no inversor, em °C", "num"),
    _s("Verificar ventoinhas e filtros — quantas estão com problema", "num"),
    _s("Medir tensão de cada string conectada, em V", "num"),
    _s("Medir corrente de cada string conectada, em A", "num"),
    _s("Verificar conectores MC4 e polaridade dos cabos CC", "verif"),
    _s("Anexar registros de temperatura, fotos da inspeção e medições de tensão de string",
       "texto", anexo=True),
]

POR_TEMA["inversor_substituicao"] = [
    _s("Confirmar bloqueio e etiquetagem (LOTO) e ausência de tensão antes de iniciar",
       "verif", anexo=True),
    _s("Aguardar o tempo de descarga dos capacitores internos conforme manual do fabricante", "verif"),
    _s("Registrar número de série (SN) do inversor retirado", "texto"),
    _s("Registrar número de série (SN) do inversor instalado", "texto"),
    _s("Conferir polaridade dos cabos CC (positivo/negativo) antes da conexão ao inversor", "verif"),
    _s("Configurar parâmetros do inversor substituto conforme o projeto", "verif"),
    _s("Solicitar ao COS a autorização para o restabelecimento do sistema", "simnao"),
    _s("Confirmar geração após o restabelecimento", "simnao"),
    _s("Anexar fotos do antes e depois da intervenção", "texto", anexo=True),
]

POR_TEMA["inversor_garantia"] = [
    _s("Identificação do equipamento (inversor, string box, TCU do tracker)", "texto"),
    _s("Número de série (SN) do equipamento", "texto"),
    _s("Tipo de erro apresentado (código no display ou no portal)", "texto"),
    _s("Coletar os logs do equipamento / smartlogger", "texto", anexo=True),
    _s("Anexar os logs para abertura do chamado", "texto", anexo=True),
    _s("Anexar relatório de serviço ou termo de conclusão assinado", "verif", anexo=True),
]

POR_TEMA["tracker_chamado"] = [
    _s("Verificar alarmes ativos e status de comunicação na TCU antes da intervenção", "verif"),
    _s("Endereço MAC da TCU", "texto"),
    _s("ID do rastreador (para equipamentos Soltec)", "texto"),
    _s("Testar a movimentação nos modos manual e automático", "verif"),
    _s("Validar o sincronismo, o alinhamento e a ausência de falhas no supervisório", "verif"),
    _s("Registrar fotos, parâmetros de operação e evidências de liberação do equipamento",
       "texto", anexo=True),
]

# A classificacao de cada um saiu da DISTRIBUICAO real das solicitacoes da familia, e nao de
# palpite: inversor em geral 27% "Nao Para o Ativo"; substituicao espalhada, com 21% em "Leve";
# garantia 35% "Moderado"; tracker 44% "Leve". O dominio abaixo e essa porcentagem.
TEMAS["inversor_inspecao"] = {
    "nome": "Inversor — inspeção e medição",
    "motivo": "Inspeção e medição de inversor",
    "classif1": "Não Para o Ativo", "dominio": 27,
    "tipo": "Elétrica", "solicitacoes": 751,
}
TEMAS["inversor_substituicao"] = {
    "nome": "Inversor — substituição",
    "motivo": "Substituição de inversor",
    "classif1": "Leve (Não Parou o Ativo, mas Afetou a Eficiência)", "dominio": 21,
    "tipo": "Elétrica", "solicitacoes": 178,
}
TEMAS["inversor_garantia"] = {
    "nome": "Inversor — chamado de garantia",
    "motivo": "Abertura de chamado de garantia",
    "classif1": "Moderado (Impacto Parcial no Ativo)", "dominio": 35,
    "tipo": "Elétrica", "solicitacoes": 173,
}
TEMAS["tracker_chamado"] = {
    "nome": "Tracker — chamado e comunicação da TCU",
    "motivo": "Chamado de tracker",
    "classif1": "Leve (Não Parou o Ativo, mas Afetou a Eficiência)", "dominio": 44,
    "tipo": "", "solicitacoes": 468,
}

# ── O bloco da sugestão, na observação ───────────────────────────────────────
# A solicitação do Fracttal NÃO tem campo de técnico. Verificado nas 2.500: todos os campos de
# pessoa são de quem CRIOU (`accounts_name`, `id_user`, `id_personnel_log`) ou de quem mudou o
# status. Então a sugestão do supervisor vai num bloco parseável na observação — exatamente o que
# o `perf_spec.MARCADOR` faz com a prioridade da Performance, e pelo mesmo motivo.
#
# `date_maintenance` existe e serve de data pretendida (difere da criação em 44% dos casos), mas
# fica FORA daqui de propósito: campo nativo é melhor que texto, e o bloco é para o que não tem
# campo. O bloco carrega a data só como cópia legível para quem lê a observação no Fracttal web.
MARCADOR = "[PCM]"
# "Data sugerida" desde 03/09 (era "Data pretendida"). O parse aceita os DOIS rotulos: as
# solicitacoes ja criadas trazem o nome antigo, e perder a data delas seria apagar informacao
# que alguem escreveu.
_CAMPOS = [("Tema", "tema"), ("Técnico sugerido", "tecnico"), ("Data sugerida", "data")]
_ALIAS = {"data pretendida": "data"}

# Rotulo legivel de cada tipo de campo da subtarefa. O PCM precisa saber se aquela linha vai
# pedir texto, numero, foto ou um sim/nao — e a diferenca entre um checklist e um campo em branco.
# O sufixo que marca "anexo obrigatório" na linha da subtarefa dentro do bloco [PCM].
# Texto, e não um código: a observação é lida no Fracttal web por gente que não tem manual.
MARCA_ANEXO = "  (anexo obrigatório)"

TIPO_ROTULO = {"texto": "Texto", "longo": "Texto", "num": "Numérico",
               "simnao": "Sim/Não", "verif": "Verificação", "lista": "Lista"}
_ROTULO_TIPO = {"texto": "texto", "numérico": "num", "numerico": "num",
                "sim/não": "simnao", "sim/nao": "simnao", "verificação": "verif",
                "verificacao": "verif", "lista": "lista"}


def bloco(dados: dict) -> str:
    """dict → texto do bloco, para concatenar na observação da solicitação na CRIAÇÃO.
    Só emite campo preenchido: bloco enxuto é bloco que a pessoa lê."""
    linhas = [MARCADOR]
    for rot, k in _CAMPOS:
        v = str((dados or {}).get(k) or "").strip()
        if v:
            linhas.append("%s: %s" % (rot, v))
    # A LISTA vai no bloco porque o supervisor agora pode editar as subtarefas, e sem isso a
    # edicao dele morreria aqui: o PCM abriria a fila e veria de novo a lista padrao do tema.
    # Formato legivel de proposito — quem ler a observacao no Fracttal web entende sem manual.
    subs = (dados or {}).get("subtarefas") or []
    if subs:
        linhas.append("Subtarefas:")
        for x in subs:
            # O SUFIXO DO ANEXO. Sem ele a marca de "anexo obrigatório" que o supervisor pôs
            # morria aqui: o bloco guardava só tipo e descrição, e o PCM abria a fila com todas
            # as subtarefas desmarcadas. Medido na SS 3550 — as três voltavam com anexo=None.
            # Fica em texto, e não num código, porque quem lê a observação no Fracttal web tem
            # de entender sem manual; blocos antigos, sem o sufixo, viram False.
            linhas.append("- [%s] %s%s" % (TIPO_ROTULO.get(x.get("tipo", "texto"), "Texto"),
                                           str(x.get("desc") or "").strip(),
                                           MARCA_ANEXO if x.get("anexo") else ""))
    return "\n".join(linhas) if len(linhas) > 1 else ""


def parse(texto) -> dict:
    """INVERSO: lê o bloco de uma observação → {'tema','tecnico','data'}. {} quando não tem bloco.

    Tolera acento e caixa no rótulo — quem edita a observação no Fracttal web digita como quiser,
    e um acento perdido não pode fazer a fila do PCM esquecer o tema."""
    t = str(texto or "")
    if MARCADOR.lower() not in t.lower():
        return {}
    import unicodedata

    def _norm(s):
        s = unicodedata.normalize("NFKD", str(s).lower())
        return "".join(c for c in s if not unicodedata.combining(c)).strip()

    rot2k = {_norm(r): k for r, k in _CAMPOS}
    rot2k.update({_norm(r): k for r, k in _ALIAS.items()})   # "Data pretendida", dos blocos antigos
    out, subs = {}, []
    for linha in t.splitlines():
        cru = linha.strip()
        # "- [Tipo] descricao" e uma subtarefa; o resto sao os campos "Rotulo: valor"
        if cru.startswith("- [") and "]" in cru:
            rot, desc = cru[3:].split("]", 1)
            desc = desc.strip()
            anexo = desc.endswith(MARCA_ANEXO.strip())
            if anexo:
                desc = desc[:-len(MARCA_ANEXO.strip())].strip()
            subs.append({"tipo": _ROTULO_TIPO.get(_norm(rot), "texto"), "desc": desc,
                         "anexo": anexo})
            continue
        if ":" not in linha:
            continue
        rot, val = linha.split(":", 1)
        k = rot2k.get(_norm(rot))
        if k:
            v = val.strip()
            out[k] = "" if v in ("", "—") else v
    if subs:
        out["subtarefas"] = subs
    return out


def para_api(subs: list) -> list:
    """[{'tipo','desc'}] -> o formato que o Fracttal espera nas subtarefas da OS.

    As tres da BASE continuam vindo de `subtarefas()`/`subtarefas_base()`; esta funcao existe
    para o que a PESSOA escreveu, que nao passa pelo catalogo de temas."""
    return [{"description": str(x.get("desc") or "").strip(),
             "id_task_form_item_type": TIPO_ID.get(x.get("tipo", "texto"), 1),
             "is_required": True,
             "attachments_required": False}
            for x in (subs or []) if str(x.get("desc") or "").strip()]


def de_api(subs: list) -> list:
    """O caminho inverso: o formato do Fracttal -> [{'tipo','desc','anexo'}] para o editor."""
    inv = {}
    for nome, i in TIPO_ID.items():
        inv.setdefault(i, nome)
    return [{"tipo": inv.get(x.get("id_task_form_item_type"), "texto"),
             "desc": str(x.get("description") or ""),
             "anexo": bool(x.get("attachments_required"))}
            for x in (subs or [])]


def observacao_com_bloco(observacao: str, dados: dict) -> str:
    """Junta o texto que o supervisor escreveu com o bloco da sugestão.

    O texto dele vem PRIMEIRO: quem abre a solicitação no Fracttal quer ler o relato, não o
    metadado. E um bloco anterior é substituído, não duplicado — reenviar a mesma solicitação
    empilhava dois `[PCM]` e o `parse` ficava com o primeiro, que era o velho."""
    b = bloco(dados)
    corpo = []
    for linha in str(observacao or "").splitlines():
        if linha.strip().lower().startswith(MARCADOR.lower()):
            break                       # daqui para baixo é bloco antigo: descarta
        corpo.append(linha)
    texto = "\n".join(corpo).strip()
    if not b:
        return texto
    return (texto + "\n\n" + b).strip() if texto else b


def _limpa_ativo(ativo: str) -> str:
    """Nome do ativo sem o código entre chaves e sem os espaços que o Fracttal deixa no meio.

    A descrição do ativo vem como `Chave Seccionadora 1      { TESTE100-CHSC1 }` — com o código
    embutido e espaçamento de largura fixa. Sem limpar, o título gerado saía com o código dentro
    dos colchetes e uma fileira de espaços (visto na solicitação de teste 3534). É o mesmo corte
    que o `api._req_row_to_d` já faz ao montar o card da solicitação."""
    import re
    nome = str(ativo or "").split("{")[0]
    return re.sub(r"\s+", " ", nome).strip()


# ── Etiquetas obrigatorias ───────────────────────────────────────────────────
# Regra do Levi (03/09): toda OS de TRACKER, de ETM ou de GARANTIA leva tambem a etiqueta
# PERFORMANCE. O motivo e de processo, nao de sistema: sao os tres assuntos que a Performance
# acompanha depois, e uma OS sem a etiqueta nao entra no relatorio dela.
#
# O gatilho NAO e uma etiqueta: no Fracttal nao existe etiqueta "Tracker" nem "ETM" (conferido
# nas 42 do catalogo em 03/09). Tracker e ETM vem do TEMA ou do ATIVO; garantia, sim, e etiqueta.
ETIQUETA_PERFORMANCE = "PERFORMANCE"
_GATILHO_ATIVO = ("tracker", "tcu", "estacao meteo", "estação meteo", "meteorolog",
                  "piranometro", "piranômetro", "etm")


def exige_performance(tema: str = "", ativo: str = "", etiquetas=()) -> bool:
    """True quando esta solicitacao tem de sair com a etiqueta PERFORMANCE."""
    import unicodedata

    def _n(x):
        x = unicodedata.normalize("NFKD", str(x or "").lower())
        return "".join(c for c in x if not unicodedata.combining(c))

    if str(tema or "").startswith("tracker"):
        return True
    alvo = _n(ativo)
    if any(g in alvo for g in (_n(x) for x in _GATILHO_ATIVO)):
        return True
    return any("garantia" in _n(e) for e in (etiquetas or ()))


def motivo(tema: str) -> str:
    """So o motivo do tema — "Inject na TCU", "Roçagem e supressão vegetal".

    E o titulo que a SOLICITACAO passa a usar (decisao do Levi, 03/09). O padrao completo
    `[Usina][Ativo] - Motivo` continua existindo em `titulo()`, mas migra para o painel do PCM:
    quem padroniza e quem aprova, e o padrao ainda vai ser definido por ele. Pedir o padrao ao
    supervisor era pedir que ele decorasse a forma; o motivo ele ja sabe dizer."""
    return (TEMAS.get(tema) or {}).get("motivo") or ""


def titulo(usina: str, ativo: str, tema: str) -> str:
    """Título no padrão `[Usina][Ativo] - Motivo`, o mesmo que as OS já usam.

    Existe porque só 33,2% das 2.500 solicitações seguem esse padrão hoje — o resto é texto livre,
    e é por isso que 163 descrições diferentes acabam significando a mesma coisa."""
    motivo = (TEMAS.get(tema) or {}).get("motivo") or ""
    partes = "".join("[%s]" % p for p in (str(usina or "").strip(), _limpa_ativo(ativo)) if p)
    return ("%s - %s" % (partes, motivo)).strip(" -") if partes else motivo
