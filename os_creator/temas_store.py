# -*- coding: utf-8 -*-
"""Os temas da Solicitação, guardados no banco da Gridco em vez de no código.

POR QUE SAIR DO CÓDIGO. Até 04/09/2026 os temas viviam em `solic_spec.py`, num dicionário
Python: mudar o nome de um tema, acrescentar uma subtarefa ou marcar anexo obrigatório exigia
editar código e subir release. O Levi pediu que isso passasse para a mão do PCM, e liberou o
banco ("pode usar o banco", 04/09).

ONDE, e por que não nos outros lugares óbvios:

- **Workbook próprio** (`os_creator`), e não uma aba no `plataforma_estado`: aquele workbook é
  publicado pela plataforma com `sync-xlsx?replace=true`, que substitui o workbook INTEIRO (ver
  `plataforma/estado_backup.py:publicar`). Uma aba de temas lá seria apagada no backup seguinte.
- **Não numa aba de planilha**: o pipeline de coleta sobe os .xlsx de origem com `replace=true`,
  e escrita em aba que ele alimenta morre no sync — a armadilha que `tickets_escrita.py`
  documenta no cabeçalho.

O FORMATO é o mesmo das abas de estado da plataforma: duas colunas, `chave` e `valor`, com o
valor em JSON. Uma linha por tema.

LEITURA É ABERTA (sem credencial), como em `tickets_api.py`. ESCRITA exige o GRIDCO_SQL_TOKEN,
e por isso mora atrás de `pode_gravar()` — quem não tem o token vê os temas e não consegue
salvar, em vez de descobrir isso no meio de uma edição.

O CÓDIGO CONTINUA SENDO A SEMENTE. Se o banco estiver fora do ar, `solic_spec` responde e a
tela funciona igual — só não salva. Sem isso, uma queda da API deixaria o PCM sem tema nenhum
para escolher, que é pior do que temas desatualizados.
"""
import json
import threading
import time

import requests

import solic_spec as sp

BASE = "https://app.gridco.com.br/db_performace"
WORKBOOK = "os_creator"
ABA = "temas"
ABA_ID_PADRAO = 415        # atalho: evita uma requisição por leitura; confirmado na criação
TIMEOUT = 20
TTL = 300                  # s: de quanto em quanto o os_web relê (o tema salvo no app chega assim)
TTL_ERRO = 60              # s: banco fora → tenta de novo depois disto, sem segurar cada requisição

_cache = None              # [{chave, ...}] da última leitura bem-sucedida
_aba_id = None
_estado = {"proxima": 0.0, "erro": ""}      # do `garantir`: quando reler, e o que deu errado na última
_trava = threading.Lock()


def _tok():
    """O GRIDCO_SQL_TOKEN desta máquina. Reusa o do módulo de tickets: é a mesma credencial,
    e duas cópias da mesma regra de busca divergiriam na primeira mudança."""
    try:
        from tickets_escrita import _token
        return _token()
    except Exception:
        return ""


def pode_gravar() -> bool:
    return bool(_tok())


def aba_id() -> int:
    """O id da aba `temas`. Procura pelo NOME, e não confia só na constante.

    O id sai do banco quando a aba é criada; se um dia o workbook for recriado, o número muda.
    Perguntar custa uma requisição na primeira vez e evita gravar na aba de outra pessoa."""
    global _aba_id
    if _aba_id:
        return _aba_id
    try:
        r = requests.get(BASE + "/api/sheets", timeout=TIMEOUT)
        r.raise_for_status()
        for s in r.json():
            if s.get("workbook_key") == WORKBOOK and s.get("sheet_name") == ABA:
                _aba_id = int(s["id"])
                return _aba_id
    except Exception:
        pass
    _aba_id = ABA_ID_PADRAO
    return _aba_id


# ── leitura ───────────────────────────────────────────────────────────────────
def _linhas(buscar=None):
    """As linhas cruas da aba. `buscar` é injetável para o teste rodar sem rede."""
    if buscar:
        return buscar()
    r = requests.get("%s/api/sheets/%s/rows" % (BASE, aba_id()),
                     params={"limit": 1000, "offset": 0}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else (d.get("rows") or d.get("items") or [])


def _de_linha(l):
    """Uma linha do banco vira o dicionário de um tema, ou None se estiver quebrada.

    Linha ilegível é PULADA, não derruba a leitura: um JSON estragado num tema não pode tirar
    os outros treze da tela."""
    vals = l.get("values") or []
    if len(vals) < 2 or not str(vals[0] or "").strip():
        return None
    try:
        d = json.loads(vals[1] or "{}")
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    d["chave"] = str(vals[0]).strip()
    d["_linha"] = l.get("row_number")
    d.setdefault("subtarefas", [])
    d.setdefault("arquivado", False)
    # `etiquetas` NAO ganha default aqui de proposito: a ausencia da chave e o que diz "este
    # tema nunca foi salvo pela tela nova", e e ela que faz a Fila cair na regra antiga
    # (`exige_performance`) em vez de concluir que o tema nao leva etiqueta nenhuma.
    return d


def do_banco(buscar=None) -> list:
    """Os temas do banco e SÓ do banco: levanta se a API não responder, devolve [] se a aba estiver vazia.

    Existe para quem precisa saber se o que veio é do banco ou da semente — a abertura do app de mesa
    (`modelos_banco.py`). Reaplicar a semente por cima do código não é neutro: ela não guarda o `obrig` das
    subtarefas, e a opcional da Vegetação viraria obrigatória por causa de uma queda de rede."""
    itens = [x for x in (_de_linha(l) for l in _linhas(buscar)) if x]
    itens.sort(key=lambda x: (x.get("arquivado", False), x.get("nome") or x["chave"]))
    return itens


def carregar(buscar=None, forcar=False) -> list:
    """Os temas do banco. Cai na semente do código se a API não responder."""
    global _cache
    if _cache is not None and not forcar and buscar is None:
        return _cache
    try:
        itens = do_banco(buscar)
    except Exception:
        return _cache if _cache is not None else da_semente()
    if not itens:
        return _cache if _cache is not None else da_semente()
    if buscar is None:
        _cache = itens
    return itens


def da_semente() -> list:
    """Os temas como estão em `solic_spec.py` — o valor inicial e a rede de segurança."""
    out = []
    for chave, t in sorted(sp.TEMAS.items()):
        out.append({
            "chave": chave,
            "nome": t.get("nome", ""),
            "motivo": t.get("motivo", ""),
            "classif1": t.get("classif1", ""),
            "tipo_os": t.get("tipo", ""),
            "tipo_equipamento": t.get("tipo_equipamento", ""),
            "solicitacoes": t.get("solicitacoes", 0),
            "arquivado": False,
            "subtarefas": [{"desc": s["desc"], "tipo": s.get("tipo", "texto"),
                            "anexo": bool(s.get("anexo"))}
                           for s in sp.POR_TEMA.get(chave, [])],
        })
    return out


def aplicar_no_spec(itens=None):
    """Joga os temas do banco por cima dos do código, EM MEMÓRIA.

    É o que faz o resto do app não precisar saber que os temas mudaram de casa: `sp.TEMAS` e
    `sp.POR_TEMA` continuam sendo a fonte para a Solicitação, a Fila e o `titulo()`. Chamado
    na abertura do app (`modelos_banco.py`, com a leitura fora da thread da interface) e depois
    de salvar na tela de Temas. Até 27/09/2026 este parágrafo dizia "na abertura" e ninguém
    chamava: as outras máquinas ficavam com os temas do código até alguém salvar nelas.

    Tema ARQUIVADO some de `TEMAS` (ninguém mais pode escolhê-lo) mas o histórico não quebra:
    quem já foi criado com ele guarda o texto na própria OS."""
    itens = carregar() if itens is None else itens
    novos, passos = {}, {}
    for t in itens:
        if t.get("arquivado"):
            continue
        ch = t["chave"]
        novos[ch] = {"nome": t.get("nome", ""), "motivo": t.get("motivo", ""),
                     "classif1": t.get("classif1", ""), "tipo": t.get("tipo_os", ""),
                     "tipo_equipamento": t.get("tipo_equipamento", ""),
                     "dominio": (sp.TEMAS.get(ch) or {}).get("dominio", 0),
                     "solicitacoes": t.get("solicitacoes", 0)}
        if "etiquetas" in t:
            novos[ch]["etiquetas"] = list(t.get("etiquetas") or [])
        passos[ch] = [sp._s(x.get("desc", ""), x.get("tipo", "texto"),
                            anexo=bool(x.get("anexo"))) for x in t.get("subtarefas", [])]
    if not novos:
        return False
    # SEM ESVAZIAR NO MEIO, e nesta ordem. O os_web lê de várias threads, e quem lê pega a chave
    # em `TEMAS` para depois ir ao `POR_TEMA`. O `clear()` + `update()` de antes deixava um
    # instante com a lista vazia — página sem tema nenhum, ou "tema desconhecido" no meio de uma
    # aprovação. Entrando as subtarefas antes do tema, e saindo o tema antes das subtarefas, toda
    # chave visível em `TEMAS` tem as suas.
    sp.POR_TEMA.update(passos)
    sp.TEMAS.update(novos)
    for ch in [ch for ch in sp.TEMAS if ch not in novos]:
        del sp.TEMAS[ch]
    for ch in [ch for ch in sp.POR_TEMA if ch not in passos]:
        del sp.POR_TEMA[ch]
    return True


def garantir():
    """Para o os_web, que não tem "abertura": relê os temas do banco quando a última leitura passou
    do TTL e aplica. Nunca levanta. Banco fora ou aba vazia = fica o que já estava, sem reaplicar a
    semente (ver `do_banco`).

    O mesmo desenho do `chamado_modelos_store.garantir`: a janela seguinte é marcada ANTES de ler,
    então quem chega com uma leitura em curso segue com os temas já aplicados em vez de esperar.
    Banco fora custa uma espera por janela de `TTL_ERRO`, não uma por requisição."""
    agora = time.time()
    if agora < _estado["proxima"]:
        return
    with _trava:
        if agora < _estado["proxima"]:
            return
        _estado["proxima"] = agora + TTL
    try:
        itens = do_banco()
        if itens:
            aplicar_no_spec(itens)
        _estado["erro"] = ""
    except Exception as e:                  # noqa: BLE001 — banco fora: segue o que já estava
        _estado.update(proxima=time.time() + TTL_ERRO, erro=str(e)[:200])


def etiquetas_efetivas(t) -> list:
    """As etiquetas que este tema VAI aplicar de verdade — vindo do campo ou da regra antiga.

    Existe porque a tela de Temas e a Fila estavam DISCORDANDO. Os temas gravados antes de
    04/09 não têm o campo `etiquetas`; a Fila caía em `sp.exige_performance` e punha a
    PERFORMANCE em tracker, ETM e garantia, mas a tela de Temas mostrava lista vazia. O PCM não
    via — e não conseguia tirar — uma etiqueta que estava sendo aplicada. Foi o que o Levi
    relatou em 04/09: "não está mostrando os temas que tem a etiqueta de performance".

    Uma função só, usada pelas duas telas: enquanto o campo não existir, as duas leem a mesma
    regra; assim que o PCM salvar, as duas leem a lista dele."""
    if isinstance(t, str):
        t = sp.TEMAS.get(t) or {}
    t = t or {}
    if "etiquetas" in t:
        return [str(x).strip() for x in (t.get("etiquetas") or []) if str(x).strip()]
    chave = t.get("chave") or ""
    return ([sp.ETIQUETA_PERFORMANCE]
            if sp.exige_performance(chave, "", []) else [])


def tipo_equipamento(tema: str) -> str:
    """O tipo de equipamento do tema — o que FILTRA a lista de ativos na Solicitação.

    Pedido do Levi (04/09): "ao escolher o tipo de equipamento no tema, quando esse tema for
    escolhido deve filtrar os ativos na solicitação". Vazio significa não filtrar."""
    return str((sp.TEMAS.get(tema) or {}).get("tipo_equipamento") or "").strip()


# ── escrita ───────────────────────────────────────────────────────────────────
def _valor(t: dict) -> str:
    return json.dumps({k: t.get(k) for k in
                       ("nome", "motivo", "classif1", "tipo_os", "tipo_equipamento",
                        "solicitacoes", "arquivado", "subtarefas", "etiquetas")},
                      ensure_ascii=False)


def salvar(tema: dict, enviar=None) -> dict:
    """Grava UM tema. Cria a linha se a chave ainda não existe, atualiza se já existe.

    RELÊ ANTES DE GRAVAR, sempre. O `row_number` do banco NÃO é chave — ele muda quando linhas
    são inseridas ou removidas, e guardar o número da última leitura já fez a escrita cair na
    linha de outro registro (ver a memória dos tickets). A chave é a coluna `chave`."""
    if not pode_gravar():
        raise PermissionError(
            "Sem o GRIDCO_SQL_TOKEN nesta máquina: dá para ver e ajustar os temas na tela, "
            "mas não para salvar no banco. Peça o token ao Levi.")
    ch = str(tema.get("chave") or "").strip()
    if not ch:
        raise ValueError("tema sem chave")
    h = {"Authorization": "Bearer " + _tok(), "Content-Type": "application/json"}
    sid = aba_id()
    alvo = next((l for l in _linhas() if (l.get("values") or [""])[0] == ch), None)
    corpo = {"values": [ch, _valor(tema)]}
    if enviar:
        return enviar("PUT" if alvo else "POST", alvo, corpo)
    if alvo:
        r = requests.put("%s/api/sheets/%s/rows/%s" % (BASE, sid, alvo["row_number"]),
                         headers=h, data=json.dumps(corpo), timeout=TIMEOUT)
    else:
        r = requests.post("%s/api/sheets/%s/rows" % (BASE, sid),
                          headers=h, data=json.dumps(corpo), timeout=TIMEOUT)
    r.raise_for_status()
    global _cache
    _cache = None                     # a próxima leitura vai ao banco
    return r.json() if r.content else {}


def arquivar(chave: str, on: bool = True, **kw) -> dict:
    """Arquiva em vez de excluir. Um tema usado em 751 solicitações não pode sumir: some da
    lista de escolha e o histórico continua de pé."""
    t = next((x for x in carregar(forcar=True) if x["chave"] == chave), None)
    if t is None:
        raise KeyError(chave)
    t = dict(t, arquivado=bool(on))
    return salvar(t, **kw)
