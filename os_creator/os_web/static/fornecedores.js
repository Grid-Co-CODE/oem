/* os_creator/os_web/static/fornecedores.js — o editor do Controle de fornecedores (27/09/2026).

   O estado da tela é o JSON do servidor (fornecedores_web.tela) + os RASCUNHOS: cada bloco editado vira uma cópia em
   `S.rasc[chave]` até ser salvo ou descartado — trocar de aba ou de fornecedor não perde o que foi digitado, e a lista
   marca com um ponto âmbar o que está sem salvar. Salvar manda o bloco inteiro com a versão que a tela leu; se alguém
   salvou antes, o servidor recusa (409) em vez de apagar a edição do outro. O visual é o do chamados.css — o mesmo
   escuro do Acompanhamento (Levi, 27/09: "leva o mesmo visual escuro para o Controle de fornecedores"). */
(function () {
  "use strict";
  const H = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  };
  const norm = function (s) { return String(s || "").trim().toLowerCase(); };
  const copia = function (x) { return JSON.parse(JSON.stringify(x)); };
  const raiz = document.getElementById("forn");
  if (!raiz) return;
  let D = JSON.parse(document.getElementById("f_dados").textContent);
  const S = {aba: 0, sel: null, rasc: {}, msg: {texto: "", tipo: ""}, novo: false, conf: ""};
  // o nome da ABA para o tipo do pacote: "Estrutura Trackers" é "Tracker" para quem usa a tela (não existe tipo Tracker)
  const nomeTipo = function (t) {
    const a = D.abas.find(function (x) { return x.tipo === t; });
    return a ? a.nome : t;
  };

  const aba = function () { return S.aba >= 0 ? D.abas[S.aba] : null; };
  const bloco = function (ch) { return S.rasc[ch] || D.blocos[ch]; };
  const salvo = function (ch) { return (D.blocos[ch] || {}).subtarefas || []; };
  function editar(ch) {
    if (!S.rasc[ch]) {
      S.rasc[ch] = copia(D.blocos[ch] || {subtarefas: [], canal: "", atende: [], arquivado: false, versao: ""});
    }
    return S.rasc[ch];
  }
  function sujo(ch) {
    const r = S.rasc[ch];
    if (!r) return false;
    const b = D.blocos[ch];
    if (!b) return true;
    const k = function (x) {
      return JSON.stringify({s: x.subtarefas || [], c: x.canal || "", a: (x.atende || []).slice().sort(), q: !!x.arquivado});
    };
    return k(r) !== k(b);
  }
  // o que a inspeção leva para (tipo, fornecedor): a mesma conta do pacote — base → tipo → fornecedor, sem as de outro
  // tipo e sem repetir pergunta. Base e tipo entram SALVOS; o fornecedor, como está na tela.
  function efetivas(tipo, ch) {
    const vistos = new Set(), out = [];
    salvo("BASE").concat(salvo("TIPO:" + tipo), ch ? ((bloco(ch) || {}).subtarefas || []) : []).forEach(function (s) {
      if (s.so_para && s.so_para.length && s.so_para.indexOf(tipo) < 0) return;
      const k = norm(s.desc);
      if (!k || vistos.has(k)) return;
      vistos.add(k);
      out.push(s);
    });
    return out;
  }
  function resumo(subs) {
    const ob = subs.filter(function (s) { return s.obrig; }).length, an = subs.filter(function (s) { return s.anexo; }).length;
    return subs.length + " subtarefa" + (subs.length === 1 ? "" : "s") + " · " + ob + " obrigatória" + (ob === 1 ? "" : "s") +
      " · " + an + " com anexo obrigatório";
  }

  // ── desenho ──────────────────────────────────────────────────────────────────────────────────────────────────
  function desenhar() {
    desenharAbas();
    desenharLista();
    desenharDetalhe();
  }

  function desenharAbas() {
    const nb = salvo("BASE").length;
    document.getElementById("f_abas").innerHTML =
      '<button type="button" class="aba' + (S.aba === -1 ? " on" : "") + '" data-aba="-1">Base<em>' + nb + "</em></button>" +
      D.abas.map(function (a, i) {
        const n = a.fornecedores.filter(function (f) { return !f.arquivado; }).length;
        return '<button type="button" class="aba' + (i === S.aba ? " on" : "") + '" data-aba="' + i + '">' + H(a.nome) +
          "<em>" + n + "</em></button>";
      }).join("");
  }

  function itemLista(x) {
    return '<button type="button" class="li' + (x.ch === S.sel ? " on" : "") + (x.arq ? " arq" : "") + '" data-sel="' + H(x.ch) + '">' +
      '<div class="li-n">' + H(x.n) + (x.clone ? '<span class="chip">igual à ' + H(x.clone) + "</span>" : "") +
      (sujo(x.ch) ? '<i class="sujo" title="alteração não salva"></i>' : "") + "</div>" +
      '<div class="li-m">' + H(x.m) + "</div>" + (x.c ? '<div class="li-c">' + H(x.c) + "</div>" : "") + "</button>";
  }

  function desenharLista() {
    const a = aba(), alvo = document.getElementById("f_lista");
    if (!a) {
      S.sel = "BASE";
      alvo.innerHTML = '<div class="cf-lh"><span class="lbl">Base</span></div>' +
        itemLista({ch: "BASE", n: "Toda inspeção", m: ((bloco("BASE") || {}).subtarefas || []).length +
                   " perguntas · abrem toda inspeção, de qualquer ativo e fornecedor"});
      return;
    }
    const tch = "TIPO:" + a.tipo;
    const itens = [{ch: tch, n: a.todo, m: ((bloco(tch) || {}).subtarefas || []).length + " perguntas · valem para todo fornecedor",
                    c: a.alias.length ? "inclui " + a.alias.join(", ") : ""}];
    a.fornecedores.forEach(function (f) {
      itens.push({ch: "MARCA:" + f.marca, n: f.marca, c: f.canal, clone: f.igual_a, arq: f.arquivado,
                  m: f.arquivado ? "arquivado · não aparece na inspeção" :
                     f.n_proprias + " própria" + (f.n_proprias === 1 ? "" : "s") + " · a inspeção nasce com " + f.n_total});
    });
    Object.keys(S.rasc).forEach(function (ch) {
      if (ch.indexOf("MARCA:") === 0 && !D.blocos[ch] && (S.rasc[ch].atende || []).indexOf(a.tipo) >= 0) {
        itens.push({ch: ch, n: ch.slice(6), m: "novo · ainda não salvo", c: S.rasc[ch].canal});
      }
    });
    if (!S.sel || !itens.some(function (x) { return x.ch === S.sel; })) S.sel = itens.length > 1 ? itens[1].ch : itens[0].ch;
    let h = '<div class="cf-lh"><span class="lbl">' + H(a.nome) + "</span>" +
            (D.pode_gravar ? '<button type="button" data-novo="1">+ novo fornecedor</button>' : "") + "</div>";
    if (S.novo) {
      h += '<div class="li novo"><input class="in" id="novo_nome" maxlength="40" placeholder="nome do fornecedor">' +
           '<div class="bar"><button type="button" class="btn btn-g btn-p" data-novo-ok="1">Criar</button>' +
           '<button type="button" class="btn btn-o btn-p" data-novo="0">Cancelar</button></div><div class="msg er" id="novo_msg"></div></div>';
    }
    h += itens.map(itemLista).join("");
    const sd = (a.sem_doc || []).filter(function (m) { return !S.rasc["MARCA:" + m]; });
    if (sd.length) {
      h += '<div class="cf-lh sep"><span class="lbl">Sem processo escrito</span></div>' + sd.map(function (m) {
        return '<button type="button" class="li sd" data-sem="' + H(m) + '"><div class="li-n">' + H(m) + "</div>" +
               '<div class="li-m">só a base e o bloco do tipo · pedir o documento à Singrid</div></button>';
      }).join("");
    }
    alvo.innerHTML = h;
  }

  const CAB_BLOCO = '<div class="rw cab"><span></span><span>Pergunta ao técnico</span><span>Tipo</span><span>Obrigatória</span><span>Anexo</span><span>Campo</span><span></span></div>';
  const CAB_MARCA = '<div class="rw cab"><span></span><span>Pergunta ao técnico</span><span>Tipo</span><span>Obrigatória</span><span>Anexo</span><span>Vale para</span><span></span></div>';

  function linhaLeitura(s, n) {
    return '<div class="rw"><span class="n">' + n + '</span><span class="ro">' + H(s.desc) + '</span><span class="t">' +
      H(D.tipos[s.tipo] || s.tipo) + '</span><span class="t' + (s.obrig ? " on" : "") + '">' +
      (s.obrig ? "obrigatória" : "—") + '</span><span class="t' + (s.anexo ? " on" : "") + '">' +
      (s.anexo ? "anexo" : "—") + '</span><span class="ch" title="campo no formulário do fornecedor">' + H(s.chave || "—") +
      "</span><span></span>" + (s.tipo === "lista" && (s.opcoes || []).length ?
        '<div class="ops">' + s.opcoes.map(function (o) { return "<span>" + H(o) + "</span>"; }).join("") + "</div>" : "") + "</div>";
  }

  function linhaEdicao(ch, s, i, n, marca) {
    const fora = marca && s.so_para && s.so_para.length && s.so_para.indexOf(marca.tipo) < 0;
    const rep = marca && !fora && marca.antes.has(norm(s.desc));
    const tipos = Object.keys(D.tipos).map(function (k) {
      return '<option value="' + k + '"' + (k === s.tipo ? " selected" : "") + ">" + H(D.tipos[k]) + "</option>";
    }).join("");
    let col6;
    if (marca) {
      col6 = '<select class="sel" data-k="vale" data-osb="nativo"><option value="">todos os tipos</option>' + (marca.atende || []).map(function (t) {
        return '<option value="' + H(t) + '"' + ((s.so_para || [])[0] === t ? " selected" : "") + ">só " + H(nomeTipo(t)) + "</option>";
      }).join("") + "</select>";
    } else {
      col6 = '<span class="ch" title="campo no formulário do fornecedor">' + H(s.chave || "—") + "</span>";
    }
    let nota = "";
    if (fora) nota = "vale só para " + H(s.so_para.map(nomeTipo).join(", ")) + ": não entra na inspeção deste tipo";
    else if (rep) nota = "já é pedida em cima: a inspeção não repete a pergunta";
    else if (marca && s.chave) nota = "campo no formulário do fornecedor: " + H(s.chave);
    return '<div class="rw' + (fora ? " fora" : "") + (rep ? " rep" : "") + '" data-ch="' + H(ch) + '" data-i="' + i + '">' +
      '<span class="n">' + (fora || rep ? "—" : n) + "</span>" +
      '<input class="in" data-k="desc" value="' + H(s.desc) + '" maxlength="250" placeholder="a pergunta ao técnico">' +
      '<select class="sel" data-k="tipo" data-osb="nativo">' + tipos + "</select>" +
      '<label><input type="checkbox" data-k="obrig"' + (s.obrig ? " checked" : "") + "> obrigatória</label>" +
      '<label><input type="checkbox" data-k="anexo"' + (s.anexo ? " checked" : "") + "> anexo</label>" + col6 +
      '<span class="mv"><button type="button" data-mv="-1" title="Subir">↑</button><button type="button" data-mv="1" title="Descer">↓</button>' +
      '<button type="button" class="x" data-tira="1" title="Tirar a pergunta">×</button></span>' +
      (s.tipo === "lista" ? '<div class="ops">' + (s.opcoes || []).map(function (o, j) {
        return "<span>" + H(o) + ' <button type="button" class="x" data-tira-op="' + j + '" title="Tirar a opção">×</button></span>';
      }).join("") + '<input class="in" data-op-nova="1" maxlength="60" placeholder="nova opção e Enter"></div>' : "") +
      (nota ? '<div class="nota">' + nota + "</div>" : "") + "</div>";
  }

  function barra(ch, extra) {
    const pode = D.pode_gravar;
    return '<div class="bar"><button type="button" class="btn btn-g" data-salvar="' + H(ch) + '"' + (pode && sujo(ch) ? "" : " disabled") + ">" +
      (ch.indexOf("MARCA:") === 0 ? "Salvar fornecedor" : ch === "BASE" ? "Salvar a base" : "Salvar") + "</button>" +
      '<button type="button" class="btn btn-o" data-descartar="' + H(ch) + '"' + (sujo(ch) ? "" : " disabled") + ">Descartar alterações</button>" +
      (extra || "") + "</div>";
  }

  function detalheBloco(ch, titulo, sub, deslocamento) {
    const b = bloco(ch) || {subtarefas: []};
    const origem = (D.blocos[ch] || {}).origem === "banco" && (D.blocos[ch] || {}).por ?
      '<div class="dica">salvo por ' + H(D.blocos[ch].por) + "</div>" : "";
    return '<div class="cf-t">' + H(titulo) + "</div>" + '<div class="cf-s">' + sub + "</div>" + origem +
      '<div class="sec">' + CAB_BLOCO + b.subtarefas.map(function (s, i) { return linhaEdicao(ch, s, i, deslocamento + i + 1, null); }).join("") +
      '<button type="button" class="add" data-add="' + H(ch) + '">+ Adicionar pergunta</button></div>' + barra(ch);
  }

  function detalheMarca(ch, a) {
    const b = bloco(ch) || editar(ch);
    const m = ch.slice(6), novo = !D.blocos[ch];
    const ef = efetivas(a.tipo, ch);
    const nb = salvo("BASE").length, nt = salvo("TIPO:" + a.tipo).length;
    const marca = {tipo: a.tipo, atende: b.atende || [],
                   antes: new Set(salvo("BASE").concat(salvo("TIPO:" + a.tipo)).map(function (s) { return norm(s.desc); }))};
    let n = nb + nt;
    const linhas = (b.subtarefas || []).map(function (s, i) {
      const fora = s.so_para && s.so_para.length && s.so_para.indexOf(a.tipo) < 0;
      const rep = !fora && marca.antes.has(norm(s.desc));
      return linhaEdicao(ch, s, i, fora || rep ? 0 : ++n, marca);
    }).join("");
    const tiposPoe = D.tipos_ativo.filter(function (t) { return (b.atende || []).indexOf(t) < 0; });
    const arq = novo ? "" : (S.conf === ch ?
      '<span class="dica av">' + (b.arquivado ? "Reativar volta a oferecer " + H(m) + " na inspeção." :
        "Arquivar tira " + H(m) + " da inspeção; as OS já criadas não mudam.") + '</span><button type="button" class="btn btn-i btn-p" data-arq-ok="' + H(ch) + '">' +
        (b.arquivado ? "Reativar" : "Arquivar") + '</button><button type="button" class="btn btn-o btn-p" data-arq-nao="1">Voltar</button>' :
      '<button type="button" class="btn btn-o" data-arquivar="' + H(ch) + '"' + (D.pode_gravar ? "" : " disabled") + ">" +
        ((D.blocos[ch] || {}).arquivado ? "Reativar fornecedor" : "Arquivar fornecedor") + "</button>");
    return '<div class="cf-t">' + H(m) + " · " + H(a.nome) + (b.arquivado ? ' <span class="chip">arquivado</span>' : "") + "</div>" +
      '<div class="cf-s">' + (b.arquivado ? "Arquivado: não aparece na inspeção." : 'A inspeção nasce com <b id="f_resumo">' + H(resumo(ef)) + "</b>.") +
      " Editar não mexe em inspeção já criada: a OS copia as subtarefas ao nascer.</div>" +
      ((D.blocos[ch] || {}).por ? '<div class="dica">salvo por ' + H(D.blocos[ch].por) + "</div>" : "") +
      '<div class="campos"><div class="fc"><span class="lbl">Fornecedor</span><input class="in" value="' + H(m) + '" disabled></div>' +
      '<div class="fc"><span class="lbl">Como abrir o chamado</span><input class="in" data-canal="' + H(ch) + '" value="' + H(b.canal || "") +
      '" maxlength="300" placeholder="portal, e-mail, formulário…"></div></div>' +
      '<div class="fc"><span class="lbl">Atende</span><div class="atende">' + (b.atende || []).map(function (t) {
        return '<span class="chip">' + H(nomeTipo(t)) + '<button type="button" data-tira-tipo="' + H(t) + '" title="Tirar este tipo">×</button></span>';
      }).join("") + (tiposPoe.length ? '<select data-osb="nativo" data-poe-tipo="' + H(ch) + '"><option value="">+ tipo de ativo</option>' +
        tiposPoe.map(function (t) { return '<option value="' + H(t) + '">' + H(nomeTipo(t)) + "</option>"; }).join("") + "</select>" : "") + "</div></div>" +
      (b.igual_a && !S.rasc[ch] ? '<p class="aviso">Hoje é o mesmo pacote da ' + H(b.igual_a) + ": no código as duas listas são uma só, e " +
        H(m) + " acompanha o que for salvo na " + H(b.igual_a) + ". Salvando aqui, " + H(m) + " passa a ter a lista dela.</p>" : "") +
      '<div class="sec"><div class="sec-t"><span class="lbl">1 · Base</span><span>toda inspeção</span><button type="button" data-ir-base="1">editar a base</button></div>' +
        salvo("BASE").map(function (s, i) { return linhaLeitura(s, i + 1); }).join("") + "</div>" +
      '<div class="sec"><div class="sec-t"><span class="lbl">2 · ' + H(a.todo) + "</span><span>todo fornecedor deste tipo</span>" +
        '<button type="button" data-sel-ir="TIPO:' + H(a.tipo) + '">editar</button></div>' +
        salvo("TIPO:" + a.tipo).map(function (s, i) { return linhaLeitura(s, nb + i + 1); }).join("") + "</div>" +
      '<div class="sec"><div class="sec-t"><span class="lbl">3 · Só ' + H(m) + "</span><span>o que o formulário deste fornecedor pede a mais</span></div>" +
        CAB_MARCA + (linhas || '<div class="vazio">Nada além da base e do bloco do tipo: o formulário deste fornecedor não pede nada que já não esteja sendo coletado.</div>') +
        '<button type="button" class="add" data-add="' + H(ch) + '">+ Adicionar pergunta a ' + H(m) + "</button></div>" + barra(ch, arq);
  }

  function desenharDetalhe() {
    const a = aba(), ch = S.sel;
    let h;
    if (ch === "BASE") {
      h = detalheBloco("BASE", "Base · toda inspeção", "Abrem <b>toda</b> inspeção, de qualquer ativo e qualquer fornecedor. Mudar aqui muda em todos.", 0);
    } else if (ch.indexOf("TIPO:") === 0) {
      h = detalheBloco(ch, a.todo, "Entram na inspeção de <b>" + H(a.todo.toLowerCase()) + "</b>, depois da base e antes das do fornecedor. " +
        "É aqui que mora a identificação do equipamento (série, modelo, TAG)." +
        (a.alias.length ? " Vale também para " + H(a.alias.join(", ")) + ", que usam este bloco." : ""), salvo("BASE").length);
    } else {
      h = detalheMarca(ch, a);
    }
    document.getElementById("f_det").innerHTML = h + '<div class="msg ' + H(S.msg.tipo) + '" id="f_msg">' + H(S.msg.texto) + "</div>";
  }

  // ── edição ───────────────────────────────────────────────────────────────────────────────────────────────────
  function linhaDo(el) {
    const rw = el.closest(".rw[data-ch]");
    if (!rw) return null;
    const r = editar(rw.dataset.ch);
    return {ch: rw.dataset.ch, r: r, i: +rw.dataset.i, s: r.subtarefas[+rw.dataset.i]};
  }

  function novoFornecedor(nome, tipo) {
    nome = String(nome || "").trim().replace(/\s+/g, " ");
    const existe = Object.keys(D.blocos).concat(Object.keys(S.rasc)).some(function (ch) {
      return ch.indexOf("MARCA:") === 0 && norm(ch.slice(6)) === norm(nome);
    });
    if (!nome) return "Escreva o nome do fornecedor.";
    if (nome.length > 40 || nome.indexOf(":") >= 0) return "Nome de até 40 caracteres, sem dois-pontos.";
    if (existe) return "Já existe um fornecedor com esse nome.";
    S.rasc["MARCA:" + nome] = {subtarefas: [], canal: "", atende: [tipo], arquivado: false, versao: ""};
    S.sel = "MARCA:" + nome;
    S.novo = false;
    return "";
  }

  async function salvar(ch) {
    const r = S.rasc[ch] || copia(D.blocos[ch]);
    S.msg = {texto: "Salvando…", tipo: ""};
    desenharDetalhe();
    try {
      const resp = await fetch("/os/api/fornecedores/salvar", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "fetch"},
        body: JSON.stringify({chave: ch, versao: (D.blocos[ch] || {}).versao || "",
                              dados: {subtarefas: r.subtarefas || [], canal: r.canal || "", atende: r.atende || [],
                                      arquivado: !!r.arquivado}})});
      let j = {};
      try { j = await resp.json(); } catch (e) { j = {}; }
      if (resp.status === 401 && j.login) {
        location.href = "/os/login?next=" + encodeURIComponent(location.pathname);
        return;
      }
      if (!resp.ok || j.erro) throw new Error(j.erro || ("HTTP " + resp.status));
      D = j.tela;
      delete S.rasc[ch];
      S.conf = "";
      S.msg = {texto: j.mensagem || "Salvo.", tipo: "ok"};
    } catch (e) {
      S.msg = {texto: "Não salvou: " + e.message, tipo: "er"};
    }
    desenhar();
  }

  raiz.addEventListener("click", function (ev) {
    const t = ev.target.closest("button, [data-sel]");
    if (!t || t.disabled) return;
    const d = t.dataset;
    const a = aba();
    if (d.aba !== undefined) { S.aba = +d.aba; S.sel = null; S.novo = false; S.conf = ""; S.msg = {texto: "", tipo: ""}; desenhar(); return; }
    if (d.sel !== undefined) { S.sel = d.sel; S.conf = ""; S.msg = {texto: "", tipo: ""}; desenhar(); return; }
    if (d.selIr !== undefined) { S.sel = d.selIr; S.msg = {texto: "", tipo: ""}; desenhar(); return; }
    if (d.irBase !== undefined) { S.aba = -1; S.sel = "BASE"; S.msg = {texto: "", tipo: ""}; desenhar(); return; }
    if (d.novo !== undefined) {
      S.novo = d.novo === "1";
      desenhar();
      const i = document.getElementById("novo_nome");
      if (i) i.focus();
      return;
    }
    if (d.novoOk !== undefined) {
      const erro = novoFornecedor(document.getElementById("novo_nome").value, a.tipo);
      if (erro) { document.getElementById("novo_msg").textContent = erro; return; }
      desenhar();
      return;
    }
    if (d.sem !== undefined) { novoFornecedor(d.sem, a.tipo); desenhar(); return; }
    if (d.add !== undefined) {
      editar(d.add).subtarefas.push({desc: "", tipo: "texto", obrig: true, anexo: false, opcoes: [], chave: "", so_para: []});
      desenhar();
      const campos = document.querySelectorAll('.rw[data-ch="' + CSS.escape(d.add) + '"] input[data-k="desc"]');
      if (campos.length) campos[campos.length - 1].focus();
      return;
    }
    if (d.mv !== undefined) {
      const l = linhaDo(t);
      const j = l.i + (+d.mv);
      if (j >= 0 && j < l.r.subtarefas.length) {
        const x = l.r.subtarefas.splice(l.i, 1)[0];
        l.r.subtarefas.splice(j, 0, x);
        desenhar();
      }
      return;
    }
    if (d.tira !== undefined) { const l = linhaDo(t); l.r.subtarefas.splice(l.i, 1); desenhar(); return; }
    if (d.tiraOp !== undefined) { const l = linhaDo(t); l.s.opcoes.splice(+d.tiraOp, 1); desenhar(); return; }
    if (d.tiraTipo !== undefined) {
      const r = editar(S.sel);
      r.atende = (r.atende || []).filter(function (x) { return x !== d.tiraTipo; });
      (r.subtarefas || []).forEach(function (s) {
        s.so_para = (s.so_para || []).filter(function (x) { return x !== d.tiraTipo; });
      });
      desenhar();
      return;
    }
    if (d.salvar !== undefined) { salvar(d.salvar); return; }
    if (d.descartar !== undefined) {
      const eraNovo = !D.blocos[d.descartar];
      delete S.rasc[d.descartar];
      if (eraNovo) S.sel = null;
      S.msg = {texto: "", tipo: ""};
      desenhar();
      return;
    }
    if (d.arquivar !== undefined) { S.conf = d.arquivar; desenhar(); return; }
    if (d.arqNao !== undefined) { S.conf = ""; desenhar(); return; }
    if (d.arqOk !== undefined) {
      const r = editar(d.arqOk);
      r.arquivado = !(D.blocos[d.arqOk] || {}).arquivado;
      salvar(d.arqOk);
    }
  });

  // Digitar NÃO redesenha o painel: trocar o DOM debaixo do cursor roubaria o foco, e um redesenho no "sair do campo"
  // engoliria o clique no Salvar logo depois de digitar (o botão sumiria entre o mousedown e o click). Só se atualiza
  // o que depende do texto e está FORA do campo: a lista (o ponto de "não salvo"), os botões e a contagem.
  function atualizarEmVolta() {
    desenharLista();
    document.querySelectorAll("[data-salvar]").forEach(function (b) { b.disabled = !(D.pode_gravar && sujo(b.dataset.salvar)); });
    document.querySelectorAll("[data-descartar]").forEach(function (b) { b.disabled = !sujo(b.dataset.descartar); });
    const r = document.getElementById("f_resumo"), a = aba();
    if (r && a && S.sel && S.sel.indexOf("MARCA:") === 0) r.textContent = resumo(efetivas(a.tipo, S.sel));
  }

  raiz.addEventListener("input", function (ev) {
    const t = ev.target;
    if (t.dataset.k === "desc") {
      linhaDo(t).s.desc = t.value;
      atualizarEmVolta();
      return;
    }
    if (t.dataset.canal !== undefined) {
      editar(t.dataset.canal).canal = t.value;
      atualizarEmVolta();
    }
  });

  raiz.addEventListener("change", function (ev) {
    const t = ev.target;
    const k = t.dataset.k;
    if (k) {
      const l = linhaDo(t);
      if (k === "tipo") { l.s.tipo = t.value; if (t.value !== "lista") l.s.opcoes = []; }
      else if (k === "obrig" || k === "anexo") l.s[k] = t.checked;
      else if (k === "vale") l.s.so_para = t.value ? [t.value] : [];
      desenhar();                                   // a contagem e o ponto de "não salvo" mudam
      return;
    }
    if (t.dataset.poeTipo !== undefined && t.value) {
      const r = editar(t.dataset.poeTipo);
      r.atende = (r.atende || []).concat([t.value]).sort();
      desenhar();
      return;
    }
  });

  raiz.addEventListener("keydown", function (ev) {
    const t = ev.target;
    if (ev.key === "Enter" && t.dataset.opNova !== undefined) {
      ev.preventDefault();
      const v = String(t.value || "").trim().replace(/\s+/g, " ");
      if (!v) return;
      const l = linhaDo(t);
      l.s.opcoes = l.s.opcoes || [];
      if (!l.s.opcoes.some(function (o) { return norm(o) === norm(v); })) l.s.opcoes.push(v);
      const ch = l.ch, i = l.i;
      desenhar();
      const novo = document.querySelector('.rw[data-ch="' + CSS.escape(ch) + '"][data-i="' + i + '"] [data-op-nova]');
      if (novo) novo.focus();
      return;
    }
    if (ev.key === "Enter" && t.id === "novo_nome") {
      ev.preventDefault();
      const erro = novoFornecedor(t.value, aba().tipo);
      if (erro) { document.getElementById("novo_msg").textContent = erro; return; }
      desenhar();
    }
  });

  window.addEventListener("beforeunload", function (ev) {
    if (Object.keys(S.rasc).some(sujo)) { ev.preventDefault(); ev.returnValue = ""; }
  });

  desenhar();
})();
