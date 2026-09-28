/* os_creator/os_web/static/abas.js — as ABAS ABERTAS do OS Creator web (Levi, 28/09/2026): "seria interessante que essas
   abas acima 'Início' e 'Histórico de OS' vá abrindo em estilos de abas que ficam abertas e podem ser fechadas. A minha
   ideia é que comece só com início, se eu clicar em histórico abre uma aba de histórico, se performance abre uma aba de
   performance e assim por diante".

   A tela inicial (/os/) é a CASCA: o Início mora nela e cada outra tela abre numa aba com um <iframe> — a aba fica VIVA
   enquanto a pessoa troca de uma para outra (a busca do Histórico, o formulário pela metade, o card aberto continuam
   lá; a troca é instantânea, sem ir de novo ao Fracttal). A tela aberta dentro de uma aba ("embutida") esconde o
   cabeçalho e a faixa (o <head> do base.html põe a classe antes de pintar) e conversa com a casca por postMessage:
   - o título dela vira o rótulo da aba;
   - link para OUTRO setor (lancador.ABAS_SECOES) abre — ou acende, se já estiver aberta — a aba dele: o "Clonar esta
     OS" do card aberto no Histórico não tira a pessoa do Histórico; dentro do mesmo setor a aba segue o link;
   - link para o Início acende o Início; para a Plataforma, sai da casca inteira.
   Aberta SOZINHA no navegador (link da Plataforma, favorito, botão do meio), a tela vai para a casca com ela numa aba —
   também decidido no <head> do base.html. ?solo=1 abre a tela sozinha, sem casca.

   As abas ficam na sessão DESTA aba do navegador (sessionStorage, com a chave presa no window.name): o F5 as traz de
   volta — só a ativa carrega na hora, as outras quando forem clicadas —, e uma aba nova do navegador começa só com o
   Início, como o Levi pediu. As regras de decisão são puras e o teste as roda no node
   (tests/test_os_web_abas.py). */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.OsAbas) return;

  // ── regras puras ─────────────────────────────────────────────────────────────────────────────────────────────────
  // tela do OS Creator que cabe numa aba: debaixo de /os/, e não API, arquivo, login/logout nem a própria casca
  function ehTela(caminho) {
    return /^\/os\/[^/]/.test(caminho) && !/^\/os\/(api|static|assets)\//.test(caminho) && !/^\/os\/(login|logout)(\/|$)/.test(caminho);
  }
  // o endereço da aba: caminho + busca, sem o token do círculo (p) nem o ?solo — ou null se não é tela nossa
  function normalizar(href, base) {
    let u, b;
    try { b = new URL(base); u = new URL(href, b); } catch (e) { return null; }
    if (u.origin !== b.origin || !ehTela(u.pathname)) return null;
    u.searchParams.delete('p'); u.searchParams.delete('solo');
    const q = u.searchParams.toString();
    return u.pathname + (q ? '?' + q : '');
  }
  // o setor pelo começo do caminho (o prefixo mais comprido vence); sem linha na tabela, o 1º pedaço do caminho
  function secaoDe(caminho, tabela) {
    const c = String(caminho || '').split(/[?#]/)[0];
    if (c === '/os/' || c === '/os') return 'inicio';
    let melhor = null;
    (tabela || []).forEach(function (par) {
      const pre = par[0];
      if ((c === pre || c.indexOf(pre + '/') === 0) && (!melhor || pre.length > melhor[0].length)) melhor = par;
    });
    if (melhor) return melhor[1];
    const m = /^\/os\/([^/]+)/.exec(c);
    return m ? 'outra:' + m[1] : 'outra';
  }
  // "Histórico de OS · Grid Co." → "Histórico de OS"
  function rotulo(titulo) { return String(titulo || '').replace(/\s*·\s*Grid Co\.?\s*$/, '').replace(/\s+/g, ' ').trim(); }
  // a aba que já mostra este endereço — pelo endereço de agora ou pelo que a abriu
  function acharAba(abas, url) {
    for (let i = 0; i < (abas || []).length; i++) if (abas[i].url === url || abas[i].origem === url) return abas[i];
    return null;
  }
  // quem acende quando a aba ATIVA fecha: a da direita; na ponta, a da esquerda; sem nenhuma, o Início
  function vizinha(abas, id) {
    const i = (abas || []).findIndex(function (a) { return a.id === id; });
    if (i < 0) return 'inicio';
    const v = abas[i + 1] || abas[i - 1];
    return v ? v.id : 'inicio';
  }
  // ?aba=/os/historico (a tela que veio sozinha e foi mandada para a casca): só tela nossa — nunca outro site,
  // nunca javascript:, nunca a API
  function abaDoEndereco(busca, base) {
    let v = null;
    try { v = new URLSearchParams(busca || '').get('aba'); } catch (e) { return null; }
    if (!v || v.indexOf('/os/') !== 0) return null;
    return normalizar(v, base);
  }
  // o clique num link DENTRO de uma aba: 'seguir' (o navegador faz), 'abrir' (aba nossa), 'inicio', 'fechar' ou 'topo'
  // (a janela inteira). `a` = {href, target, download, fechar, botao, mod}; `pagina` = {pathname, search}.
  function destino(a, pagina, tabela, base) {
    if (a.botao !== 0 || a.mod) return 'seguir';          // botão do meio, Ctrl: outra aba DO NAVEGADOR (que vai para a casca)
    if (a.fechar) return 'fechar';                         // o "Fechar" da OS aberta numa aba: fecha a aba
    if (a.download) return 'seguir';
    let u, b;
    try { b = new URL(base); u = new URL(a.href, b); } catch (e) { return 'seguir'; }
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return 'seguir';   // mailto:, tel:, javascript:
    if (u.origin !== b.origin) return 'seguir';            // outro site (o supervisório da Engenharia já é _blank)
    const c = u.pathname;
    if (c === '/os/' || c === '/os') return 'inicio';
    if (c.indexOf('/os/') !== 0) return 'topo';            // a Plataforma: a janela toda, nunca dentro da aba
    if (/^\/os\/(login|logout)(\/|$)/.test(c)) return 'topo';
    if (!ehTela(c)) return 'seguir';                       // download da API, arquivo estático
    if (a.target && a.target !== '_self') return 'abrir';  // "abre numa aba nova": aqui, uma aba nossa
    if (c === pagina.pathname && u.search === (pagina.search || '')) return 'seguir';   // só a âncora
    return secaoDe(c, tabela) === secaoDe(pagina.pathname, tabela) ? 'seguir' : 'abrir';
  }
  // o endereço de uma tela: o <link rel=canonical> quando ela tem (a OS aberta pelo nº é a mesma aberta pelo id), senão o
  // da barra
  function endereco(doc, loc) {
    const can = doc && doc.querySelector && doc.querySelector('link[rel="canonical"]');
    if (can) { try { const u = new URL(can.getAttribute('href'), loc.href); return u.pathname + u.search; } catch (e) { /* segue */ } }
    return loc.pathname + loc.search;
  }
  // a busca do Início, a mesma regra do /os/buscar (rotas.buscar): número (com ou sem #) abre a OS; texto procura nos Ativos
  function destinoDaBusca(q) {
    const t = String(q || '').replace(/\s+/g, ' ').trim();
    if (!t) return null;
    const n = t.replace(/^#/, '').trim();
    if (/^\d+$/.test(n)) return {url: '/os/os/folio/' + n, rotulo: 'OS ' + n, secao: 'os'};
    return {url: '/os/ativos?' + new URLSearchParams({busca: t}).toString(), rotulo: 'Ativos', secao: 'ativos'};
  }
  // o rótulo provisório de um link (até a tela dizer o título dela): o título do cartão, senão o texto
  function rotuloDoLink(el) {
    const forte = el.querySelector && el.querySelector('b, h3, strong');
    const t = rotulo((forte && forte.textContent) || el.getAttribute('title') || el.textContent || '');
    return t.length > 40 ? t.slice(0, 39) + '…' : t;
  }

  const puro = {ehTela: ehTela, normalizar: normalizar, secaoDe: secaoDe, rotulo: rotulo, acharAba: acharAba,
                vizinha: vizinha, abaDoEndereco: abaDoEndereco, destino: destino, destinoDaBusca: destinoDaBusca};
  window.OsAbas = {puro: puro, casca: false};
  if (typeof document === 'undefined' || !document.documentElement) return;       // o teste no node

  const html = document.documentElement;
  let pai = null;
  try { if (window.parent !== window && window.parent.OsAbas && window.parent.OsAbas.casca) pai = window.parent; } catch (e) { pai = null; }
  if (html.getAttribute('data-casca') === '1') {
    // a tela inicial DENTRO de uma aba (a busca vazia volta ao Início, um link que escapou): nunca uma casca dentro da
    // outra — avisa a casca, que acende o Início e fecha esta aba (aoCarregar)
    if (window.parent === window) casca();
    else if (pai) pai.postMessage({osAbas: 1, tipo: 'inicio'}, location.origin);
    return;
  }
  if (html.classList.contains('os-embutido') && pai) embutida(pai);   // embutida noutra coisa (não a casca): só sem o cabeçalho

  // ── a tela dentro de uma aba ─────────────────────────────────────────────────────────────────────────────────────
  function embutida(pai) {
    const tabela = pai.OsAbas.secoes || [];
    function enviar(tipo, extra) {
      const m = {osAbas: 1, tipo: tipo};
      if (extra) Object.keys(extra).forEach(function (k) { m[k] = extra[k]; });
      try { pai.postMessage(m, location.origin); } catch (e) { /* a casca foi embora */ }
    }
    function pagina() { enviar('pagina', {url: endereco(document, location), titulo: document.title}); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', pagina); else pagina();
    // o título que a tela troca depois e a URL que ela reescreve (os filtros): o rótulo e o F5 acompanham
    const t = document.querySelector('title');
    if (t && window.MutationObserver) new MutationObserver(pagina).observe(t, {childList: true, characterData: true, subtree: true});
    ['pushState', 'replaceState'].forEach(function (m) {
      const orig = history[m];
      if (typeof orig !== 'function') return;
      history[m] = function () { const r = orig.apply(this, arguments); pagina(); return r; };
    });
    window.addEventListener('pagehide', function () { enviar('saindo'); });
    // na BOLHA, na janela — o último a ouvir: o link que a própria tela já tratou (o nº da OS no Histórico abre o card
    // ali mesmo, com preventDefault) não é tocado. O círculo do carga.js decide depois (setTimeout) e respeita o nosso.
    window.addEventListener('click', function (e) {
      if (e.defaultPrevented) return;
      const a = e.target && e.target.closest && e.target.closest('a[href]');
      if (!a) return;
      const d = destino({href: a.getAttribute('href'), target: a.getAttribute('target') || '', download: a.hasAttribute('download'),
                         fechar: a.hasAttribute('data-aba-fechar'), botao: e.button, mod: e.ctrlKey || e.metaKey || e.shiftKey || e.altKey},
                        {pathname: location.pathname, search: location.search}, tabela, location.href);
      if (d === 'seguir') return;
      e.preventDefault();
      if (d === 'abrir') enviar('abrir', {url: normalizar(a.getAttribute('href'), location.href), rotulo: rotuloDoLink(a)});
      else if (d === 'topo') enviar('topo', {url: new URL(a.getAttribute('href'), location.href).href});
      else enviar(d);
    });
  }

  // ── a casca (a tela inicial) ─────────────────────────────────────────────────────────────────────────────────────
  function casca() {
    const lista = document.getElementById('abas_lista'), paineis = document.getElementById('abas_paineis');
    const abaInicio = document.getElementById('aba_inicio'), painelInicio = document.getElementById('painel_inicio');
    if (!lista || !paineis || !abaInicio || !painelInicio) return;
    let tabela = [];
    try { tabela = JSON.parse(document.getElementById('abas_secoes').textContent) || []; } catch (e) { tabela = []; }
    const icones = {};
    const tpl = document.getElementById('abas_icones');
    if (tpl && tpl.content) tpl.content.querySelectorAll('[data-secao]').forEach(function (s) { icones[s.getAttribute('data-secao')] = s.innerHTML; });
    const X = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
    const chave = 'osAbas:' + idJanela();
    let abas = [], ativa = 'inicio', seq = 0;
    const vivas = {};                                     // id → {aba, painel, frame, carga, ...}

    function idJanela() {
      let n = '';
      try { n = window.name || ''; } catch (e) { n = ''; }
      const m = /^osCasca:([a-z0-9]{4,24})$/.exec(n);
      if (m) return m[1];
      if (n) return 'nome-' + n.replace(/[^A-Za-z0-9]/g, '').slice(0, 24);   // janela com nome de outro dono: não mexo nele
      const id = (Math.random().toString(36).slice(2, 10) + Date.now().toString(36)).slice(0, 16);
      try { window.name = 'osCasca:' + id; } catch (e) { /* sem nome, as abas duram até fechar a aba do navegador */ }
      return id;
    }
    function salvar() {
      try { sessionStorage.setItem(chave, JSON.stringify({v: 1, ativa: ativa, abas: abas.map(function (a) {
        return {id: a.id, origem: a.origem, url: a.url, titulo: a.titulo, secao: a.secao}; })})); } catch (e) { /* modo privado */ }
    }
    function restaurar() {
      try {
        Object.keys(sessionStorage).forEach(function (k) { if (k.indexOf('osAbas:') === 0 && k !== chave) sessionStorage.removeItem(k); });
        const j = JSON.parse(sessionStorage.getItem(chave) || 'null');
        if (!j || j.v !== 1 || !Array.isArray(j.abas)) return;
        abas = j.abas.filter(function (a) { return a && a.id && normalizar(a.url, location.href); }).map(function (a) {
          return {id: String(a.id), origem: normalizar(a.origem || a.url, location.href) || normalizar(a.url, location.href),
                  url: normalizar(a.url, location.href), titulo: rotulo(a.titulo), secao: secaoDe(a.url, tabela)}; });
        ativa = abas.some(function (a) { return a.id === j.ativa; }) ? j.ativa : 'inicio';
        abas.forEach(function (a) { const n = parseInt(String(a.id).replace(/\D/g, ''), 10); if (n > seq) seq = n; });
      } catch (e) { abas = []; ativa = 'inicio'; }
    }
    const achar = function (id) { return abas.filter(function (a) { return a.id === id; })[0] || null; };

    function montar(a) {
      const el = document.createElement('div');
      el.className = 'aba'; el.id = 'aba_' + a.id; el.setAttribute('role', 'tab'); el.setAttribute('aria-selected', 'false');
      el.setAttribute('aria-controls', 'painel_' + a.id); el.tabIndex = -1; el.setAttribute('data-aba', a.id);
      el.innerHTML = '<span class="aba-ic"></span><span class="aba-t"></span>'
        + '<button type="button" class="aba-x" tabindex="-1">' + X + '</button>';
      lista.appendChild(el);
      const p = document.createElement('div');
      p.className = 'aba-painel'; p.id = 'painel_' + a.id; p.setAttribute('role', 'tabpanel');
      p.setAttribute('aria-labelledby', 'aba_' + a.id); p.hidden = true;
      paineis.appendChild(p);
      vivas[a.id] = {aba: el, painel: p, frame: null, carga: null};
      pintarAba(a);
    }
    function pintarAba(a) {
      const v = vivas[a.id]; if (!v) return;
      const nome = a.titulo || 'Carregando…';
      v.aba.querySelector('.aba-ic').innerHTML = icones[a.secao] || icones.outra || '';
      v.aba.querySelector('.aba-t').textContent = nome;
      v.aba.title = nome;
      v.aba.querySelector('.aba-x').setAttribute('aria-label', 'Fechar a aba ' + nome);
      if (v.frame) v.frame.title = nome;
      if (a.id === ativa) document.title = nome + ' · Grid Co.';
    }
    function carregando(v, sim) { if (v) v.aba.classList.toggle('carregando', !!sim); }

    // o círculo do painel enquanto a tela não chega (o mesmo desenho do carga.js); no Histórico, com o progresso
    // dos pedidos ao Fracttal (o `p=` que o carga.js sempre mandou)
    const R = 27, C = 2 * Math.PI * R;
    function pintarCarga(el, feito, total) {
      const anel = el.querySelector('.carga-anel'), arco = el.querySelector('.carga-arco');
      if (!total) { anel.classList.add('ind'); el.querySelector('.carga-pct').textContent = ''; return; }
      anel.classList.remove('ind');
      const f = Math.max(0, Math.min(1, feito / total));
      arco.setAttribute('stroke-dashoffset', (C * (1 - f)).toFixed(2));
      el.querySelector('.carga-pct').textContent = Math.round(f * 100) + '%';
      el.querySelector('.carga-sub').textContent = feito + ' de ' + total + ' pedidos ao Fracttal';
      el.querySelector('.carga-txt').textContent = f >= 1 ? 'Montando a tabela…' : 'Buscando as OS no Fracttal…';
    }
    function mostrarCarga(v, a, token) {
      esconderCarga(v);
      const el = document.createElement('div');
      el.className = 'aba-carga'; el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite');
      el.innerHTML = '<div class="carga-caixa"><svg class="carga-anel ind" viewBox="0 0 64 64" aria-hidden="true">'
        + '<circle class="carga-trilho" cx="32" cy="32" r="' + R + '"/><circle class="carga-arco" cx="32" cy="32" r="' + R
        + '" stroke-dasharray="' + C.toFixed(2) + '" stroke-dashoffset="' + (C * 0.75).toFixed(2) + '"/></svg>'
        + '<div class="carga-pct"></div><div class="carga-txt"></div><div class="carga-sub"></div></div>';
      el.querySelector('.carga-txt').textContent = 'Abrindo ' + (a.titulo || 'a tela') + '…';
      el.classList.add('espera');                          // 250 ms: a tela que vem rápido não pisca o círculo
      v.cargaAtraso = setTimeout(function () { el.classList.remove('espera'); }, 250);
      if (token) {
        v.cargaRelogio = setInterval(function () {
          fetch('/os/historico/progresso?p=' + encodeURIComponent(token), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) { if (j && v.carga === el) pintarCarga(el, j.feito || 0, j.total || 0); })
            .catch(function () { /* a tela já está chegando */ });
        }, 350);
      }
      v.painel.appendChild(el); v.carga = el;
    }
    function esconderCarga(v) {
      clearTimeout(v.cargaAtraso); clearInterval(v.cargaRelogio);
      if (v.carga) { v.carga.remove(); v.carga = null; }
    }

    function carregar(a) {
      const v = vivas[a.id]; if (!v || v.frame) return;
      const f = document.createElement('iframe');
      f.title = a.titulo || 'Tela do OS Creator';
      let src = a.url, token = null;
      if (a.secao === 'hist') {
        token = (window.OsCarga && OsCarga.token && OsCarga.token()) || String(Date.now());
        src += (src.indexOf('?') >= 0 ? '&' : '?') + 'p=' + encodeURIComponent(token);
      }
      mostrarCarga(v, a, token);
      carregando(v, true);
      f.addEventListener('load', function () { aoCarregar(a.id); });
      f.src = src;
      v.painel.appendChild(f); v.frame = f;
    }
    // o `load` da moldura: normalmente a tela já avisou (DOMContentLoaded); aqui é a rede de segurança — tela sem o
    // abas.js (a resposta de erro da Plataforma) ou a que o navegador se recusou a pôr numa moldura
    function aoCarregar(id) {
      const v = vivas[id], a = achar(id); if (!v || !a) return;
      esconderCarga(v); carregando(v, false); tirarErro(v);
      let doc = null;
      try { doc = v.frame.contentDocument; } catch (e) { doc = null; }
      if (!doc) { erroNoPainel(v, a); return; }
      try {
        const u = normalizar(endereco(doc, v.frame.contentWindow.location), location.href);
        if (u && u !== a.url) { a.url = u; a.secao = secaoDe(u, tabela); }
        const t = rotulo(doc.title);
        if (t) a.titulo = t;
        if (!u && /^\/os\/?$/.test(v.frame.contentWindow.location.pathname)) {   // a tela mandou para o Início (busca vazia)
          fechar(id); return;
        }
        if (duplicada(a)) return;
      } catch (e) { /* tela fora do OS Creator: fica como está */ }
      pintarAba(a); salvar();
    }
    function tirarErro(v) { v.painel.querySelectorAll('.aba-erro').forEach(function (x) { x.remove(); }); }
    function erroNoPainel(v, a) {
      const el = document.createElement('div');
      el.className = 'aba-erro';
      el.innerHTML = '<p>Não consegui mostrar esta tela dentro da aba.</p><a class="aba-erro-b" target="_blank" rel="noopener">Abrir fora das abas</a>';
      el.querySelector('a').href = a.url + (a.url.indexOf('?') >= 0 ? '&' : '?') + 'solo=1';
      v.painel.appendChild(el);
    }

    function ativar(id, opcoes) {
      if (id !== 'inicio' && !achar(id)) id = 'inicio';
      ativa = id;
      const noInicio = id === 'inicio';
      abaInicio.classList.toggle('on', noInicio); abaInicio.setAttribute('aria-selected', noInicio ? 'true' : 'false');
      abaInicio.tabIndex = noInicio ? 0 : -1;
      painelInicio.hidden = !noInicio;
      Object.keys(vivas).forEach(function (k) {
        const v = vivas[k], on = k === id;
        v.aba.classList.toggle('on', on); v.aba.setAttribute('aria-selected', on ? 'true' : 'false'); v.aba.tabIndex = on ? 0 : -1;
        v.painel.hidden = !on;
      });
      if (noInicio) {
        document.title = 'Início · Grid Co.';
      } else {
        const a = achar(id), v = vivas[id];
        carregar(a); pintarAba(a);
        try { v.aba.scrollIntoView({block: 'nearest', inline: 'nearest'}); } catch (e) { /* navegador velho */ }
        // o teclado vai para a tela (Esc, F5 do Histórico); pela faixa com as setas, fica na faixa
        if (opcoes && opcoes.focar && v.frame) { try { v.frame.contentWindow.focus(); } catch (e) { /* ainda carregando */ } }
      }
      salvar();
    }
    // os Ativos são UMA tela (o catálogo, com a busca dentro): o cartão acende a aba que já existe, sem perder a busca
    // dela; a busca nova do Início leva essa mesma aba para a busca nova. As outras telas abrem uma aba por endereço
    // (o Histórico geral e a Visão COS lado a lado; a String e o Tracker parado pela metade, cada um na sua).
    const UMA_ABA = {ativos: true};
    function abrir(url, nome) {
      const u = normalizar(url, location.href); if (!u) return null;
      const ja = acharAba(abas, u);
      if (ja) { ativar(ja.id, {focar: true}); return ja.id; }
      const sec = secaoDe(u, tabela);
      const mesma = UMA_ABA[sec] && abas.filter(function (a) { return a.secao === sec; })[0];
      if (mesma) {
        if (u.indexOf('?') >= 0) navegar(mesma.id, u); else ativar(mesma.id, {focar: true});
        return mesma.id;
      }
      seq += 1;
      const a = {id: 'a' + seq, origem: u, url: u, titulo: rotulo(nome), secao: secaoDe(u, tabela), primeira: true};
      abas.push(a); montar(a);
      vivas[a.id].aba.classList.add('nova');
      ativar(a.id, {focar: true});
      return a.id;
    }
    function navegar(id, url, nome) {
      const a = achar(id), v = vivas[id]; if (!a || !v) return;
      const u = normalizar(url, location.href); if (!u) return;
      a.url = u; a.secao = secaoDe(u, tabela); if (nome) a.titulo = rotulo(nome);
      if (v.frame) {
        mostrarCarga(v, a, null); carregando(v, true); tirarErro(v);
        try { v.frame.contentWindow.location.href = u; } catch (e) { v.frame.src = u; }
      }
      ativar(id, {focar: true});
    }
    function fechar(id) {
      const i = abas.findIndex(function (a) { return a.id === id; }); if (i < 0) return;
      const prox = ativa === id ? vizinha(abas, id) : ativa;
      const v = vivas[id];
      if (v) { esconderCarga(v); v.aba.remove(); v.painel.remove(); delete vivas[id]; }
      abas.splice(i, 1);
      ativar(prox);
    }
    function atualizar(id, url, titulo) {
      const a = achar(id), v = vivas[id]; if (!a || !v) return;
      const u = normalizar(url, location.href);
      if (u) { a.url = u; a.secao = secaoDe(u, tabela); }
      const t = rotulo(titulo); if (t) a.titulo = t;
      esconderCarga(v); carregando(v, false); tirarErro(v);
      if (duplicada(a)) return;
      pintarAba(a); salvar();
    }
    // A 1ª tela de uma aba que nasceu de um endereço que redireciona (a busca do Início: o número vira a OS, o texto
    // vira os Ativos) e caiu numa tela JÁ aberta noutra aba: fica a de antes, acesa — buscar a OS 14500 com ela aberta
    // não abre a segunda. Só na 1ª tela: a aba em que a pessoa andou até uma tela repetida não some.
    function duplicada(a) {
      if (!a.primeira) return false;
      a.primeira = false;
      const outra = abas.filter(function (b) { return b.id !== a.id && b.url === a.url; })[0];
      if (!outra) return false;
      fechar(a.id); ativar(outra.id, {focar: true});
      return true;
    }
    function idDaMoldura(janela) {
      const ks = Object.keys(vivas);
      for (let i = 0; i < ks.length; i++) { const f = vivas[ks[i]].frame; if (f && f.contentWindow === janela) return ks[i]; }
      return null;
    }

    window.addEventListener('message', function (e) {
      if (e.origin !== location.origin) return;
      const d = e.data;
      if (!d || d.osAbas !== 1) return;
      const id = idDaMoldura(e.source);
      if (!id) return;                                     // só as molduras das abas falam com a casca
      if (d.tipo === 'pagina') atualizar(id, d.url, d.titulo);
      else if (d.tipo === 'saindo') carregando(vivas[id], true);
      else if (d.tipo === 'inicio') ativar('inicio');
      else if (d.tipo === 'abrir') abrir(d.url, d.rotulo);
      else if (d.tipo === 'fechar') fechar(id);
      else if (d.tipo === 'topo') {
        try { const u = new URL(d.url, location.href); if (u.origin === location.origin) location.href = u.pathname + u.search + u.hash; } catch (err) { /* nada */ }
      }
    });

    // os cliques do Início abrem abas. Na CAPTURA: o carga.js trata o link do Histórico (data-carga) na bolha do
    // document e navegaria a casca inteira antes de mim.
    window.addEventListener('click', function (e) {
      if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      const el = e.target && e.target.closest && e.target.closest('a[href], .aba');
      if (!el) return;
      if (el === abaInicio) { e.preventDefault(); ativar('inicio'); return; }
      if (el.classList.contains('aba')) {                  // a faixa: o X fecha, o resto acende
        e.preventDefault();
        const id = el.getAttribute('data-aba');
        if (e.target.closest('.aba-x')) fechar(id); else ativar(id, {focar: true});
        return;
      }
      if (!painelInicio.contains(el) || el.hasAttribute('download')) return;   // o cabeçalho (Plataforma, sair) segue
      const u = normalizar(el.getAttribute('href'), location.href);
      if (!u) return;
      e.preventDefault();
      abrir(u, rotuloDoLink(el));
    }, true);
    // a busca do Início: o resultado (a OS pelo número, os ativos pelo texto) abre numa aba
    window.addEventListener('submit', function (e) {
      const f = e.target;
      if (!f || !painelInicio.contains(f) || (f.method || 'get').toLowerCase() !== 'get') return;
      let u;
      try { u = new URL(f.getAttribute('action') || location.href, location.href); } catch (err) { return; }
      if (u.pathname === '/os/buscar') {
        const d = destinoDaBusca((f.querySelector('input[name="q"]') || {}).value);
        if (!d) return;
        e.preventDefault();
        abrir(d.url, d.rotulo);
        return;
      }
      new FormData(f).forEach(function (val, k) { u.searchParams.append(k, val); });
      const url = normalizar(u.pathname + u.search, location.href);
      if (!url) return;
      e.preventDefault();
      abrir(url, rotuloDoLink(f));
    }, true);
    // o botão do meio na aba fecha, como no navegador
    lista.addEventListener('auxclick', function (e) {
      const el = e.target.closest && e.target.closest('.aba');
      if (el && e.button === 1) { e.preventDefault(); fechar(el.getAttribute('data-aba')); }
    });
    lista.addEventListener('mousedown', function (e) { if (e.button === 1 && e.target.closest('.aba')) e.preventDefault(); });   // sem a rolagem automática
    // a roda do mouse na faixa cheia anda para os lados
    lista.addEventListener('wheel', function (e) {
      if (lista.scrollWidth <= lista.clientWidth || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      lista.scrollLeft += e.deltaY; e.preventDefault();
    }, {passive: false});
    // teclado na faixa (o padrão de tablist): setas andam, Home/End vão às pontas, Enter/Espaço acendem, Delete fecha
    lista.addEventListener('keydown', function (e) {
      const todas = [abaInicio].concat(abas.map(function (a) { return vivas[a.id] && vivas[a.id].aba; }).filter(Boolean));
      const i = todas.indexOf(document.activeElement);
      if (i < 0) return;
      let alvo = null;
      if (e.key === 'ArrowRight') alvo = todas[(i + 1) % todas.length];
      else if (e.key === 'ArrowLeft') alvo = todas[(i - 1 + todas.length) % todas.length];
      else if (e.key === 'Home') alvo = todas[0];
      else if (e.key === 'End') alvo = todas[todas.length - 1];
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ativar(i === 0 ? 'inicio' : todas[i].getAttribute('data-aba')); return; }
      else if (e.key === 'Delete' && i > 0) {
        e.preventDefault(); const id = todas[i].getAttribute('data-aba'); const prox = todas[i + 1] || todas[i - 1];
        fechar(id); if (prox) prox.focus(); return;
      }
      if (alvo) { e.preventDefault(); todas.forEach(function (t) { t.tabIndex = t === alvo ? 0 : -1; }); alvo.focus(); }
    });

    window.OsAbas = {puro: puro, casca: true, secoes: tabela, abrir: abrir, ativar: ativar, fechar: fechar,
                     abas: function () { return abas.map(function (a) { return {id: a.id, url: a.url, titulo: a.titulo, secao: a.secao}; }); },
                     ativa: function () { return ativa; }};

    restaurar();
    abas.forEach(montar);
    const pedida = abaDoEndereco(location.search, location.href);
    if (location.search) { try { history.replaceState(null, '', '/os/'); } catch (e) { /* sem history */ } }
    if (pedida) abrir(pedida); else ativar(ativa);
  }
})();
