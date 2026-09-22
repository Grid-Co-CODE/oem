// os_creator/os_web/static/tickets_painel.js — o painel de acompanhamento dos tickets (22/09/2026).
//
// SÓ DESENHA. Toda conta vem pronta do servidor (tickets_painel.py), pelo mesmo leitor da tela de
// Tickets — aqui não se soma nem se decide nada, para o número deste painel nunca discordar do da
// lista. Porte do mockup aprovado (docs/design/dashboard-tickets-mockup.html).
(function () {
  'use strict';
  const EL = document.getElementById('tp_dados');
  if (!EL) return;
  const J = JSON.parse(EL.textContent);
  const DADOS = J.dados || {}, ESTADOS = J.estados || [];
  let aba = J.aba;
  const tip = document.getElementById('tp_tip');
  const NS = 'http://www.w3.org/2000/svg';

  const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('pt-BR'));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const $ = (id) => document.getElementById(id);
  function el(tag, at, pai) { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); if (pai) pai.appendChild(e); return e; }
  function limpa(svg) { while (svg.firstChild) svg.removeChild(svg.firstChild); }
  function mostraTip(ev, html) { tip.innerHTML = html; tip.style.display = 'block'; tip.style.left = Math.min(ev.clientX + 14, innerWidth - 270) + 'px'; tip.style.top = (ev.clientY + 14) + 'px'; }
  function escondeTip() { tip.style.display = 'none'; }
  // o passo do eixo: redondo e NUNCA menor que 1 — tudo aqui é contagem, e "0,5 ocorrência" não existe
  function passo(max) { const bruto = max / 4, p = Math.pow(10, Math.floor(Math.log10(bruto || 1))); return Math.max(1, [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= bruto) || p); }
  // o link para a tela de Tickets com o filtro: o painel aponta, a lista resolve
  function linkTickets(filtro) {
    const q = new URLSearchParams({aba: aba});
    Object.keys(filtro || {}).forEach((k) => q.set(k, filtro[k]));
    return '/os/tickets?' + q.toString();
  }
  function barraH(x, y, w, h) {          // ponta de dado arredondada, base reta no eixo
    const r = Math.min(4, w / 2, h / 2);
    return 'M' + x + ',' + y + ' H' + (x + w - r) + ' Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) +
      ' V' + (y + h - r) + ' Q' + (x + w) + ',' + (y + h) + ' ' + (x + w - r) + ',' + (y + h) + ' H' + x + ' Z';
  }

  // ── fluxo semanal: DUAS linhas no MESMO eixo (mesma unidade) — nunca eixo duplo ──
  function fluxo(s) {
    const svg = $('g_fluxo'); limpa(svg);
    const W = 560, H = 230, L = 38, R = 86, T = 12, B = 30, sem = s.semanas || [];
    if (sem.length < 2) return;
    const max = Math.max(1, ...sem.map((x) => Math.max(x.abertas, x.fechadas)));
    const st = passo(max), topo = Math.ceil(max / st) * st;
    const x = (i) => L + i * (W - L - R) / (sem.length - 1), y = (v) => T + (H - T - B) * (1 - v / topo);
    for (let g = 0; g <= topo; g += st) {
      el('line', {x1: L, x2: W - R, y1: y(g), y2: y(g), stroke: 'var(--tp-grade)', 'stroke-width': 1}, svg);
      el('text', {x: L - 6, y: y(g) + 4, 'text-anchor': 'end'}, svg).textContent = fmt(g);
    }
    // um rótulo a cada duas semanas, ancorado na MAIS RECENTE (é a que a pessoa procura)
    sem.forEach((w, i) => { if ((sem.length - 1 - i) % 2 === 0) el('text', {x: x(i), y: H - 10, 'text-anchor': 'middle'}, svg).textContent = w.ate; });
    [['abertas', 'var(--tp-s1)'], ['fechadas', 'var(--tp-s2)']].forEach(([campo, cor]) => {
      el('path', {d: sem.map((w, i) => (i ? 'L' : 'M') + x(i) + ',' + y(w[campo])).join(' '), fill: 'none', stroke: cor,
                  'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
      el('circle', {cx: x(sem.length - 1), cy: y(sem[sem.length - 1][campo]), r: 4, fill: cor, stroke: 'var(--tp-card)', 'stroke-width': 2}, svg);
    });
    // rótulo seletivo: só a ponta de cada série. Quando as duas encostam, empilham ACIMA da linha
    // de base — abaixo dela invadiriam a data do eixo (visto no mockup: "2 abertas / 0 fechadas")
    const u = sem[sem.length - 1], ya = y(u.abertas), yf = y(u.fechadas);
    let la = ya + 4, lf = yf + 4;
    if (Math.abs(ya - yf) < 14) {
      const cima = Math.min(Math.min(ya, yf) - 2, H - B - 21);
      if (u.abertas >= u.fechadas) { la = cima; lf = cima + 16; } else { lf = cima; la = cima + 16; }
    }
    el('text', {x: W - R + 8, y: la, 'class': 'tp-lab'}, svg).textContent = fmt(u.abertas) + ' abertas';
    el('text', {x: W - R + 8, y: lf, 'class': 'tp-lab'}, svg).textContent = fmt(u.fechadas) + ' fechadas';
    const cruz = el('line', {x1: 0, x2: 0, y1: T, y2: H - B, stroke: 'var(--tp-txt2)', 'stroke-width': 1, opacity: 0}, svg);
    const alvo = el('rect', {x: L, y: T, width: W - L - R, height: H - T - B, fill: 'transparent'}, svg);
    alvo.addEventListener('mousemove', (ev) => {
      const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width;
      const i = Math.max(0, Math.min(sem.length - 1, Math.round((px - L) / ((W - L - R) / (sem.length - 1)))));
      cruz.setAttribute('x1', x(i)); cruz.setAttribute('x2', x(i)); cruz.setAttribute('opacity', 0.5);
      mostraTip(ev, '<div class="tp-t">' + esc(sem[i].de) + ' a ' + esc(sem[i].ate) + '</div>' + fmt(sem[i].abertas) + ' abertas · ' + fmt(sem[i].fechadas) + ' fechadas');
    });
    alvo.addEventListener('mouseleave', () => { cruz.setAttribute('opacity', 0); escondeTip(); });
    $('t_fluxo').innerHTML = '<thead><tr><th>Semana</th><th class="tp-num">Abertas</th><th class="tp-num">Fechadas</th></tr></thead><tbody>' +
      sem.map((w) => '<tr><td>' + esc(w.de) + ' a ' + esc(w.ate) + '</td><td class="tp-num">' + fmt(w.abertas) + '</td><td class="tp-num">' + fmt(w.fechadas) + '</td></tr>').join('') + '</tbody>';
  }

  // ── idade: faixas ORDENADAS; a cor diz só se passou do alarme (o servidor diz qual) ──
  function idade(s) {
    const svg = $('g_idade'); limpa(svg);
    const W = 560, H = 230, L = 38, R = 12, T = 18, B = 30, fx = s.faixas || [];
    if (!fx.length) return;
    const max = Math.max(1, ...fx.map((f) => f.n)), st = passo(max), topo = Math.ceil(max / st) * st;
    const y = (v) => T + (H - T - B) * (1 - v / topo), banda = (W - L - R) / fx.length, larg = Math.min(24, banda * 0.5);
    for (let g = 0; g <= topo; g += st) {
      el('line', {x1: L, x2: W - R, y1: y(g), y2: y(g), stroke: 'var(--tp-grade)', 'stroke-width': 1}, svg);
      el('text', {x: L - 6, y: y(g) + 4, 'text-anchor': 'end'}, svg).textContent = fmt(g);
    }
    fx.forEach((f, i) => {
      const cx = L + banda * i + banda / 2, x0 = cx - larg / 2, y0 = y(f.n), h = (H - B) - y0;
      if (h > 0) {
        const r = Math.min(4, h);
        el('path', {d: 'M' + x0 + ',' + (H - B) + ' V' + (y0 + r) + ' Q' + x0 + ',' + y0 + ' ' + (x0 + r) + ',' + y0 +
                       ' H' + (x0 + larg - r) + ' Q' + (x0 + larg) + ',' + y0 + ' ' + (x0 + larg) + ',' + (y0 + r) + ' V' + (H - B) + ' Z',
                    fill: f.alarme ? 'var(--tp-crit)' : 'var(--tp-s1)'}, svg);
      }
      el('text', {x: cx, y: y0 - 5, 'text-anchor': 'middle', 'class': 'tp-lab'}, svg).textContent = fmt(f.n);
      el('text', {x: cx, y: H - 10, 'text-anchor': 'middle'}, svg).textContent = f.rotulo + ' d';
      const hit = el('rect', {x: L + banda * i, y: T, width: banda, height: H - T - B, fill: 'transparent'}, svg);
      hit.addEventListener('mousemove', (ev) => mostraTip(ev, '<div class="tp-t">abertas há ' + esc(f.rotulo) + ' dias</div>' + fmt(f.n) + ' ocorrência(s)' + (f.alarme ? '<br>acima do alarme de 30 dias' : '')));
      hit.addEventListener('mouseleave', escondeTip);
    });
    $('t_idade').innerHTML = '<thead><tr><th>Idade</th><th class="tp-num">Abertas</th></tr></thead><tbody>' +
      fx.map((f) => '<tr><td>' + esc(f.rotulo) + ' dias</td><td class="tp-num">' + fmt(f.n) + '</td></tr>').join('') + '</tbody>';
  }

  // ── por cliente: UMA série, uma cor; "(sem cliente)" em cinza, com o motivo no tooltip ──
  function clientes(s) {
    const svg = $('g_cli'); limpa(svg);
    const lst = s.clientes || [], W = 560, L = 118, R = 70, T = 6, linha = 26, H = T + Math.max(1, lst.length) * linha + 6;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    if (!lst.length) { el('text', {x: L, y: T + 14}, svg).textContent = 'nenhuma ocorrência aberta'; return; }
    const max = Math.max(1, ...lst.map((c) => c[2])), esc_ = (v) => (W - L - R) * v / max;
    lst.forEach((c, i) => {
      const y0 = T + i * linha, alt = 14, w = Math.max(2, esc_(c[2])), sem = c[0] === J.sem_cliente, outros = /^outros \(/.test(c[0]);
      el('text', {x: L - 8, y: y0 + alt - 2, 'text-anchor': 'end', 'class': 'tp-lab'}, svg).textContent = c[0];
      el('path', {d: barraH(L, y0, w, alt), fill: sem ? 'var(--tp-cinza)' : 'var(--tp-s1)'}, svg);
      el('text', {x: L + w + 6, y: y0 + alt - 2, 'class': 'tp-lab'}, svg).textContent = fmt(c[2]);
      const hit = el('rect', {x: 0, y: y0 - 5, width: W, height: linha, fill: 'transparent', 'class': outros ? '' : 'tp-clicavel'}, svg);
      hit.addEventListener('mousemove', (ev) => mostraTip(ev, '<div class="tp-t">' + esc(c[0]) + '</div>' + fmt(c[2]) + ' ' + esc(s.rotulo_qtd) +
        ' em ' + fmt(c[1]) + ' ocorrência(s) aberta(s)' + (sem ? '<br>cliente não preenchido na planilha' : '') + (outros ? '' : '<br>clique para abrir na tela de Tickets')));
      hit.addEventListener('mouseleave', escondeTip);
      if (!outros) hit.addEventListener('click', () => { location.href = linkTickets({cliente: c[0]}); });
    });
  }

  function pintar() {
    const s = DADOS[aba] || {};
    const erro = $('tp_erro'), corpo = $('tp_corpo');
    if (s.erro) { erro.textContent = s.erro; erro.hidden = false; corpo.hidden = true; return; }
    erro.hidden = true; corpo.hidden = false;
    $('tp_sub').textContent = fmt(s.total) + ' ocorrências na aba ' + aba + ' · ' + fmt(s.abertas) + ' abertas · lido em ' + J.lido;
    $('k_qtd').textContent = fmt(s.qtd);
    // "segundo a planilha", não "agora": quem diz o que está parado AGORA é o tempo real
    $('k_qtd_l').textContent = s.rotulo_qtd + ' segundo a planilha, em ' + fmt(s.abertas) + ' ocorrências abertas';
    $('k_30').textContent = fmt(s.mais_30);
    $('k_30_d').textContent = s.abertas ? Math.round(100 * s.mais_30 / s.abertas) + '% das abertas' : '—';
    $('k_30_a').href = linkTickets({alarme: '1'});
    $('k_med').textContent = s.mediana_dias == null ? '—' : fmt(s.mediana_dias) + ' dias';
    $('k_med_d').textContent = s.sem_inicio ? fmt(s.sem_inicio) + ' sem data de início ficam fora' : 'todas com data de início';
    $('k_fech').textContent = fmt(s.fechadas_30d);
    $('k_semos').textContent = fmt(s.sem_os);
    $('k_semos_d').textContent = s.abertas ? Math.round(100 * s.sem_os / s.abertas) + '% das abertas' : '—';
    $('k_semos_a').href = linkTickets({estado: 'aberta'});
    const al = $('tp_alerta');
    if (s.alerta) { $('tp_alerta_t').textContent = s.alerta.titulo; $('tp_alerta_p').textContent = s.alerta.texto; al.hidden = false; } else al.hidden = true;
    $('tp_ciclo').innerHTML = ESTADOS.map(([k, rot, cor]) =>
      '<a href="' + esc(linkTickets({estado: k})) + '" title="Abrir na tela de Tickets"><div class="tp-n" style="color:' + esc(cor) + '">' +
      fmt((s.estados || {})[k]) + '</div><div class="tp-r">' + esc(rot) + '</div></a>').join('');
    const qual = s.qualidade || [];
    $('tp_qual').innerHTML = qual.length ? qual.map((q) => '<li><span class="tp-ic" aria-hidden="true">!</span><b>' + esc(q.destaque) + '</b>' + esc(q.texto) +
      (q.filtro ? '<a href="' + esc(linkTickets(q.filtro)) + '">ver na tela de Tickets</a>' : '') + '</li>').join('')
      : '<li>Nada a apontar.</li>';
    const titulo = s.rotulo_qtd ? s.rotulo_qtd.charAt(0).toUpperCase() + s.rotulo_qtd.slice(1) : 'Equipamento parado';
    $('cli_t').textContent = titulo + ' por cliente';
    $('top_q').textContent = titulo;
    const top = s.top || [], maxTop = Math.max(1, ...top.map((t) => t[2]));
    $('tp_top').innerHTML = top.length ? top.map((t, i) => '<tr><td>' + (i + 1) + '</td><td><a href="' + esc(linkTickets({usina: t[0]})) + '">' + esc(t[0]) +
      '</a></td><td>' + esc(t[1]) + '</td><td><div class="tp-barra"><span class="tp-b' + (t[1] === J.sem_cliente ? ' tp-cinza' : '') +
      '" style="width:' + Math.max(3, 150 * t[2] / maxTop) + 'px"></span>' + fmt(t[2]) + '</div></td><td class="tp-num">' + fmt(t[3]) + '</td></tr>').join('')
      : '<tr><td colspan="5">Nenhuma ocorrência aberta.</td></tr>';
    fluxo(s); idade(s); clientes(s);
  }

  // a troca de aba é só redesenho — os dois conjuntos já vieram; a URL guarda a escolha (F5 volta nela)
  document.querySelectorAll('.os-subnav a[data-aba]').forEach((a) => {
    a.addEventListener('click', (ev) => {
      if (!DADOS[a.dataset.aba]) return;                 // sem dado: deixa o link recarregar
      ev.preventDefault();
      aba = a.dataset.aba;
      document.querySelectorAll('.os-subnav a[data-aba]').forEach((x) => x.classList.toggle('on', x === a));
      $('tp_voltar').href = '/os/tickets?aba=' + encodeURIComponent(aba);
      try { history.replaceState(null, '', '/os/tickets/painel?aba=' + encodeURIComponent(aba)); } catch (e) { /* sem história, segue */ }
      pintar();
    });
  });
  pintar();
})();
