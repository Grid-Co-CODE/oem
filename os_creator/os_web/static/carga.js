/* os_creator/os_web/static/carga.js — o círculo de carga (Levi, 27/09/2026: "no período de carregamento poderia ter um
   círculo de carregar mostrando o progresso do carregamento").

   A busca do Histórico é do SERVIDOR (ele pagina o Fracttal): a página velha fica na tela até a nova chegar. Quem manda a
   busca gera um token, o põe na URL (`p=`) e chama `OsCarga.mostrar(token)`; o círculo pergunta a
   /os/historico/progresso quantos pedidos ao Fracttal já terminaram (as páginas da listagem e os lotes do meta) e enche
   com isso. Antes de a 1ª página revelar o total, o círculo GIRA sem número — não inventa porcentagem.

   Aparece só depois de 250 ms: a busca que vem da memória (a visão já vista) é instantânea, e um círculo piscando nela
   seria ruído. Links com `data-carga` (a aba Históricos de OS) ganham o token e o círculo sozinhos. */
(function () {
  'use strict';
  if (window.OsCarga) return;
  const R = 27, C = 2 * Math.PI * R;
  let el = null, relogio = null, atraso = null;

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

  function mostrar(t) {
    montar(); clearTimeout(atraso); clearInterval(relogio);
    pintar(0, 0);
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
  // voltar pelo botão do navegador traz a página da memória dele — com o círculo ainda na tela, se não esconder
  window.addEventListener('pageshow', esconder);

  window.OsCarga = {token: token, mostrar: mostrar, esconder: esconder};
})();
