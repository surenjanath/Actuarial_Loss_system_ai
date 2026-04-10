(function () {
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.documentElement.classList.add('reduced-motion');
    }
  } catch (e) {}

  var DISMISS_MS = 8000;

  function dismissMessage(el) {
    if (!el || el.classList.contains('message--out')) return;
    el.classList.add('message--out');
    window.setTimeout(function () {
      el.remove();
      var banner = document.querySelector('.messages-banner');
      if (banner && !banner.querySelector('.message')) {
        banner.remove();
      }
    }, 280);
  }

  function initMessages() {
    document.querySelectorAll('.messages-banner .message').forEach(function (msg) {
      var closeBtn = msg.querySelector('.message-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', function () {
          dismissMessage(msg);
        });
      }
      if (msg.hasAttribute('data-auto-dismiss')) {
        window.setTimeout(function () {
          dismissMessage(msg);
        }, DISMISS_MS);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMessages);
  } else {
    initMessages();
  }
})();
