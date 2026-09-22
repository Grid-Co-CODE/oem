// os_creator/os_web/static/os_busca.js — todo <select> comprido vira campo de BUSCA.
//
// Levi, 21/09: "quando vou pesquisar algo não consigo digitar; aparece uma barra suspensa onde eu
// até posso digitar mas não aparece o que estou digitando". É o comportamento do <select> nativo:
// o navegador pula para a opção que começa com a tecla apertada, sem mostrar o que foi digitado e
// sem casar no MEIO do nome. Com 60 usinas isso é inútil. O app de mesa resolveu isso com o
// `steps/searchcombo.tornar_pesquisavel`; aqui é o mesmo contrato.
//
// DECISÃO IMPORTANTE: o <select> original CONTINUA na página, escondido, e é ele que guarda o
// valor. Todo o resto do código (`cbCli.value`, `onchange`, `querySelector('select')`) segue
// funcionando sem saber que existe uma busca por cima — nenhuma tela precisou ser reescrita.
(function () {
  'use strict';
  const MIN_OPC = 6;              // abaixo disso o nativo já resolve, e a caixa extra só atrapalha

  const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  function textoAtual(sel) {
    const o = sel.options[sel.selectedIndex];
    return o ? o.text : '';
  }

  function montar(sel) {
    if (sel.dataset.osb || sel.multiple || sel.hidden) return;
    sel.dataset.osb = '1';

    const cx = document.createElement('div');
    cx.className = 'osb';
    sel.parentNode.insertBefore(cx, sel);
    cx.appendChild(sel);

    const inp = document.createElement('input');
    inp.type = 'text';
    inp.className = 'osb-in';
    inp.autocomplete = 'off';
    inp.spellcheck = false;
    inp.value = textoAtual(sel);
    inp.disabled = sel.disabled;
    if (sel.id) inp.setAttribute('aria-controls', sel.id);
    cx.appendChild(inp);

    const lst = document.createElement('div');
    lst.className = 'osb-lista';
    lst.hidden = true;
    cx.appendChild(lst);

    let marcado = -1;               // índice na lista VISÍVEL (navegação por seta)

    function opcoes() {
      return [...sel.options].map((o, i) => ({i: i, txt: o.text, val: o.value, dis: o.disabled}));
    }

    function pintar(filtro) {
      const f = norm(filtro);
      // as opções são lidas AGORA, e não na montagem: usinas e responsáveis chegam por fetch
      // depois da tela pronta, e uma lista congelada mostraria o estado vazio para sempre.
      const vis = opcoes().filter((o) => !o.dis && (!f || norm(o.txt).includes(f)));
      marcado = vis.length ? 0 : -1;
      lst.innerHTML = vis.length
        ? vis.map((o, k) => '<div class="osb-op' + (k === 0 ? ' on' : '') + '" data-i="' + o.i + '">'
            + o.txt.replace(/[&<>]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c])) + '</div>').join('')
        : '<div class="osb-vazio">nada com esse texto</div>';
      lst._vis = vis;
    }

    function abrir() {
      if (sel.disabled) return;
      pintar('');
      lst.hidden = false;
      inp.select();
    }

    function fechar(reverter) {
      lst.hidden = true;
      if (reverter !== false) inp.value = textoAtual(sel);
    }

    function escolher(idx) {
      if (idx == null || idx < 0) return;
      sel.selectedIndex = idx;
      inp.value = textoAtual(sel);
      fechar(false);
      // o `change` é o que as telas escutam — sem ele a cascata cliente→usina não anda
      sel.dispatchEvent(new Event('change', {bubbles: true}));
    }

    function mover(d) {
      const ops = [...lst.querySelectorAll('.osb-op')];
      if (!ops.length) return;
      marcado = Math.max(0, Math.min(ops.length - 1, marcado + d));
      ops.forEach((e, k) => e.classList.toggle('on', k === marcado));
      ops[marcado].scrollIntoView({block: 'nearest'});
    }

    inp.addEventListener('focus', abrir);
    inp.addEventListener('click', abrir);
    inp.addEventListener('input', () => { lst.hidden = false; pintar(inp.value); });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (lst.hidden) abrir(); else mover(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); mover(-1); }
      else if (e.key === 'Enter') {
        const op = lst.querySelector('.osb-op.on');
        if (op) { e.preventDefault(); escolher(Number(op.dataset.i)); }
      } else if (e.key === 'Escape') { e.preventDefault(); fechar(); inp.blur(); }
    });
    lst.addEventListener('mousedown', (e) => {         // mousedown, não click: o blur chegaria antes
      const op = e.target.closest('.osb-op');
      if (op) { e.preventDefault(); escolher(Number(op.dataset.i)); }
    });
    inp.addEventListener('blur', () => setTimeout(() => fechar(), 120));
    // alguém mexeu no <select> por código (cascata, sugestão do deep link, reset após criar)
    sel.addEventListener('change', () => { if (lst.hidden) inp.value = textoAtual(sel); });
    new MutationObserver(() => {
      inp.disabled = sel.disabled;
      if (lst.hidden) inp.value = textoAtual(sel);
    }).observe(sel, {childList: true, attributes: true, attributeFilter: ['disabled']});
  }

  function aplicar(raiz) {
    (raiz || document).querySelectorAll('select').forEach((s) => {
      if (s.options.length >= MIN_OPC || s.dataset.busca === '1') montar(s);
    });
  }

  window.OsBusca = {aplicar: aplicar};
  document.addEventListener('DOMContentLoaded', () => {
    aplicar(document);
    // telas que trocam o conteúdo (tabela de ativos, filtros do histórico) ganham a busca sozinhas
    new MutationObserver((ms) => {
      for (const m of ms) {
        for (const n of m.addedNodes) {
          if (n.nodeType !== 1) continue;
          if (n.tagName === 'SELECT') { if (n.options.length >= MIN_OPC) montar(n); }
          else aplicar(n);
        }
      }
    }).observe(document.body, {childList: true, subtree: true});
  });
})();
