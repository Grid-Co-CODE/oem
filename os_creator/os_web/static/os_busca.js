// os_creator/os_web/static/os_busca.js — todo <select> comprido vira campo de BUSCA, e toda lista de marcar comprida
// (<details class="os-multi">) ganha uma caixa de busca no topo. É o componente ÚNICO de "digitar para achar" do OS
// Creator Web: as telas só marcam o campo (data-busca="1"); nenhuma tem a sua própria busca.
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
//
// Levi, 08/10/2026: "Conseguir digitar no responsável na criação de OS" e "Conseguir digitar o nome da usina no filtro
// do histórico". O responsável chega por fetch DEPOIS da tela pronta: o <select> nascia com 1 opção ("carregando…"), a
// regra dos 6 itens não o pegava e ele ficava nativo, sem digitar (Performance, Engenharia, trocar responsável). Daí:
//  - campo marcado com data-busca="1" vira busca mesmo nascendo vazio, inclusive o que entra depois na página;
//  - casa sem acento e sem caixa, palavra por palavra e em qualquer ordem ("silva ana" acha "Ana Teste Silva");
//  - o valor do <select> só muda escolhendo uma opção da lista: texto que não é de ninguém NÃO vale. Ao sair do campo,
//    vale a opção cujo nome é exatamente o digitado; qualquer outro texto volta para a escolha que valia, e a tela diz
//    por quê. O que vai ao servidor é sempre o value de uma <option>, como antes;
//  - teclado: setas, Enter (escolhe; nunca envia o formulário por baixo), Tab (depois de digitar, aceita a opção
//    marcada) e Esc. O <select> escondido sai do Tab, e o clique no rótulo cai na busca;
//  - a lista de marcar (Cliente, Usina, Tipo... do Histórico) esconde o que não casa por CLASSE (osm-fora), nunca por
//    [hidden]: o hidden é a cascata cliente → usina do Histórico, e o que está marcado continua valendo no filtro mesmo
//    fora da busca.
(function () {
  'use strict';
  const MIN_OPC = 6;              // abaixo disso o nativo já resolve, e a caixa extra só atrapalha
  const raizGlobal = typeof window !== 'undefined' ? window : globalThis;

  // sem acento, sem caixa e com os espaços colapsados: "  SÃO  joão " → "sao joao"
  const norm = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/\s+/g, ' ').trim();
  // cada palavra digitada tem de aparecer no texto (no meio também), em qualquer ordem; filtro vazio casa com tudo
  function casa(texto, filtro) {
    const t = norm(texto);
    return norm(filtro).split(' ').every((f) => t.includes(f));
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

  raizGlobal.OsBusca = {aplicar: aplicar, norm: norm, casa: casa};
  if (typeof document === 'undefined') return;          // fora do navegador (o teste das regras) só valem as funções

  let seq = 0;

  // o nome do campo para quem usa leitor de tela: o aria-label, ou o rótulo visível ao lado
  function rotuloDe(el) {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const caixa = el.closest('label, .os-campo, .os-cell, .hf-cel, .fcampo');
    const r = caixa && caixa.querySelector('.os-lbl, .hf-lbl, .flbl');
    if (!r) return '';
    const c = r.cloneNode(true);                         // só o nome: sem o "*", a dica "(digite…)" e o botão ↻
    c.querySelectorAll('small, button, i').forEach((x) => x.remove());
    return c.textContent.replace(/\s+/g, ' ').trim();
  }

  function textoAtual(sel) {
    const o = sel.options[sel.selectedIndex];
    return o ? o.text : '';
  }

  // ═══ o <select> vira campo de busca (combobox) ═══
  function montar(sel) {
    if (sel.dataset.osb || sel.multiple || sel.hidden) return;
    sel.dataset.osb = '1';
    const id = 'osb' + (++seq);

    const cx = document.createElement('div');
    cx.className = 'osb';
    sel.parentNode.insertBefore(cx, sel);
    cx.appendChild(sel);

    const inp = document.createElement('input');
    inp.type = 'text';
    inp.className = 'osb-in';
    inp.autocomplete = 'off';
    inp.spellcheck = false;
    inp.disabled = sel.disabled;
    inp.setAttribute('role', 'combobox');
    inp.setAttribute('aria-autocomplete', 'list');
    inp.setAttribute('aria-expanded', 'false');
    inp.setAttribute('aria-controls', id + '-l');
    const rot = rotuloDe(sel);
    if (rot) inp.setAttribute('aria-label', rot);
    cx.appendChild(inp);

    const lst = document.createElement('div');
    lst.className = 'osb-lista';
    lst.id = id + '-l';
    lst.setAttribute('role', 'listbox');
    lst.hidden = true;
    cx.appendChild(lst);

    const aviso = document.createElement('div');
    aviso.className = 'osb-aviso';
    aviso.setAttribute('role', 'status');
    aviso.hidden = true;
    cx.appendChild(aviso);

    // o <select> escondido sai do Tab; o clique no rótulo (que foca o <select>) e o .focus() das telas caem na busca
    sel.tabIndex = -1;
    sel.addEventListener('focus', () => { if (!inp.disabled) inp.focus(); });

    let marcado = -1;               // índice na lista VISÍVEL (navegação por seta)
    let digitou = false;            // o texto da caixa é o que a pessoa digitou, e não o nome da opção escolhida
    let tAviso = null;

    // a caixa mostra o nome da opção que vale; a opção vazia ("— selecione —", "carregando…", "Todos os tipos") vira o
    // texto de fundo, apagado: a caixa fica livre para digitar e não parece já preenchida
    function mostrar() {
      const o = sel.options[sel.selectedIndex], vazia = !o || o.value === '';
      inp.value = vazia ? '' : o.text;
      inp.placeholder = vazia ? (o ? o.text : '') : '';
    }
    mostrar();

    function opcoes() {
      return [...sel.options].map((o, i) => ({i: i, txt: o.text, val: o.value, dis: o.disabled}));
    }

    function avisar(txt) {
      aviso.textContent = txt || '';
      aviso.hidden = !txt;
      clearTimeout(tAviso);
      if (txt) tAviso = setTimeout(() => { aviso.hidden = true; }, 8000);
    }

    function mostrarMarcado() {     // rola SÓ a lista (scrollIntoView rolaria também a página e a moldura do Nexus)
      const el = lst.children[marcado];
      if (!el || !el.classList.contains('osb-op')) return;
      if (el.offsetTop < lst.scrollTop) lst.scrollTop = el.offsetTop;
      else if (el.offsetTop + el.offsetHeight > lst.scrollTop + lst.clientHeight) lst.scrollTop = el.offsetTop + el.offsetHeight - lst.clientHeight;
    }

    function pintar(filtro) {
      // as opções são lidas AGORA, e não na montagem: usinas e responsáveis chegam por fetch
      // depois da tela pronta, e uma lista congelada mostraria o estado vazio para sempre.
      const vis = opcoes().filter((o) => !o.dis && casa(o.txt, filtro));
      marcado = vis.length ? 0 : -1;
      if (!norm(filtro)) {          // sem nada digitado, a lista abre na opção que já vale
        const k = vis.findIndex((o) => o.i === sel.selectedIndex);
        if (k >= 0) marcado = k;
      }
      lst.innerHTML = vis.length
        ? vis.map((o, k) => '<div class="osb-op' + (k === marcado ? ' on' : '') + '" role="option" id="' + id + '-' + k
            + '" aria-selected="' + (k === marcado) + '" data-i="' + o.i + '" title="' + esc(o.txt) + '">' + esc(o.txt) + '</div>').join('')
        : '<div class="osb-vazio">' + (norm(filtro) ? 'Nenhuma opção tem “' + esc(filtro.trim()) + '”.' : 'Nada para escolher ainda.') + '</div>';
      if (marcado >= 0) inp.setAttribute('aria-activedescendant', id + '-' + marcado);
      else inp.removeAttribute('aria-activedescendant');
      mostrarMarcado();
    }

    function abrir() {
      if (sel.disabled || !lst.hidden) return;
      digitou = false;
      avisar('');
      lst.hidden = false;
      inp.setAttribute('aria-expanded', 'true');
      pintar('');
      inp.select();
    }

    function fechar() {
      lst.hidden = true;
      inp.setAttribute('aria-expanded', 'false');
      inp.removeAttribute('aria-activedescendant');
    }

    // o texto volta para a opção que vale; com `motivo`, a tela diz por que o digitado não valeu
    function voltar(motivo) {
      fechar();
      digitou = false;
      mostrar();
      if (motivo) avisar(motivo + (sel.value ? ' Continua valendo: ' + textoAtual(sel) + '.' : ' Nada escolhido ainda.'));
    }

    function escolher(idx) {
      if (idx == null || idx < 0) return;
      sel.selectedIndex = idx;
      digitou = false;
      mostrar();
      fechar();
      avisar('');
      // o `change` é o que as telas escutam — sem ele a cascata cliente→usina não anda
      sel.dispatchEvent(new Event('change', {bubbles: true}));
    }

    // saiu do campo sem escolher: vale a opção cujo nome é EXATAMENTE o digitado; qualquer outro texto volta e é avisado
    function sair() {
      if (!digitou) { fechar(); mostrar(); return; }
      const txt = inp.value, n = norm(txt);
      if (!n || n === norm(sel.value === '' ? '' : textoAtual(sel))) { voltar(''); return; }
      const ops = opcoes().filter((o) => !o.dis);
      const exatas = ops.filter((o) => norm(o.txt) === n);
      if (exatas.length === 1) { escolher(exatas[0].i); return; }
      const parecidas = ops.filter((o) => casa(o.txt, txt)).length;
      voltar(parecidas ? '“' + txt.trim() + '” não foi escolhido: clique numa opção da lista ou tecle Enter.'
                       : 'Nenhuma opção tem “' + txt.trim() + '”.');
    }

    function mover(d) {
      const ops = [...lst.querySelectorAll('.osb-op')];
      if (!ops.length) return;
      marcado = Math.max(0, Math.min(ops.length - 1, marcado + d));
      ops.forEach((e, k) => { e.classList.toggle('on', k === marcado); e.setAttribute('aria-selected', String(k === marcado)); });
      inp.setAttribute('aria-activedescendant', ops[marcado].id);
      mostrarMarcado();
    }

    inp.addEventListener('focus', abrir);
    // o clique que dá o foco também põe o cursor e desfaz o select() do foco: refaz, enquanto nada foi digitado
    inp.addEventListener('click', () => { if (lst.hidden) abrir(); else if (!digitou) inp.select(); });
    inp.addEventListener('input', () => {
      digitou = true;
      avisar('');
      if (lst.hidden) { lst.hidden = false; inp.setAttribute('aria-expanded', 'true'); }
      pintar(inp.value);
    });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (lst.hidden) abrir(); else mover(e.key === 'ArrowDown' ? 1 : -1);
      } else if (e.key === 'Enter') {
        // o Enter escolhe e NUNCA envia o formulário por baixo (no Histórico, refaria a busca inteira no Fracttal)
        e.preventDefault();
        if (lst.hidden) { abrir(); return; }
        const op = lst.querySelector('.osb-op.on');
        if (op) escolher(Number(op.dataset.i));
        else avisar('Nenhuma opção tem “' + inp.value.trim() + '”.');
      } else if (e.key === 'Tab') {
        // depois de digitar, o Tab aceita a opção marcada (como o Enter) e segue para o próximo campo
        const op = !lst.hidden && digitou && norm(inp.value) ? lst.querySelector('.osb-op.on') : null;
        if (op) escolher(Number(op.dataset.i));
      } else if (e.key === 'Escape') {
        if (!lst.hidden) { e.preventDefault(); e.stopPropagation(); }
        voltar('');
      }
    });
    lst.addEventListener('mousedown', (e) => {          // mousedown, não click: o blur chegaria antes
      if (e.target === lst) return;                     // a barra de rolagem da lista segue nativa
      e.preventDefault();
      const op = e.target.closest('.osb-op');
      if (op) escolher(Number(op.dataset.i));
    });
    // a lista mora dentro do <label> do campo: o clique nela não pode "clicar no rótulo", que focaria o <select> e
    // reabriria a lista que acabou de fechar
    lst.addEventListener('click', (e) => e.preventDefault());
    // saiu do campo: resolve NA HORA, e não 120 ms depois. Com o atraso, o clique no "Criar OS" (mousedown tira o foco,
    // o click vem logo atrás) chegava antes: a caixa mostrava o nome exato de outra pessoa, digitado por cima da escolha,
    // e a OS saía com quem valia antes
    // (revisão de 08/10/2026, reproduzido no Chrome sem janela). A lista não rouba o foco (mousedown com preventDefault),
    // e na janela que perde o foco (Alt+Tab) o activeElement continua sendo a busca: nada se resolve à toa.
    inp.addEventListener('blur', () => { if (document.activeElement !== inp) sair(); });

    // alguém mexeu no <select> por código (cascata, sugestão do deep link, reset após criar)
    sel.addEventListener('change', () => { if (lst.hidden) { digitou = false; mostrar(); } });
    // ... inclusive sem disparar o change (`sel.value = x`): o texto da busca acompanha
    ['value', 'selectedIndex'].forEach((p) => {
      const d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, p);
      if (!d || !d.get || !d.set) return;
      Object.defineProperty(sel, p, {configurable: true, enumerable: true,
        get() { return d.get.call(this); },
        set(v) { d.set.call(this, v); if (lst.hidden && !digitou) mostrar(); }});
    });
    // as opções trocadas (o fetch que chega, o ↻) entram na lista aberta; o disabled acompanha
    new MutationObserver(() => {
      inp.disabled = sel.disabled;
      if (sel.disabled && !lst.hidden) fechar();
      if (!digitou) mostrar();        // com a lista aberta também: o "carregando…" de fundo vira o "— selecione —"
      if (!lst.hidden) pintar(digitou ? inp.value : '');
    }).observe(sel, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['disabled']});
  }

  // ═══ a lista de marcar (<details class="os-multi">) ganha a caixa de busca ═══
  function montarMulti(det) {
    if (det.dataset.osb) return;
    const lista = det.querySelector('.os-multi-lista');
    if (!lista) return;
    det.dataset.osb = '1';

    const inp = document.createElement('input');
    inp.type = 'search';                                 // sem name: não vai no formulário
    inp.className = 'osm-busca';
    inp.placeholder = 'Digite para filtrar…';
    inp.autocomplete = 'off';
    inp.spellcheck = false;
    const rot = rotuloDe(det);
    inp.setAttribute('aria-label', 'Filtrar ' + (rot ? rot.toLowerCase() : 'a lista'));
    lista.insertBefore(inp, lista.firstChild);

    const vazio = document.createElement('div');
    vazio.className = 'osm-vazio';
    vazio.hidden = true;
    lista.appendChild(vazio);

    let marcado = -1;
    const linhas = () => [...lista.querySelectorAll('label')];
    // visível = nem a cascata ([hidden]) nem a busca (osm-fora) a esconderam
    const visiveis = () => linhas().filter((l) => !l.hidden && !l.classList.contains('osm-fora'));

    function marcar(k) {
      const vis = visiveis();
      marcado = vis.length && k >= 0 ? Math.min(vis.length - 1, k) : -1;
      linhas().forEach((l) => l.classList.remove('on'));
      if (marcado < 0) return;
      const l = vis[marcado], topo = inp.offsetHeight + 8;  // a busca fica parada no topo e cobre o que passa por baixo
      l.classList.add('on');
      if (l.offsetTop - topo < lista.scrollTop) lista.scrollTop = Math.max(0, l.offsetTop - topo);
      else if (l.offsetTop + l.offsetHeight > lista.scrollTop + lista.clientHeight) lista.scrollTop = l.offsetTop + l.offsetHeight - lista.clientHeight;
    }

    function filtrar() {
      const f = inp.value;
      linhas().forEach((l) => l.classList.toggle('osm-fora', !casa(l.textContent, f)));
      const n = visiveis().length;
      vazio.hidden = n > 0;
      vazio.textContent = norm(f) ? 'Nenhuma opção tem “' + f.trim() + '”.' : 'Nada para escolher.';
      marcar(norm(f) ? 0 : -1);
    }

    inp.addEventListener('input', filtrar);
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        marcar(marcado < 0 ? 0 : Math.max(0, marcado + (e.key === 'ArrowDown' ? 1 : -1)));
      } else if (e.key === 'Enter') {
        e.preventDefault();                              // o Enter marca/desmarca e nunca envia o formulário
        const l = visiveis()[marcado];
        const c = l && l.querySelector('input[type=checkbox]');
        if (c) c.click();                                // o click dispara o change que a tela escuta
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        if (inp.value) { inp.value = ''; filtrar(); }
        else { det.open = false; const s = det.querySelector('summary'); if (s) s.focus(); }
      }
    });
    det.addEventListener('toggle', () => {
      if (det.open) {
        filtrar();
        // no computador a busca já abre com o foco; no celular não (o teclado cobriria metade da lista)
        if (window.matchMedia && window.matchMedia('(pointer: fine)').matches) inp.focus({preventScroll: true});
      } else if (inp.value) {
        inp.value = '';
        filtrar();
      }
    });
  }

  const querSelect = (s) => s.dataset.busca === '1' || s.options.length >= MIN_OPC;
  const querMulti = (d) => d.dataset.busca === '1' || d.querySelectorAll('.os-multi-lista label').length >= MIN_OPC;

  function aplicar(raiz) {
    raiz = raiz || document;
    const eh = (sel) => !!(raiz.matches && raiz.matches(sel));
    (eh('select') ? [raiz] : [...raiz.querySelectorAll('select')]).forEach((s) => { if (querSelect(s)) montar(s); });
    (eh('details.os-multi') ? [raiz] : [...raiz.querySelectorAll('details.os-multi')]).forEach((d) => { if (querMulti(d)) montarMulti(d); });
  }

  function iniciar() {
    aplicar(document);
    // telas que trocam o conteúdo (tabela de ativos, filtros do histórico, diálogos) ganham a busca sozinhas
    new MutationObserver((ms) => {
      for (const m of ms) {
        // as linhas que a própria busca desenha (centenas, a cada tecla) não têm o que montar
        for (const n of m.addedNodes) if (n.nodeType === 1 && !n.classList.contains('osb-op')) aplicar(n);
      }
    }).observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
