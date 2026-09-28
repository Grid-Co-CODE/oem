# tests/test_os_web_anexos_zip.py
"""O "Baixar todos (N)" dos anexos na web (Levi, 28/09/2026: "falta só um botão de baixar todos os anexos"). No app de mesa
(steps/galeria.py, steps/documentos.py) o botão grava tudo numa pasta com `baixar_em_massa`; na web o servidor junta o
card num .zip com a MESMA arrumação — uma subpasta por subtarefa, a numeração dentro de cada uma, a nota de texto como
.txt, o nome repetido com " (2)" — e diz o que não veio. O primeiro teste roda a função do app de verdade (sem o Qt,
tirada do código-fonte) e compara caminho por caminho."""
import ast
import io
import mimetypes
import os
import zipfile

import pytest

import api
from os_web import criar_app, os_acoes_web as regra, rotas, rotas_os_acoes

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira (o oem é público)
_DOC_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "steps", "documentos.py")
_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web")


def _baixar_em_massa_do_app():
    """`_limpar_nome` + `baixar_em_massa` do steps/documentos.py, sem importar o módulo (ele puxa o PyQt6)."""
    arv = ast.parse(open(_DOC_APP, encoding="utf-8").read())
    funcs = [n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name in ("_limpar_nome", "baixar_em_massa")]
    assert len(funcs) == 2, "o app mudou: procure o baixar_em_massa no steps/documentos.py"
    ns = {"io": io, "os": os}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), _DOC_APP, "exec"), ns)
    return ns["baixar_em_massa"]


ITENS = [
    {"url": "https://s3/1", "nome": "image.jpg", "descricao": "", "subtarefa": "Foto do inversor", "is_text": False},
    {"url": "https://s3/2", "nome": "image.jpg", "descricao": "", "subtarefa": "Foto do inversor", "is_text": False},
    {"url": None, "nome": "nota", "descricao": "", "subtarefa": "Foto do inversor", "is_text": True},        # vazia: fica de fora
    {"url": None, "nome": "Medição", "descricao": "612 V no barramento", "subtarefa": "Medição: tensão/corrente", "is_text": True},
    {"url": "https://s3/3", "nome": "laudo final.pdf", "descricao": "", "subtarefa": "", "is_text": False},
    {"url": "https://s3/4", "nome": 'relat*ório?.zip', "descricao": "", "subtarefa": "Documentos.", "is_text": False},
    {"url": "https://s3/5", "nome": "IMAGE.JPG", "descricao": "", "subtarefa": "Foto do inversor", "is_text": False},
]


def test_o_zip_tem_a_arrumacao_do_baixar_em_massa_do_app(tmp_path):
    gravados, falhas = _baixar_em_massa_do_app()(ITENS, str(tmp_path), baixar=lambda url: b"x")
    assert not falhas
    do_app = {os.path.relpath(g, tmp_path).replace(os.sep, "/"): open(g, "rb").read() for g in gravados}
    plano = regra.plano_do_zip(ITENS)
    da_web = {p["caminho"]: (p["texto"].encode("utf-8") if p["tipo"] == "nota" else b"x") for p in plano}
    assert da_web == do_app
    assert "Foto do inversor/04 - IMAGE.JPG" in da_web                  # a nota vazia conta na numeração, como lá
    assert "Medição_ tensão_corrente/01 - Medição.txt" in da_web and "Documentos/01 - relat_ório_.zip" in da_web


def test_arquivo_sem_link_continua_arquivo_e_a_rota_renova_o_link():
    """O PDF cujo link não veio (o s3_object_get falhou) aparecia como NOTA, com o caminho do S3 por texto."""
    sem_link = {"url": None, "value": ".ot/x/laudo.pdf", "nome": "laudo.pdf", "descricao": "Laudo", "subtarefa": "Laudo",
                "is_image": False, "is_text": False}
    imgs, docs, notas = regra.separar_anexos([sem_link])
    assert (imgs, notas) == ([], []) and docs == [sem_link]
    it = regra.itens_subtarefas([sem_link], 501)[0]
    assert it["tipo"] == "documento" and it["url"] == "/os/api/os/501/anexo?value=.ot%2Fx%2Flaudo.pdf&nome=laudo.pdf&abrir=1"
    assert [p["tipo"] for p in regra.plano_do_zip(regra.itens_para_baixar("sub", [sem_link], []))] == ["arquivo"]


def test_um_arquivo_que_falha_nao_derruba_o_zip(tmp_path):
    plano = regra.plano_do_zip(ITENS)

    def baixar(item):
        if item["url"] == "https://s3/2":
            raise api.FracttalError("Falha ao baixar a imagem (HTTP 403).")
        return b"conteudo " + item["url"].encode()
    r = regra.montar_zip(str(tmp_path / "a.zip"), plano, baixar)
    assert (r["arquivos"], r["notas"]) == (4, 1) and r["falhas"] == [("Foto do inversor/02 - image.jpg", "Falha ao baixar a imagem (HTTP 403).")]
    with zipfile.ZipFile(tmp_path / "a.zip") as z:
        nomes = z.namelist()
        assert "Foto do inversor/02 - image.jpg" not in nomes and regra.NAO_VIERAM in nomes
        assert "02 - image.jpg" in z.read(regra.NAO_VIERAM).decode("utf-8")
        assert z.read("Medição_ tensão_corrente/01 - Medição.txt").decode("utf-8") == "612 V no barramento"
        assert z.getinfo("01 - laudo final.pdf").compress_type == zipfile.ZIP_STORED     # já comprimido: só guardar


def test_o_teto_do_zip(tmp_path):
    plano = regra.plano_do_zip(ITENS[:2])
    r = regra.montar_zip(str(tmp_path / "b.zip"), plano, lambda item: b"x" * 60, teto=100)
    assert r["arquivos"] == 1 and r["falhas"] == [("Foto do inversor/02 - image.jpg", "o .zip passou de 0 MB")]


# ── as rotas ───────────────────────────────────────────────────────────────────────────────────────────
SUBS = [{"url": "https://s3/foto1", "descricao": "Foto da string", "nome": "image.jpg", "value": ".ot/x/image.jpg",
         "subtarefa": "Foto da string", "is_image": True, "is_text": False},
        {"url": "https://s3/vencida", "descricao": "Foto da string", "nome": "image.jpg", "value": ".ot/x/renova.jpg",
         "subtarefa": "Foto da string", "is_image": True, "is_text": False},
        {"url": "https://s3/perdida", "descricao": "Laudo", "nome": "laudo.pdf", "value": "", "subtarefa": "Laudo",
         "is_image": False, "is_text": False},
        {"url": None, "descricao": "Medição  ·  612 V", "nome": "612 V", "value": "", "subtarefa": "Medição",
         "is_image": False, "is_text": True}]
OSS = [{"value": ".ot/x/image.jpg", "nome": "image.jpg", "user": "Pessoa Teste", "url": "https://s3/foto1", "is_image": True,
        "is_text": False, "desc": ""},
       {"value": ".ot/y/relatorio.zip", "nome": "relatorio.zip", "user": "Pessoa Teste", "url": "https://s3/relatorio",
        "is_image": False, "is_text": False, "desc": ""}]


@pytest.fixture
def cli(monkeypatch, tmp_path):
    rotas._MEMO.clear()
    chamadas = {"sub": 0, "os": 0, "s3": []}

    def subs(wid):
        chamadas["sub"] += 1
        return [dict(a) for a in SUBS]

    def oss(wid):
        chamadas["os"] += 1
        return [dict(a) for a in OSS]

    def baixar(url):
        if url in ("https://s3/vencida", "https://s3/perdida"):
            raise api.FracttalError("Falha ao baixar a imagem (HTTP 403).")
        return ("bytes de " + url).encode()

    def s3(value):
        chamadas["s3"].append(value)
        return "https://s3/renovada" if value == ".ot/x/renova.jpg" else None

    monkeypatch.setattr(api, "get_os_subtarefa_anexos", subs)
    monkeypatch.setattr(api, "get_os_anexos", oss)
    monkeypatch.setattr(api, "baixar_imagem", baixar)
    monkeypatch.setattr(api, "s3_get_url", s3)
    monkeypatch.setattr(rotas_os_acoes, "_pasta_zips", lambda: str(tmp_path))
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    c.chamadas = chamadas
    c.app_ = app
    return c


def test_zip_das_subtarefas_com_o_que_nao_veio(cli):
    j = cli.post("/os/api/os/501/anexos-zip", json={"grupo": "sub", "folio": "9812"}).get_json()
    assert j["ok"] and j["nome"] == "OS 9812 - anexos das subtarefas.zip"
    assert (j["arquivos"], j["notas"]) == (2, 1)                          # a vencida renovou pelo caminho no S3
    # a perdida não tem caminho no S3 para renovar: fica com o erro do download, como veio
    assert j["falhas"] == [{"nome": "Laudo/01 - laudo.pdf", "motivo": "Falha ao baixar a imagem (HTTP 403)."}]
    assert cli.chamadas["s3"] == [".ot/x/renova.jpg"]                    # só a que venceu foi ao Fracttal
    r = cli.get(j["url"])
    assert r.status_code == 200 and r.mimetype == "application/zip"
    assert 'attachment; filename="OS 9812 - anexos das subtarefas.zip"' in r.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        assert sorted(z.namelist()) == ["Foto da string/01 - image.jpg", "Foto da string/02 - image.jpg",
                                        "Medição/01 - 612 V.txt", regra.NAO_VIERAM]
        assert z.read("Foto da string/02 - image.jpg") == b"bytes de https://s3/renovada"


def test_zip_da_os_tira_o_que_ja_e_de_subtarefa(cli):
    j = cli.post("/os/api/os/501/anexos-zip", json={"grupo": "os", "folio": "9812"}).get_json()
    assert j["nome"] == "OS 9812 - anexos da OS.zip" and (j["arquivos"], j["notas"], j["falhas"]) == (1, 0, [])
    with zipfile.ZipFile(io.BytesIO(cli.get(j["url"]).data)) as z:
        assert z.namelist() == ["01 - relatorio.zip"]


def test_o_zip_reaproveita_a_lista_recem_aberta(cli):
    """Abrir os anexos e clicar em Baixar todos não vai duas vezes ao Fracttal (cada arquivo de subtarefa custa um
    s3_object_get e o limite é da EMPRESA); a lista em si sempre vem nova."""
    lista = cli.get("/os/api/os/501/anexos-lista").get_json()
    assert (lista["sub"]["baixar"], lista["os"]["baixar"]) == (4, 1)     # o N do "Baixar todos (N)" de cada card
    cli.post("/os/api/os/501/anexos-zip", json={"grupo": "sub"})
    assert (cli.chamadas["sub"], cli.chamadas["os"]) == (1, 1)
    cli.get("/os/api/os/501/anexos-lista")
    assert cli.chamadas["sub"] == 2                                      # reabrir a lista busca de novo


def test_o_zip_e_de_quem_pediu_e_vale_10_minutos(cli, monkeypatch):
    j = cli.post("/os/api/os/501/anexos-zip", json={"grupo": "sub"}).get_json()
    assert j["nome"] == "OS 501 - anexos das subtarefas.zip"             # sem o nº, fica o id
    assert cli.get(j["url"].replace("/501/", "/502/")).status_code == 404
    assert cli.get("/os/api/os/501/anexos-zip/nao-existe").status_code == 404
    outro = cli.app_.test_client()
    with outro.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Outra Pessoa", "email": "outra@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    assert outro.get(j["url"]).status_code == 404
    token = j["url"].rsplit("/", 1)[-1]
    rotas_os_acoes._ZIPS[token]["criado"] -= rotas_os_acoes._ZIP_TTL + 1
    assert cli.get(j["url"]).status_code == 404


def test_grupo_errado_card_vazio_e_nada_que_venha(cli, monkeypatch):
    assert cli.post("/os/api/os/501/anexos-zip", json={"grupo": "tudo"}).status_code == 400
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: [])
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: [])
    rotas._MEMO.clear()
    assert cli.post("/os/api/os/501/anexos-zip", json={"grupo": "sub"}).status_code == 404
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: [dict(SUBS[2])])
    rotas._MEMO.clear()
    r = cli.post("/os/api/os/501/anexos-zip", json={"grupo": "sub"})
    assert r.status_code == 502 and "Nenhum anexo veio" in r.get_json()["erro"]


def test_abrir_mostra_no_navegador_e_baixar_baixa(cli, monkeypatch):
    monkeypatch.setattr(api, "s3_get_url", lambda value: "https://s3/foto1")
    r = cli.get("/os/api/os/501/anexo?value=.ot%2Fx%2Flaudo.pdf&nome=laudo.pdf&abrir=1")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.headers["Content-Disposition"].startswith("inline;")
    # o tipo é o que o sistema dá pela extensão (no Windows o ZIP é application/x-zip-compressed) — nunca o genérico
    for nome in ("relatorio.zip", "rel.docx", "planilha.xlsx"):
        r = cli.get("/os/api/os/501/anexo?value=.ot%2Fx%2F" + nome + "&nome=" + nome)
        assert r.mimetype == mimetypes.guess_type(nome)[0] and r.mimetype != "application/octet-stream", nome
        assert r.headers["Content-Disposition"].startswith("attachment;"), nome


def test_a_tela_tem_o_botao_e_a_linha_do_resultado():
    tpl = open(os.path.join(_WEB, "templates", "os_detalhe_conteudo.html"), encoding="utf-8").read()
    anexos = tpl[tpl.index('<template data-dlg="anexos">'):]
    anexos = anexos[:anexos.index("</template>")]
    assert '<button type="button" class="det-b verde" data-baixar-todos hidden>Baixar todos</button>' in anexos
    assert 'data-anx-msg role="status" hidden' in anexos
    js = open(os.path.join(_WEB, "static", "os_acoes.js"), encoding="utf-8").read()
    for txt in ("'Baixar todos (' + n + ')'", "'Juntando os anexos num .zip…'", "/anexos-zip'", "_nao_vieram.txt",
                "a URL do Fracttal expira; abrir os anexos de novo renova", "'Abrindo os anexos…'"):
        assert txt in js, txt
    css = open(os.path.join(_WEB, "static", "os_acoes.css"), encoding="utf-8").read()
    assert ".acoes-dlg [hidden]{display:none!important}" in css
