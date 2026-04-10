(function () {
  function filterMembers() {
    var q = (document.getElementById('member-search').value || '').toLowerCase().trim();
    var dept = document.getElementById('member-dept').value;
    var cards = document.querySelectorAll('#members-grid .member-card');
    var n = 0;

    cards.forEach(function (el) {
      var name = el.getAttribute('data-name') || '';
      var d = el.getAttribute('data-dept') || '';
      var ok =
        (dept === 'all' || d === dept) &&
        (q === '' || name.indexOf(q) !== -1);
      el.style.display = ok ? '' : 'none';
      if (ok) n++;
    });

    var c = document.getElementById('member-count');
    if (c) c.textContent = String(n);
  }

  function init() {
    var search = document.getElementById('member-search');
    var dept = document.getElementById('member-dept');
    if (search) search.addEventListener('input', filterMembers);
    if (dept) dept.addEventListener('change', filterMembers);

  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
