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

import requests

import solic_spec as sp

BASE = "https://app.gridco.com.br/db_performace"
WORKBOOK = "os_creator"
ABA = "temas"
ABA_ID_PADRAO = 415        # atalho: evita uma requisição por leitura; confirmado na criação
TIMEOUT = 20

_cache = None              # [{chave, ...}] da última leitura bem-sucedida
_aba_id = None


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


def carregar(buscar=None, forcar=False) -> list:
    """Os temas do banco. Cai na semente do código se a API não responder."""
    global _cache
    if _cache is not None and not forcar and buscar is None:
        return _cache
    try:
        itens = [x for x in (_de_linha(l) for l in _linhas(buscar)) if x]
    except Exception:
        return _cache if _cache is not None else da_semente()
    if not itens:
        return _cache if _cache is not None else da_semente()
    itens.sort(key=lambda x: (x.get("arquivado", False), x.get("nome") or x["chave"]))
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
    uma vez na abertura do app.

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
    sp.TEMAS.clear()
    sp.TEMAS.update(novos)
    sp.POR_TEMA.clear()
    sp.POR_TEMA.update(passos)
    return True


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
