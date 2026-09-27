// os_creator/os_web/static/insp.js — a Inspeção de chamados do app (steps/insp_chamado.py) na web.
//
// A REGRA mora no servidor (insp_web.py: marca sugerida, marca pelos irmãos, herança da OS pai, amanhã às 8h). Aqui é
// só a tela: a cascata cliente → usina → tipo → ativo → marca, a prévia das subtarefas, o painel das últimas OS, a OS
// pai e o botão de criar. Com ?pai=<nº> (o "Abrir chamado" do card da OS) a tela nasce com o ativo, a data do
// incidente e o responsável daquela OS; com ?ativo=<id> (atalho da aba Ativos), com o ativo.
(function () {
  'use strict';
  const R = document.getElementById('insp');
  if (!R) return;
  const $ = (id) => document.getElementById(id);
  const cb = {cli: $('cb_cli'), usi: $('cb_usi'), tipo: $('cb_tipo'), ativo: $('cb_ativo'), marca: $('cb_marca'),
              resp: $('cb_resp')};
  const edPai = $('ed_pai'), lbPai = $('lb_pai'), bHist = $('b_hist'), dtInc = $('dt_inc'), dtProg = $('dt_prog');
  const edObs = $('ed_obs'), lbResumo = $('lb_resumo'), lbSubs = $('lb_subs'), hint = $('hint'), bCriar = $('b_criar');
  const res = $('res'), modal = $('modal_hist');
  const SEM_PAI = R.dataset.semPai, SEM_PREVIA = R.dataset.semPrevia;
  const VAZIO = {};                  // a 1ª opção de cada combo é o texto do app ("— Selecione … —"), lido do HTML
  Object.keys(cb).forEach((k) => { VAZIO[k] = cb[k].options[0] ? cb[k].options[0].text : ''; });

  let ativosUsina = [];              // [{id, code, nome, tipo}] da usina escolhida
  let hist = [];                     // as últimas OS do ativo
  let pai = null;                    // a OS pai encontrada ({folio, id_work_order, …})
  let paiDataPainel = '', paiFolioClick = '';
  let aplicando = false;             // cascata por código: os handlers não disparam de novo
  let criando = false, seqPrevia = 0, seqHist = 0;

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const dica = (t) => { hint.textContent = t || ''; };

  async function pedir(url, opts) {
    const r = await fetch(url, Object.assign({headers: {'Accept': 'application/json'}}, opts || {}));
    let j = {};
    try { j = await r.json(); } catch (e) { /* corpo vazio */ }
    if (!r.ok) throw new Error(j.erro || ('HTTP ' + r.status));
    return j;
  }
  const postar = (url, corpo) => pedir(url, {method: 'POST', body: JSON.stringify(corpo),
    headers: {'Accept': 'application/json', 'Content-Type': 'application/json'}});

  // os combos: o valor mora no <select> (o os_busca só desenha a busca por cima dele)
  function encher(sel, vazio, itens) {
    sel.innerHTML = '<option value="">' + esc(vazio) + '</option>' +
      itens.map((it) => '<option value="' + esc(it.v) + '">' + esc(it.t) + '</option>').join('');
    sel.disabled = !itens.length;
  }
  function escolher(sel, v) {        // por código: o `change` é o que redesenha a busca por cima do combo
    sel.value = v == null ? '' : String(v);
    sel.dispatchEvent(new Event('change', {bubbles: true}));
  }
  const ativoAtual = () => ativosUsina.find((a) => String(a.id) === String(cb.ativo.value)) || null;

  // ── a carga ──
  async function carregarClientes() {
    dica('carregando ativos…');
    try {
      const j = await pedir('/os/api/insp/catalogo');
      encher(cb.cli, VAZIO.cli, (j.clientes || []).map((c) => ({v: c, t: c})));
      dica('');
    } catch (e) { dica('não consegui carregar os ativos: ' + e.message); }
  }
  async function carregarPessoas() {
    try {
      const j = await pedir('/os/api/responsaveis');
      encher(cb.resp, VAZIO.resp, (j.pessoas || []).map((p) => ({v: p.id_personnel, t: p.name || ''})));
    } catch (e) { /* sem a lista, o Criar avisa que falta o responsável */ }
  }

  // ── a cascata (cada nível zera os de baixo, como os _fill_* do app) ──
  function semAtivo() {
    encher(cb.marca, VAZIO.marca, []);
    hist = []; bHist.hidden = true;
    previa();
  }
  async function usinas(cliente) {
    encher(cb.usi, VAZIO.usi, []); encher(cb.tipo, VAZIO.tipo, []); encher(cb.ativo, VAZIO.ativo, []);
    ativosUsina = []; semAtivo();
    if (!cliente) return;
    const j = await pedir('/os/api/insp/catalogo?cliente=' + encodeURIComponent(cliente));
    encher(cb.usi, VAZIO.usi, (j.usinas || []).map((u) => ({v: u, t: u})));
  }
  async function tiposEAtivos(usina) {
    encher(cb.tipo, VAZIO.tipo, []); encher(cb.ativo, VAZIO.ativo, []);
    ativosUsina = []; semAtivo();
    if (!usina) return;
    const j = await pedir('/os/api/insp/catalogo?usina=' + encodeURIComponent(usina));
    ativosUsina = j.ativos || [];
    encher(cb.tipo, VAZIO.tipo, (j.tipos || []).map((t) => ({v: t, t: t})));
    ativosDoTipo('');
  }
  function ativosDoTipo(tipo) {
    encher(cb.ativo, VAZIO.ativo, ativosUsina.filter((a) => !tipo || a.tipo === tipo).map((a) => ({v: a.id, t: a.nome})));
    semAtivo();
  }
  async function marcas() {
    const a = ativoAtual();
    semAtivo();
    if (!a) return;
    // o tipo acompanha o ativo: escolhido o ativo sem o tipo, a lista de marcas do app viria vazia
    if (cb.tipo.value !== a.tipo) { aplicando = true; escolher(cb.tipo, a.tipo); aplicando = false; }
    bHist.hidden = false;
    historico(a);
    const j = await pedir('/os/api/insp/marcas?ativo=' + encodeURIComponent(a.id) + '&tipo=' + encodeURIComponent(a.tipo));
    if (String((ativoAtual() || {}).id) !== String(a.id)) return;        // trocou de ativo no meio
    encher(cb.marca, VAZIO.marca, (j.marcas || []).map((m) => ({v: m, t: m})));
    if (j.sugerida) { aplicando = true; escolher(cb.marca, j.sugerida); aplicando = false; }
    dica(j.aviso || '');
    previa();
  }

  // ── a prévia das subtarefas (o card 4) ──
  async function previa() {
    const seq = ++seqPrevia;
    const a = ativoAtual(), tipo = (a && a.tipo) || cb.tipo.value, marca = cb.marca.value;
    if (!tipo || !marca) {
      lbResumo.textContent = SEM_PREVIA;
      lbSubs.innerHTML = '<li class="insp-vazio">—</li>';
      return;
    }
    try {
      const j = await pedir('/os/api/insp/subtarefas?tipo=' + encodeURIComponent(tipo) + '&marca=' + encodeURIComponent(marca));
      if (seq !== seqPrevia) return;                                     // chegou depois de outra
      lbResumo.textContent = j.resumo || '';
      lbSubs.innerHTML = (j.linhas || []).map((l) => {
        const m = [l.obrigatoria ? 'obrigatória' : '', l.anexo ? 'anexo' : ''].filter(Boolean);
        return '<li>' + esc(l.texto) + (m.length ? ' <span class="insp-marca">(' + m.join(', ') + ')</span>' : '') + '</li>';
      }).join('') || '<li class="insp-vazio">—</li>';
    } catch (e) { if (seq === seqPrevia) lbResumo.textContent = 'não consegui ler as subtarefas: ' + e.message; }
  }

  // ── as últimas OS do ativo (a dica do campo OS pai) ──
  async function historico(a) {
    const seq = ++seqHist;
    hist = [];
    bHist.title = 'buscando as últimas OS deste ativo…';
    try {
      const j = await pedir('/os/api/insp/ultimas-os?ativo=' + encodeURIComponent(a.id));
      if (seq !== seqHist) return;
      hist = j.linhas || [];
      bHist.title = hist.length ? 'As últimas ' + hist.length + ' OS deste ativo — clique para escolher a OS pai'
                                : 'Este ativo ainda não tem OS registrada.';
    } catch (e) { if (seq === seqHist) bHist.title = 'não consegui ler o histórico deste ativo: ' + e.message; }
  }
  function abrirHist() {
    const a = ativoAtual();
    if (!a) return;
    $('hist_nome').textContent = a.nome || '—';
    $('hist_dica').hidden = !hist.length;
    $('hist_lista').innerHTML = hist.length ? hist.map((d, i) =>
      '<button type="button" class="insp-hist-l" data-i="' + i + '">' +
        '<span class="insp-hist-n">' + esc(d.folio || '—') + '</span>' +
        '<span class="insp-hist-m"><span class="insp-hist-t" title="' + esc(d.descricao) + '">' + esc(d.descricao || '—') + '</span>' +
        '<span class="insp-hist-s">' + esc([d.tipo_tarefa, d.data_br].filter(Boolean).join(' · ')) + '</span></span>' +
        '<span class="insp-hist-st" style="--c:' + esc(d.cor || '#8a90a2') + '">' + esc(d.status || '—') + '</span>' +
      '</button>').join('') : '<p class="insp-hist-vazio">Este ativo ainda não tem OS registrada.</p>';
    $('hist_rod').textContent = hist.length ? hist.length + ' OS registradas neste ativo' : '';
    modal.hidden = false;
  }

  // ── a OS pai: passa DATA DO INCIDENTE e RESPONSÁVEL (e o ativo, quando a tela ainda não tem um) ──
  async function aplicarAtivo(c) {    // o `aplicar_ativo` do app: desce a cascata até o ativo
    aplicando = true;
    try {
      escolher(cb.cli, c.cliente);
      await usinas(c.cliente); escolher(cb.usi, c.usina);
      await tiposEAtivos(c.usina); escolher(cb.tipo, c.tipo);
      ativosDoTipo(c.tipo); escolher(cb.ativo, c.id);
    } finally { aplicando = false; }
    await marcas();
  }
  async function buscarPai() {
    const folio = edPai.value.trim();
    if (folio !== paiFolioClick) paiDataPainel = '';                     // digitado à mão: sem a data do painel
    if (!folio) { pai = null; lbPai.textContent = SEM_PAI; return; }
    lbPai.textContent = 'procurando a OS ' + folio + '…';
    try {
      const j = await pedir('/os/api/insp/pai?folio=' + encodeURIComponent(folio) +
                            (paiDataPainel ? '&data=' + encodeURIComponent(paiDataPainel) : ''));
      if (edPai.value.trim() !== folio) return;                          // digitou outro número no meio
      pai = j;
      if (j.ativo && !ativoAtual()) await aplicarAtivo(j.ativo);
      if (j.inc) dtInc.value = j.inc;
      if (j.prog) dtProg.value = j.prog;
      if (j.resp_id) escolher(cb.resp, j.resp_id);
      lbPai.textContent = j.texto || '';
      if (j.aviso_ativo) dica(j.aviso_ativo);
    } catch (e) { pai = null; lbPai.textContent = e.message; }
  }

  // ── criar ──
  async function criar() {
    if (criando) return;
    const a = ativoAtual();
    if (!a) { alert('Escolha o ativo.'); return; }
    if (!cb.marca.value) { alert('Escolha a marca do ativo.'); return; }
    if (!cb.resp.value) { alert('Escolha o responsável em campo.'); return; }
    let conf;
    try { conf = await postar('/os/api/insp/confirmacao', {ativo: a.id, marca: cb.marca.value}); }
    catch (e) { alert(e.message); return; }
    if (!confirm(conf.texto)) return;
    criando = true; bCriar.disabled = true; res.hidden = true; dica('criando no Fracttal…');
    try {
      const j = await postar('/os/api/insp/criar', {
        ativo: a.id, marca: cb.marca.value, resp_id: cb.resp.value,
        resp_nome: cb.resp.options[cb.resp.selectedIndex] ? cb.resp.options[cb.resp.selectedIndex].text : '',
        inc: dtInc.value, prog: dtProg.value, pai_id: pai && pai.id_work_order ? pai.id_work_order : null,
        obs: edObs.value.trim()});
      res.className = 'insp-ok' + (j.aviso ? ' aviso' : '');
      res.innerHTML = esc(j.texto) + (j.folio ? ' <a href="/os/os/folio/' + encodeURIComponent(j.folio) +
        '" target="_blank" rel="noopener">abrir a OS ' + esc(j.folio) + '</a>' : '') + (j.aviso ? '<br>' + esc(j.aviso) : '');
      res.hidden = false;
      reiniciar();
    } catch (e) { alert(e.message); }
    finally { criando = false; bCriar.disabled = false; dica(''); }
  }

  // ── voltar à tela limpa (o `reiniciar` do app) ──
  const doisDig = (n) => String(n).padStart(2, '0');
  const local = (d) => d.getFullYear() + '-' + doisDig(d.getMonth() + 1) + '-' + doisDig(d.getDate()) + 'T' +
    doisDig(d.getHours()) + ':' + doisDig(d.getMinutes());
  function reiniciar() {
    edPai.value = ''; edObs.value = ''; pai = null; paiDataPainel = ''; paiFolioClick = '';
    lbPai.textContent = SEM_PAI;
    const agora = new Date(), amanha = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + 1, 8, 0);
    dtInc.value = local(agora);
    dtProg.value = local(amanha);                // o reset do app zerava a programada no MESMO dia; aqui é amanhã 8h
    escolher(cb.cli, ''); escolher(cb.resp, '');
    // a OS de origem sai do endereço também: recarregar a página não pode preencher a inspeção de novo
    try { history.replaceState(null, '', '/os/chamados/inspecao'); } catch (e) { /* sem história, segue */ }
  }

  // ── os eventos ──
  cb.cli.addEventListener('change', () => { if (!aplicando) usinas(cb.cli.value).catch((e) => dica(e.message)); });
  cb.usi.addEventListener('change', () => { if (!aplicando) tiposEAtivos(cb.usi.value).catch((e) => dica(e.message)); });
  cb.tipo.addEventListener('change', () => { if (!aplicando) ativosDoTipo(cb.tipo.value); });
  cb.ativo.addEventListener('change', () => { if (!aplicando) marcas().catch((e) => dica(e.message)); });
  cb.marca.addEventListener('change', () => { if (!aplicando) previa(); });
  edPai.addEventListener('change', () => { buscarPai(); });
  edPai.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); edPai.blur(); } });
  bHist.addEventListener('click', abrirHist);
  bCriar.addEventListener('click', criar);
  $('hist_lista').addEventListener('click', (e) => {
    const b = e.target.closest('.insp-hist-l');
    const d = b ? hist[Number(b.dataset.i)] : null;
    if (!d) return;
    // guarda a data que o PAINEL mostrou: nem toda OS tem event_date no detalhe (a 6647 não tem)
    paiDataPainel = d.event_date || ''; paiFolioClick = String(d.folio || '');
    edPai.value = paiFolioClick;
    modal.hidden = true;
    buscarPai();
  });
  modal.addEventListener('click', (e) => { if (e.target.closest('[data-fechar]')) modal.hidden = true; });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) modal.hidden = true; });

  (async function iniciar() {
    await Promise.all([carregarClientes(), carregarPessoas()]);
    if (R.dataset.ativo) {
      try { await aplicarAtivo(await pedir('/os/api/insp/ativo/' + encodeURIComponent(R.dataset.ativo))); }
      catch (e) { dica(e.message); }
    }
    if (edPai.value.trim()) await buscarPai();
  })();
})();
