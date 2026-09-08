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
import time

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
# Ficou vazio de 06 a 08/09/2026, enquanto o corte esteve ligado. VOLTOU em 08/09: o Levi desligou
# o corte — "o OS Creator ainda não é 100% dono dessas abas... a equipe está utilizando excel
# ainda, pode subir os dados" —, e a subida daquele dia mostrou o custo em número: as 189 linhas
# do Excel entraram, e junto voltaram os nomes velhos de usina e sumiram as duas ocorrências que
# alguém tinha criado pelo app horas antes.
#
# Era isto que o comentário anterior previa: sem este conjunto a tela diz "salvo" para uma edição
# que o próximo sync desfaz, e isso é pior do que não ter salvado. Enquanto o Excel for a origem,
# o aviso é a verdade.
#
# QUANDO O CORTE VOLTAR: esvaziar de novo, junto com `ABAS_DO_APP` do `sync_gridco_api.py`. Os
# dois andam sempre no mesmo sentido.
SHEETS_QUE_O_SYNC_SOBRESCREVE = {123, 128}

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


# ── por onde a escrita sai ────────────────────────────────────────────────────────────────
# RELAY POR PADRÃO (Levi, 07/09/2026: "manda uma mensagem para um canto seguro onde tem o
# token"). A alteração vai para a plataforma, que confere o login do Fracttal e grava com o token
# DELA. Assim o token fica num lugar só, e o instalador do GitHub basta. Escrita direta só com
# OSC_ESCRITA_DIRETA=1 E token local — modo de desenvolvimento, fora da distribuição.
#
# A plataforma não tem endereço fixo (quick tunnel do Cloudflare): ela publica a URL atual no
# banco, em os_creator/plataforma (chave/valor), e é de lá que `url_relay` a lê — aberto.
RELAY_DIRETO_ENV = "OSC_ESCRITA_DIRETA"
RELAY_WORKBOOK = "os_creator"
RELAY_ABA = "plataforma"
RELAY_URL_TTL = 300                 # s: quanto tempo a URL lida do banco vale sem reler
_relay = {"url": "", "quando": 0.0, "sheet": None}


class RelayIndisponivel(RuntimeError):
    """A plataforma não respondeu (fora do ar, túnel caído ou URL não publicada)."""


class RelayRecusou(EscritaBloqueada):
    """A plataforma recusou o login do Fracttal que o app mandou."""


def _jwt() -> str:
    # import tardio: o módulo de escrita não puxa o cliente do Fracttal só por ser importado
    import api as _api
    return _api.jwt_sessao()


def url_relay(buscar=None, forcar=False, agora=None) -> str:
    """A URL atual da plataforma, lida do banco. Cache de RELAY_URL_TTL; `forcar` relê.

    `buscar(caminho) -> json` é injetável para o teste. Sem nada publicado, cai para a URL que a
    pessoa configurou na tela de sugestões (dash_config), se houver; senão RelayIndisponivel."""
    t = time.time() if agora is None else agora
    if _relay["url"] and not forcar and t - _relay["quando"] < RELAY_URL_TTL:
        return _relay["url"]

    def _get(caminho):
        if buscar is not None:
            return buscar(caminho)
        r = requests.get(BASE + caminho, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    url = ""
    try:
        sid = _relay["sheet"]
        if sid is None:
            abas = _get("/api/sheets")
            abas = abas if isinstance(abas, list) else (abas or {}).get("sheets") or []
            for a in abas:
                if a.get("workbook_key") == RELAY_WORKBOOK and a.get("sheet_name") == RELAY_ABA:
                    sid = a.get("id")
                    break
        if sid is not None:
            _relay["sheet"] = sid
            pag = _get("/api/sheets/%s/rows?limit=100" % sid)
            for r in ((pag.get("rows") if isinstance(pag, dict) else pag) or []):
                v = r.get("values") or []
                if len(v) >= 2 and str(v[0]) == "tunnel_url":
                    url = str(v[1] or "").strip().rstrip("/")
    except Exception:                                    # noqa: BLE001 — cai no fallback
        url = ""
    if not url.startswith("http"):
        try:
            import api as _api
            url = _api._dash_url(_api.load_dash_config())
        except Exception:                                # noqa: BLE001
            url = ""
    if not url.startswith("http"):
        raise RelayIndisponivel(
            "não achei a plataforma: ela ainda não publicou a URL do túnel no banco (ou está "
            "fora do ar). Sem ela dá para ler os tickets, mas não para gravar.")
    _relay.update(url=url, quando=t)
    return url


def _resposta_do_relay(r, metodo: str):
    """Traduz a resposta da plataforma. 401 = login recusado; 403 = aba fora da lista; 5xx =
    plataforma ou banco fora; 2xx devolve o corpo (o eco do banco), vazio vira {}."""
    if r.status_code == 401:
        raise RelayRecusou("a plataforma não aceitou seu login do Fracttal: %s"
                           % _erro_de(r))
    if r.status_code == 403:
        raise EscritaBloqueada("a plataforma recusou: %s" % _erro_de(r))
    if r.status_code in (502, 503, 504):
        raise RelayIndisponivel("a plataforma respondeu %d: %s" % (r.status_code, _erro_de(r)))
    if r.status_code >= 400:
        raise RuntimeError("%s pela plataforma: HTTP %d — %s" % (metodo, r.status_code, _erro_de(r)))
    conteudo = (r.content or b"").strip()
    return r.json() if conteudo else {}


def _erro_de(r) -> str:
    try:
        j = r.json()
        if isinstance(j, dict) and j.get("error"):
            return str(j["error"])[:300]
    except ValueError:
        pass
    return (r.text or "")[:300]


def _relay_request(metodo: str, caminho: str, corpo):
    """Uma chamada à plataforma com o JWT no header. Se a ligação falhar, relê a URL do banco UMA
    vez e tenta de novo: o túnel pode ter trocado de endereço desde a última leitura."""
    cab = {"X-Fracttal-JWT": _jwt(), "Content-Type": "application/json"}
    for tentativa in (1, 2):
        base = url_relay(forcar=(tentativa == 2))
        try:
            r = requests.request(metodo, base + caminho, headers=cab, json=corpo, timeout=TIMEOUT)
        except requests.ConnectionError as e:
            if tentativa == 2:
                raise RelayIndisponivel("a plataforma não respondeu em %s: %s" % (base, str(e)[:120]))
            continue
        return _resposta_do_relay(r, metodo)


def _via_plataforma(metodo: str, sheet_id: int, row_number, corpo):
    """A implementação de `enviar` que fala com a plataforma — mesma assinatura da injetada."""
    caminho = "/api/tickets/%s/rows" % sheet_id + ("" if row_number is None else "/%s" % row_number)
    return _relay_request(metodo, caminho, corpo)


def _transporte():
    """Quem grava: None = direto (requests + _cabecalho), senão a função `enviar` do relay."""
    if os.environ.get(RELAY_DIRETO_ENV, "").strip() == "1" and _token():
        return None
    return _via_plataforma


def criar_aba(workbook: str, corpo: dict, enviar=None) -> dict:
    """Cria uma aba nova (o diário, quando precisa de coluna nova). Pelo relay, como o resto."""
    if enviar is not None:
        return enviar("POST", ("workbook", workbook), None, corpo)
    if _transporte() is None:
        r = requests.post("%s/api/workbooks/%s/sheets" % (BASE, workbook),
                          headers=_cabecalho(), json=corpo, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    return _relay_request("POST", "/api/tickets/workbooks/%s/sheets" % workbook, corpo)


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
    if enviar is None:
        enviar = _transporte()
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
    if enviar is None:
        enviar = _transporte()
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
    if enviar is None:
        enviar = _transporte()
    if enviar is not None:
        return enviar("POST", sheet_id, None, corpo)
    r = requests.post("%s/api/sheets/%s/rows" % (BASE, sheet_id),
                      headers=_cabecalho(), json=corpo, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()
