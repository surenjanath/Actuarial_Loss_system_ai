(function () {
  function init() {
    var t = document.getElementById('db-sync-time');
    if (t) t.textContent = new Date().toLocaleString();

    var search = document.querySelector('#db-controls input[name="q"]');
    var form = document.getElementById('db-controls');
    if (search && form) {
      var timer;
      search.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          form.submit();
        }, 400);
      });
    }

    var checks = document.querySelectorAll('.db-row-check');
    var all = document.getElementById('db-check-all');
    var bar = document.getElementById('db-selected-bar');
    var cnt = document.getElementById('db-sel-count');

    function updateSel() {
      var n = 0;
      checks.forEach(function (c) {
        if (c.checked) n++;
      });
      if (bar) bar.style.display = n > 0 ? 'flex' : 'none';
      if (cnt) cnt.textContent = String(n);
      document.querySelectorAll('.db-row').forEach(function (row) {
        var cb = row.querySelector('.db-row-check');
        if (cb && cb.checked) row.style.background = 'rgba(42,200,235,0.1)';
        else row.style.background = '';
      });
    }

    checks.forEach(function (c) {
      c.addEventListener('change', updateSel);
    });

    if (all) {
      all.addEventListener('change', function () {
        checks.forEach(function (c) {
          c.checked = all.checked;
        });
        updateSel();
      });
    }

    var tableBtn = document.getElementById('db-view-table');
    var cardsBtn = document.getElementById('db-view-cards');
    var tableWrap = document.getElementById('db-table-wrap');
    var cardsWrap = document.getElementById('db-cards-wrap');
    var importBtn = document.getElementById('db-btn-import');
    if (importBtn) {
      importBtn.addEventListener('click', function () {
        window.alert(
          'Import is not available in this build. Use Export to download CSV, or Regenerate data to refresh the session dataset.',
        );
      });
    }

    if (tableBtn && cardsBtn && tableWrap && cardsWrap) {
      tableBtn.addEventListener('click', function () {
        tableWrap.classList.remove('hidden');
        cardsWrap.classList.add('hidden');
        tableBtn.classList.add('active');
        cardsBtn.classList.remove('active');
      });
      cardsBtn.addEventListener('click', function () {
        tableWrap.classList.add('hidden');
        cardsWrap.classList.remove('hidden');
        cardsBtn.classList.add('active');
        tableBtn.classList.remove('active');
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
