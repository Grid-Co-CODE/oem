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
   Este arquivo carrega SEM `defer` no base.html: as telas o usam já na carga (o catálogo dos Ativos).

   Sem fim, nunca (13/10/2026, Levi: "As vezes o OS Creator Web fica em um loop infinito, isso é por causa do
   fractal?"): o círculo esperava a resposta sem prazo, e no caso do print o Nexus do servidor ficou 3 min sem responder
   nem o /saude, com as 16 threads presas (o casca/presos.py do Nexus diz em quê). Aos ESPERA_S o círculo conta a
   espera; aos LIMITE_S (o prazo de uma chamada ao Fracttal) diz que está demorando e dá a saída: "Tentar de novo" só
   onde repetir é seguro (abrir uma página por link; formulário e gravação nunca, para não criar duas OS) e "Fechar" (o
   pedido segue; se a resposta chegar, a página segue normal). No Histórico, que tem progresso, o prazo conta do último
   pedido ao Fracttal que terminou: busca grande andando não está demorando. */
(function () {
  'use strict';
  if (window.OsCarga) return;
  const R = 27, C = 2 * Math.PI * R;
  const TEXTO_HIST = 'Buscando as OS no Fracttal…';
  const ESPERA_S = 15, LIMITE_S = 45;
  let el = null, relogio = null, atraso = null, pendentes = 0, espera = null, feitoVisto = -1;

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

  // a espera contada na caixa; `repetir` só onde repetir é seguro (abrir uma página por link)
  function contarEspera(caixa, repetir, fechar) {
    let desde = Date.now(), acoes = null;
    const linha = document.createElement('div');
    linha.className = 'carga-sub carga-espera';
    caixa.appendChild(linha);
    const relogioEspera = setInterval(function () {
      const s = Math.round((Date.now() - desde) / 1000);
      if (s < ESPERA_S) { linha.textContent = ''; return; }
      if (s < LIMITE_S) { linha.textContent = 'Esperando o servidor há ' + s + ' s'; return; }
      linha.textContent = 'Está demorando mais que o normal: esperando o servidor há ' + s
        + ' s. O Fracttal pode estar lento ou o Nexus, ocupado.';
      if (acoes) return;
      acoes = document.createElement('div');
      acoes.className = 'carga-acoes';
      if (repetir) {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'os-btn mini'; b.textContent = 'Tentar de novo';
        b.addEventListener('click', function () { avancou(); repetir(); });   // a espera conta de novo
        acoes.appendChild(b);
      }
      const f = document.createElement('button');
      f.type = 'button'; f.className = 'os-btn secondary mini'; f.textContent = 'Fechar';
      f.addEventListener('click', fechar);
      acoes.appendChild(f);
      caixa.appendChild(acoes);
    }, 1000);
    function avancou() { desde = Date.now(); linha.textContent = ''; if (acoes) { acoes.remove(); acoes = null; } }
    return {parar: function () { clearInterval(relogioEspera); linha.remove(); if (acoes) acoes.remove(); }, avancou: avancou};
  }

  function esperar(repetir) {
    if (!espera) espera = contarEspera(el.querySelector('.carga-caixa'), repetir, function () { pendentes = 0; esconder(); });
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
  function girar(texto, repetir) {
    montar(); clearInterval(relogio); esperar(repetir);
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

  function mostrar(t, repetir) {
    montar(); clearTimeout(atraso); clearInterval(relogio);
    if (espera) { espera.parar(); espera = null; }
    esperar(repetir); feitoVisto = -1;
    pintar(0, 0);
    el.querySelector('.carga-txt').textContent = TEXTO_HIST;
    atraso = setTimeout(function () { el.hidden = false; }, 250);
    relogio = setInterval(function () {
      fetch('/os/historico/progresso?p=' + encodeURIComponent(t), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (!j || !el) return;
          if ((j.feito || 0) !== feitoVisto) { feitoVisto = j.feito || 0; if (espera) espera.avancou(); }
          pintar(j.feito || 0, j.total || 0);
        })
        .catch(function () { /* a página nova já está chegando */ });
    }, 350);
  }

  function esconder() {
    clearTimeout(atraso); clearInterval(relogio);
    if (espera) { espera.parar(); espera = null; }
    if (el) el.hidden = true;
  }

  document.addEventListener('click', function (e) {
    const a = e.target.closest && e.target.closest('a[data-carga]');
    if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const t = token(), u = new URL(a.getAttribute('href'), location.href);
    u.searchParams.set('p', t);
    const destino = u.pathname + u.search;
    mostrar(t, function () { location.href = destino; });
    location.href = destino;
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
    const destino = a.href;
    setTimeout(function () {
      if (!e.defaultPrevented) girar(a.getAttribute('data-carga-texto') || 'Carregando…', function () { location.href = destino; });
    }, 0);
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
