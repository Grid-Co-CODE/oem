# os_creator/os_web/cos_web.py
"""Regras da tela COS na web — as MESMAS do `steps/varias_os.py` (VariasOSsDialog), sem Qt e sem rede.

O COS é o setor de tempo real, o que fala com o cliente: a OS que sai daqui não pode ter um campo diferente da que o app
de mesa criaria na mesma tela. Por isso nada de regra é reescrito: o texto (título '[Equip] - Motivo', observação-pipe,
'Falha:') sai do `cos_spec`, o mesmo módulo do app; o nome curto e o título, do `api` (`_asset_short_name`,
`perf_os_nome`); e o que o widget decidia dentro dos próprios métodos — tipo de tarefa, classificações, criticidade,
subtarefas, bloco de falha, as validações e a ordem delas — mora aqui, um espelho por método:

    _preview            → preview()              _tarefa_nome / _classif_nomes / _crit_* → tarefa_nome() & cia.
    _tipo_dict          → tipo_dict()            _subtarefas                             → subtarefas()
    _criar              → criacao()              _ok                                     → mensagem_resultado()
    _sel_desc           → escolher_desc()        _sugerir_falha                          → sugestoes_falha()
    _generic_asset      → ativo_generico()       _clone_ok / _aplicar_clone              → modelo_clone()
    _fill_clientes / _fill_usinas / _on_usi / _usinas_alvo / _cands                     → clientes(), usinas_para(), alvo()

A criação devolve os argumentos POSICIONAIS que o `_criar` passa a `api.create_work_orders_bulk` (Vários ativos · 1 data)
e a `api.create_work_orders_datas` (Mesmo ativo · várias datas), na mesma ordem — o motor recebe da web exatamente o que
já recebe do desktop.

O estado da tela chega de dois jeitos: JSON na criação e query string na prévia (`estado` / `estado_da_query`). O que
não veio vale como na tela recém-aberta; o que veio fora das opções que a tela oferece (onde atuou, falha do inversor,
causa da comunicação, categoria…) é recusado com `ErroTela` — o app não consegue produzir esse estado, então ele só
chega por defeito, e defeito não pode virar OS.

Constantes copiadas do widget de propósito (o módulo de lá é Qt); `tests/test_os_web_cos.py` lê o fonte (ast) e acusa
divergência."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field

import api
import cos_spec as cs

# ── constantes do widget ───────────────────────────────────────────────────────────────────────────────────────────
# Ativo genérico "Grid Co. - Emergências e outros pontos" (code GRID): o das OS de usina de terceiros, a planta que não
# é ativo cadastrado no Fracttal. O id veio de OSs reais (ex.: 9184) — varias_os.py::GENERICO_ID.
GENERICO_ID = 49349933
GENERICO_DESC = "Grid Co. - Emergências e outros pontos      { GRID }"
GENERICO_LABEL = "Grid Co. - Emergências e outros pontos"
# Classificação 1 que o PCM deixou "depende do contexto" (cat C): sentinela que obriga o operador a escolher — vermelha na
# linha "Registrada no Fracttal como" e barrando a criação enquanto ficar assim (varias_os.py::_PREENCHER).
PREENCHER = "Preencher"
# Tipos de equipamento que SÓ plantas têm: decidem quais clientes/usinas são "reais" — o catálogo tem inventário do
# Almoxarifado com cliente e usina próprios (varias_os.py::_CARTEIRA_EQUIP).
CARTEIRA_EQUIP = frozenset({"Inversor", "Cabine", "Tracker", "Estrutura Trackers", "Estação Meteorológica", "Skid"})
SEL = "— selecione —"                                                   # varias_os.py::_SEL

# os rótulos dos segmentados, na ordem dos índices que a tela manda
MODOS = ("Vários ativos · 1 data", "Mesmo ativo · várias datas")
CATEGORIAS_ROTULO = ("A · Proteções", "B · Inversores", "C · Comunicação")
ACOES_ROTULO = ("Remoto — resolvo agora", "Local — equipe em campo")
TIPOS = (cs.TIPO_RELIGAMENTO, cs.TIPO_INSPECAO)
CATS = (cs.CAT_A, cs.CAT_B, cs.CAT_C)
# A ORDEM DOS CHIPS é a ordem da proteção na OS: `_codigos` lê os chips pela ordem em que foram criados, não pela do
# clique — quem marca 59 e depois 27 recebe "27 e 59". O "Sem proteção/trip ativo" vem por último, como na grade.
CHIPS = tuple(cs.PROTECOES) + (cs.SEM_TRIP,)
BRT = dt.timezone(dt.timedelta(hours=-3))                              # o `brt` do _criar

TRILHO_BULK, TRILHO_DATAS = "bulk", "datas"

# ── as frases do app (QMessageBox do _criar e do clonador) ────────────────────────────────────────────────────────
ERRO_TERCEIROS = "Preencha o Cliente e a Usina (texto livre)."
ERRO_SEM_ATIVO = "Marque ao menos um ativo."
ERRO_SEM_RESP = "Escolha o responsável (requerido por)."
ERRO_TIPOS = ("Os tipos ainda não carregaram (ou a sessão expirou). Aguarde um instante ou relogue e tente de novo.")
ERRO_PREENCHER = ("Escolha a Classificação 1 — clique no 'Preencher' em vermelho na linha 'Registrada no Fracttal como'.")
ERRO_PROTECAO = "Marque ao menos uma proteção que atuou (categoria A · Proteções)."
ERRO_FALHA = "Preencha Tipo de falha, Causa e Método de detecção (ou desmarque 'O ativo falhou?')."
ERRO_SEM_DATA = "Adicione ao menos uma data."
ERRO_LINHA = "Conclusão anterior ao evento (linha {:%d/%m %H:%M})."
ERRO_CONCLUSAO = "A conclusão não pode ser anterior ao evento."
# Estas não existem como QMessageBox porque no app o estado é impossível: o QDateTimeEdit não guarda data inválida, o
# `travar_no_passado` não deixa nem digitar evento no futuro (a frase é o tooltip dele, steps/ui.py) e o `_on_prot` não
# deixa código e "Sem trip" juntos. Na web o pedido pode chegar assim — e uma OS com "27 e Sem proteção/trip ativo"
# diria duas coisas contrárias ao cliente.
ERRO_DATA = "Data inválida."
ERRO_FUTURO = "Data do evento não aceita futuro — é quando aconteceu."
ERRO_SEM_TRIP_JUNTO = "Marque as proteções que atuaram OU 'Sem proteção/trip ativo' — os dois juntos não."
ERRO_SEV_DANO = "Escolha a Severidade e o Tipo de dano (ou desmarque 'O ativo falhou?')."
# folga para o relógio do navegador adiantado em relação ao servidor — a mesma do Tradicional (tradicional_web.py)
_FOLGA_FUTURO = dt.timedelta(minutes=10)

CLONE_VAZIO = "Digite o número da OS que quer clonar."
CLONE_NAO_ACHOU = "Não achei nenhuma OS com esse número."
CLONE_FORA_PADRAO = ("A OS {} não segue o padrão do COS na observação (UFV | Proteção | Ação | Falha), então não dá "
                     "para remontar este formulário.\n\nUse o 'Clonar OS' da tela inicial para OSs fora do padrão.")
CLONE_OK = "Formulário preenchido a partir da OS {}.\nConfira o ativo, a data do evento e o responsável antes de criar."

# ── o permissivo e o "Fora de serviço" (os textos do _preview e do _upd_oos) ──────────────────────────────────────
# O app escreve "⚠ Impedimento ativo (86)…": aqui o símbolo sai e o `nivel` vira a cor (sem emoji na interface).
PERM_86 = ("Impedimento ativo (86) — religamento remoto não autorizado. Abra para equipe em campo (Ação: Local).")
PERM_REMOTO_C = "Falha de comunicação — verificação remota."
PERM_REMOTO = "Sem impedimento — pode ser resolvido remoto."
PERM_LOCAL = "Local — a OS abre para a equipe em campo resolver."
OOS_SIM = "Sim — ativo segue fora de serviço (desde a data do evento)"
OOS_NAO = "Não — OS já tem conclusão, o ativo voltou"
SUFIXO_VARIOS = "   (cada OS usa o seu ativo)"

# Os textos que o `cos.js` escreve na tela, todos do app (sem o "⚠" das mensagens de erro: a cor diz). Moram aqui para a
# frase ter UM dono — a mesma que o widget usa.
TEXTOS_JS = {
    "sel": SEL,
    "sel_usina": "— Selecione a usina —",
    "todos_tipos": "Todos os tipos",
    "multi_ok": ("Lista os ativos de TODAS as usinas do cliente selecionado.\n"
                 "Cada OS continua nascendo com a usina do seu próprio ativo."),
    "multi_terceiros": "Não vale para usina de terceiros — ali o ativo é o genérico.",
    "multi_modo": "Só no modo 'Vários ativos · 1 data' — no 'Mesmo ativo' existe um ativo só.",
    "multi_cliente": "Escolha o Cliente primeiro: o modo lista as usinas DELE.",
    "listas_nao_carregaram": ("As listas do Fracttal ainda não carregaram (ou a sessão expirou). "
                              "Aguarde um instante ou relogue e tente de novo."),
    "voltar_auto": "↩  voltar ao automático",
    "carregando": "carregando…",
    "carregando_resp": "carregando responsáveis…",
    "resp_falha": "falha — relogue e clique em ↻",
    "resp_hint": "responsável: ",
    "classif_err": "tipos de tarefa não carregaram (sessão expirada?). Relogue e reabra o COS.",
    "confirma_limpar": "Limpar todos os campos e voltar à tela inicial?",
    "tela_limpa": "tela limpa",
    "criando": "criando {n} OS… (pode levar alguns segundos)",
    "nenhuma": "Nenhuma OS criada.",
    "erro_criar": "Erro ao criar OSs: ",
    "erro_clone": "Erro ao buscar a OS: ",
    "buscando": "buscando…",
    "clonar": "Clonar",
    "futuro": ERRO_FUTURO,
    "digite_cli": "Digite o cliente…",
    "digite_usi": "Digite a usina…",
}


class ErroTela(ValueError):
    """Um estado que a tela do app não produz (valor fora das opções do combo, categoria que não existe…)."""


# ── o estado da tela ───────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Estado:
    tipo: int = 0                        # 0 = Religamento da UFV · 1 = Inspeção e Normalização (_seg_tipo)
    cat: str = cs.CAT_A                  # _cat
    remoto: bool = True                  # _seg_acao: 0 = Remoto — resolvo agora
    modo: int = 0                        # 0 = Vários ativos · 1 data · 1 = Mesmo ativo · várias datas
    codigos: list = field(default_factory=list)
    onde: str = cs.ONDE[0]
    falha_b: str = cs.FALHAS_B[0]
    causa_c: str = cs.CAUSAS_C[0]
    obs: str = ""                        # ed_obs (comentário do operador)
    ids: list = field(default_factory=list)          # _checked
    terceiros: bool = False
    cliente: str = ""                    # _cli(): o texto livre em terceiros; senão, o cliente escolhido no combo
    usina: str = ""                      # _usi(): idem
    ovr: dict = field(default_factory=lambda: {"tipo": None, "c1": None, "c2": None, "crit": None})
    realizada: bool = True               # _fin.is_finalizar() — "Esta tarefa já foi realizada?"
    em_verificacao: bool = False         # _fin.to_in_review() — "Enviar para OS: Verificação"
    responsavel: dict = field(default_factory=dict)
    falha: dict = field(default_factory=dict)
    evento: str = ""
    conclusao: str = ""
    datas: list = field(default_factory=list)


def _primeiro(v):
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def _texto(v) -> str:
    v = _primeiro(v)
    return "" if v is None else str(v)


def _bool(v, padrao: bool) -> bool:
    v = _primeiro(v)
    if v is None or (isinstance(v, str) and not v.strip()):
        return padrao
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() in ("1", "true", "on", "sim", "yes")


def _indice(v, n: int, padrao: int, nome: str) -> int:
    v = _primeiro(v)
    if v is None or (isinstance(v, str) and not v.strip()):
        return padrao
    try:
        if isinstance(v, bool):
            raise ValueError
        i = int(str(v).strip())
    except ValueError:
        raise ErroTela("%s inválido: %r." % (nome, v)) from None
    if not 0 <= i < n:
        raise ErroTela("%s inválido: %r." % (nome, v))
    return i


def _categoria(v) -> str:
    s = _texto(v).strip().upper()
    if not s:
        return cs.CAT_A
    if s in CATS:
        return s
    raise ErroTela("Categoria inválida: %r." % s)


def _opcao(v, opcoes, nome: str) -> str:
    """Combo de lista fixa: o que não veio é o item 0 (o índice em que o combo nasce); o que veio tem de ser uma das
    opções, letra por letra — é o `value` do <option>, e ele sai desta mesma lista."""
    s = _texto(v)
    if not s:
        return opcoes[0]
    if s in opcoes:
        return s
    raise ErroTela("%s inválido: '%s'." % (nome, s))


def _codigos_da_tela(v) -> list:
    brutos = v if isinstance(v, (list, tuple)) else ([v] if v else [])
    marcados = {str(c).strip() for c in brutos if str(c or "").strip()}
    return [c for c in CHIPS if c in marcados]


def ler_ids(v) -> list:
    """ids dos ativos marcados: lista de números (JSON) ou "11,12" (query). O que não é número fica de fora."""
    brutos = v if isinstance(v, (list, tuple)) else [v]
    out = []
    for x in brutos:
        partes = x.split(",") if isinstance(x, str) else [x]
        for p in partes:
            if isinstance(p, bool):
                continue
            try:
                i = int(str(p).strip())
            except (TypeError, ValueError):
                continue
            if i not in out:
                out.append(i)
    return out


_CRIT_IDS = frozenset(i for _n, i in api.CRITICIDADES)


def _crit(v):
    v = _primeiro(v)
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        return None
    try:
        i = int(str(v).strip())
    except ValueError:
        return None
    return i if i in _CRIT_IDS else None       # o menu só oferece os 5 de api.CRITICIDADES


def _ovr(v) -> dict:
    v = v if isinstance(v, dict) else {}
    out = {k: (_texto(v.get(k)).strip() or None) for k in ("tipo", "c1", "c2")}
    out["crit"] = _crit(v.get("crit"))
    return out


def estado(d: dict | None) -> Estado:
    """O estado da tela a partir do JSON que o `cos.js` manda (as chaves do `estado()` de lá)."""
    d = d if isinstance(d, dict) else {}
    cat = _categoria(d.get("cat"))
    datas = d.get("datas")
    return Estado(
        tipo=_indice(d.get("tipo"), 2, 0, "Tipo de OS"),
        cat=cat,
        remoto=_bool(d.get("remoto"), cat == cs.CAT_A),        # o default de ação por categoria (A=Remoto · B/C=Local)
        modo=_indice(d.get("modo"), 2, 0, "Modo"),
        codigos=_codigos_da_tela(d.get("codigos")),
        # só o combo da categoria ativa é lido pelo app (_falha / _equip_nome); os outros ficam no padrão
        onde=_opcao(d.get("onde"), cs.ONDE, "Onde atuou") if cat == cs.CAT_A else cs.ONDE[0],
        falha_b=_opcao(d.get("falha_b"), cs.FALHAS_B, "Falha do equipamento") if cat == cs.CAT_B else cs.FALHAS_B[0],
        causa_c=_opcao(d.get("causa_c"), cs.CAUSAS_C, "Causa da comunicação") if cat == cs.CAT_C else cs.CAUSAS_C[0],
        obs=_texto(d.get("obs")),
        ids=ler_ids(d.get("ids")),
        terceiros=_bool(d.get("terceiros"), False),
        cliente=_texto(d.get("cliente")),
        usina=_texto(d.get("usina")),
        ovr=_ovr(d.get("ovr")),
        realizada=_bool(d.get("realizada"), True),
        em_verificacao=_bool(d.get("em_verificacao"), False),
        responsavel=d.get("responsavel") if isinstance(d.get("responsavel"), dict) else {},
        falha=d.get("falha") if isinstance(d.get("falha"), dict) else {},
        evento=_texto(d.get("evento")).strip(),
        conclusao=_texto(d.get("conclusao")).strip(),
        datas=[x for x in datas if isinstance(x, dict)] if isinstance(datas, list) else [],
    )


def estado_da_query(q: dict) -> Estado:
    """O mesmo estado a partir da query string da prévia (`{chave: [valores]}`): códigos repetidos, ids "11,12" e as
    trocas manuais como ovr_tipo / ovr_c1 / ovr_c2 / ovr_crit."""
    q = q or {}
    um = (lambda k: (q.get(k) or [None])[0])
    d = {k: um(k) for k in ("tipo", "cat", "remoto", "modo", "onde", "falha_b", "causa_c", "obs", "terceiros",
                            "cliente", "usina", "realizada")}
    d["codigos"] = list(q.get("codigos") or [])
    d["ids"] = list(q.get("ids") or [])
    d["ovr"] = {k: um("ovr_" + k) for k in ("tipo", "c1", "c2", "crit")}
    return estado(d)


def falha_marcada(corpo) -> bool:
    f = corpo.get("falha") if isinstance(corpo, dict) else None
    return isinstance(f, dict) and _bool(f.get("marcado"), False)


# ── cascata do ativo (_carteira*, _fill_clientes, _fill_usinas, _cliente_da_usina, _usinas_alvo, _cands) ──────────
def carteira(usina) -> str:
    """Prefixo do label da usina ('Thopen - Altair 1 - SP' → 'Thopen')."""
    return (usina or "").split(" - ", 1)[0].strip()


def carteira_de(a: dict) -> str:
    """A carteira "de verdade" do ativo: o prefixo da usina nomeada, senão o campo cliente (materiais e o plano TESTE
    não têm o prefixo)."""
    u = a.get("usina") or ""
    return carteira(u) if " - " in u else (a.get("cliente") or "").strip()


def carteiras_de(a: dict) -> set:
    """TODAS as carteiras do ativo: o campo cliente E o prefixo da usina. O Fracttal diverge entre os dois — cliente
    'Ultragaz' com usina 'Utragaz - Ibirapuã 1 - BA' (faltou o 'l') —, e o filtro de usinas tem de aceitar os dois."""
    out = set()
    c = (a.get("cliente") or "").strip()
    if c:
        out.add(c)
    u = a.get("usina") or ""
    if " - " in u and carteira(u):
        out.add(carteira(u))
    return out


def clientes_reais(assets: list) -> set:
    return {a.get("cliente") for a in (assets or []) if a.get("tipo") in CARTEIRA_EQUIP and a.get("cliente")}


def clientes(assets: list) -> list:
    """O combo Cliente (_fill_clientes): só quem tem equipamento de planta — o Almoxarifado fica de fora."""
    return sorted(clientes_reais(assets))


def usinas_para(assets: list, cliente) -> list:
    """O combo Usina (_fill_usinas): filtrado pela carteira do cliente, ou TODAS as usinas de planta sem cliente."""
    reais = clientes_reais(assets)
    base = [a for a in (assets or []) if a.get("usina") and a.get("tipo") in CARTEIRA_EQUIP and (carteiras_de(a) & reais)]
    if cliente:
        return sorted({a["usina"] for a in base if cliente in carteiras_de(a)})
    return sorted({a["usina"] for a in base})


def cliente_da_usina(assets: list, usina) -> str:
    """O cliente de uma usina pelo campo cliente de um ativo dela (a fonte do combo); cai no prefixo se nenhum tiver.
    É o auto-preenchimento: 'Utragaz - …' escolhe 'Ultragaz' mesmo com o typo."""
    for a in assets or []:
        if a.get("usina") == usina and (a.get("cliente") or "").strip():
            return a["cliente"].strip()
    return carteira(usina)


def usinas_alvo(assets: list, usina, cliente, multi: bool) -> set:
    """As usinas que a tabela cobre (_usinas_alvo): todas as do cliente no modo várias usinas, senão a escolhida."""
    if multi and cliente:
        reais = clientes_reais(assets)
        return {a["usina"] for a in (assets or [])
                if a.get("usina") and a.get("tipo") in CARTEIRA_EQUIP
                and cliente in carteiras_de(a) and (carteiras_de(a) & reais)}
    return {usina} if usina else set()


def _linha(a: dict) -> dict:
    """O ativo como a tabela (e o clonador) precisa — o registro inteiro do catálogo fica no servidor."""
    return {"id": a.get("id"), "code": a.get("code"), "label": a.get("label"), "tipo": a.get("tipo"),
            "usina": a.get("usina"), "usina_curta": api._usina_short(a.get("usina")), "cliente": a.get("cliente")}


def alvo(assets: list, usina=None, cliente=None, multi: bool = False, marcados=()) -> dict:
    """O `_on_usi` inteiro, numa resposta: (1) a usina nomeada preenche o Cliente, se ele for um cliente do combo;
    (2) as usinas alvo, com o cliente JÁ preenchido; (3) a poda — o marcado é sempre um subconjunto do que a tabela pode
    mostrar, porque ativo que some da tela e continua marcado viraria uma OS que ninguém revisou; (4) o filtro de tipo,
    só com os equipamentos do COS; (5) os candidatos, na ordem do app (usina, rótulo) — o "marcados primeiro" é feito
    pela tela, que sabe o que está marcado a cada redesenho.

    `usinas` volta junto: é o combo Usina re-filtrado para o cliente efetivo (o `_fill_usinas` que o app roda depois do
    auto-preenchimento), para a tela não precisar de outra ida ao servidor."""
    assets = assets or []
    usina = usina or None
    cliente = cliente or None
    if usina and " - " in usina:
        cart = cliente_da_usina(assets, usina)
        if cart and cart != cliente and cart in clientes_reais(assets):
            cliente = cart
    usinas = usinas_alvo(assets, usina, cliente, bool(multi))
    ids_alvo = {a.get("id") for a in assets if a.get("usina") in usinas}
    tipos = sorted({a["tipo"] for a in assets if a.get("usina") in usinas and a.get("tipo") in cs.COS_EQUIP}) if usinas else []
    cands = [a for a in assets if a.get("usina") in usinas and a.get("tipo")]   # ALLOWED_TIPOS = qualquer tipo não vazio
    cands.sort(key=lambda x: (x.get("usina") or "", x.get("label") or ""))
    return {"cliente": cliente or "", "usinas": usinas_para(assets, cliente), "tipos": tipos,
            "ativos": [_linha(a) for a in cands], "marcados": [i for i in ler_ids(list(marcados)) if i in ids_alvo]}


# ── o ativo genérico (usina de terceiros) ──────────────────────────────────────────────────────────────────────────
def ativo_generico(cliente, usina) -> dict:
    """Asset sintético do genérico com o cliente/usina digitados (_generic_asset) — alimenta título e criação."""
    return {"id": GENERICO_ID, "code": "GRID", "id_type_item": 2, "id_parent": None,
            "id_group_task": None, "tipo": "Usina", "description": GENERICO_DESC,
            "label": GENERICO_LABEL,
            "usina": (usina or "").strip(), "cliente": (cliente or "").strip()}


# ── as peças do título / observação (espelhos de _codigos, _equip_nome, _acao_txt, _tipo_os, _falha, _obs_final) ──
def _cli(st: Estado):
    return ((st.cliente or "").strip() or None) if st.terceiros else (st.cliente or None)


def _usi(st: Estado):
    return ((st.usina or "").strip() or None) if st.terceiros else (st.usina or None)


def _codigos(st: Estado) -> list:
    return list(st.codigos) if st.cat == cs.CAT_A else []          # proteção só existe na categoria A; B/C = --/--


def _equip_nome(st: Estado, asset) -> str:
    return api._asset_short_name(asset) if asset else (st.onde if st.cat == cs.CAT_A else "Equipamento")


def _acao(st: Estado) -> str:
    return cs.acao_texto(st.cat, st.remoto)                          # escolha do operador em QUALQUER categoria


def _tipo_os(st: Estado) -> str:
    return cs.TIPO_INSPECAO if st.tipo == 1 else cs.TIPO_RELIGAMENTO


def _falha(st: Estado, equip: str = "") -> str:
    """Texto 'Falha:' por categoria (A = onde atuou; B = o equipamento marcado; C = fixo pela causa)."""
    if st.cat == cs.CAT_A:
        return cs.falha_texto(cs.CAT_A, st.onde, _codigos(st))
    if st.cat == cs.CAT_B:
        return cs.falha_texto(cs.CAT_B, equip or "Equipamento", motivo_b=st.falha_b)
    return cs.falha_texto(cs.CAT_C, causa_c=st.causa_c)


def _obs_final(st: Estado, obs_pipe: str) -> str:
    """Observação = padrão pipe + (se houver) o comentário do operador numa nova linha."""
    extra = (st.obs or "").strip()
    return obs_pipe + ("\n" + extra if extra else "")


# ── "Registrada no Fracttal como" (_tarefa_nome, _classif_nomes, _crit_id, _crit_nome, _tipo_dict) ────────────────
def tarefa_nome(st: Estado) -> str:
    """Mapa do PCM (23/07): A (cabine/usina/transf) = Religamento · B (inversor) = Corretiva Emergencial ·
    C (comunicação) = Corretiva · Inspeção = Corretiva Emergencial. A troca manual (ovr) vence."""
    if st.ovr.get("tipo"):
        return st.ovr["tipo"]
    if _tipo_os(st) == cs.TIPO_INSPECAO:
        return "Corretiva Emergencial"
    if st.cat == cs.CAT_A:
        return "Religamento Remoto" if _acao(st) == cs.ACAO_REMOTO else "Religamento"
    if st.cat == cs.CAT_B:
        return "Corretiva Emergencial"
    return "Corretiva"


def classif_nomes(st: Estado) -> tuple:
    """(Classificação 1, Classificação 2). Cat C = 'Preencher': o PCM diz "depende do contexto" e o operador escolhe."""
    if _tipo_os(st) == cs.TIPO_INSPECAO:
        auto1 = "Emergencial"
    elif st.cat == cs.CAT_A:
        auto1 = "Religamento"
    elif st.cat == cs.CAT_B:
        auto1 = "Emergencial"
    else:
        auto1 = PREENCHER
    return (st.ovr.get("c1") or auto1, st.ovr.get("c2") or "Elétrica")


def crit_id(st: Estado) -> int:
    return st.ovr.get("crit") or api.CRITICIDADE_MUITO_ALTO


def crit_nome(st: Estado) -> str:
    cid = crit_id(st)
    return next((n for n, i in api.CRITICIDADES if i == cid), "Muito alto")


def _by_desc(classif, chave: str, desc: str):
    for it in (classif or {}).get(chave, []) or []:
        if (it.get("description") or "").strip().lower() == desc.strip().lower():
            return it.get("id")
    return None


def tipo_dict(st: Estado, classif) -> dict:
    """O `tipo` do create: id do tipo de tarefa e criticidade; a Classificação 1 só entra se casar com a lista do
    Fracttal, e a 2 só com a 1 presente — é assim no app (`_tipo_dict`)."""
    d = {"id_main": _by_desc(classif, "tipos", tarefa_nome(st)), "id_priorities": crit_id(st)}
    c1nome, c2nome = classif_nomes(st)
    c1 = _by_desc(classif, "c1", c1nome)
    if c1:
        d["id_c1"] = c1
        d["desc_c1"] = c1nome
        c2 = _by_desc(classif, "c2", c2nome)
        if c2:
            d["id_c2"] = c2
            d["desc_c2"] = c2nome
    return d


def meta(st: Estado) -> dict:
    c1, c2 = classif_nomes(st)
    return {"tarefa": tarefa_nome(st), "c1": c1, "c2": c2, "crit": crit_nome(st), "c1_preencher": c1 == PREENCHER}


# ── permissivo e fora de serviço ───────────────────────────────────────────────────────────────────────────────────
def permissivo(st: Estado) -> dict:
    """O permissivo de segurança: 86 (lockout) na categoria A barra o remoto — a OS tem de abrir para a equipe."""
    if st.cat == cs.CAT_A and cs.exige_equipe_campo(_codigos(st)):
        return {"texto": PERM_86, "nivel": "alerta"}
    if st.remoto:
        return {"texto": PERM_REMOTO_C if st.cat == cs.CAT_C else PERM_REMOTO, "nivel": "ok"}
    return {"texto": PERM_LOCAL, "nivel": "info"}


def oos(st: Estado) -> dict:
    """Fora de serviço = a OS NÃO tem data de conclusão (nasce aberta). Já realizada = o ativo voltou (_oos_ativo)."""
    ativo = not st.realizada
    return {"ativo": ativo, "texto": OOS_SIM if ativo else OOS_NAO,
            "curto": "Fora de Serviço: Sim" if ativo else "Fora de Serviço: Não"}


# ── a prévia (_preview) ────────────────────────────────────────────────────────────────────────────────────────────
def _ativo_da_previa(st: Estado, assets: list):
    if st.terceiros:
        return ativo_generico(_cli(st), _usi(st)) if _usi(st) else None
    ids = set(st.ids)
    return next((a for a in (assets or []) if a.get("id") in ids), None)     # o 1º marcado na ordem do catálogo


def preview(st: Estado, assets: list) -> dict:
    """Título, observação, "Registrada no Fracttal como", permissivo e fora de serviço — o `_preview` do app."""
    asset = _ativo_da_previa(st, assets)
    equip = _equip_nome(st, asset)
    usina = api._usina_short(asset.get("usina")) if asset else (_usi(st) or "{usina}")
    acao = _acao(st)
    motivo = cs.motivo_titulo(_tipo_os(st), equip, acao)
    # sem ativo do catálogo o título é montado à mão — no MESMO padrão do perf_os_nome, senão a prévia mente
    tit = api.perf_os_nome(asset, motivo) if asset else f"[{equip}] - {motivo}"
    ids = set(st.ids)
    n = 0 if st.terceiros else sum(1 for a in (assets or []) if a.get("id") in ids)
    # o sufixo é do "Vários ativos": no "Mesmo ativo" as OS são todas do primeiro (27/09 — o app dizia o sufixo ali também)
    return {"titulo": tit + (SUFIXO_VARIOS if n > 1 and st.modo != 1 else ""),
            "observacao": _obs_final(st, cs.observacao(usina, _codigos(st), acao, _falha(st, equip))),
            "meta": meta(st), "permissivo": permissivo(st), "oos": oos(st)}


# ── as subtarefas obrigatórias (_subtarefas) ───────────────────────────────────────────────────────────────────────
def _opts(*opcoes) -> list:
    return [{"description": o} for o in opcoes]


def subtarefas(st: Estado, realizada: bool, dados: dict) -> tuple:
    """Subtarefas OBRIGATÓRIAS por tipo. Escolhas viram tipo Lista (menu, id 7). Já realizada → já respondidas; aberta →
    em branco para o técnico responder no Fracttal. (No app o parâmetro se chama `remoto`, mas o que chega nele é o
    "Esta tarefa já foi realizada?" — é a finalização que decide, não a ação.)"""
    LST = 7                                                         # tipo Lista (DROPDOWN)
    if _tipo_os(st) == cs.TIPO_INSPECAO:
        subs = [
            {"description": "Equipamento e sintoma", "id_task_form_item_type": 1},
            {"description": "Diagnóstico", "id_task_form_item_type": LST,
             "dropdown_options": _opts("Desligado", "Só sem comunicação (segue gerando)")},
            {"description": "Ação", "id_task_form_item_type": LST,
             "dropdown_options": _opts("Religamento local", "Operador avisado")},
            {"description": "Normalizado?", "id_task_form_item_type": LST,
             "dropdown_options": _opts("Sim", "Não", "Parcial")},
        ]
        vals = [dados["falha"], "", "", ""]                         # técnico preenche diagnóstico/ação/resultado
    else:
        subs = [
            {"description": "Categoria e proteção", "id_task_form_item_type": 1},
            {"description": "Onde atuou", "id_task_form_item_type": 1},
            {"description": "Foi necessário religamento?", "id_task_form_item_type": LST,
             "dropdown_options": _opts("Sim", "Não — já normalizado")},
            {"description": "Resultado", "id_task_form_item_type": LST,
             "dropdown_options": _opts("Normalizado", "Persistiu", "Parcial")},
        ]
        vals = [dados["cat_prot"], dados["onde"],
                ("Sim" if realizada else ""), ("Normalizado" if realizada else "")]
    for s in subs:
        s["is_required"] = True
    return subs, (vals if realizada else None)


# ── o bloco "O ativo falhou?" (_sel_desc, _sugerir_falha, e o falha_dict do _criar) ────────────────────────────────
def _texto_item(it: dict) -> str:
    return str(it.get("description") or "?")                        # o texto do item no combo (`or "?"` do app)


def escolher_desc(itens, desc):
    """O item que o `_sel_desc` do app selecionaria para `desc` (ou None): igual; igual sem diferença de caixa; e por
    prefixo, nos dois sentidos, com o MAIS LONGO vencendo — senão "Desligamento Inversor" seria truncado para
    "Desligamento", e sufixos como " (MCO)" não casariam."""
    pares = [(it, _texto_item(it)) for it in (itens or []) if isinstance(it, dict)]
    for it, t in pares:                                             # QComboBox.findText: exato, sensível à caixa
        if t == desc:
            return it
    alvo_ = (desc or "").strip().lower()
    for it, t in pares:
        if t.strip().lower() == alvo_:
            return it
    if alvo_:
        melhor, mlen = None, -1
        for it, t in pares:
            tl = t.strip().lower()
            if tl and (tl.startswith(alvo_) or alvo_.startswith(tl)) and len(tl) > mlen:
                melhor, mlen = it, len(tl)
        return melhor
    return None


# (tipo, causa) sugeridos por caso — `None` = o app não mexe naquele combo (B só sugere o tipo). A detecção é SEMPRE o
# monitoramento (Levi, 14/07). A Inspeção tem os seus; senão vale a categoria.
SUGESTAO_FALHA = {
    "insp": ("Desligamento Inversor", "Perda de sinal em redes de comunicação"),
    cs.CAT_C: ("Conectividade/Comunicação", "Perda de sinal em redes de comunicação"),
    cs.CAT_B: ("Desligamento Inversor", None),
    cs.CAT_A: ("Desligamento", "Queda de energia"),                 # cabine/usina/transf — PCM: Desligamento
}
DETECCAO_SEMPRE = "Monitoramento de Condição Online (MCO)"


def sugestoes_falha(listas) -> dict:
    """Os ids que o `_sugerir_falha` escolheria em cada caso, já resolvidos contra as listas do Fracttal. A tela aplica
    a do momento (tipo e categoria de agora) — e só nos combos com id: o que não casou fica como está, como no app."""
    listas = listas or {}
    det = escolher_desc(listas.get("metodos"), DETECCAO_SEMPRE)
    out = {}
    for chave, (tipo, causa) in SUGESTAO_FALHA.items():
        it_t = escolher_desc(listas.get("tipos"), tipo)
        it_c = escolher_desc(listas.get("causas"), causa) if causa else None
        out[chave] = {"id_type": it_t.get("id") if it_t else None, "id_cause": it_c.get("id") if it_c else None,
                      "id_detection": det.get("id") if det else None}
    return out


def _idx_severidade_alta() -> int:
    """Índice de 'Muito alto' na Severidade (0 se a lista mudar de nome) — varias_os.py::_idx_severidade_alta."""
    for i, (nome, _id) in enumerate(api.FALHA_SEVERIDADES):
        if nome.strip().lower().startswith("muito alto"):
            return i
    return 0


# SEMPRE "Muito alto" no COS (Levi, 30/07): a lista do Fracttal começa em "Muito baixo" e o combo nascia no item 0, então
# toda OS de religamento saía com a severidade MÍNIMA — o inverso do que o COS significa.
SEVERIDADE_PADRAO = api.FALHA_SEVERIDADES[_idx_severidade_alta()][1]


def ordenar_pessoas(pessoas) -> list:
    return sorted([p for p in (pessoas or []) if isinstance(p, dict)], key=lambda x: (x.get("name") or "").lower())


def _item_por_id(itens, valor):
    s = "" if valor is None or isinstance(valor, bool) else str(valor).strip()
    if not s:
        return None
    return next((it for it in (itens or [])
                 if isinstance(it, dict) and it.get("id") is not None and str(it.get("id")) == s), None)


def _par_por_id(pares, valor):
    s = "" if valor is None or isinstance(valor, bool) else str(valor).strip()
    if not s:
        return None
    return next(((n, i) for n, i in pares if str(i) == s), None)


# ── datas ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def agora_brt() -> dt.datetime:
    return dt.datetime.now(BRT).replace(second=0, microsecond=0)


def fmt_local(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M")                              # o valor de um <input type=datetime-local>


def data_brt(texto) -> dt.datetime:
    """'2026-09-12T14:00' (o datetime-local) → aware em Brasília: o `.replace(tzinfo=brt)` que o `_criar` faz sobre o
    QDateTimeEdit. Se vier com fuso, o instante é preservado."""
    s = str(texto or "").strip()
    if not s:
        raise ValueError("vazia")
    d = dt.datetime.fromisoformat(s)
    return d.astimezone(BRT) if d.tzinfo else d.replace(tzinfo=BRT)


# ── a criação (_criar) ─────────────────────────────────────────────────────────────────────────────────────────────
def criacao(corpo: dict, assets: list, classif: dict, falhas: dict, agora: dt.datetime | None = None) -> tuple:
    """Do JSON da tela → (trilho, argumentos posicionais, erro).

    As validações são as do `_criar`, NA MESMA ORDEM (é a ordem que decide qual frase a pessoa lê primeiro), e os
    argumentos saem posicionais como lá:
      - Vários ativos · 1 data → create_work_orders_bulk(ativos, "Religamento", tarefa, subs, "", code, name,
        id_personnel, None, "", tipo, finalizar, event_date, None, None, por_ativo, falha)
      - Mesmo ativo · várias datas → create_work_orders_datas(ativo, titulo, tarefa, subs, datas, code, name,
        id_personnel, None, obs, tipo, finalizar, None, falha)
    `classif` é o get_tipos_classif e `falhas` o get_falha_listas — as listas que no app estão nos combos."""
    try:
        st = estado(corpo)
    except ErroTela as e:
        return "", (), str(e)
    agora = agora or dt.datetime.now(BRT)
    if st.terceiros:                                                # 1 ativo genérico com o Cliente/Usina digitados
        if not (_cli(st) and _usi(st)):
            return "", (), ERRO_TERCEIROS
        ativos = [ativo_generico(_cli(st), _usi(st))]
    else:
        ids = set(st.ids)
        ativos = [a for a in (assets or []) if a.get("id") in ids]    # o registro INTEIRO, na ordem do catálogo
        if not ativos:
            return "", (), ERRO_SEM_ATIVO
    p = st.responsavel
    if not isinstance(p, dict) or not p.get("id_personnel"):
        return "", (), ERRO_SEM_RESP
    tipo = tipo_dict(st, classif)
    if not tipo.get("id_main"):
        return "", (), ERRO_TIPOS
    if classif_nomes(st)[0] == PREENCHER:                           # cat C: o PCM diz "depende do contexto"
        return "", (), ERRO_PREENCHER
    codigos = _codigos(st)
    if st.cat == cs.CAT_A and not codigos:
        return "", (), ERRO_PROTECAO
    if cs.SEM_TRIP in codigos and len(codigos) > 1:
        return "", (), ERRO_SEM_TRIP_JUNTO
    falha_in = st.falha
    marcada = _bool(falha_in.get("marcado"), False)
    listas = falhas or {}
    if marcada:
        it_t = _item_por_id(listas.get("tipos"), falha_in.get("id_type"))
        it_c = _item_por_id(listas.get("causas"), falha_in.get("id_cause"))
        it_d = _item_por_id(listas.get("metodos"), falha_in.get("id_detection"))
        if not (it_t and it_c and it_d):
            return "", (), ERRO_FALHA
        sev = _par_por_id(api.FALHA_SEVERIDADES, falha_in.get("id_severity"))
        dano = _par_por_id(api.FALHA_DANOS, falha_in.get("id_damage"))
        if not (sev and dano):
            return "", (), ERRO_SEV_DANO
    realizada = st.realizada
    acao = _acao(st)
    cat_prot = (f"{cs.CATEGORIAS[st.cat]} — {cs.juntar_codigos(codigos)}" if st.cat == cs.CAT_A
                else (f"{cs.CATEGORIAS[st.cat]} — {st.falha_b}" if st.cat == cs.CAT_B else st.causa_c))
    onde_val = st.onde if st.cat == cs.CAT_A else "—"
    subs, respostas = subtarefas(st, realizada, {"falha": _falha(st, _equip_nome(st, ativos[0])),
                                                 "cat_prot": cat_prot, "onde": onde_val})
    falha_dict = None
    if marcada:
        falha_dict = {"id_type": it_t.get("id"), "type_desc": _texto_item(it_t),
                      "id_cause": it_c.get("id"), "cause_desc": _texto_item(it_c),
                      "id_detection": it_d.get("id"), "detection_desc": _texto_item(it_d),
                      "id_severity": sev[1], "severity_desc": sev[0],
                      "id_damage": dano[1], "damage_desc": dano[0],
                      "out_of_service": not realizada}              # derivado: sem data de conclusão → fora de serviço
    code, name, id_personnel = p.get("code"), p.get("name"), p.get("id_personnel")
    teto = agora + _FOLGA_FUTURO

    if st.modo == 1:                                                # "Mesmo ativo · várias datas" → N OS para o MESMO ativo
        if not st.datas:
            return "", (), ERRO_SEM_DATA
        a = ativos[0]
        equip = _equip_nome(st, a)
        usina = api._usina_short(a.get("usina"))
        titulo = api.perf_os_nome(a, cs.motivo_titulo(_tipo_os(st), equip, acao))
        obs = _obs_final(st, cs.observacao(usina, codigos, acao, _falha(st, equip)))
        datas = []
        for linha in st.datas:
            try:
                ini = data_brt(linha.get("evento"))
            except (ValueError, TypeError):
                return "", (), ERRO_DATA
            if ini > teto:
                return "", (), ERRO_FUTURO
            if realizada:
                try:
                    fim = data_brt(linha.get("conclusao"))
                except (ValueError, TypeError):
                    return "", (), ERRO_DATA
                if fim < ini:
                    return "", (), ERRO_LINHA.format(ini)
                datas.append((ini, fim))
            else:
                datas.append(ini)
        finalizar = ({"to_in_review": st.em_verificacao, "id_assigned_user": id_personnel, "name": name,
                      "respostas": respostas} if realizada else None)
        return TRILHO_DATAS, (a, titulo, tarefa_nome(st), subs, datas, code, name, id_personnel,
                              None, obs, tipo, finalizar, None, falha_dict), ""

    # "Vários ativos · 1 data" → 1 OS por ativo, cada uma com o título e a observação do SEU ativo
    try:
        event_date = data_brt(st.evento)
    except (ValueError, TypeError):
        return "", (), ERRO_DATA
    if event_date > teto:
        return "", (), ERRO_FUTURO
    finalizar = None
    if realizada:
        try:
            fim = data_brt(st.conclusao)
        except (ValueError, TypeError):
            return "", (), ERRO_DATA
        if fim < event_date:
            return "", (), ERRO_CONCLUSAO
        finalizar = {"to_in_review": st.em_verificacao, "final_date": fim,
                     "id_assigned_user": id_personnel, "name": name, "respostas": respostas}
    por_ativo = {}
    for a in ativos:
        equip = _equip_nome(st, a)
        usina = api._usina_short(a.get("usina"))
        motivo = cs.motivo_titulo(_tipo_os(st), equip, acao)
        por_ativo[a["code"]] = {"description": api.perf_os_nome(a, motivo),
                                "note": _obs_final(st, cs.observacao(usina, codigos, acao, _falha(st, equip)))}
    return TRILHO_BULK, (ativos, "Religamento", tarefa_nome(st), subs, "", code, name, id_personnel,
                         None, "", tipo, finalizar, event_date, None, None, por_ativo, falha_dict), ""


def mensagem_resultado(res) -> dict:
    """[{'code'|'data','ok','os'|'erro'}] → a mensagem do `_ok`: "N OS criada(s) — Nº …." + Avisos (até 6) + Falhas
    (até 8). `ok` > 0 é o que manda a tela limpar para a próxima, como o `_reset` depois do "OSs criadas"."""
    res = [r for r in (res if isinstance(res, list) else []) if isinstance(r, dict)]
    ok = [r for r in res if r.get("ok")]
    fail = [r for r in res if not r.get("ok")]
    folios = [(r.get("os") or {}).get("wo_folio") for r in ok if (r.get("os") or {}).get("wo_folio")]
    msg = f"{len(ok)} OS criada(s)" + (f" — Nº {', '.join(str(f) for f in folios)}" if folios else "") + "."
    avisos = [str((r.get("os") or {}).get("aviso")) for r in ok if (r.get("os") or {}).get("aviso")]
    if avisos:
        msg += "\n\nAvisos:\n- " + "\n- ".join(avisos[:6])
    if fail:
        msg += "\n\nFalhas:\n- " + "\n- ".join(f"{r.get('code') or r.get('data')}: {r.get('erro')}" for r in fail[:8])
    return {"ok": len(ok), "falhas": len(fail), "folios": folios, "mensagem": msg}


# ── o clonador do COS (_clone_ok / _aplicar_clone) ─────────────────────────────────────────────────────────────────
def _casa_opcao(opcoes, falha_baixa: str) -> str:
    """A opção cujo texto INTEIRO aparece na falha da OS, a mais longa vencendo (as da C se contêm)."""
    melhor, mlen = "", 0
    for o in opcoes:
        t = o.strip().lower()
        if t and t in falha_baixa and len(t) > mlen:
            melhor, mlen = o, len(t)
    return melhor


def modelo_clone(d, assets: list) -> tuple:
    """Uma OS do COS → o que remonta o formulário: (modelo, erro, status HTTP).

    Tipo pelo título (tem "inspeção"), categoria pelo `categoria_de`, proteções pelo pipe, falha do inversor / causa da
    comunicação pela opção contida na falha, ação pelo texto exato, e o ativo pelo código. A tela aplica na ordem do
    app (tipo → categoria → proteções → falha → ação → cliente → usina → tipo de equipamento → marcado), porque cada
    passo tem os seus efeitos (a ação padrão da categoria, a sugestão da falha…).

    Diferença deliberada: OS sem código de ativo não casa com ativo nenhum. O `next(...)` do app, com código vazio,
    pegaria o primeiro ativo do catálogo que também não tem código — uma OS para um ativo que ninguém escolheu."""
    if not isinstance(d, dict):
        return None, CLONE_NAO_ACHOU, 404
    info = cs.parse_observacao(d.get("notas"))
    if not (info["codigos"] or info["falha"] or info["acao"]):
        return None, CLONE_FORA_PADRAO.format(d.get("folio") or ""), 400
    titulo = (d.get("descricao") or "").lower()
    tipo = 1 if ("inspeção" in titulo or "inspecao" in titulo) else 0
    cat = cs.categoria_de(info["codigos"], info["falha"])
    fal = (info["falha"] or "").lower()
    code = (d.get("code") or "").strip()
    a = next((x for x in (assets or []) if (x.get("code") or "").strip() == code), None) if code else None
    return {"folio": d.get("folio"), "tipo": tipo, "cat": cat,
            "codigos": [c for c in CHIPS if c in info["codigos"]],        # só os chips que existem, como o setChecked
            "falha_b": _casa_opcao(cs.FALHAS_B, fal) if cat == cs.CAT_B else "",
            "causa_c": _casa_opcao(cs.CAUSAS_C, fal) if cat == cs.CAT_C else "",
            "remoto": (info["acao"] or "").strip().lower() == cs.ACAO_REMOTO.lower(),
            "ativo": dict(_linha(a), carteira=carteira_de(a)) if a else None,
            "mensagem": CLONE_OK.format(d.get("folio") or "")}, "", 200


# ── a página ───────────────────────────────────────────────────────────────────────────────────────────────────────
def contexto_pagina(assets: list, agora: dt.datetime) -> dict:
    """O que o cos.html precisa para abrir como a tela recém-aberta do app: os combos, as listas fixas e a prévia do
    estado inicial (Religamento · A · Remoto · já realizada), já montada — sem esperar a 1ª ida ao servidor."""
    st0 = Estado()
    return {
        "tipos": TIPOS, "modos": MODOS, "categorias": CATEGORIAS_ROTULO, "acoes": ACOES_ROTULO,
        "clientes": clientes(assets), "usinas": usinas_para(assets, None),
        "protecoes": list(cs.PROTECOES), "sem_trip": cs.SEM_TRIP, "onde": cs.ONDE, "falhas_b": cs.FALHAS_B,
        "causas_c": cs.CAUSAS_C, "ansi": cs.ANSI_REF, "severidades": api.FALHA_SEVERIDADES, "danos": api.FALHA_DANOS,
        "sev_padrao": SEVERIDADE_PADRAO, "oos": oos(st0),
        "agora": fmt_local(agora), "evento": fmt_local(agora - dt.timedelta(minutes=10)), "conclusao": fmt_local(agora),
        "dados": {"cats": list(CATS),
                  "tipo_da_cat": {c: (1 if cs.TIPO_DA_CAT[c] == cs.TIPO_INSPECAO else 0) for c in CATS},
                  "sem_trip": cs.SEM_TRIP, "sev_padrao": SEVERIDADE_PADRAO,
                  "criticidades": [[n, i] for n, i in api.CRITICIDADES],
                  "preview": preview(st0, []), "textos": TEXTOS_JS},
    }
