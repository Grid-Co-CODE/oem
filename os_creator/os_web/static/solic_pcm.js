/* os_creator/os_web/static/solic_pcm.js — o que as páginas do PCM dividem (Levi, 13/10/2026: "referência é a fila do app
   desktop, nem painel do PCM nem histórico nem temas"): o editor de subtarefas do app (`steps/subtarefas_edit.py`), que a
   Fila e os Temas usam; o aviso que some sozinho; e o pedido JSON com o círculo de carga do OsCarga. */
(function () {
  'use strict';
  if (window.SolicPcm) return;

  function esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  // sem acento e sem caixa: a regra da PERFORMANCE compara "garantia" em qualquer grafia
  function norm(t) { return String(t == null ? '' : t).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }

  // o pedido JSON: GET sem corpo, POST com. Devolve {ok, status, j}; a rede que caiu vira {ok:false, j:{erro}}
  function pedir(url, corpo, texto) {
    var op = {credentials: 'same-origin', headers: {'Accept': 'application/json'}};
    if (corpo !== undefined) {
      op.method = 'POST';
      op.headers['Content-Type'] = 'application/json';
      op.body = JSON.stringify(corpo || {});
    }
    return window.OsCarga.buscar(url, op, texto || 'Gravando no Fracttal…')
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { return {ok: r.ok, status: r.status, j: j || {}}; });
      })
      .catch(function (e) { return {ok: false, status: 0, j: {erro: 'Sem resposta do servidor: ' + e}}; });
  }

  // o aviso de canto (a QMessageBox do app, sem travar a tela): o bom some em 5 s, o ruim em 9
  var caixa = null, relogio = null;
  function aviso(txt, ruim) {
    if (!caixa) {
      caixa = document.createElement('div');
      caixa.className = 'spc-flutua';
      caixa.setAttribute('role', 'status');
      caixa.addEventListener('click', function () { caixa.hidden = true; });
      document.body.appendChild(caixa);
    }
    caixa.textContent = txt;
    caixa.classList.toggle('ruim', !!ruim);
    caixa.hidden = false;
    clearTimeout(relogio);
    relogio = setTimeout(function () { caixa.hidden = true; }, ruim ? 9000 : 5000);
  }

  /* O EditorSubtarefas do app: número verde, o texto (parece texto; editar é clicar), o tipo, o "anexo obrigatório" e o ×;
     "+ Adicionar subtarefa" no fim, e o cabeçalho diz com quantas a OS vai nascer. `tipos` = [[chave, rótulo]].
     `itens()` devolve o que está na tela, na ordem da tela, sem as linhas em branco. */
  function editorSubs(raiz, opcoes) {
    var tipos = opcoes.tipos || [['texto', 'Texto']], vazio = opcoes.vazio || '', aoMudar = opcoes.aoMudar || function () {};
    var linhas = [], editavel = true, mexeu = false;
    raiz.classList.add('spc-subs');
    raiz.innerHTML = '<p class="spc-subs-cab"></p><ol class="spc-subs-lista"></ol>'
      + '<button type="button" class="spc-subs-add">+&nbsp;&nbsp;&nbsp;Adicionar subtarefa</button>';
    var cab = raiz.querySelector('.spc-subs-cab'), ol = raiz.querySelector('.spc-subs-lista'),
        add = raiz.querySelector('.spc-subs-add');

    function opcoesTipo(atual) {
      return tipos.map(function (t) {
        return '<option value="' + esc(t[0]) + '"' + (t[0] === atual ? ' selected' : '') + '>' + esc(t[1]) + '</option>';
      }).join('');
    }
    function cabecalho() {
      var n = linhas.length;
      cab.innerHTML = n ? 'A OS vai nascer com <b>' + n + ' subtarefa' + (n === 1 ? '' : 's') + '</b>'
                        : '<span class="spc-mudo">' + esc(vazio) + '</span>';
    }
    function pintar(focar) {
      ol.innerHTML = linhas.map(function (d, i) {
        var dis = editavel ? '' : ' disabled';
        return '<li class="spc-sub" data-i="' + i + '"><span class="spc-sub-n">' + (i + 1) + '</span>'
          + '<input class="spc-sub-txt" type="text" value="' + esc(d.desc) + '" placeholder="descreva o que o técnico deve fazer"'
          + ' aria-label="Subtarefa ' + (i + 1) + '"' + dis + '>'
          + '<select class="spc-sub-tipo" title="clique para trocar o tipo" aria-label="Tipo da subtarefa ' + (i + 1) + '"' + dis + '>'
          + opcoesTipo(d.tipo || 'texto') + '</select>'
          + '<label class="spc-sub-anexo"><input type="checkbox"' + (d.anexo ? ' checked' : '') + dis + '> anexo obrigatório</label>'
          + '<button type="button" class="spc-sub-x" title="Remover esta subtarefa" aria-label="Remover a subtarefa ' + (i + 1) + '"'
          + dis + '>&times;</button></li>';
      }).join('');
      cabecalho();
      add.disabled = !editavel;
      if (focar) {
        var ult = ol.querySelector('li:last-child .spc-sub-txt');
        if (ult) ult.focus();
      }
    }
    function mudou() { mexeu = true; cabecalho(); aoMudar(); }
    ol.addEventListener('input', function (e) {
      var li = e.target.closest('.spc-sub'); if (!li) return;
      var d = linhas[Number(li.dataset.i)]; if (!d) return;
      if (e.target.classList.contains('spc-sub-txt')) d.desc = e.target.value;
      mudou();
    });
    ol.addEventListener('change', function (e) {
      var li = e.target.closest('.spc-sub'); if (!li) return;
      var d = linhas[Number(li.dataset.i)]; if (!d) return;
      if (e.target.classList.contains('spc-sub-tipo')) d.tipo = e.target.value;
      else if (e.target.type === 'checkbox') d.anexo = e.target.checked;
      mudou();
    });
    ol.addEventListener('click', function (e) {
      var x = e.target.closest('.spc-sub-x'); if (!x || !editavel) return;
      linhas.splice(Number(x.closest('.spc-sub').dataset.i), 1);
      pintar(false); mudou();
    });
    add.addEventListener('click', function () {
      if (!editavel) return;
      linhas.push({desc: '', tipo: 'texto', anexo: false});
      pintar(true); mudou();
    });

    return {
      set: function (lista) {
        linhas = (lista || []).map(function (d) { return {desc: String(d.desc || ''), tipo: d.tipo || 'texto', anexo: !!d.anexo}; });
        mexeu = false; pintar(false);
      },
      itens: function () {
        return linhas.filter(function (d) { return String(d.desc || '').trim(); })
          .map(function (d) { return {desc: String(d.desc).trim(), tipo: d.tipo || 'texto', anexo: !!d.anexo}; });
      },
      editavel: function (on) { editavel = !!on; pintar(false); },
      mexeu: function () { return mexeu; }
    };
  }

  window.SolicPcm = {esc: esc, norm: norm, pedir: pedir, aviso: aviso, editorSubs: editorSubs};
})();
