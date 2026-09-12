// os_creator/os_web/static/sso_bookmarklet.js — vira o favorito "Copiar sessão do Fracttal" (rotas: sso.bookmarklet_href).
// Roda NA ABA DO FRACTTAL, depois que a pessoa entrou pela Microsoft. E o mesmo _POLL_JS/_HOOK_JS do app desktop
// (steps/sso_login.py): varre localStorage, sessionStorage e cookies por um JWT; se nao achar, engancha XHR/fetch e
// espera a proxima requisicao do proprio Fracttal. Copia para a area de transferencia; a pessoa cola no login da web.
// Uma linha no favorito: quem monta o href tira as quebras de linha e os comentarios.
(function () {
  var re = /eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+/;
  if (location.hostname.indexOf('fracttal.com') < 0) { alert('Abra o Fracttal (app.fracttal.com), entre pela Microsoft e clique neste favorito la.'); return; }
  function scan(st) { try { for (var i = 0; i < st.length; i++) { var m = (st.getItem(st.key(i)) || '').match(re); if (m) return m[0]; } } catch (e) {} return ''; }
  function ok(t) {
    var msg = 'Sessao do Fracttal copiada. Volte a plataforma, cole no campo do SSO e FECHE esta aba do Fracttal (ele renova a sessao e mata a copia).';
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t).then(function () { alert(msg); }, function () { prompt('Copie a sessao (Ctrl+C) e cole na plataforma:', t); }); }
    else { prompt('Copie a sessao (Ctrl+C) e cole na plataforma:', t); }
  }
  var t = scan(localStorage) || scan(sessionStorage) || ((document.cookie || '').match(re) || [''])[0];
  if (t) { ok(t); return; }
  if (window.__gridco_sso) { alert('Ainda procurando a sessao: clique em qualquer coisa dentro do Fracttal e depois neste favorito de novo.'); return; }
  window.__gridco_sso = true;
  function cap(v) { try { if (v && ('' + v).indexOf('Bearer ') === 0) { var tk = ('' + v).slice(7).trim(); if (re.test(tk)) { window.__gridco_sso_tok = tk; } } } catch (e) {} }
  var oSet = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) { try { if (('' + k).toLowerCase() === 'authorization') cap(v); } catch (e) {} return oSet.apply(this, arguments); };
  var oF = window.fetch;
  if (oF) window.fetch = function (input, init) { try { var h = init && init.headers; var a = h ? (h.get ? h.get('Authorization') : (h['Authorization'] || h['authorization'])) : ''; cap(a); } catch (e) {} return oF.apply(this, arguments); };
  var n = 0, it = setInterval(function () { if (window.__gridco_sso_tok) { clearInterval(it); ok(window.__gridco_sso_tok); } else if (++n > 40) { clearInterval(it); window.__gridco_sso = false; alert('Nao achei a sessao. Navegue em qualquer tela do Fracttal e clique no favorito de novo.'); } }, 500);
  alert('Sessao ainda nao visivel. Clique em qualquer tela do Fracttal (ex.: Ordens de Trabalho) e aguarde: assim que ele falar com o servidor, eu copio.');
})();
