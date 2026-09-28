# tests/test_os_web_galeria_carrossel.py
"""A galeria dos anexos da OS na web (28/09/2026). Pedido do Levi: "aumente o campo para aparecer de 5 em 5 fotos, quando
eu clicar na foto quero que abra uma visão das fotos ... basicamente abrindo o Carrossel das fotos". O carrossel é o
ImagemViewer do app (steps/galeria.py): a foto ajustada à tela, a legenda, "‹ Anterior · N de M · Próxima ›", Salvar… e
Fechar, as setas do teclado. A conta de cada foto (posição, travas, Salvar) é pura e roda aqui no node, sem navegador."""
import json
import os
import re
import shutil
import subprocess

import pytest

from os_web import os_acoes_web

_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web")
_JS = os.path.join(_WEB, "static", "os_acoes.js")
_CSS = os.path.join(_WEB, "static", "os_acoes.css")
_OS_CSS = os.path.join(_WEB, "static", "os.css")
_GALERIA_APP = os.path.join(os.path.dirname(_WEB), "steps", "galeria.py")


def _ler(p):
    return open(p, encoding="utf-8").read()


# ── a grade: 5 por linha ───────────────────────────────────────────────────────────────────────────────
def test_grade_de_5_fotos_por_linha_que_desce_com_a_tela():
    css = _ler(_CSS)
    assert ".acoes-fotos{display:grid;grid-template-columns:repeat(5,minmax(0,1fr))" in css
    for largura, n in ((1180, 4), (940, 3), (680, 2)):      # no celular ficam 2: uma coluna só era foto demais por tela
        assert "@media (max-width:%dpx){.acoes-fotos{grid-template-columns:repeat(%d,minmax(0,1fr))}}" % (largura, n) in css
    assert ".acoes-dlg-anexos{width:min(1480px,96vw)}" in css      # a caixa cresce para caber as 5
    assert "aspect-ratio:4/3" in css                                 # a miniatura do app é 273×205


def test_cabecalho_da_os_quebra_linha_no_celular():
    """Num telefone de 375 px a pílula da solicitação alargava a página para 461 px, e a galeria (fixa, centrada na página
    larga) saía cortada à direita — visto na bancada em 28/09."""
    css = _ler(_OS_CSS)
    m = re.search(r"@media \(max-width:640px\)\{\.det-top\{([^}]*)\}", css)
    assert m and "flex-wrap:wrap" in m.group(1)


# ── o carrossel: o ImagemViewer do app ────────────────────────────────────────────────────────────────
def test_textos_sao_os_do_imagemviewer_do_app():
    js, app = _ler(_JS), _ler(_GALERIA_APP)
    for txt in ("‹ Anterior", "Próxima ›", "Salvar…", "Fechar", "baixando imagem…", "(não consegui baixar a imagem)"):
        assert txt in app, "o app mudou o texto: " + txt             # a fonte é o app — se ele mudar, este teste avisa
        assert txt in js, txt


def test_carrossel_fica_acima_da_galeria_que_fica_acima_do_card_do_historico():
    css = _ler(_CSS)
    z_visor = int(re.search(r"\.visor\{[^}]*z-index:(\d+)", css).group(1))
    z_fundo = int(re.search(r"\.acoes-fundo\{[^}]*z-index:(\d+)", css).group(1))
    assert z_visor > z_fundo > 60                                    # 60 = o modal do Histórico


def test_esc_fecha_so_o_carrossel_e_as_setas_andam():
    """O `keydown` da janela, na captura, responde pelo carrossel ANTES de fechar a galeria — sem isso o primeiro Esc fechava
    as duas (e o do Histórico, o card inteiro)."""
    js = _ler(_JS)
    ini = js.index("window.addEventListener('keydown'")
    trecho = js[ini:js.index("}, true);", ini)]
    assert trecho.index("visor.fechar()") < trecho.index("aberto.fechar()")
    assert "ArrowLeft" in trecho and "ArrowRight" in trecho and "return;" in trecho


def test_miniatura_abre_na_posicao_dela_e_ctrl_clique_segue_para_outra_aba():
    js = _ler(_JS)
    assert "data-foto=\"' + k + '\"" in js                         # cada miniatura sabe a sua posição na lista
    assert "corpo._fotos = imgs" in js                               # o carrossel anda pelas fotos da grade, na ordem dela
    assert "e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey" in js


def test_salvar_do_carrossel_usa_a_rota_da_casa():
    """A conta do Salvar parte da barra inicial: a rota /os/api/.../anexo renova a URL e baixa na mesma página. Se o link
    mudar de forma, o carrossel passaria a abrir o Salvar em outra aba."""
    assert os_acoes_web.link_baixar(7, "a/b.jpg", "b.jpg").startswith("/os/api/os/7/anexo?")


_HARNESS = r"""
const fs = require('fs');
global.window = {addEventListener: () => {}};
global.document = {readyState: 'complete', addEventListener: () => {}, querySelectorAll: () => [], dispatchEvent: () => {}};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const A = window.OsAcoes;
const fotos = [{url: 'https://s3.exemplo/f1.jpg', baixar: '/os/api/os/7/anexo?value=a&nome=f1.jpg', nome: 'f1.jpg', legenda: 'Antes'},
               {url: 'https://s3.exemplo/f2.jpg', baixar: 'https://s3.exemplo/f2.jpg', nome: 'f2.jpg', legenda: ''},
               {url: 'https://s3.exemplo/f3.jpg', nome: '', legenda: 'Depois'}];
console.log(JSON.stringify({
  e: [0, 1, 2].map((i) => A.estadoVisor(fotos, i)),
  passos: [A.passoVisor(0, -1, 3), A.passoVisor(0, 1, 3), A.passoVisor(2, 1, 3), A.passoVisor(1, -1, 3), A.passoVisor(0, 1, 1)],
  deslize: [A.deslize(-120), A.deslize(120), A.deslize(30), A.deslize(-50), A.deslize(51)]}));
"""


def test_conta_de_cada_foto_no_node(tmp_path):
    """O `_carregar` do app: "N de M", Anterior desligado na 1ª, Próxima na última, o título "Foto N de M — legenda"; nas
    pontas as setas não andam; o dedo precisa andar mais de 50 px (toque curto não troca a foto)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    (tmp_path / "h.js").write_text(_HARNESS, encoding="utf-8")
    r = subprocess.run([node, str(tmp_path / "h.js"), _JS], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    e0, e1, e2 = out["e"]
    assert (e0["pos"], e0["titulo"], e0["antOff"], e0["proxOff"]) == ("1 de 3", "Foto 1 de 3 — Antes", True, False)
    assert (e1["pos"], e1["titulo"], e1["antOff"], e1["proxOff"]) == ("2 de 3", "Foto 2 de 3", False, False)
    assert (e2["pos"], e2["antOff"], e2["proxOff"]) == ("3 de 3", False, True)
    # Salvar: pela rota da casa baixa aqui; a URL do S3 (outro domínio) ignora o `download` — vai para outra aba
    assert (e0["salvar"], e0["download"], e0["salvarOutraAba"]) == ("/os/api/os/7/anexo?value=a&nome=f1.jpg", "f1.jpg", False)
    assert (e1["salvar"], e1["salvarOutraAba"]) == ("https://s3.exemplo/f2.jpg", True)
    assert (e2["salvar"], e2["download"], e2["salvarOutraAba"]) == ("https://s3.exemplo/f3.jpg", "foto.jpg", True)
    assert out["passos"] == [0, 1, 2, 0, 0]
    assert out["deslize"] == [1, -1, 0, 0, -1]
