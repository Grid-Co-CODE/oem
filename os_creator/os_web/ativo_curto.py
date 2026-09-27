# os_creator/os_web/ativo_curto.py
"""O nome CURTO do ativo, para a coluna Ativo do Histórico (Levi, 27/09/2026: "diminua a descrição sem exportar marca ou
algo do tipo, quero algo direto, por exemplo 'Inversor 1.1', 'Tracker 1.100', 'Estação Meteorológica', 'Relé de
Proteção'"). PURO — sem Flask e sem rede.

O nome no Fracttal é "<tipo> <número> <marca> <modelo>", muitas vezes seguido do ENDEREÇO da usina. Medido no catálogo
inteiro (21.639 ativos, 27/09):

    Inversor 1.10 Sungrow SG125HV                          → Inversor 1.10
    Tracker 35.100 AXIALtracker                            → Tracker 35.100
    Cabine 1  Araputanga  Mato Grosso Brasil               → Cabine 1           o endereço vem depois de DOIS espaços…
    Sala de O&M FZ. Pau da Imbira, S/N, Zona Rural …       → Sala de O&M        …ou depois de um marcador de endereço
    Módulo Fotovoltaico Risen RSM132-8-700 725BHDG         → Módulo Fotovoltaico  marca conhecida ou código de modelo
    Disjuntor circuito auxiliar - Ub 115 V In 6A Icu 5 kA  → Disjuntor circuito auxiliar   " - " abre a ficha técnica
    Disjuntor do Inversor 1.1                              → Disjuntor do Inversor 1.1

A REGRA: o nome até o NÚMERO do ativo (inclusive), ou até a primeira marca, código de modelo ou pedaço de endereço.
Quando nada disso aparece (endereço sem marcador: "Infraestrutura Civil Recanto do Ratinho"), vale a FRASE que os ativos
do mesmo tipo repetem no catálogo ("Infraestrutura Civil") — é o próprio cadastro dizendo onde o tipo termina.

O nome inteiro continua no `title` da célula, na busca e no CSV: aqui só se decide o que a coluna MOSTRA.
"""
from __future__ import annotations

import collections
import re
import unicodedata

# marcas que aparecem no catálogo (as do pacote do chamado + as de módulo, tracker, rede e proteção). Comparadas sem
# acento e em minúscula; as de 4+ letras valem também como começo de palavra ("AXIALtracker", "SolarEdge…").
MARCAS = {
    "axial", "brametal", "canadian", "convert", "huawei", "hukseflux", "romiotto", "soltec", "sti", "sungrow", "trina",
    "solaredge", "growatt", "solplanet", "weg", "norland", "risen", "jinko", "longi", "byd", "fronius", "abb", "sma",
    "siemens", "schneider", "pextron", "kostal", "refusol", "chint", "hopewind", "ingeteam", "nextracker", "arctech",
    "gamechange", "sigma", "kipp", "campbell", "sofar", "goodwe", "deye", "solis", "ginlong", "tigo", "enphase",
    "apsystems", "phb", "intelbras", "hikvision", "moxa", "ubiquiti", "mikrotik", "dell", "lenovo", "positivo",
    "schweitzer", "woodward", "treetech", "arteche", "novus", "hitachi", "toshiba", "eaton", "steck", "clamper",
}
# o que abre endereço no meio do nome ("Sala de O&M FZ. Pau da Imbira", "Sistema Supervisório SITIO SANTA MARIA")
ENDERECO = {"rua", "r.", "av", "av.", "avenida", "estrada", "estr.", "est.", "rodovia", "rod.", "sitio", "fazenda",
            "faz.", "fz.", "zona", "chacara", "lote", "loteamento", "gleba", "km", "cep", "cep:", "s/n", "povoado",
            "distrito", "bairro", "localidade", "comunidade", "br"}   # "BR 101 KM 80": rodovia federal

_NUM = re.compile(r"^\d+(?:[.,]\d+)*$")                  # 1 · 1.10 · 40.100 · 06.101 · 2,5
_TEM_LETRA, _TEM_DIGITO = re.compile(r"[A-Za-zÀ-ÿ]"), re.compile(r"\d")


def _n(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def _eh_marca(tok: str) -> bool:
    n = _n(tok).strip(".,;:()")
    return n in MARCAS or any(len(m) >= 4 and n.startswith(m) for m in MARCAS)


def _eh_modelo(tok: str) -> bool:
    """Código de modelo: letra E dígito no mesmo pedaço (SUN2000-250KTL-H1, SG125HV, V05, 665W)."""
    return bool(_TEM_LETRA.search(tok) and _TEM_DIGITO.search(tok))


def _limpa(nome: str) -> str:
    s = str(nome or "").split("{")[0].strip()
    s = re.split(r"\s{2,}", s)[0]                        # endereço depois de dois espaços
    s = s.split(",")[0]                                  # …ou de vírgula
    s = re.split(r"\s+-\s+", s)[0]                       # " - " abre a ficha técnica
    return s.strip()


def _caminhar(s: str) -> list:
    out = []
    for t in s.split():
        if _NUM.match(t):
            out.append(t)                                # o número do ativo fecha o nome
            break
        n = _n(t)
        if n in ENDERECO or _eh_marca(t) or _eh_modelo(t):
            break
        out.append(t)
    return out


def frases(catalogo) -> dict:
    """{tipo: [frases do tipo, da mais longa à mais curta]} — o nome curto que ≥ 3 ativos do mesmo tipo repetem. É o
    que corta o endereço SEM marcador ("Infraestrutura Civil Recanto do Ratinho" → "Infraestrutura Civil")."""
    cont = collections.defaultdict(collections.Counter)
    for a in catalogo or []:
        if not isinstance(a, dict):
            continue
        toks = _caminhar(_limpa(a.get("description") or a.get("label") or ""))
        if toks and not _NUM.match(toks[-1]):            # só frase de TIPO (sem o número de um ativo)
            cont[a.get("tipo") or ""][" ".join(toks)] += 1
    return {t: sorted((f for f, n in c.items() if n >= 3), key=len, reverse=True) for t, c in cont.items()}


def curto(nome, frases_do_tipo=None) -> str:
    """O nome curto. Sem nada a cortar, devolve o nome limpo; vazio vira '—'."""
    bruto = str(nome or "").strip()
    if not bruto or bruto == "—":
        return "—"
    s = _limpa(bruto)
    toks = _caminhar(s)
    r = " ".join(toks)
    # sem número nem marca que fechassem o nome, e ele segue além da frase do tipo: corta na frase
    if toks and not _NUM.match(toks[-1]):
        for f in frases_do_tipo or []:
            if r != f and r.startswith(f + " "):
                resto = r[len(f) + 1:].split()
                r = f + ((" " + resto[0]) if resto and _NUM.match(resto[0]) else "")
                break
    return r or s or bruto[:40]
