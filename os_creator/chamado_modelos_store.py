# -*- coding: utf-8 -*-
"""Os modelos da inspeção de chamado — base, tipo de ativo e fornecedor — no banco da Gridco, editáveis pela tela
"Controle de fornecedores" do OS Creator web.

Pedido do Levi em 27/09/2026: "as subtarefas padrões utilizadas para a criação de chamado no inspeção de chamados …
mudam por ativo e fornecedor … algo parecido com o PCM no OS Creator app na parte de administração dos temas".

O MOLDE É O `temas_store.py`: o mesmo workbook (`os_creator`), a mesma forma chave/valor em JSON e o CÓDIGO como
semente e rede de segurança. As chaves:

    BASE                  toda inspeção, de qualquer ativo e fornecedor
    TIPO:<tipo de ativo>  o bloco do tipo ("TIPO:Inversor", "TIPO:Estrutura Trackers"…)
    MARCA:<fornecedor>    o que o fornecedor pede a mais, o canal de abertura e os tipos que ele atende

Bloco sem linha no banco vale o do código. Com o banco fora do ar a tela funciona igual — só não salva.

O QUE ISTO NÃO ALCANÇA: o App de Campo. Ele carrega a SUA cópia do pacote `chamado_garantia`, e é por ele que o
técnico abre a maioria das inspeções. Até o App ler esta aba, o que se salva aqui vale para a Inspeção do OS Creator
e o App segue no código. A tela diz isso em cima, porque é justamente a divergência que o pacote veio evitar ("a OS do
supervisor e a do técnico pedindo coisas diferentes ao mesmo fabricante").

COMO VALE NO PROCESSO: `aplicar()` reescreve, EM MEMÓRIA e NO LUGAR, as estruturas do `chamado_garantia.spec` (e o
`chamado_spec.CANAL`). No lugar, e não trocando o objeto, porque o `chamado_insp_spec` fez
`from chamado_garantia.spec import BASE, POR_TIPO, …` — nomes presos ao objeto de origem. Nada no disco muda.

QUEM APLICA: o os_web chama `garantir()` antes de cada rota da Inspeção (TTL de 5 min). O app de mesa lê UMA vez, na
abertura (`modelos_banco.py`: `carregar` no worker, `aplicar` na thread da interface) — o que se salva aqui chega nele
na próxima vez que ele abrir.
"""
import copy
import datetime as dt
import json
import re
import threading
import time

import chamado_insp_spec  # noqa: F401 — a ponte põe a raiz do repositório no sys.path, onde o pacote mora
import chamado_spec as cs
import gridco_abas as ga
from chamado_garantia import spec as sp

WORKBOOK = "os_creator"
NOME_ABA = "chamado_modelos"
COLUNAS = ["chave", "valor"]
TTL = 300          # s: de quanto em quanto tempo o processo relê o banco (a edição de outra máquina chega assim)
TTL_ERRO = 60      # s: banco fora do ar → tenta de novo depois disto, sem travar cada requisição

ABA = ga.Aba(WORKBOOK, NOME_ABA, COLUNAS)
SemCredencial = ga.SemCredencial

TIPOS = tuple(sp.TIPO_ID)                       # texto, longo, num, simnao, verif, lista
LIMITE_DESC = 250
LIMITE_CANAL = 300
LIMITE_NOME = 40


class Conflito(RuntimeError):
    """O bloco mudou no banco entre a leitura da tela e o clique em salvar."""

    def __init__(self, por: str, versao: str):
        self.por, self.versao = por, versao
        super().__init__("alguém salvou este bloco depois que você abriu a tela%s. Recarregue para ver a versão nova."
                         % ((" (%s)" % por) if por else ""))


# ── a foto do código, tirada na importação — é a ela que `aplicar` sempre volta antes de pôr o banco por cima ─────
def _foto() -> dict:
    return {"BASE": copy.deepcopy(sp.BASE), "POR_TIPO": copy.deepcopy(sp.POR_TIPO),
            # deepcopy por marca quebra a identidade dos clones de propósito: ela é refeita por `CLONES`
            "POR_FABRICANTE": {m: copy.deepcopy(v) for m, v in sp.POR_FABRICANTE.items()},
            "TIPOS_DA_MARCA": copy.deepcopy(sp.TIPOS_DA_MARCA), "MARCAS_CONHECIDAS": list(sp.MARCAS_CONHECIDAS),
            "CANAL": dict(cs.CANAL)}


_ORIG = _foto()
# No código, Brametal e Romiotto não têm lista própria: são o MESMO objeto da STI e da Hukseflux (chamado_spec,
# "CLONES (28/07)"). Enquanto ninguém salvar o clone sozinho, ele segue o original — inclusive a versão editada dele.
CLONES = {c: o for c, o in {"Brametal": "STI", "Romiotto": "Hukseflux"}.items()
          if c in sp.POR_FABRICANTE and sp.POR_FABRICANTE.get(c) is sp.POR_FABRICANTE.get(o)}

_estado = {"banco": None, "lido": 0.0, "proxima": 0.0, "erro": ""}
_trava = threading.Lock()


def agora_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(microsecond=0).isoformat()


# ── subtarefa: o dict do pacote (`spec._s`, com `so_para` em set) ↔ o JSON do banco ───────────────────────────────
def para_json(s: dict) -> dict:
    return {"desc": str(s.get("desc") or ""), "tipo": s.get("tipo") or "texto", "obrig": bool(s.get("obrig")),
            "anexo": bool(s.get("anexo")), "opcoes": list(s.get("opcoes") or []), "chave": str(s.get("chave") or ""),
            "so_para": sorted(s.get("so_para") or [])}


def de_json(d: dict) -> dict:
    return sp._s(str(d.get("desc") or "").strip(), d.get("tipo") or "texto", obrig=bool(d.get("obrig")),
                 anexo=bool(d.get("anexo")), opcoes=list(d.get("opcoes") or []) or None,
                 chave=str(d.get("chave") or ""), so_para=list(d.get("so_para") or []) or None)


def chave_valida(ch: str) -> bool:
    ch = str(ch or "")
    if ch == "BASE":
        return True
    if ch.startswith("TIPO:"):
        return ch[5:] in _ORIG["POR_TIPO"]
    if ch.startswith("MARCA:"):
        nome = ch[6:]
        return bool(nome.strip()) and nome == nome.strip() and len(nome) <= LIMITE_NOME and ":" not in nome
    return False


def semente() -> dict:
    """Os blocos como estão no código — o valor inicial e a rede de segurança."""
    out = {"BASE": {"subtarefas": [para_json(s) for s in _ORIG["BASE"]]}}
    for t, subs in _ORIG["POR_TIPO"].items():
        out["TIPO:" + t] = {"subtarefas": [para_json(s) for s in subs]}
    for m in sorted(set(_ORIG["POR_FABRICANTE"]) | set(_ORIG["TIPOS_DA_MARCA"])):
        out["MARCA:" + m] = {"subtarefas": [para_json(s) for s in _ORIG["POR_FABRICANTE"].get(m, [])],
                             "canal": _ORIG["CANAL"].get(m, ""), "atende": sorted(_ORIG["TIPOS_DA_MARCA"].get(m, [])),
                             "arquivado": False, "igual_a": CLONES.get(m, "")}
    return out


# ── leitura ───────────────────────────────────────────────────────────────────────────────────────────────────
def _linhas() -> list:
    """As linhas cruas da aba — o ÚNICO ponto que vai à rede na leitura (os testes trocam só este)."""
    return ABA.linhas()


def _de_linha(l: dict):
    """Linha do banco → (chave, valor) ou None. Linha ilegível é PULADA: um JSON estragado num fornecedor não pode
    tirar os outros da tela."""
    r = ABA.registro(l)
    ch = str(r.get("chave") or "").strip()
    if not chave_valida(ch):
        return None
    try:
        v = json.loads(r.get("valor") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(v, dict) or not isinstance(v.get("subtarefas", []), list):
        return None
    v["_linha"] = r.get("_linha")
    return ch, v


def carregar(forcar: bool = False) -> dict:
    """{chave: valor} do banco (cache de TTL). Levanta se o banco não responder — quem chama decide o que fazer."""
    with _trava:
        if _estado["banco"] is not None and not forcar and time.time() - _estado["lido"] < TTL:
            return _estado["banco"]
    banco = {}
    for l in _linhas():
        x = _de_linha(l)
        if not x:
            continue
        ch, v = x
        # chave repetida (duas máquinas criando o mesmo fornecedor ao mesmo tempo): vale a versão mais nova
        if ch not in banco or str(v.get("versao") or "") >= str(banco[ch].get("versao") or ""):
            banco[ch] = v
    with _trava:
        _estado.update(banco=banco, lido=time.time())
    return banco


def efetivo(banco: dict = None) -> dict:
    """Cada bloco como vale AGORA: o do banco quando existe, o do código quando não. `origem` diz qual."""
    if banco is None:
        banco = _estado["banco"] or {}
    out = {ch: dict(v, origem="codigo", versao="", por="") for ch, v in semente().items()}
    for ch, v in banco.items():
        out[ch] = dict(out.get(ch, {"subtarefas": [], "canal": "", "atende": [], "arquivado": False, "igual_a": ""}),
                       **{k: x for k, x in v.items() if not k.startswith("_")}, origem="banco")
        if ch.startswith("MARCA:"):
            out[ch]["igual_a"] = ""                       # salvo sozinho, o clone passou a ter a lista dele
    return out


def _trocar_dict(d: dict, novo: dict):
    """Troca o conteúdo sem esvaziar no meio: quem lê em outra thread nunca vê o dicionário vazio."""
    d.update(novo)
    for k in [k for k in d if k not in novo]:
        del d[k]


def aplicar(banco: dict = None):
    """Joga os blocos do banco por cima do código, em memória, no lugar. Sem banco (ou `{}`), volta ao código puro."""
    banco_efetivo = (_estado["banco"] or {}) if banco is None else banco
    ef = efetivo(banco_efetivo)
    base = [de_json(x) for x in ef["BASE"].get("subtarefas") or []]
    tipos = {ch[5:]: [de_json(x) for x in v.get("subtarefas") or []] for ch, v in ef.items() if ch.startswith("TIPO:")}
    fabr, atende, canal = {}, {}, dict(_ORIG["CANAL"])
    for ch, v in ef.items():
        if not ch.startswith("MARCA:") or v.get("arquivado"):
            continue                                      # arquivado some da escolha; o histórico fica na OS criada
        m = ch[6:]
        fabr[m] = [de_json(x) for x in v.get("subtarefas") or []]
        if v.get("atende"):
            atende[m] = set(v["atende"])
        canal[m] = str(v.get("canal") or "")
    for c, o in CLONES.items():
        if ("MARCA:" + c) not in banco_efetivo and c in fabr and o in fabr:
            fabr[c] = fabr[o]                             # a mesma lista, como no código
    sp.BASE[:] = base
    _trocar_dict(sp.POR_TIPO, tipos)
    _trocar_dict(sp.POR_FABRICANTE, fabr)
    _trocar_dict(sp.TIPOS_DA_MARCA, atende)
    sp.MARCAS_CONHECIDAS[:] = sorted(set(_ORIG["MARCAS_CONHECIDAS"]) | set(atende))
    _trocar_dict(cs.CANAL, canal)


def garantir():
    """Relê o banco se a última leitura passou do TTL e aplica. Nunca levanta: sem banco, fica o que já estava."""
    agora = time.time()
    if agora < _estado["proxima"]:
        return
    with _trava:
        if agora < _estado["proxima"]:
            return
        _estado["proxima"] = agora + TTL                  # os outros threads não repetem a leitura enquanto esta roda
    try:
        aplicar(carregar(forcar=True))
        _estado["erro"] = ""
    except Exception as e:                               # noqa: BLE001 — banco fora: segue o que já estava aplicado
        _estado.update(proxima=time.time() + TTL_ERRO, erro=str(e)[:200])


# ── validação ─────────────────────────────────────────────────────────────────────────────────────────────────
def _limpa(s) -> str:
    return " ".join(str(s or "").split())


def normalizar(chave: str, dados: dict) -> tuple:
    """(valor pronto para gravar, erro). A régua é a do pacote: tipo conhecido, lista com opções, nada repetido, e
    fornecedor com pelo menos um tipo de ativo — senão ele não aparece para ninguém escolher."""
    if not chave_valida(chave):
        return None, "Bloco desconhecido: %s." % chave
    dados = dados if isinstance(dados, dict) else {}
    marca = chave.startswith("MARCA:")
    atende = []
    if marca:
        atende = sorted({str(t) for t in (dados.get("atende") or []) if str(t) in _ORIG["POR_TIPO"]})
        if not atende and not dados.get("arquivado"):
            return None, "Diga que tipo de ativo este fornecedor atende — sem isso ele não aparece na inspeção."
    subs, vistos = [], set()
    for i, s in enumerate(dados.get("subtarefas") or [], 1):
        if not isinstance(s, dict):
            return None, "Pergunta %d ilegível." % i
        desc = _limpa(s.get("desc"))
        if not desc:
            return None, "A pergunta %d está vazia." % i
        if len(desc) > LIMITE_DESC:
            return None, "A pergunta %d passa de %d caracteres." % (i, LIMITE_DESC)
        if desc.lower() in vistos:
            return None, "A pergunta \"%s\" aparece duas vezes." % desc[:60]
        vistos.add(desc.lower())
        tipo = s.get("tipo") if s.get("tipo") in TIPOS else None
        if not tipo:
            return None, "Tipo desconhecido na pergunta %d." % i
        opcoes = []
        if tipo == "lista":
            for o in s.get("opcoes") or []:
                o = _limpa(o)
                if o and o.lower() not in {x.lower() for x in opcoes}:
                    opcoes.append(o)
            if len(opcoes) < 2:
                return None, "A pergunta \"%s\" é Lista e precisa de pelo menos duas opções." % desc[:60]
        so_para = sorted({str(t) for t in (s.get("so_para") or []) if str(t)})
        if marca and so_para and not set(so_para) <= set(atende):
            return None, "A pergunta \"%s\" vale para um tipo que o fornecedor não atende." % desc[:60]
        if not marca:
            so_para = []                                  # base e bloco do tipo valem sempre para o bloco inteiro
        chave_campo = re.sub(r"[^a-z0-9_]", "", str(s.get("chave") or "").lower())[:30]
        subs.append({"desc": desc, "tipo": tipo, "obrig": bool(s.get("obrig")), "anexo": bool(s.get("anexo")),
                     "opcoes": opcoes, "chave": chave_campo, "so_para": so_para})
    if chave == "BASE" and not subs:
        return None, "A base precisa de pelo menos uma pergunta — ela abre toda inspeção."
    valor = {"subtarefas": subs}
    if marca:
        canal = _limpa(dados.get("canal"))
        if len(canal) > LIMITE_CANAL:
            return None, "O canal de abertura passa de %d caracteres." % LIMITE_CANAL
        valor.update(canal=canal, atende=atende, arquivado=bool(dados.get("arquivado")))
    return valor, ""


# ── escrita ───────────────────────────────────────────────────────────────────────────────────────────────────
def salvar(chave: str, dados: dict, versao_lida: str, quem: str) -> dict:
    """Grava UM bloco e aplica na hora neste processo.

    RELÊ ANTES DE GRAVAR, sempre: o `row_number` não é chave (muda quando linha entra ou sai) e a versão que a tela
    leu tem de ser a que está no banco — senão a edição de outra pessoa sumiria em silêncio."""
    valor, erro = normalizar(chave, dados)
    if erro:
        raise ValueError(erro)
    if not ga.pode_gravar():
        raise SemCredencial("Este servidor não tem a credencial de escrita do banco da Gridco: dá para ver os "
                            "modelos, mas não para salvar.")
    banco = carregar(forcar=True)
    atual = banco.get(chave)
    if str(versao_lida or "") != str((atual or {}).get("versao") or ""):
        raise Conflito((atual or {}).get("por") or "", (atual or {}).get("versao") or "")
    valor.update(versao=agora_iso(), por=str(quem or "").strip())
    registro = {"chave": chave, "valor": json.dumps(valor, ensure_ascii=False)}
    if atual and atual.get("_linha"):
        ABA.trocar(atual["_linha"], registro)
    else:
        ABA.inserir(registro)
    aplicar(carregar(forcar=True))
    _estado["proxima"] = time.time() + TTL
    return valor
