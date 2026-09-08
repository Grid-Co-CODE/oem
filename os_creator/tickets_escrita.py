"""Escrita na Gridco Performance API — fase 2 dos tickets.

SEPARADO da leitura (`tickets_api.py`) de propósito. A leitura é aberta e roda o tempo todo; a
escrita exige credencial e só acontece por ação explícita. Deixar as duas no mesmo módulo faria
um `import` inocente carregar o token.

ONDE ISTO PODE ESCREVER. Enquanto o pipeline de coleta subir o `Tickets de Performance.xlsx` com
`replace=true`, o que gravarmos numa aba que ele alimenta pode ser apagado no sync seguinte. A
lista `SHEETS_LIBERADAS` era só a aba de teste por causa disso.

**Levi liberou a produção em 31/08**, sabendo do risco: "deixe gravando por hora mesmo que suba
com o sync". Ele pretende matar o sync ou criar a cópia no banco. Enquanto isso, quem grava é
avisado NA TELA de que a planilha ainda pode sobrescrever — o combinado é conviver com o sync,
não fingir que ele não existe.

Gravar numa aba fora dessa lista levanta erro em vez de tentar. É trava de código, não lembrete.
"""
import io
import os

import requests

BASE = "https://app.gridco.com.br/db_performace"
TIMEOUT = 30

# sheet_id → apelido. Só o que estiver aqui aceita escrita.
SHEETS_LIBERADAS = {
    374: "teste/FASE2_Trackers",          # zz_teste_claude_apagar, descartável
    123: "tickets_performance/Trackers",       # liberada pelo Levi em 31/08
    128: "tickets_performance/Strings indisp",  # idem
}

# As abas que o pipeline AINDA sobrescreve. Não bloqueiam a escrita — avisam. A tela usa isto
# para dizer, depois de gravar, que a planilha do OneDrive pode desfazer no próximo sync.
#
# VAZIO desde 06/09/2026: o corte foi ligado. O `sync_gridco_api.py` passou a excluir 'Trackers' e
# 'Strings indisp' do upload (`ABAS_DO_APP`), conferido em modo seguro — "2 aba(s) fora do upload".
# O app virou a única origem dessas duas abas, então o aviso deixou de ser verdade e sair.
#
# Se o corte for desligado um dia, ESTE conjunto volta junto: sem ele a tela diz "salvo" para uma
# edição que o próximo sync desfaz, que é pior do que não ter salvado.
SHEETS_QUE_O_SYNC_SOBRESCREVE = set()

COL_OS = "Nº OS"          # a coluna nova da fase 2; não existe nas abas de produção ainda


class EscritaBloqueada(RuntimeError):
    """Tentativa de gravar numa aba que o pipeline ainda sobrescreve."""


class SemCredencial(EscritaBloqueada):
    """Esta máquina não tem o GRIDCO_SQL_TOKEN.

    Subclasse, e não irmã: quem já tratava `EscritaBloqueada` continua pegando o caso. A tela usa
    o tipo mais específico para dizer O QUE FAZER — que é outro assunto do da aba fora da lista.

    Levi, 07/09: o app dele dizia isto e a tela do Salvar culpava o sync da planilha. O token
    "existia" na pasta certa para os meus shells e não para o app — o Claude é MSIX e virtualiza
    o AppData de tudo que nasce dele, então o arquivo gravado de uma sessão minha em 31/08 ficou
    numa camada que só os meus processos enxergam. Ver os_creator/CLAUDE.md."""


class ConflitoDeEdicao(RuntimeError):
    """A linha mudou no banco entre a leitura da tela e o clique em salvar."""
    def __init__(self, campos):
        self.campos = campos        # {coluna: (valor_que_a_tela_tinha, valor_agora)}
        super().__init__("a linha mudou desde que a tela carregou: %s" % ", ".join(campos))


SERVICO_COFRE = "CriarOS-Fracttal"          # mesmo serviço que o app já usa para o JWT
ARQ_TOKEN = "gridco_sql_token.txt"          # em %APPDATA%/CriarOS-Fracttal


def _pasta_usuario() -> str:
    base = (os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME")
            or os.path.expanduser("~"))
    return os.path.join(base, SERVICO_COFRE)


def guardar_token(valor: str) -> str:
    """Guarda o token da máquina. Cofre do SO quando existir; senão, arquivo na pasta do
    usuário. Devolve onde guardou, para a tela poder dizer."""
    valor = (valor or "").strip()
    try:
        import keyring
        keyring.set_password(SERVICO_COFRE, "gridco_sql_token", valor)
        return "cofre do Windows"
    except Exception:
        pass
    pasta = _pasta_usuario()
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, ARQ_TOKEN)
    with io.open(caminho, "w", encoding="utf-8") as f:
        f.write(valor + "\n")
    return caminho


def _token() -> str:
    """O GRIDCO_SQL_TOKEN desta máquina.

    NÃO vai embutido no .exe, de propósito: esse token dá escrita no banco INTEIRO — os três
    workbooks, não só os tickets — e um segredo dentro de um binário distribuído para várias
    pessoas é um segredo que vaza. Então a ordem é: ambiente (dev) → cofre do SO → arquivo na
    pasta do usuário → tokens.txt do repositório (só existe na máquina de desenvolvimento).

    Sem token a escrita nem tenta: a API responderia 401 e a pessoa leria "falha de rede"."""
    v = os.environ.get("GRIDCO_SQL_TOKEN", "").strip()
    if v:
        return v
    try:
        import keyring
        v = (keyring.get_password(SERVICO_COFRE, "gridco_sql_token") or "").strip()
        if v:
            return v
    except Exception:
        pass
    aqui = os.path.dirname(os.path.abspath(__file__))
    caminhos = [os.path.join(_pasta_usuario(), ARQ_TOKEN),
                os.path.join(aqui, "tokens.txt"),
                os.path.join(os.path.dirname(aqui), "tokens.txt"),
                os.path.join(os.path.dirname(os.path.dirname(aqui)), "tokens.txt")]
    for cand in caminhos:
        try:
            with io.open(cand, encoding="utf-8", errors="replace") as f:
                conteudo = f.read()
        except OSError:
            continue
        # o arquivo da pasta do usuário guarda só o token; o tokens.txt é CHAVE=valor
        if cand.endswith(ARQ_TOKEN):
            v = conteudo.strip()
            if v:
                return v
            continue
        for linha in conteudo.splitlines():
            if linha.strip().upper().startswith("GRIDCO_SQL_TOKEN"):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _cabecalho():
    tok = _token()
    if not tok:
        # Quem lê isto pode ser o próprio Levi, então "peça ao Levi" não resolve nada. O que
        # resolve: o caminho EXATO do arquivo e o nome do instalador que o grava. O do GitHub —
        # que o auto-update baixa — não traz a credencial de propósito, o repositório é público.
        raise SemCredencial(
            "Esta máquina não tem a credencial de escrita do banco — dá para ler os tickets, "
            "mas não para gravar.\n\n"
            "O arquivo tem de estar em:\n%s\n\n"
            "Quem grava esse arquivo é o instalador do SharePoint (\"Criar OS - Fracttal - "
            "Setup.exe\", na pasta \"12. Criação de OS Fractal\"). A atualização automática "
            "baixa o instalador do GitHub, que NÃO traz a credencial. Instale uma vez pelo "
            "SharePoint; as atualizações seguintes não apagam o arquivo."
            % os.path.join(_pasta_usuario(), ARQ_TOKEN))
    return {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}


def _confere_liberada(sheet_id):
    if sheet_id not in SHEETS_LIBERADAS:
        raise EscritaBloqueada(
            "aba %s não está na lista de escrita do app. A lista é curta de propósito: este "
            "token grava no banco inteiro, e um id errado aqui altera a planilha de outra "
            "área sem ninguém perceber." % sheet_id)


def para_valores(dados: dict, headers: list) -> list:
    """{coluna: valor} → lista na ORDEM do cabeçalho, que é como a API espera.

    Coluna ausente vira string vazia, não None: `None` chega no banco como o texto 'None' em
    alguns caminhos, e texto 'None' numa célula é pior que célula vazia."""
    out = []
    for c in headers:
        v = dados.get(c, "")
        out.append("" if v is None else v)
    return out


_PRIMEIRA = {}          # sheet_id → row_number da primeira linha (a aba não começa na 1)


def _pagina(sheet_id: int, offset: int, limit: int) -> list:
    r = requests.get("%s/api/sheets/%s/rows" % (BASE, sheet_id),
                     params={"offset": offset, "limit": limit}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return (d.get("rows") if isinstance(d, dict) else d) or []


def _linha_para_dict(r: dict) -> dict:
    headers = r.get("headers") or []
    valores = r.get("values") or []
    return {c: (valores[i] if i < len(valores) else None)
            for i, c in enumerate(headers) if str(c or "").strip()}


def ler_linha(sheet_id: int, row_number: int, buscar=None) -> dict:
    """A linha como {coluna: valor}, direto do banco. É a releitura que antecede o salvar.

    A API NÃO TEM GET de linha única: em `/rows/{row_number}` existem só PUT e DELETE, e um GET
    ali responde 404. A versão anterior chamava exatamente essa rota — passava nos testes (que
    injetam a leitura de propósito, para não bater na rede) e teria quebrado no primeiro salvar
    de verdade. Achado em 31/08 provando a gravação contra a aba real antes de liberar.

    O caminho que sobra é a coleção paginada. Como ela devolve em ordem de `row_number`, o
    atalho é calcular o offset — mas o palpite é SEMPRE conferido contra o row_number que
    voltou: aba com linha apagada tem buraco na numeração, e aceitar o palpite de olhos
    fechados leria a linha do vizinho, que aqui significa comparar a edição de outra
    ocorrência. Errando o palpite, varre."""
    if buscar is not None:
        return buscar(sheet_id, row_number)
    if sheet_id not in _PRIMEIRA:
        cabeca = _pagina(sheet_id, 0, 1)
        if not cabeca:
            return {}
        _PRIMEIRA[sheet_id] = cabeca[0].get("row_number") or 1
    palpite = max(0, int(row_number) - int(_PRIMEIRA[sheet_id]))
    achado = _pagina(sheet_id, palpite, 1)
    if achado and achado[0].get("row_number") == row_number:
        return _linha_para_dict(achado[0])
    offset = 0
    while True:
        pag = _pagina(sheet_id, offset, 1000)     # o teto de `limit` da API é 1000
        if not pag:
            return {}
        for r in pag:
            if r.get("row_number") == row_number:
                return _linha_para_dict(r)
        offset += len(pag)


def gravar_linha(sheet_id: int, row_number: int, dados: dict, headers: list,
                 base: dict = None, enviar=None, ler=None) -> dict:
    """Grava a linha. Se `base` vier, confere antes se alguém mexeu nela nesse meio-tempo.

    A conferência é otimista de propósito: poucos analistas, raramente ao mesmo tempo (Levi,
    28/08), então travar a linha seria burocracia para um caso que quase não acontece. Mas
    gravar por cima sem olhar seria perder a edição do outro em silêncio, que é justamente a
    classe de erro que este projeto não aceita."""
    _confere_liberada(sheet_id)
    if base is not None:
        agora = (ler or ler_linha)(sheet_id, row_number)
        mudou = {}
        for c, antes in base.items():
            depois = agora.get(c)
            if str(antes or "").strip() != str(depois or "").strip():
                mudou[c] = (antes, depois)
        if mudou:
            raise ConflitoDeEdicao(mudou)
    corpo = {"values": para_valores(dados, headers), "headers": list(headers)}
    if enviar is not None:
        return enviar("PUT", sheet_id, row_number, corpo)
    r = requests.put("%s/api/sheets/%s/rows/%s" % (BASE, sheet_id, row_number),
                     headers=_cabecalho(), json=corpo, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def apagar_linha(sheet_id: int, row_number: int, enviar=None) -> dict:
    """Apaga a linha da aba. NAO TEM DESFAZER — quem chama e' que confirma com quem clicou.

    Por que nao ha' conferencia de conflito aqui, se o `gravar_linha` tem: a conferencia existe
    para nao gravar por cima da edicao de outra pessoa, e ela compara CAMPO a campo. Apagar nao
    tem campo para comparar — o que se decide e' se aquela ocorrencia deve existir, e isso e'
    decisao de quem esta' olhando a tela, nao do estado dos campos. O que a tela faz e' recarregar
    depois, para ninguem seguir editando uma linha que ja' nao existe.

    O DIARIO NAO SALVA DISTO. Ele guarda EDICAO (`tickets_diario.CAMPOS`), nao linha apagada: um
    registro da linha que se foi vira orfao e e' ignorado na leitura seguinte — que e' o certo,
    porque repor campo numa ocorrencia inexistente seria pior que perde-lo."""
    _confere_liberada(sheet_id)
    if enviar is not None:
        return enviar("DELETE", sheet_id, row_number, None)
    r = requests.delete("%s/api/sheets/%s/rows/%s" % (BASE, sheet_id, row_number),
                        headers=_cabecalho(), timeout=TIMEOUT)
    r.raise_for_status()
    # a API responde 200 com corpo vazio nesta rota; `r.json()` sozinho levantaria
    # JSONDecodeError e a tela diria "nao consegui apagar" numa exclusao que deu certo.
    return r.json() if (r.content or b"").strip() else {}


def criar_linha(sheet_id: int, dados: dict, headers: list, enviar=None) -> dict:
    """Acrescenta uma linha. É o que roda quando uma OS é criada no Performance."""
    _confere_liberada(sheet_id)
    corpo = {"values": para_valores(dados, headers), "headers": list(headers)}
    if enviar is not None:
        return enviar("POST", sheet_id, None, corpo)
    r = requests.post("%s/api/sheets/%s/rows" % (BASE, sheet_id),
                      headers=_cabecalho(), json=corpo, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()
