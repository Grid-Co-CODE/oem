"""Resolve ativo e cabine pelo catálogo do Fracttal, não pela planilha.

Por que não pela planilha: a coluna `Inversor` da aba Trackers tem 212 vazios e o resto com
anotação no lugar do valor ('A ser verificado', 'Mapeamento agendado para 04/05'). O catálogo dá
o nome e o código reais.

Cadeias medidas em 28/08 (16.289 ativos em cache):
    tracker  : Tracker 1.100 -> Estrutura Trackers -> Usina        — sem cabine
    inversor : Inversor 1.1 -> QGBT 1 -> SKID 1 -> Cabine 1 -> Usina

Trackers não penduram em cabine no cadastro. A tela mostra 'não se aplica' — mentir um valor
seria pior que não ter."""

_LIMITE_SUBIDA = 12          # trava contra id_parent circular; a cadeia real tem no máximo 5


def indexar(ativos):
    return {a.get("id"): a for a in (ativos or []) if a.get("id") is not None}


def cadeia_de_pais(ativo, por_id):
    """Do ativo até a raiz, ele próprio incluído."""
    out, atual, visto = [], ativo, set()
    while atual is not None and len(out) < _LIMITE_SUBIDA:
        ident = atual.get("id")
        if ident in visto:
            break
        visto.add(ident)
        out.append(atual)
        atual = por_id.get(atual.get("id_parent"))
    return out


def cabine_de(ativo, por_id):
    """A cabine na linhagem do ativo, ou None quando não existe (caso dos trackers)."""
    for a in cadeia_de_pais(ativo, por_id):
        if str(a.get("tipo") or "").strip().lower() == "cabine":
            return a
    return None
