// os_creator/os_web/static/cos.js — a tela COS do app (steps/varias_os.py, VariasOSsDialog) no navegador.
//
// A REGRA NÃO MORA AQUI. Título, observação-pipe, "Registrada no Fracttal como", permissivo e "Fora de serviço" vêm do
// servidor (/os/api/cos/preview, que monta tudo com o cos_spec — o mesmo módulo do app); a cascata do ativo e a poda dos
// marcados também (/os/api/cos/ativos, o `_on_usi`); e a criação — validações, ordem delas e argumentos do Fracttal — é
// do Python (cos_web.criacao). O que fica no navegador é o que no app é sinal entre widgets: tipo ↔ categoria, a ação
// padrão da categoria, a sugestão da falha, conclusão = evento + 10 min, o botão habilitado.
//
// Cada função leva no comentário o método do app que ela espelha, e roda na MESMA ordem dele: a ordem decide os efeitos
// (a categoria que muda reaplica a ação padrão e a sugestão da falha; o tipo que muda reabre ou fecha o "já realizada").
// `setValor` é o blockSignals do Qt: mexer num combo por código não dispara o handler da tela.
(function () {
  'use strict';
  const root = document.getElementById('cos');
  if (!root) return;
  const D = JSON.parse(document.getElementById('cos_dados').textContent);
  const T = D.textos;
  const CATS = D.cats;                                   // índice do segmentado → 'A' | 'B' | 'C'
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const enc = encodeURIComponent;
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + r.status);

  // ── elementos ──
  const edClone = $('ed_clone'), bClone = $('b_clone'), msgClone = $('msg_clone');
  const swTerc = $('sw_terc'), wCliSel = $('w_cli_sel'), wUsiSel = $('w_usi_sel'), cbCli = $('cb_cli'), cbUsi = $('cb_usi');
  const edCli = $('ed_cli'), edUsi = $('ed_usi'), ckMulti = $('ck_multi'), lbMulti = $('lb_multi');
  const linTipo = $('lin_tipo'), cbTipo = $('cb_tipo'), busca = $('busca'), barAtivos = $('bar_ativos');
  const wTbl = $('w_tbl'), tbody = $('tbody'), selLbl = $('sel_lbl'), genNote = $('gen_note');
  const infoAnsi = $('info_ansi'), chipsEl = $('chips'), cbOnde = $('cb_onde'), cbFalhaB = $('cb_falha_b'), cbCausaC = $('cb_causa_c');
  const lblPerm = $('lbl_perm'), cbResp = $('cb_resp'), bResp = $('b_resp');
  const ckFalha = $('ck_falha'), falhaBox = $('falha_box'), cbFtipo = $('cb_ftipo'), cbFcausa = $('cb_fcausa'), cbFdetec = $('cb_fdetec');
  const cbFsev = $('cb_fsev'), cbFdano = $('cb_fdano'), lblOos = $('lbl_oos'), prevMeta = $('prev_meta');
  const edObs = $('ed_obs'), prevTit = $('prev_tit'), prevObs = $('prev_obs');
  const campoEv = $('campo_ev'), dtEv = $('dt_ev'), bAgora = $('b_agora'), lblOosEv = $('lbl_oos_ev'), campoFim = $('campo_fim'), dtFim = $('dt_fim');
  const datasMulti = $('datas_multi'), listaDatas = $('datas_lista'), ckFin = $('ck_fin'), finPanel = $('fin_panel'), rbVerif = $('rb_verif');
  const resultado = $('resultado'), bLimpar = $('b_limpar'), btnCriar = $('btn_criar'), hintEl = $('hint');

  // ── estado (os atributos do VariasOSsDialog) ──
  const checked = new Set();                             // _checked
  let terceiros = false;                                 // _terceiros
  let ovr = {tipo: null, c1: null, c2: null, crit: null};   // _ovr: null = automático pela categoria
  let ativos = [];                                       // candidatos da(s) usina(s) alvo, na ordem do servidor (usina, rótulo)
  let classif = null, SUG = null, pessoas = [];          // as três listas do __init__
  let carregando = 0, criando = false, clonando = false;
  let seqAtivos = 0, seqUsinas = 0, seqPrev = 0, tPrev = null, menuAberto = null;
  const linhas = [];                                     // _date_rows: {el, ev, fim, seta, oos}
  let oosCurto = D.preview.oos.curto;                    // "Fora de Serviço: Sim/Não" que as linhas novas recebem
  const usinasTodas = [...cbUsi.options].slice(1).map((o) => o.value);   // a lista LIVRE (sem cliente) já veio na página

  // ── o blockSignals do Qt ──
  let bloqueio = 0;
  function setValor(sel, v) {
    sel.value = v;
    bloqueio++;                                          // o os_busca escuta o change para trocar o texto da busca
    try { sel.dispatchEvent(new Event('change', {bubbles: true})); } finally { bloqueio--; }
  }
  const temOpcao = (sel, v) => [...sel.options].some((o) => o.value === v);

  // ── rede: o que a pessoa disparou leva o círculo de carga; o que a tela busca sozinha, não ──
  // A cascata e a prévia vão por POST com JSON: no modo várias usinas a maior carteira tem 12 mil ativos, e os ids
  // marcados na URL passariam do que o túnel aceita.
  const postJson = (corpo) => ({method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)});
  async function getJson(url, texto, opcoes) {
    const r = await OsCarga.buscar(url, opcoes || {credentials: 'same-origin'}, texto || 'Carregando…');
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(apiErro(j, r));
    return j;
  }
  async function getJsonFundo(url, opcoes) {
    const r = await fetch(url, opcoes || {credentials: 'same-origin'});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(apiErro(j, r));
    return j;
  }

  let hintDaPrevia = false;                              // o aviso na linha de dica é o de uma prévia que falhou?
  function hint(txt, erro) { hintEl.textContent = txt || ''; hintEl.classList.toggle('erro', !!erro); hintDaPrevia = false; }
  function mostrar(caixa, msg, ruim) {                   // o QMessageBox do app: fica até a pessoa fechar
    caixa.querySelector('.cos-res-txt').textContent = msg || '';
    caixa.classList.toggle('ruim', !!ruim);
    caixa.hidden = false;
  }
  [resultado, msgClone].forEach((c) => c.querySelector('.cos-res-x').addEventListener('click', () => { c.hidden = true; }));

  // ── os segmentados (Segmentado: o clique só avisa quando o índice MUDA; `set` é o set_index(emit=False)) ──
  function segmentado(id, aoMudar) {
    const bts = [...$(id).querySelectorAll('.os-seg-btn')];
    let idx = 0;
    const pintar = () => bts.forEach((b, k) => { b.classList.toggle('on', k === idx); b.setAttribute('aria-pressed', k === idx ? 'true' : 'false'); });
    bts.forEach((b, k) => b.addEventListener('click', () => { if (k !== idx) { idx = k; pintar(); aoMudar(k); } }));
    pintar();
    return {get: () => idx, set: (k) => { idx = k; pintar(); }};
  }
  const segTipo = segmentado('seg_tipo', () => onTipo());
  const segCat = segmentado('seg_cat', () => onCat());
  const segAcao = segmentado('seg_acao', () => onAcao());
  const segModo = segmentado('seg_modo', (i) => onModo(i));
  const cat = () => CATS[segCat.get()];
  const modo = () => segModo.get();

  // ═══ tipo / categoria / ação ═══
  // O tipo de OS e a categoria são A MESMA decisão vista de dois ângulos: "Inspeção e Normalização" existe para a C
  // (falha de comunicação não tem religamento, o técnico vai inspecionar) e "Religamento da UFV" para A e B. Os
  // `aplicar*` aplicam os efeitos SEM tocar no outro controle — é o que deixa a sincronia valer nos dois sentidos.
  function aplicarTipo(insp) {                           // _aplicar_tipo
    setRealizada(!insp);                                 // Inspeção nasce ABERTA para o técnico; Religamento, concluída
    setFalha(true);                                      // "o ativo falhou" SEMPRE marcado (editável) — Inspeção também
  }
  function aplicarCat(i) {                               // _aplicar_cat
    ['page_a', 'page_b', 'page_c'].forEach((p, k) => { $(p).hidden = k !== i; });
    infoAnsi.hidden = i !== 0;                           // a tabela ANSI só faz sentido na categoria A
    segAcao.set(i === 0 ? 0 : 1);                        // ação padrão da categoria (A = Remoto · B/C = Local); dá para trocar
    if (ckFalha.checked) sugerirFalha();                 // re-sugere a falha para a nova categoria
  }
  function onTipo() {                                    // _on_tipo
    const insp = segTipo.get() === 1;
    const alvo = insp ? 2 : (segCat.get() === 2 ? 0 : segCat.get());
    if (segCat.get() !== alvo) { segCat.set(alvo); aplicarCat(alvo); }
    aplicarTipo(insp);
    preview();
  }
  function onCat() {                                     // _on_cat — escolher "C · Comunicação" com o tipo no padrão
    aplicarCat(segCat.get());                            // abria RELIGAMENTO de uma ocorrência sem religamento (31/08)
    const alvo = D.tipo_da_cat[cat()];
    if (segTipo.get() !== alvo) { segTipo.set(alvo); aplicarTipo(alvo === 1); }
    preview();
  }
  function onAcao() { preview(); }                       // _on_acao

  // setChecked só avisa (toggled) quando o estado MUDA — os dois efeitos abaixo dependem disso
  function setRealizada(v) { if (ckFin.checked !== v) { ckFin.checked = v; syncFin(); } }
  function setFalha(v) { if (ckFalha.checked !== v) { ckFalha.checked = v; onFalha(); } }
  function onFalha() {                                   // _on_falha
    falhaBox.hidden = !ckFalha.checked;
    if (ckFalha.checked) sugerirFalha();
  }
  function sugerirFalha() {                              // _sugerir_falha: Inspeção tem Tipo/Causa próprios; senão, a categoria
    if (!SUG) return;                                    // listas ainda não chegaram: o _sel_desc do app também não acha nada
    const s = SUG[segTipo.get() === 1 ? 'insp' : cat()];
    if (!s) return;
    // o `_sel_desc` só troca o combo quando ACHA a opção: o que não veio (a B não sugere causa) fica como está
    if (s.id_type != null) setValor(cbFtipo, String(s.id_type));
    if (s.id_cause != null) setValor(cbFcausa, String(s.id_cause));
    if (s.id_detection != null) setValor(cbFdetec, String(s.id_detection));   // detecção é SEMPRE o monitoramento
  }

  // ── proteções: 'Sem trip' e os códigos não coexistem (_on_prot) ──
  const chips = () => [...chipsEl.querySelectorAll('.cos-chip')];
  const codigos = () => chips().filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.dataset.cod);
  chipsEl.addEventListener('click', (ev) => {
    const ch = ev.target.closest('.cos-chip');
    if (!ch) return;
    const on = ch.getAttribute('aria-pressed') !== 'true';
    ch.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) {
      const sem = ch.dataset.cod === D.sem_trip;
      chips().forEach((c) => { if (c !== ch && (c.dataset.cod === D.sem_trip) !== sem) c.setAttribute('aria-pressed', 'false'); });
    }
    preview();
  });
  [cbOnde, cbFalhaB, cbCausaC].forEach((s) => s.addEventListener('change', () => { if (!bloqueio) preview(); }));

  // ═══ usina de terceiros (ativo genérico) ═══
  swTerc.addEventListener('change', () => togTerceiros(swTerc.checked));
  function togTerceiros(on) {                            // _tog_terceiros
    terceiros = !!on;
    swTerc.checked = terceiros;
    if (terceiros) {                                     // Cliente/Usina viram texto livre, vazios; nada marcado
      wCliSel.hidden = true; edCli.hidden = false; edCli.value = '';
      wUsiSel.hidden = true; edUsi.hidden = false; edUsi.value = '';
      checked.clear();
    } else {                                             // _fill_clientes: os dropdowns voltam, no "— Selecione —"
      edCli.hidden = true; wCliSel.hidden = false; edUsi.hidden = true; wUsiSel.hidden = false;
      setValor(cbCli, '');
      preencherUsinas(usinasTodas, null);
      ativos = []; preencherTipos([]);
    }
    [linTipo, barAtivos, wTbl, selLbl, lbMulti].forEach((w) => { w.hidden = terceiros; });
    syncMultiUsi();                                      // em terceiros o ativo é o genérico: não há o que listar
    genNote.hidden = !terceiros;
    if (!terceiros) refreshAtivos();
    preview();
  }
  [edCli, edUsi].forEach((e) => e.addEventListener('input', () => preview()));   // textEdited → _preview

  // ═══ cascata do ativo ═══
  function cliSel() { return terceiros ? (edCli.value.trim() || null) : (cbCli.value || null); }   // _cli
  function usiSel() { return terceiros ? (edUsi.value.trim() || null) : (cbUsi.value || null); }   // _usi
  // VÁRIAS USINAS DO MESMO CLIENTE (Levi, 02/09): um desligamento na distribuidora derruba várias plantas do mesmo
  // cliente de uma vez. Ligado, quem manda é o CLIENTE; cada OS continua nascendo com a usina do seu próprio ativo.
  const multiOn = () => ckMulti.checked && !!cliSel() && modo() === 0 && !terceiros;   // _multi_on
  function syncMultiUsi() {                              // _sync_multi_usi — devolve true quando DESLIGOU a caixa (quem
    const pode = !!cliSel() && modo() === 0 && !terceiros;   // chamou roda o onUsi, que é o que o toggled faz no app)
    ckMulti.disabled = !pode;
    lbMulti.classList.toggle('off', !pode);
    // marcador cinza sem motivo faz a pessoa achar que a tela quebrou: o título diz por quê
    lbMulti.title = pode ? T.multi_ok : (terceiros ? T.multi_terceiros : (modo() !== 0 ? T.multi_modo : T.multi_cliente));
    if (!pode && ckMulti.checked) { ckMulti.checked = false; return true; }
    return false;
  }
  ckMulti.addEventListener('change', () => { onUsi(); });   // _on_multi_usi: a poda é do _on_usi — UMA regra só
  cbCli.addEventListener('change', () => { if (!bloqueio) onCli(); });
  cbUsi.addEventListener('change', () => { if (!bloqueio) onUsi(); });
  cbTipo.addEventListener('change', () => { if (!bloqueio) refreshAtivos(); });
  // o filtro redesenha a tabela inteira (12 mil linhas na maior carteira, no modo várias usinas): espera a pessoa
  // parar de digitar um instante — só a exibição espera, os marcados não mudam com o filtro
  let tBusca = null;
  busca.addEventListener('input', () => { clearTimeout(tBusca); tBusca = setTimeout(refreshAtivos, 150); });

  function preencherUsinas(lista, cur) {                 // o miolo do _fill_usinas: preserva a usina se ainda vale
    cbUsi.innerHTML = '<option value="">' + esc(T.sel_usina) + '</option>' + lista.map((u) => '<option value="' + esc(u) + '">' + esc(u) + '</option>').join('');
    setValor(cbUsi, cur && lista.includes(cur) ? cur : '');
  }
  function preencherTipos(tipos) {                       // "Todos os tipos" + só os equipamentos do COS
    cbTipo.innerHTML = '<option value="">' + esc(T.todos_tipos) + '</option>' + tipos.map((t) => '<option value="' + esc(t) + '">' + esc(t) + '</option>').join('');
    cbTipo.disabled = !tipos.length;
  }
  async function fillUsinas() {                          // _fill_usinas: pela carteira do cliente, ou TODAS
    const cli = cliSel(), cur = usiSel();
    if (!cli) { preencherUsinas(usinasTodas, cur); return; }
    const seq = ++seqUsinas;
    carregando++; upd();
    try {
      const j = await getJson('/os/api/cos/usinas?cliente=' + enc(cli), 'Carregando as usinas…');
      if (seq === seqUsinas) preencherUsinas(j.usinas || [], cur);
    } catch (e) {
      if (seq === seqUsinas) hint('usinas: ' + e.message, true);
    } finally { carregando--; upd(); }
  }
  async function onCli() {                               // _on_cli
    if (terceiros) return;
    await fillUsinas();
    syncMultiUsi();
    await onUsi();
  }
  // _on_usi — no app é síncrono; aqui a lista vem pela rede. Enquanto ela não chega a tabela e o "Criar OSs" ficam
  // travados: a poda dos marcados tem de acontecer ANTES de qualquer criação, como lá.
  async function onUsi() {
    if (terceiros) return;
    const seq = ++seqAtivos;
    const usi = usiSel(), cli = cliSel(), multi = ckMulti.checked && !!cli && modo() === 0;
    if (!usi && !multi) {                                // nada escolhido: tabela vazia e nada marcado, como no app
      aplicarAlvo({cliente: '', tipos: [], ativos: [], marcados: []});
      return;
    }
    carregando++; upd(); wTbl.classList.add('carregando');
    try {
      const j = await getJson('/os/api/cos/ativos', 'Carregando os ativos…',
        postJson({usina: usi || '', cliente: cli || '', multi: multi, marcados: [...checked]}));
      if (seq === seqAtivos) aplicarAlvo(j);
    } catch (e) {
      if (seq === seqAtivos) hint('ativos: ' + e.message, true);
    } finally { carregando--; wTbl.classList.remove('carregando'); upd(); }
  }
  function aplicarAlvo(j) {
    // a usina nomeada preenche o Cliente pelo campo cliente de um ativo dela — acerta 'Ultragaz' apesar do 'Utragaz'
    if (j.cliente && cliSel() !== j.cliente && temOpcao(cbCli, j.cliente)) {
      setValor(cbCli, j.cliente);
      if (j.usinas) preencherUsinas(j.usinas, usiSel());   // re-filtra a usina para a carteira (mantém a seleção)
      syncMultiUsi();                                    // [web] o app não reavalia a caixa aqui e ela ficava apagada
    }
    // O marcado é sempre um subconjunto do que a tabela pode mostrar: ativo que sumiu da tela e continua marcado
    // viraria uma OS que ninguém revisou. A poda veio pronta do servidor (a regra do _on_usi).
    checked.clear();
    (j.marcados || []).forEach((id) => checked.add(id));
    ativos = j.ativos || [];
    preencherTipos(j.tipos || []);
    refreshAtivos();
  }
  function cands() {                                     // _cands: tipo + busca no rótulo; marcados PRIMEIRO (o do clone no topo)
    const tipo = cbTipo.value, txt = (busca.value || '').trim().toLowerCase();
    return ativos.map((a, i) => [a, i])
      .filter(([a]) => (!tipo || a.tipo === tipo) && (!txt || String(a.label || '').toLowerCase().includes(txt)))
      .sort((x, y) => ((checked.has(x[0].id) ? 0 : 1) - (checked.has(y[0].id) ? 0 : 1)) || (x[1] - y[1]))
      .map(([a]) => a);
  }
  function refreshAtivos() {                             // _refresh_ativos
    const multi = multiOn();
    tbody.innerHTML = cands().map((a) => {
      let rot = a.label || a.code || '?';
      // com várias usinas na mesma lista, 'Inversor 1.1' se repete: sem a usina no rótulo a escolha vira adivinhação
      if (multi) rot += '   ·   ' + (a.usina_curta || '?');
      const on = checked.has(a.id);
      return '<tr data-id="' + esc(a.id) + '"' + (on ? ' class="on"' : '') + '><td><label class="cos-chk" title="' + esc(a.label || '')
        + '"><input type="checkbox"' + (on ? ' checked' : '') + '><span>' + esc(rot) + '</span></label></td></tr>';
    }).join('');
    preview();
  }
  tbody.addEventListener('change', (ev) => {
    const inp = ev.target;
    if (!inp || inp.type !== 'checkbox') return;
    const tr = inp.closest('tr'), id = Number(tr.dataset.id);
    if (carregando) { inp.checked = checked.has(id); return; }   // a lista está mudando: o marcado espera a poda
    onCheck(tr, id, inp.checked);
  });
  function onCheck(tr, id, chk) {                        // _on_check_multi
    if (chk && modo() === 1) {                           // mesmo ativo → só 1 marcado por vez
      checked.clear();
      tbody.querySelectorAll('tr[data-id]').forEach((o) => {
        if (o !== tr) { o.classList.remove('on'); const c = o.querySelector('input'); if (c) c.checked = false; }
      });
    }
    if (chk) checked.add(id); else checked.delete(id);
    tr.classList.toggle('on', chk);
    preview();
  }
  function marcarTodos(marcar) {                         // _marcar_todos: SÓ as linhas que a tabela mostra (o filtro manda)
    if (carregando) return;
    // "Mesmo ativo": o app deixa marcar todos e cria só para o 1º (27/09) — aqui o botão nem age nesse modo
    if (marcar && modo() === 1) return;
    tbody.querySelectorAll('tr[data-id]').forEach((tr) => {
      const id = Number(tr.dataset.id), c = tr.querySelector('input');
      if (c) c.checked = marcar;
      tr.classList.toggle('on', marcar);
      if (marcar) checked.add(id); else checked.delete(id);
    });
    preview();
  }
  $('b_all').addEventListener('click', () => marcarTodos(true));
  $('b_none').addEventListener('click', () => marcarTodos(false));

  // ═══ datas ═══
  // O relógio é o de Brasília (UTC−3, fixo), o mesmo com que o servidor lê o datetime-local: "Agora" num PC com outro
  // fuso cairia no futuro para o servidor. O evento é quando a coisa ACONTECEU (travar_no_passado, Levi 07/08): teto =
  // agora, renovado a cada minuto — fixar só na abertura travaria a tela deixada aberta o dia todo.
  function agora() { return new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 16); }
  function somaMin(v, min) {
    const t = Date.parse(String(v || '').slice(0, 16) + ':00Z');
    return isNaN(t) ? '' : new Date(t + min * 60e3).toISOString().slice(0, 16);
  }
  function travar(inp) { inp.max = agora(); }
  const menosDez = () => somaMin(agora(), -10);          // o "Agora" do COS é 10 min atrás (currentDateTime().addSecs(-600))
  dtEv.addEventListener('input', () => { if (dtEv.value) dtFim.value = somaMin(dtEv.value, 10); });   // a conclusão acompanha (+10 min)
  bAgora.addEventListener('click', () => { dtEv.value = menosDez(); dtFim.value = somaMin(dtEv.value, 10); });

  function addData() {                                   // _add_data: uma linha = uma OS (evento → conclusão)
    const el = document.createElement('div');
    el.className = 'cos-data';
    el.innerHTML = '<input type="datetime-local" class="ev" aria-label="Data/hora do evento" title="' + esc(T.futuro) + '">'
      + '<button type="button" class="os-btn secondary mini agora">Agora</button><span class="seta">→</span>'
      + '<input type="datetime-local" class="fim" aria-label="Data/hora da conclusão">'
      + '<button type="button" class="os-btn secondary mini del">Remover</button><span class="cos-oos-curto oos"></span>';
    const l = {el: el, ev: el.querySelector('.ev'), fim: el.querySelector('.fim'), seta: el.querySelector('.seta'), oos: el.querySelector('.oos')};
    l.ev.value = menosDez(); l.fim.value = agora(); travar(l.ev);
    l.ev.addEventListener('input', () => { if (l.ev.value) l.fim.value = somaMin(l.ev.value, 10); });
    el.querySelector('.agora').addEventListener('click', () => { l.ev.value = menosDez(); l.fim.value = somaMin(l.ev.value, 10); });
    el.querySelector('.del').addEventListener('click', () => delData(l));
    const fin = ckFin.checked;
    l.seta.hidden = !fin; l.fim.hidden = !fin;
    l.oos.textContent = oosCurto;                        // "Fora de Serviço" por OS, à direita do Remover
    listaDatas.appendChild(el);
    linhas.push(l);
    upd();
  }
  function delData(l) {                                  // _del_data
    const i = linhas.indexOf(l);
    if (i >= 0) linhas.splice(i, 1);
    l.el.remove();
    upd();
  }
  $('b_add_data').addEventListener('click', () => addData());
  setInterval(() => { travar(dtEv); linhas.forEach((l) => travar(l.ev)); }, 60000);

  // "Esta tarefa já foi realizada?" (FinalizarPanel) e o que ela mostra/esconde
  ckFin.addEventListener('change', () => syncFin());
  ckFalha.addEventListener('change', () => onFalha());
  function syncFin() {                                   // _sync_fin (+ o painel das respostas, que abre com a caixa)
    const on = ckFin.checked;
    finPanel.hidden = !on;
    campoFim.hidden = !(on && modo() === 0);
    linhas.forEach((l) => { l.seta.hidden = !on; l.fim.hidden = !on; });
    preview();
  }

  async function onModo(i) {                             // _on_modo
    const mesmo = i === 1;
    $('b_all').disabled = mesmo;                         // um ativo só nesse modo: "Selecionar todos" não tem o que fazer
    $('b_all').title = mesmo ? 'No modo Mesmo ativo · várias datas vale um ativo só' : '';
    campoEv.hidden = mesmo;
    campoFim.hidden = mesmo || !ckFin.checked;
    datasMulti.hidden = !mesmo;
    if (mesmo && !linhas.length) addData();
    if (syncMultiUsi()) await onUsi();                   // antes da poda abaixo: desligar o modo já reduz à usina atual
    if (mesmo && checked.size > 1) {                     // mesmo ativo → fica só 1 marcado: o primeiro da tabela
      const um = cands().find((a) => checked.has(a.id));
      const fica = um ? um.id : checked.values().next().value;
      checked.clear(); checked.add(fica);
      refreshAtivos();
    }
    preview();
  }

  // ═══ a prévia (_preview): pede ao servidor e pinta ═══
  function estado() {                                    // a tela num instante — as chaves que o cos_web.estado lê
    const iResp = cbResp.value;
    const p = iResp === '' ? null : (pessoas[Number(iResp)] || null);
    return {
      tipo: segTipo.get(), cat: cat(), remoto: segAcao.get() === 0, modo: modo(),
      codigos: codigos(), onde: cbOnde.value, falha_b: cbFalhaB.value, causa_c: cbCausaC.value, obs: edObs.value,
      ids: terceiros ? [] : [...checked], terceiros: terceiros,
      cliente: terceiros ? edCli.value : cbCli.value, usina: terceiros ? edUsi.value : cbUsi.value,
      ovr: {tipo: ovr.tipo, c1: ovr.c1, c2: ovr.c2, crit: ovr.crit},
      realizada: ckFin.checked, em_verificacao: rbVerif.checked,
      responsavel: p || {},
      falha: {marcado: ckFalha.checked, id_type: cbFtipo.value || null, id_cause: cbFcausa.value || null,
              id_detection: cbFdetec.value || null, id_severity: cbFsev.value || null, id_damage: cbFdano.value || null},
      evento: dtEv.value, conclusao: dtFim.value,
      datas: linhas.map((l) => ({evento: l.ev.value, conclusao: l.fim.value})),
    };
  }
  function preview() {
    upd();
    clearTimeout(tPrev);
    tPrev = setTimeout(pedirPreview, 120);
  }
  async function pedirPreview() {
    const seq = ++seqPrev;
    try {
      const j = await getJsonFundo('/os/api/cos/preview', postJson(estado()));   // o MESMO estado que a criação manda
      if (seq !== seqPrev) return;
      pintarPreview(j);
      if (hintDaPrevia) hint('');
    } catch (e) {
      // prévia velha na tela mentiria sobre o que vai ser criado: some, e o motivo aparece
      if (seq === seqPrev) { prevTit.textContent = '—'; prevObs.textContent = '—'; hint('prévia: ' + e.message, true); hintDaPrevia = true; }
    }
  }
  function pintarPreview(p) {
    prevTit.textContent = p.titulo;
    prevObs.textContent = p.observacao;
    pintarMeta(p.meta);
    lblPerm.textContent = p.permissivo.texto;
    lblPerm.dataset.nivel = p.permissivo.nivel;          // a cor diz o que o "⚠" dizia no app
    lblOos.textContent = p.oos.texto;                    // _upd_oos
    oosCurto = p.oos.curto;
    lblOosEv.textContent = oosCurto;
    linhas.forEach((l) => { l.oos.textContent = oosCurto; });
  }
  function pintarMeta(m) {                               // _meta_html: verde = trocável; vermelho = precisa preencher
    const v = (campo, txt, extra) => '<button type="button" class="cos-meta-v' + (extra ? ' ' + extra : '') + '" data-campo="' + campo + '">' + esc(txt) + '</button>';
    const sep = '<span class="cos-meta-sep">·</span>';
    prevMeta.innerHTML = 'Tipo de tarefa ' + v('tipo', m.tarefa) + sep + 'Classificação ' + v('c1', m.c1, m.c1_preencher ? 'preencher' : '')
      + ' / ' + v('c2', m.c2) + sep + 'Criticidade ' + v('crit', m.crit);
  }
  edObs.addEventListener('input', () => preview());

  // ── "Registrada no Fracttal como": clicar num valor verde abre as opções, com "voltar ao automático" (_editar_meta) ──
  prevMeta.addEventListener('click', (ev) => {
    const b = ev.target.closest('.cos-meta-v');
    if (b) { ev.stopPropagation(); abrirMenu(b.dataset.campo, b); }
  });
  function fecharMenu() { if (menuAberto) { menuAberto.remove(); menuAberto = null; } }
  function abrirMenu(campo, alvoEl) {
    let opcoes;
    if (campo === 'crit') opcoes = D.criticidades.map((c) => ({rot: c[0], val: c[1]}));
    else {
      const lst = (classif || {})[{tipo: 'tipos', c1: 'c1', c2: 'c2'}[campo]] || [];
      opcoes = lst.map((x) => String(x.description || '').trim()).filter(Boolean).map((d) => ({rot: d, val: d}));
    }
    if (!opcoes.length) { alert(T.listas_nao_carregaram); return; }
    fecharMenu();
    const m = document.createElement('div');
    m.className = 'cos-menu';
    m.setAttribute('role', 'menu');
    m.innerHTML = (ovr[campo] != null ? '<button type="button" role="menuitem" data-auto="1">' + esc(T.voltar_auto) + '</button><hr>' : '')
      + opcoes.map((o, k) => '<button type="button" role="menuitem" data-k="' + k + '">' + esc(o.rot) + '</button>').join('');
    m.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const b = ev.target.closest('button');
      if (!b) return;
      ovr[campo] = b.dataset.auto ? null : opcoes[Number(b.dataset.k)].val;
      fecharMenu();
      preview();
    });
    document.body.appendChild(m);
    const r = alvoEl.getBoundingClientRect(), largura = document.documentElement.clientWidth;
    m.style.left = (window.scrollX + Math.max(8, Math.min(r.left, largura - m.offsetWidth - 8))) + 'px';
    m.style.top = (window.scrollY + r.bottom + 4) + 'px';
    menuAberto = m;
    const primeiro = m.querySelector('button');
    if (primeiro) primeiro.focus();
  }
  document.addEventListener('click', () => fecharMenu());
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') fecharMenu(); });

  // ═══ o botão (_upd): proteção, responsável e tipo são checados NO CLIQUE, com a frase — nunca travado em silêncio ═══
  function upd() {
    let ok;
    if (terceiros) {                                     // 1 ativo genérico → vale o Cliente + Usina digitados
      ok = !!(cliSel() && usiSel()) && (modo() !== 1 || linhas.length > 0);
    } else {
      const n = checked.size;
      if (modo() === 1) {
        const nd = linhas.length;
        selLbl.textContent = n + ' ativo · ' + nd + ' data(s) → ' + (n ? nd : 0) + ' OS';
        ok = !!(n && nd);
      } else {
        // no modo várias usinas o número de OS não diz o tamanho do estrago: 12 ativos podem ser 12 usinas
        const nu = multiOn() ? new Set(ativos.filter((a) => checked.has(a.id)).map((a) => a.usina)).size : 0;
        selLbl.textContent = n + ' ativo(s) marcado(s)' + (nu > 1 ? ' · ' + nu + ' usina(s)' : '');
        ok = n > 0;
      }
    }
    btnCriar.disabled = !ok || criando || carregando > 0;
  }
  cbResp.addEventListener('change', () => { if (!bloqueio) upd(); });

  // ═══ criar (_criar → _ok / _err) ═══
  btnCriar.addEventListener('click', () => criar());
  async function criar() {
    if (btnCriar.disabled) return;
    const n = modo() === 1 ? linhas.length : (terceiros ? 1 : checked.size);
    const corpo = estado();
    criando = true; upd();
    resultado.hidden = true;
    hint(T.criando.replace('{n}', n));
    try {
      const r = await OsCarga.buscar('/os/api/cos/criar', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)}, 'Criando as OS no Fracttal…');
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {                                       // 400 = a frase do app (a validação); o resto, "Erro ao criar OSs"
        hint('');
        mostrar(resultado, (r.status === 400 ? '' : T.erro_criar) + apiErro(j, r), true);
        return;
      }
      if (j.ok > 0) {                                    // OSs criadas → tela limpa para a próxima; a mensagem fica
        await reset();
        mostrar(resultado, j.mensagem, false);
      } else {
        hint('');
        mostrar(resultado, j.mensagem || T.nenhuma, true);
      }
    } catch (e) {
      hint('');
      mostrar(resultado, T.erro_criar + e.message, true);
    } finally { criando = false; upd(); }
  }

  // ═══ Recomeçar (_limpar_clicado) e o reset (_reset: UM caminho só para limpar TUDO) ═══
  bLimpar.addEventListener('click', () => limparClicado());
  async function limparClicado() {
    // confirma só se já houver algo preenchido — apertar por engano numa tela cheia custa o trabalho todo
    const sujo = checked.size > 0 || !!edObs.value.trim() || (!terceiros && !!cbCli.value);
    if (sujo && !confirm(T.confirma_limpar)) return;
    await reset();
    hint(T.tela_limpa);
  }
  async function reset() {
    fecharMenu();
    resultado.hidden = true; msgClone.hidden = true;     // as mensagens da OS anterior (quem cria mostra a nova depois)
    while (linhas.length) delData(linhas[0]);           // datas do modo "várias datas"
    checked.clear();
    ovr = {tipo: null, c1: null, c2: null, crit: null};  // volta ao automático
    if (terceiros) togTerceiros(false);
    clearTimeout(tBusca); busca.value = '';
    // Zerar o cliente NÃO basta: o _fill_usinas PRESERVA a usina e o _on_usi re-seleciona o cliente a partir dela — o
    // campo voltava sozinho ao valor anterior. Por isso a usina é zerada depois, e o onUsi limpa tabela, tipos e seleção.
    setValor(cbCli, '');
    preencherUsinas(usinasTodas, usiSel());
    setValor(cbUsi, '');
    await onUsi();
    dtEv.value = menosDez(); dtFim.value = agora(); travar(dtEv);
    edObs.value = '';
    chips().forEach((c) => c.setAttribute('aria-pressed', 'false'));
    [cbOnde, cbFalhaB, cbCausaC, cbFtipo, cbFcausa, cbFdetec, cbFdano].forEach((s) => { if (s.options.length) setValor(s, s.options[0].value); });
    setValor(cbFsev, D.sev_padrao);                      // severidade volta ao PADRÃO DO COS (Muito alto), não ao item 0
    // o RESPONSÁVEL também zera: responsável errado numa OS de campo manda o técnico errado para a usina (Levi, 30/07)
    if (cbResp.options.length) setValor(cbResp, cbResp.options[0].value);
    edClone.value = '';
    segTipo.set(0); segCat.set(0); segModo.set(0);       // Tipo = Religamento · Categoria = A · Modo = Vários ativos
    await onModo(0);
    setRealizada(true);                                  // remoto resolvido = default
    onTipo(); onCat();                                   // o onTipo remarca o "O ativo falhou?" (é o default do COS)
    segAcao.set(0); onAcao();
    refreshAtivos();
    hint('');
  }

  // ═══ o clonador do COS (_clonar_num → _clone_ok → _aplicar_clone) ═══
  bClone.addEventListener('click', () => clonarNum());
  edClone.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); clonarNum(); } });
  async function clonarNum() {
    if (clonando) return;
    clonando = true;
    bClone.disabled = true; bClone.textContent = T.buscando;
    msgClone.hidden = true;
    try {
      const r = await OsCarga.buscar('/os/api/cos/os-modelo?folio=' + enc(edClone.value.trim()), {credentials: 'same-origin'}, 'Buscando a OS no Fracttal…');
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {                                       // 400/404 = a frase do app; 502 = "Erro ao buscar a OS: …"
        mostrar(msgClone, (r.status >= 500 ? T.erro_clone : '') + apiErro(j, r), true);
        return;
      }
      await aplicarClone(j);
      mostrar(msgClone, j.mensagem, false);
    } catch (e) {
      mostrar(msgClone, T.erro_clone + e.message, true);
    } finally {
      clonando = false;
      bClone.disabled = false; bClone.textContent = T.clonar;
    }
  }
  async function aplicarClone(j) {                       // _aplicar_clone: tipo, categoria, proteções/falha, ação e ativo
    carregando++; upd();
    try {
      if (terceiros) togTerceiros(false);                // o clone sempre volta ao modo normal (ativo real)
      segTipo.set(j.tipo); onTipo();
      const ci = Math.max(0, CATS.indexOf(j.cat));
      segCat.set(ci); onCat();
      const cods = new Set(j.codigos || []);             // as proteções como vieram (o app marca sem a exclusividade)
      chips().forEach((c) => c.setAttribute('aria-pressed', cods.has(c.dataset.cod) ? 'true' : 'false'));
      if (j.cat === 'B' && j.falha_b && temOpcao(cbFalhaB, j.falha_b)) setValor(cbFalhaB, j.falha_b);
      if (j.cat === 'C' && j.causa_c && temOpcao(cbCausaC, j.causa_c)) setValor(cbCausaC, j.causa_c);
      segAcao.set(j.remoto ? 0 : 1); onAcao();
      const a = j.ativo;
      if (a) {                                           // ativo: cliente → usina → tipo de equipamento → marcado
        if (a.carteira && temOpcao(cbCli, a.carteira)) {
          if (cbCli.value !== a.carteira) { setValor(cbCli, a.carteira); await onCli(); }
        } else if (cbCli.value) {
          // [web] carteira fora do combo (o 'Utragaz' do typo): o app deixava o cliente anterior, a usina do clone não
          // aparecia na lista dele e o ativo ficava marcado FORA da tabela. Sem cliente (e sem a usina anterior, que o
          // onUsi usaria para trazer o cliente antigo de volta) a lista é a de todas as usinas, e a usina do clone,
          // escolhida a seguir, preenche o cliente certo — a OS é a mesma, só que agora visível.
          setValor(cbCli, ''); preencherUsinas(usinasTodas, null); syncMultiUsi();
          if (!(a.usina && temOpcao(cbUsi, a.usina))) await onUsi();   // a usina do clone não está em lista nenhuma
        }
        if (a.usina && temOpcao(cbUsi, a.usina) && cbUsi.value !== a.usina) { setValor(cbUsi, a.usina); await onUsi(); }
        if (a.tipo && temOpcao(cbTipo, a.tipo)) setValor(cbTipo, a.tipo);   // já filtra pelo GRUPO do ativo clonado
        checked.clear(); checked.add(a.id);              // DEPOIS do onUsi, que poda a seleção
      }
    } finally { carregando--; }
    refreshAtivos();                                     // marcados primeiro → o ativo do clone fica no topo
  }

  // ═══ as três listas do __init__ (responsáveis, tipos/classificações, falha) ═══
  function setResp(lista) {                              // _set_resp
    pessoas = lista || [];
    hint('');
    cbResp.innerHTML = '<option value="">' + esc(T.sel) + '</option>'
      + pessoas.map((p, i) => '<option value="' + i + '">' + esc(p.name || p.code || '?') + '</option>').join('');
    upd();
  }
  function respErr(m) {                                  // _resp_err
    pessoas = [];
    cbResp.innerHTML = '<option value="">' + esc(T.resp_falha) + '</option>';
    hint(T.resp_hint + m, true);
    upd();
  }
  async function carregarResp() {                        // _carregar_resp (o ↻)
    cbResp.innerHTML = '<option value="">' + esc(T.carregando) + '</option>';
    hint(T.carregando_resp);
    try {
      const j = await getJson('/os/api/cos/listas?so=responsaveis', 'Carregando os responsáveis…');
      if (j.erros && j.erros.responsaveis) throw new Error(j.erros.responsaveis);
      setResp(j.responsaveis);
    } catch (e) { respErr(e.message); }
  }
  bResp.addEventListener('click', () => carregarResp());
  function setFalhaListas(d, sug) {                      // _set_falha_listas
    const fill = (sel, itens) => {
      sel.innerHTML = '<option value="">' + esc(T.sel) + '</option>'
        + (itens || []).map((it) => '<option value="' + esc(it.id) + '">' + esc(it.description || '?') + '</option>').join('');
    };
    fill(cbFtipo, d.tipos); fill(cbFcausa, d.causas); fill(cbFdetec, d.metodos);
    SUG = sug || null;
    if (ckFalha.checked) sugerirFalha();
  }
  async function carregarListas() {
    hint(T.carregando_resp);
    let j;
    try { j = await getJsonFundo('/os/api/cos/listas'); } catch (e) { respErr(e.message); return; }
    const er = j.erros || {};
    if (er.responsaveis) respErr(er.responsaveis); else setResp(j.responsaveis);
    if (!er.falhas) setFalhaListas(j.falhas || {}, j.sugestoes);
    classif = er.classif ? null : (j.classif || {});     // _set_classif / _classif_err
    if (er.classif) hint(T.classif_err, true);
    upd();
  }

  // ═══ arranque: a tela recém-aberta (o __init__ do app e o reiniciar de quem volta a ela) ═══
  syncMultiUsi();
  pintarPreview(D.preview);
  travar(dtEv);
  upd();
  carregarListas();
})();
