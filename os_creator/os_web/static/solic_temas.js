/* os_creator/os_web/static/solic_temas.js — os Temas do app na web (`steps/temas.py::TemasTab`; Levi, 13/10/2026: "nem
   painel do PCM nem histórico nem temas").

   Como no app: a lista (nome, o tipo de equipamento ou "sem equipamento", "N subtarefas · M solicitações", arquivado), a
   busca, o "+ novo tema" (um rascunho no topo, que só vai ao banco no Salvar), o cadastro e o Salvar / Descartar /
   Arquivar. O tipo de equipamento vem do CADASTRO de ativos, do mais comum ao menos, e é o que filtra os ativos na
   Solicitação; as etiquetas mostradas são as EFETIVAS (a regra antiga da PERFORMANCE aparece no tema que nunca foi salvo
   pela tela nova). Sem o GRIDCO_SQL_TOKEN no servidor dá para ver e ajustar, mas não para salvar. A mais que o app:
   trocar de tema com alteração não salva pergunta antes (no app o `_sujo` era marcado e nunca lido). */
(function () {
  'use strict';
  var SP = window.SolicPcm, esc = SP.esc;
  function $(id) { return document.getElementById(id); }
  var D = JSON.parse($('tm_dados').textContent || '{}');
  var temas = D.temas || [], atual = null, sujo = false, relogio = null, etqs = [];
  var lista = $('tm_lista'), busca = $('tm_busca'), form = $('tm_form'), nome = $('tm_nome'), equip = $('tm_equip'),
      tipoOs = $('tm_tipo_os'), motivo = $('tm_motivo'), c1 = $('tm_c1'), chips = $('tm_chips'), etqAdd = $('tm_etq_add'),
      salvar = $('tm_salvar'), desc = $('tm_desc'), arq = $('tm_arq'), hint = $('tm_hint');
  var editor = SP.editorSubs($('tm_subs'), {tipos: D.tipos_sub, vazio: 'Sem subtarefas: a OS vai nascer só com as 3 da base.',
                                            aoMudar: function () { sujo = true; }});

  function opcoesCom(sel, valores, atual_) {
    // a lista fixa do app + o valor que o tema já tem, se ele não estiver nela (o "Limpeza e Conservação" da Vegetação:
    // no app o combo caía no vazio e salvar apagava o tipo — aqui ele aparece e fica)
    var vs = valores.slice();
    if (atual_ && vs.indexOf(atual_) < 0) vs.push(atual_);
    sel.innerHTML = vs.map(function (v) { return '<option value="' + esc(v) + '">' + esc(v) + '</option>'; }).join('');
    sel.value = atual_ || '';
  }
  function encherEquip(atual_) {
    var tipos = (D.tipos || []).map(function (p) { return {v: p[0], r: p[0] + '  (' + p[1] + ')'}; });
    if (atual_ && !tipos.some(function (t) { return t.v === atual_; })) tipos.push({v: atual_, r: atual_});
    equip.innerHTML = '<option value="">— não filtra —</option>'
      + tipos.map(function (t) { return '<option value="' + esc(t.v) + '">' + esc(t.r) + '</option>'; }).join('');
    equip.value = atual_ || '';
  }
  function syncFiltro() {
    var eq = equip.value;
    $('tm_filtro').innerHTML = eq ? 'Ao escolher este tema na Solicitação, a lista de ativos vai mostrar só <b>' + esc(eq) + '</b>.'
                                  : 'Sem tipo de equipamento, este tema não filtra a lista de ativos.';
  }

  // ── a lista ──
  function contador() {
    var ativos = temas.filter(function (t) { return !t.arquivado && t.chave; });
    var sem = ativos.filter(function (t) { return !(t.subtarefas || []).length; }).length;
    $('tm_cont').innerHTML = '<b class="spc-verde">' + ativos.length + '</b> temas' + (sem ? ' · ' + sem + ' sem checklist' : '');
  }
  function pintarLista() {
    var q = (busca.value || '').trim().toLowerCase();
    lista.innerHTML = temas.map(function (t, i) {
      if (q && ((t.nome || '') + ' ' + (t.chave || '')).toLowerCase().indexOf(q) < 0) return '';
      var eq = (t.tipo_equipamento || '').trim(), n = (t.subtarefas || []).length;
      return '<div class="spc-cel' + (t === atual ? ' on' : '') + '" role="option" tabindex="0" aria-selected="' + (t === atual)
        + '" data-i="' + i + '"><span class="spc-cel-usina">' + esc(t.nome || t.chave || 'Tema novo') + '</span>'
        + '<span class="spc-cel-meta"><span class="spc-chip' + (eq ? ' sim' : '') + '">' + esc(eq || 'sem equipamento') + '</span>'
        + '<span class="spc-cel-quem">' + n + ' subtarefa' + (n === 1 ? '' : 's') + ' · ' + (t.solicitacoes || 0) + ' solicitações</span></span>'
        + (t.arquivado ? '<span class="spc-chip">arquivado</span>' : '') + '</div>';
    }).join('') || '<p class="spc-vazio">Nenhum tema com esse texto.</p>';
    contador();
  }
  busca.addEventListener('input', function () { clearTimeout(relogio); relogio = setTimeout(pintarLista, 250); });
  lista.addEventListener('click', function (e) {
    var c = e.target.closest('.spc-cel'); if (c) trocar(temas[Number(c.dataset.i)]);
  });
  lista.addEventListener('keydown', function (e) {
    var c = e.target.closest('.spc-cel'); if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); trocar(temas[Number(c.dataset.i)]); }
  });
  function trocar(t) {
    if (t === atual) return;
    if (sujo && !window.confirm('Este tema tem alterações que não foram salvas. Descartar e abrir o outro?')) return;
    if (atual && !atual.chave && t !== atual) temas.splice(temas.indexOf(atual), 1);    // o rascunho não salvo sai
    selecionar(t);
  }

  // ── o cadastro ──
  function habilitar(on) {
    [nome, equip, tipoOs, motivo, c1, etqAdd, salvar, desc, arq].forEach(function (el) { el.disabled = !on; });
    editor.editavel(on);
    if (on && !D.pode_gravar) {
      salvar.disabled = true; arq.disabled = true;
      hint.textContent = 'Sem o GRIDCO_SQL_TOKEN neste servidor: dá para ver e ajustar, mas não para salvar.';
    }
  }
  function pintarEtq() {
    chips.innerHTML = etqs.map(function (n) {
      return '<button type="button" class="spc-etq" data-n="' + esc(n) + '" title="Clique para tirar">' + esc(n) + '&nbsp;&nbsp;&times;</button>';
    }).join('') || '<span class="spc-dica">Nenhuma etiqueta — a OS nasce sem marcação.</span>';
    var postas = new Set(etqs.map(function (n) { return n.toUpperCase(); }));
    etqAdd.innerHTML = '<option value="">+ adicionar etiqueta</option>' + (D.etiquetas || []).filter(function (n) {
      return !postas.has(n.toUpperCase());
    }).map(function (n) { return '<option value="' + esc(n) + '">' + esc(n) + '</option>'; }).join('');
  }
  chips.addEventListener('click', function (e) {
    var b = e.target.closest('.spc-etq'); if (!b || etqAdd.disabled) return;
    etqs = etqs.filter(function (n) { return n !== b.dataset.n; }); sujo = true; pintarEtq();
  });
  etqAdd.addEventListener('change', function () {
    if (etqAdd.value) { etqs.push(etqAdd.value); sujo = true; }
    pintarEtq();
  });
  function selecionar(t) {
    atual = t || null;
    pintarLista();
    form.hidden = !atual;
    if (!atual) { $('tm_tit').textContent = 'Escolha um tema à esquerda.'; $('tm_uso').textContent = ''; return; }
    $('tm_tit').textContent = t.nome || t.chave || 'Tema novo';
    $('tm_uso').textContent = 'Usado em ' + (t.solicitacoes || 0) + ' solicitações. O que estiver aqui é o que a OS vai levar '
      + 'quando o PCM escolher este tema. Editar não mexe em OS já criada.';
    nome.value = t.nome || ''; motivo.value = t.motivo || '';
    encherEquip((t.tipo_equipamento || '').trim());
    opcoesCom(tipoOs, D.tipos_os || [''], t.tipo_os || '');
    opcoesCom(c1, D.classif1 || [''], t.classif1 || '');
    etqs = (t.etiquetas || []).slice();
    pintarEtq();
    editor.set(t.subtarefas || []);
    arq.textContent = t.arquivado ? 'Desarquivar' : 'Arquivar';
    arq.hidden = !t.chave;
    hint.textContent = '';
    habilitar(true);
    syncFiltro();
    sujo = false;
  }
  [nome, motivo].forEach(function (el) { el.addEventListener('input', function () { sujo = true; }); });
  [equip, tipoOs, c1].forEach(function (el) { el.addEventListener('change', function () { sujo = true; }); });
  equip.addEventListener('change', syncFiltro);
  nome.addEventListener('input', function () { if (atual && !atual.chave) $('tm_tit').textContent = nome.value || 'Tema novo'; });

  $('tm_novo').addEventListener('click', function () {
    if (sujo && !window.confirm('Este tema tem alterações que não foram salvas. Descartar e começar um tema novo?')) return;
    if (atual && !atual.chave) temas.splice(temas.indexOf(atual), 1);
    var t = {chave: '', nome: '', motivo: '', classif1: '', tipo_os: '', tipo_equipamento: '', solicitacoes: 0,
             arquivado: false, subtarefas: [], etiquetas: []};
    temas.unshift(t);
    busca.value = '';
    selecionar(t);
    nome.focus();
  });
  desc.addEventListener('click', function () {
    if (!atual) return;
    if (!atual.chave) { temas.splice(temas.indexOf(atual), 1); selecionar(null); sujo = false; return; }
    selecionar(atual);
  });

  function depois(x, chave) {
    if (!x.ok) { hint.textContent = 'Não salvou: ' + (x.j.erro || 'sem resposta do servidor'); habilitar(true); return; }
    if (x.j.temas) temas = x.j.temas;
    sujo = false;
    selecionar(temas.filter(function (t) { return t.chave === chave; })[0] || null);
    hint.textContent = x.j.mensagem || 'salvo — vale para as próximas OS';
    setTimeout(function () { if (hint.textContent === (x.j.mensagem || '')) hint.textContent = ''; }, 4000);
  }
  salvar.addEventListener('click', function () {
    if (!atual) return;
    if (!nome.value.trim()) { hint.textContent = 'O tema precisa de um nome.'; nome.focus(); return; }
    salvar.disabled = true; hint.textContent = 'salvando…';
    SP.pedir('/os/api/solic/temas/salvar', {
      chave: atual.chave || '', nome: nome.value.trim(), motivo: motivo.value.trim(), classif1: c1.value,
      tipo_os: tipoOs.value, tipo_equipamento: equip.value, subtarefas: editor.itens(), etiquetas: etqs
    }, 'Salvando o tema no banco…').then(function (x) { depois(x, x.j.chave || atual.chave); });
  });
  arq.addEventListener('click', function () {
    var t = atual;
    if (!t || !t.chave) return;
    var indo = !t.arquivado;
    if (indo && !window.confirm('Arquivar “' + (t.nome || t.chave) + '”?\n\nEle some da lista de escolha da Solicitação e da Fila. '
        + 'As OS que já nasceram com ele não mudam — cada OS guarda as subtarefas copiadas no momento em que foi criada.')) return;
    hint.textContent = indo ? 'arquivando…' : 'desarquivando…';
    SP.pedir('/os/api/solic/temas/' + encodeURIComponent(t.chave) + '/arquivar', {arquivar: indo}, 'Gravando no banco…')
      .then(function (x) { depois(x, t.chave); });
  });

  pintarLista();
  selecionar(temas[0] || null);
  window.addEventListener('beforeunload', function (e) { if (sujo) { e.preventDefault(); e.returnValue = ''; } });
})();
