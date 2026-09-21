/* Guided tour overlay.
 *
 * Each page defines window.TOUR_STEPS = [{sel, title, text}, ...] before loading
 * this file. A "Guided tour" button is injected into the navigation; pressing it
 * spotlights each element in turn with an explanation.
 *
 * Degrades silently: no steps defined, or a step whose selector matches nothing,
 * and that step is simply skipped rather than breaking the page.
 */
(function () {
  'use strict';
  var steps = (window.TOUR_STEPS || []).slice();
  if (!steps.length) return;

  var idx = 0, shade, spot, tip, live = false;

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function build() {
    shade = el('div', 'tour-shade');
    spot = el('div', 'tour-spot');
    tip = el('div', 'tour-tip');
    shade.addEventListener('click', stop);
    document.body.appendChild(shade);
    document.body.appendChild(spot);
    document.body.appendChild(tip);
    document.addEventListener('keydown', onKey);
  }

  function onKey(e) {
    if (!live) return;
    if (e.key === 'Escape') stop();
    else if (e.key === 'ArrowRight' || e.key === 'Enter') go(1);
    else if (e.key === 'ArrowLeft') go(-1);
  }

  function target(i) {
    var s = steps[i];
    if (!s || !s.sel) return null;
    var n = document.querySelector(s.sel);
    if (!n) return null;
    // A bare input or select is too small to spotlight usefully; highlight the
    // labelled group around it so the caption is inside the light too.
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(n.tagName)) {
      var g = n.closest('.ctrl-group');
      if (g) return g;
    }
    return n;
  }

  function show() {
    // skip past any step whose element is not on this page
    var guard = 0;
    while (idx < steps.length && steps[idx].sel && !target(idx) && guard++ < steps.length) idx++;
    if (idx >= steps.length) { stop(); return; }

    var s = steps[idx], node = target(idx);
    if (node) {
      node.scrollIntoView({ block: 'center', behavior: 'auto' });
      requestAnimationFrame(function () { place(node, s); });
    } else {
      place(null, s);
    }
  }

  function place(node, s) {
    if (node) {
      var r = node.getBoundingClientRect(), pad = 6;
      spot.style.display = 'block';
      shade.classList.remove('dim');
      spot.style.top = (r.top - pad) + 'px';
      spot.style.left = (r.left - pad) + 'px';
      spot.style.width = (r.width + 2 * pad) + 'px';
      spot.style.height = (r.height + 2 * pad) + 'px';
    } else {
      spot.style.display = 'none';
      shade.classList.add('dim');
    }

    tip.innerHTML =
      '<div class="tour-step">Step ' + (idx + 1) + ' of ' + steps.length + '</div>' +
      '<h4>' + s.title + '</h4>' +
      '<p>' + s.text + '</p>' +
      '<div class="tour-btns">' +
      (idx > 0 ? '<button class="tour-b alt" data-go="-1">Back</button>' : '') +
      '<button class="tour-b" data-go="1">' +
      (idx === steps.length - 1 ? 'Finish' : 'Next') + '</button>' +
      '<button class="tour-b ghost" data-stop="1">Close</button>' +
      '</div>';

    // park the tooltip beside the spotlight, flipping when it would run off screen
    var tw = 330, th = tip.offsetHeight || 190, m = 14, top, left;
    if (node) {
      var r2 = node.getBoundingClientRect();
      left = r2.right + m;
      if (left + tw > window.innerWidth - 8) left = Math.max(8, r2.left - tw - m);
      top = r2.top;
      if (top + th > window.innerHeight - 8) top = Math.max(8, window.innerHeight - th - 8);
    } else {
      left = (window.innerWidth - tw) / 2;
      top = (window.innerHeight - th) / 2;
    }
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
    tip.style.display = 'block';
  }

  function go(d) { idx += d; show(); }

  function start() {
    if (!shade) build();
    idx = 0; live = true;
    shade.style.display = 'block';
    document.body.classList.add('tour-on');
    show();
  }

  function stop() {
    live = false;
    if (shade) shade.style.display = 'none';
    if (spot) spot.style.display = 'none';
    if (tip) tip.style.display = 'none';
    document.body.classList.remove('tour-on');
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || t.tagName !== 'BUTTON') return;
    if (t.dataset.stop) stop();
    else if (t.dataset.go) go(+t.dataset.go);
  });

  window.addEventListener('resize', function () { if (live) show(); });

  // inject the launcher into the nav
  document.addEventListener('DOMContentLoaded', function () {
    var nav = document.querySelector('.nav-links');
    if (!nav) return;
    var b = el('button', 'tour-launch', 'Guided tour');
    b.addEventListener('click', start);
    nav.appendChild(b);
  });

  window.startTour = start;
})();
