// HIIT Support: small progressive-enhancement helpers (no framework).
(function () {
  // Mobile sidebar
  var sb = document.getElementById('sidebar'), bd = document.getElementById('sidebarBackdrop'),
      tg = document.getElementById('sidebarToggle');
  function toggle(open) {
    if (!sb) return;
    sb.classList.toggle('open', open);
    if (bd) bd.classList.toggle('show', open);
  }
  if (tg) tg.addEventListener('click', function () { toggle(!sb.classList.contains('open')); });
  if (bd) bd.addEventListener('click', function () { toggle(false); });

  // Flash messages: dismiss button + auto-hide for success messages
  document.querySelectorAll('.flash').forEach(function (el) {
    var x = el.querySelector('.flash-x');
    if (x) x.addEventListener('click', function () { el.remove(); });
    if (el.classList.contains('flash-success')) setTimeout(function () { el.remove(); }, 6000);
  });

  // Loading state on form submit (prevents double submits)
  document.querySelectorAll('form[data-loading]').forEach(function (f) {
    f.addEventListener('submit', function () {
      var b = f.querySelector('button[type=submit]');
      if (b && !b.disabled) {
        setTimeout(function () { b.disabled = true; }, 0);
        b.classList.add('loading');
        b.insertAdjacentHTML('afterbegin', '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>');
      }
    });
  });

  // Description character counter
  var desc = document.getElementById('id_description'), cnt = document.getElementById('charCount');
  if (desc && cnt) {
    var upd = function () { cnt.textContent = desc.value.length; };
    desc.addEventListener('input', upd); upd();
  }
})();
