/* os_creator/os_web/static/carga.js — o círculo de carga (Levi, 27/09/2026: "no período de carregamento poderia ter um
   círculo de carregar mostrando o progresso do carregamento").

   A busca do Histórico é do SERVIDOR (ele pagina o Fracttal): a página velha fica na tela até a nova chegar. Quem manda a
   busca gera um token, o põe na URL (`p=`) e chama `OsCarga.mostrar(token)`; o círculo pergunta a
   /os/historico/progresso quantos pedidos ao Fracttal já terminaram (as páginas da listagem e os lotes do meta) e enche
   com isso. Antes de a 1ª página revelar o total, o círculo GIRA sem número — não inventa porcentagem.

   Aparece só depois de 250 ms: a busca que vem da memória (a visão já vista) é instantânea, e um círculo piscando nela
   seria ruído. Links com `data-carga` (a aba Históricos de OS) ganham o token e o círculo sozinhos.

   Desde 27/09 vale para TUDO o que demora (Levi: "inserir a visão de loading que temos no histórico de OS para tudo o
   que precisa gastar tempo carregando"), sem progresso — girando — onde não há o que contar:
   - toda página do OS Creator aberta por link ou formulário (o clique que outra tela interceptou, como o card da OS,
     não conta: a decisão espera o fim do clique);
   - as buscas e gravações que a pessoa dispara, por `OsCarga.buscar(url, opções, texto)` no lugar do `fetch`.
   O que a tela busca sozinha, em segundo plano (contagens, miniaturas, recentes), fica de fora de propósito.
   Este arquivo carrega SEM `defer` no base.html: as telas o usam já na carga (o catálogo dos Ativos). */
(function () {
  'use strict';
  if (window.OsCarga) return;
  const R = 27, C = 2 * Math.PI * R;
  const TEXTO_HIST = 'Buscando as OS no Fracttal…';
  let el = null, relogio = null, atraso = null, pendentes = 0;

  function token() { return Math.random().toString(36).slice(2, 12) + Date.now().toString(36); }

  function montar() {
    if (el) return el;
    el = document.createElement('div');
    el.className = 'carga'; el.hidden = true;
    el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite');
    el.innerHTML = '<div class="carga-caixa">'
      + '<svg class="carga-anel ind" viewBox="0 0 64 64" aria-hidden="true"><circle class="carga-trilho" cx="32" cy="32" r="' + R + '"/>'
      + '<circle class="carga-arco" cx="32" cy="32" r="' + R + '" stroke-dasharray="' + C.toFixed(2) + '" stroke-dashoffset="' + (C * 0.75).toFixed(2) + '"/></svg>'
      + '<div class="carga-pct"></div><div class="carga-txt">Buscando as OS no Fracttal…</div><div class="carga-sub"></div></div>';
    document.body.appendChild(el);
    return el;
  }

  function pintar(feito, total) {
    const anel = el.querySelector('.carga-anel'), arco = el.querySelector('.carga-arco');
    if (!total) { anel.classList.add('ind'); el.querySelector('.carga-pct').textContent = ''; return; }
    anel.classList.remove('ind');
    const f = Math.max(0, Math.min(1, feito / total));
    arco.setAttribute('stroke-dashoffset', (C * (1 - f)).toFixed(2));
    el.querySelector('.carga-pct').textContent = Math.round(f * 100) + '%';
    el.querySelector('.carga-sub').textContent = feito + ' de ' + total + ' pedidos ao Fracttal';
    el.querySelector('.carga-txt').textContent = f >= 1 ? 'Montando a tabela…' : 'Buscando as OS no Fracttal…';
  }

  // girando, sem número: a página ou a busca que não tem o que contar
  function girar(texto) {
    montar(); clearInterval(relogio);
    pintar(0, 0);
    el.querySelector('.carga-txt').textContent = texto || 'Carregando…';
    el.querySelector('.carga-sub').textContent = '';
    if (el.hidden) { clearTimeout(atraso); atraso = setTimeout(function () { el.hidden = false; }, 250); }
  }

  // o círculo enquanto a promessa não volta; várias ao mesmo tempo somem juntas, quando a última voltar
  function durante(p, texto) {
    pendentes++;
    girar(texto);
    const fim = function () { pendentes = Math.max(0, pendentes - 1); if (!pendentes) esconder(); };
    Promise.resolve(p).then(fim, fim);
    return p;
  }

  function buscar(url, opcoes, texto) { return durante(fetch(url, opcoes), texto); }

  function mostrar(t) {
    montar(); clearTimeout(atraso); clearInterval(relogio);
    pintar(0, 0);
    el.querySelector('.carga-txt').textContent = TEXTO_HIST;
    atraso = setTimeout(function () { el.hidden = false; }, 250);
    relogio = setInterval(function () {
      fetch('/os/historico/progresso?p=' + encodeURIComponent(t), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { if (j && el) pintar(j.feito || 0, j.total || 0); })
        .catch(function () { /* a página nova já está chegando */ });
    }, 350);
  }

  function esconder() { clearTimeout(atraso); clearInterval(relogio); if (el) el.hidden = true; }

  document.addEventListener('click', function (e) {
    const a = e.target.closest && e.target.closest('a[data-carga]');
    if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const t = token(), u = new URL(a.getAttribute('href'), location.href);
    u.searchParams.set('p', t);
    mostrar(t);
    location.href = u.pathname + u.search;
  });

  // é uma PÁGINA do OS Creator que vai abrir nesta aba? (não: outra aba, download, âncora, API, arquivo estático)
  function ehPagina(a) {
    if ((a.target && a.target !== '_self') || a.hasAttribute('download') || a.hasAttribute('data-sem-carga')) return false;
    let u;
    try { u = new URL(a.getAttribute('href'), location.href); } catch (err) { return false; }
    if (u.origin !== location.origin || !/^\/os(\/|$)/.test(u.pathname)) return false;
    if (/^\/os\/(api|static|assets)\//.test(u.pathname)) return false;
    return !(u.pathname === location.pathname && u.search === location.search);    // só a âncora mudou
  }
  // a decisão espera o fim do clique: a tela que abriu um card no lugar (preventDefault) não navega
  document.addEventListener('click', function (e) {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.hasAttribute('data-carga') || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (!ehPagina(a)) return;
    setTimeout(function () { if (!e.defaultPrevented) girar(a.getAttribute('data-carga-texto') || 'Carregando…'); }, 0);
  });
  document.addEventListener('submit', function (e) {
    const f = e.target;
    if (!f || f.hasAttribute('data-sem-carga') || (f.target && f.target !== '_self')) return;
    setTimeout(function () { if (!e.defaultPrevented) girar(f.getAttribute('data-carga-texto') || 'Carregando…'); }, 0);
  });
  // voltar pelo botão do navegador traz a página da memória dele — com o círculo ainda na tela, se não esconder
  window.addEventListener('pageshow', function () { pendentes = 0; esconder(); });

  window.OsCarga = {token: token, mostrar: mostrar, esconder: esconder, girar: girar, durante: durante, buscar: buscar};
})();
