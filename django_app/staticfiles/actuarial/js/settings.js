(function () {
  var STORAGE_KEY = 'actuarial_settings_tab';

  function showToast(message) {
    var el = document.getElementById('settings-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'settings-toast';
      el.className = 'settings-toast';
      el.setAttribute('role', 'status');
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('is-visible');
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(function () {
      el.classList.remove('is-visible');
    }, 2800);
  }

  function activateTab(nav, panels, sectionId, saveStorage) {
    var buttons = nav.querySelectorAll('.settings-nav-btn');
    buttons.forEach(function (b) {
      var on = b.getAttribute('data-section') === sectionId;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.setAttribute('tabindex', on ? '0' : '-1');
    });
    panels.forEach(function (p) {
      var match = p.getAttribute('data-panel') === sectionId;
      p.classList.toggle('hidden', !match);
      p.setAttribute('aria-hidden', match ? 'false' : 'true');
    });
    if (saveStorage) {
      try {
        sessionStorage.setItem(STORAGE_KEY, sectionId);
      } catch (e) {}
    }
  }

  function initTabs() {
    var nav = document.getElementById('settings-nav');
    var panels = document.querySelectorAll('.settings-panel');
    if (!nav || !panels.length) return;

    var initial = 'general';
    try {
      var stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored && nav.querySelector('[data-section="' + stored + '"]')) {
        initial = stored;
      }
    } catch (e) {}

    activateTab(nav, panels, initial, false);

    nav.querySelectorAll('.settings-nav-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        activateTab(nav, panels, btn.getAttribute('data-section'), true);
      });
      btn.addEventListener('keydown', function (e) {
        var keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
        if (keys.indexOf(e.key) === -1) return;
        e.preventDefault();
        var buttons = Array.prototype.slice.call(nav.querySelectorAll('.settings-nav-btn'));
        var i = buttons.indexOf(btn);
        var next = i;
        if (e.key === 'ArrowDown') next = Math.min(i + 1, buttons.length - 1);
        else if (e.key === 'ArrowUp') next = Math.max(i - 1, 0);
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = buttons.length - 1;
        buttons[next].focus();
        activateTab(nav, panels, buttons[next].getAttribute('data-section'), true);
      });
    });
  }

  function initSessionRange() {
    var sr = document.getElementById('session-range');
    var sv = document.getElementById('session-val');
    if (!sr || !sv) return;
    function sync() {
      var v = sr.value;
      sv.textContent = v + ' min';
      sr.setAttribute('aria-valuenow', v);
    }
    sr.addEventListener('input', sync);
    sync();
  }

  function initWorkspaceUserPanel() {
    var boot = document.getElementById('settings-workspace-user-boot');
    if (!boot) return null;
    var url = boot.getAttribute('data-url');
    if (!url) return null;
    var nameEl = document.getElementById('set-name');
    var emailEl = document.getElementById('set-email');
    var roleEl = document.getElementById('set-role');
    var deptEl = document.getElementById('set-dept');
    var avatarEl = document.getElementById('set-avatar');

    function applyProfile(p) {
      if (!p) return;
      if (nameEl) nameEl.value = p.display_name != null ? String(p.display_name) : '';
      if (emailEl) emailEl.value = p.email != null ? String(p.email) : '';
      if (roleEl) roleEl.value = p.role != null ? String(p.role) : '';
      if (deptEl) deptEl.value = p.department != null ? String(p.department) : '';
      if (avatarEl) avatarEl.value = p.avatar_initials != null ? String(p.avatar_initials) : '';
    }

    function collectBody() {
      return {
        display_name: nameEl && nameEl.value != null ? String(nameEl.value).trim() : '',
        email: emailEl && emailEl.value != null ? String(emailEl.value).trim() : '',
        role: roleEl && roleEl.value != null ? String(roleEl.value).trim() : '',
        department: deptEl && deptEl.value != null ? String(deptEl.value).trim() : '',
        avatar_initials: avatarEl && avatarEl.value != null ? String(avatarEl.value).trim() : '',
      };
    }

    fetch(url, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data && data.ok && data.profile) applyProfile(data.profile);
      })
      .catch(function () {});

    return { url: url, applyProfile: applyProfile, collectBody: collectBody };
  }

  function initSave(workspaceUser) {
    var saveBtn = document.getElementById('settings-save');
    var saveLabel = document.getElementById('save-label');
    if (!saveBtn || !saveLabel) return;
    var original = saveLabel.textContent;
    saveBtn.addEventListener('click', function () {
      var activeBtn = document.querySelector('.settings-nav-btn.active');
      var section = activeBtn ? activeBtn.getAttribute('data-section') : '';
      if (section === 'general' && workspaceUser && workspaceUser.url) {
        saveBtn.disabled = true;
        saveLabel.textContent = 'Saving…';
        saveBtn.classList.remove('settings-save--success');
        fetch(workspaceUser.url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfHeader(),
          },
          body: JSON.stringify(workspaceUser.collectBody()),
        })
          .then(function (r) {
            return r.json().then(function (data) {
              return { ok: r.ok, data: data };
            });
          })
          .then(function (res) {
            if (!res.ok || !res.data.ok) {
              showToast((res.data && res.data.error) || 'Save failed.');
              return;
            }
            if (res.data.profile) workspaceUser.applyProfile(res.data.profile);
            saveLabel.textContent = 'Saved';
            saveBtn.classList.add('settings-save--success');
            showToast('Profile saved.');
            window.setTimeout(function () {
              window.location.reload();
            }, 600);
          })
          .catch(function () {
            showToast('Network error.');
          })
          .then(function () {
            saveLabel.textContent = original;
            saveBtn.classList.remove('settings-save--success');
            saveBtn.disabled = false;
          });
        return;
      }
      saveBtn.disabled = true;
      saveLabel.textContent = 'Saving…';
      saveBtn.classList.remove('settings-save--success');
      window.setTimeout(function () {
        saveLabel.textContent = 'Saved';
        saveBtn.classList.add('settings-save--success');
        showToast('Settings saved.');
        window.setTimeout(function () {
          saveLabel.textContent = original;
          saveBtn.classList.remove('settings-save--success');
          saveBtn.disabled = false;
        }, 2000);
      }, 650);
    });
  }

  function initCopy() {
    document.querySelectorAll('[data-copy-target]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-copy-target');
        var el = id ? document.getElementById(id) : null;
        var text = el ? el.textContent.trim() : '';
        if (!text) return;
        var label = btn.textContent;
        function done() {
          btn.textContent = 'Copied';
          window.setTimeout(function () {
            btn.textContent = label;
          }, 1600);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(function () {
            showToast('Copy blocked — select the key manually.');
          });
        } else {
          showToast('Clipboard not available in this browser.');
        }
      });
    });
  }

  function initTheme() {
    var group = document.querySelector('.settings-theme-grid');
    if (!group) return;
    group.querySelectorAll('.settings-theme-option').forEach(function (opt) {
      opt.addEventListener('click', function () {
        group.querySelectorAll('.settings-theme-option').forEach(function (o) {
          o.classList.remove('is-selected');
          o.setAttribute('aria-pressed', 'false');
        });
        opt.classList.add('is-selected');
        opt.setAttribute('aria-pressed', 'true');
      });
    });
  }

  function initGenerateKey() {
    var b = document.getElementById('settings-generate-key');
    if (!b) return;
    b.addEventListener('click', function () {
      showToast('New keys are issued through your administrator or Data & privacy exports.');
    });
  }

  function csrfHeader() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') || '' : '';
  }

  function initOrganizationPanel() {
    var boot = document.getElementById('settings-company-boot');
    if (!boot) return;
    var url = boot.getAttribute('data-url');
    if (!url) return;
    var msg = document.getElementById('settings-company-msg');
    var saveBtn = document.getElementById('settings-company-save');
    var clearBtn = document.getElementById('settings-company-clear');
    var fields = {
      company_name: 'co-name',
      legal_name: 'co-legal',
      tagline: 'co-tagline',
      address: 'co-address',
      city: 'co-city',
      region: 'co-region',
      postal_code: 'co-postal',
      country: 'co-country',
      phone: 'co-phone',
      email: 'co-email',
      website: 'co-website',
      logo_url: 'co-logo',
    };

    function feedback(t, isErr) {
      if (!msg) return;
      msg.textContent = t || '';
      msg.style.color = isErr ? '#f87171' : '';
    }

    function applyProfile(p) {
      if (!p) return;
      Object.keys(fields).forEach(function (k) {
        var el = document.getElementById(fields[k]);
        if (el) el.value = p[k] != null ? String(p[k]) : '';
      });
    }

    function collectBody() {
      var o = {};
      Object.keys(fields).forEach(function (k) {
        var el = document.getElementById(fields[k]);
        o[k] = el && el.value != null ? String(el.value).trim() : '';
      });
      return o;
    }

    function load() {
      feedback('');
      fetch(url, { credentials: 'same-origin' })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data && data.ok && data.profile) applyProfile(data.profile);
        })
        .catch(function () {
          feedback('Could not load organization settings.', true);
        });
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        feedback('Saving…');
        saveBtn.disabled = true;
        fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfHeader(),
          },
          body: JSON.stringify(collectBody()),
        })
          .then(function (r) {
            return r.json().then(function (data) {
              return { ok: r.ok, data: data };
            });
          })
          .then(function (res) {
            if (!res.ok || !res.data.ok) {
              feedback((res.data && res.data.error) || 'Save failed.', true);
              return;
            }
            applyProfile(res.data.profile);
            feedback('Saved.');
            showToast('Organization branding saved.');
          })
          .catch(function () {
            feedback('Network error.', true);
          })
          .then(function () {
            saveBtn.disabled = false;
          });
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        feedback('Clearing…');
        clearBtn.disabled = true;
        fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfHeader(),
          },
          body: '{}',
        })
          .then(function (r) {
            return r.json().then(function (data) {
              return { ok: r.ok, data: data };
            });
          })
          .then(function (res) {
            if (!res.ok || !res.data.ok) {
              feedback((res.data && res.data.error) || 'Clear failed.', true);
              return;
            }
            applyProfile(res.data.profile);
            feedback('Cleared.');
            showToast('Organization branding cleared.');
          })
          .catch(function () {
            feedback('Network error.', true);
          })
          .then(function () {
            clearBtn.disabled = false;
          });
      });
    }

    load();
  }

  function initOllamaPanel() {
    var boot = document.getElementById('settings-ollama-boot');
    if (!boot) return;
    var saveUrl = boot.getAttribute('data-save-url');
    var healthUrl = boot.getAttribute('data-health-url');
    var modelsUrl = boot.getAttribute('data-models-url');
    var baseEl = document.getElementById('ollama-base-url');
    var modelEl = document.getElementById('ollama-model');
    var timeoutEl = document.getElementById('ollama-timeout');
    var fb = document.getElementById('ollama-feedback');
    var saveBtn = document.getElementById('ollama-save');
    var testBtn = document.getElementById('ollama-test');
    var resetEnvBtn = document.getElementById('ollama-reset');
    var refreshModelsBtn = document.getElementById('ollama-refresh-models');
    var modelsMeta = document.getElementById('ollama-models-meta');
    var modelsTableWrap = document.getElementById('ollama-models-table-wrap');
    var modelsTbody = document.getElementById('ollama-models-tbody');
    var modelDatalist = document.getElementById('ollama-model-datalist');
    var ollamaPanel = document.getElementById('settings-panel-ollama');
    var ollamaTab = document.getElementById('settings-tab-ollama');

    function feedback(msg) {
      if (fb) fb.textContent = msg || '';
    }

    function buildModelsQuery() {
      var base = baseEl ? baseEl.value.trim() : '';
      if (!modelsUrl) return '';
      var q = modelsUrl;
      if (base) q += (modelsUrl.indexOf('?') >= 0 ? '&' : '?') + 'base_url=' + encodeURIComponent(base);
      return q;
    }

    function setRefreshBusy(on) {
      if (refreshModelsBtn) {
        refreshModelsBtn.disabled = !!on;
        refreshModelsBtn.textContent = on ? 'Loading…' : 'Refresh models';
      }
    }

    function renderModelRows(models) {
      if (!modelsTbody || !modelsTableWrap) return;
      modelsTbody.textContent = '';
      if (!models || !models.length) {
        modelsTableWrap.classList.add('hidden');
        return;
      }
      modelsTableWrap.classList.remove('hidden');
      models.forEach(function (m) {
        var name = m.name || '';
        var tr = document.createElement('tr');
        var tdName = document.createElement('td');
        var tdSize = document.createElement('td');
        tdName.appendChild(document.createTextNode(name + ' '));
        var useBtn = document.createElement('button');
        useBtn.type = 'button';
        useBtn.className = 'btn btn-ghost btn-sm settings-ollama-model-pick';
        useBtn.textContent = 'Use';
        useBtn.setAttribute('data-model', name);
        useBtn.addEventListener('click', function () {
          if (modelEl) modelEl.value = name;
          feedback('Model set to ' + name + '. Save overrides to apply for Crew runs.');
        });
        tdName.appendChild(useBtn);
        tdSize.textContent = m.size_label || (m.size != null ? String(m.size) : '—');
        tr.appendChild(tdName);
        tr.appendChild(tdSize);
        modelsTbody.appendChild(tr);
      });
    }

    function fillDatalist(models) {
      if (!modelDatalist) return;
      modelDatalist.textContent = '';
      if (!models || !models.length) return;
      models.forEach(function (m) {
        var name = m.name || '';
        if (!name) return;
        var opt = document.createElement('option');
        opt.value = name;
        modelDatalist.appendChild(opt);
      });
    }

    function refreshModels(opts) {
      opts = opts || {};
      if (!modelsUrl) return;
      var q = buildModelsQuery();
      setRefreshBusy(true);
      if (modelsMeta && !opts.silent) modelsMeta.textContent = 'Fetching model list…';
      fetch(q, { credentials: 'same-origin' })
        .then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, data: data };
          });
        })
        .then(function (pack) {
          var data = pack.data || {};
          setRefreshBusy(false);
          if (!pack.ok && data.error) {
            if (modelsMeta) modelsMeta.textContent = '';
            renderModelRows([]);
            fillDatalist([]);
            if (!opts.silent) feedback('Models: ' + (data.error || 'request failed'));
            return;
          }
          if (!data.ok) {
            fillDatalist([]);
            renderModelRows([]);
            if (modelsMeta) modelsMeta.textContent = '';
            if (!opts.silent) feedback('Models: ' + (data.error || 'Could not list models'));
            return;
          }
          var list = data.models || [];
          fillDatalist(list);
          renderModelRows(list);
          var n = typeof data.count === 'number' ? data.count : list.length;
          var at = data.base_url || '';
          if (modelsMeta) {
            modelsMeta.textContent =
              n === 0
                ? 'No models reported at ' + at + '. Run `ollama pull <name>` on that host.'
                : n + ' model' + (n === 1 ? '' : 's') + ' at ' + at + '.';
          }
          if (!opts.silent && !opts.afterHealthOk) {
            feedback('Model list updated.');
          }
        })
        .catch(function () {
          setRefreshBusy(false);
          if (modelsMeta) modelsMeta.textContent = '';
          renderModelRows([]);
          fillDatalist([]);
          if (!opts.silent) feedback('Could not reach the app to list models.');
        });
    }

    function maybeRefreshModelsOnShow() {
      if (!ollamaPanel || ollamaPanel.classList.contains('hidden')) return;
      refreshModels({ silent: true });
    }

    if (ollamaTab) {
      ollamaTab.addEventListener('click', function () {
        window.setTimeout(maybeRefreshModelsOnShow, 0);
      });
    }
    if (ollamaPanel && !ollamaPanel.classList.contains('hidden')) {
      window.setTimeout(maybeRefreshModelsOnShow, 0);
    }

    if (refreshModelsBtn && modelsUrl) {
      refreshModelsBtn.addEventListener('click', function () {
        refreshModels({});
      });
    }

    if (saveBtn && saveUrl) {
      saveBtn.addEventListener('click', function () {
        feedback('Saving…');
        fetch(saveUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfHeader(),
          },
          body: JSON.stringify({
            base_url: baseEl ? baseEl.value : '',
            model: modelEl ? modelEl.value : '',
            timeout_sec: timeoutEl ? timeoutEl.value : '',
          }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (!data.ok) throw new Error(data.error || 'Save failed');
            showToast('Ollama settings saved.');
            feedback('Saved. Members page health check will use these values.');
            window.setTimeout(function () {
              window.location.reload();
            }, 600);
          })
          .catch(function (e) {
            feedback(e.message || 'Could not save.');
            showToast('Could not save Ollama settings.');
          });
      });
    }

    if (resetEnvBtn && saveUrl) {
      resetEnvBtn.addEventListener('click', function () {
        if (!window.confirm('Clear saved Ollama overrides and use server environment defaults?')) return;
        feedback('Resetting…');
        fetch(saveUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfHeader(),
          },
          body: JSON.stringify({ action: 'reset' }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (!data.ok) throw new Error(data.error || 'Reset failed');
            showToast('Reset to environment defaults.');
            window.location.reload();
          })
          .catch(function () {
            feedback('Reset failed.');
          });
      });
    }

    if (testBtn && healthUrl) {
      testBtn.addEventListener('click', function () {
        feedback('Testing…');
        fetch(healthUrl, { credentials: 'same-origin' })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (data.ok) {
              feedback('Reachable — model ' + (data.model || '') + ' @ ' + (data.ollama_url || ''));
              if (modelsUrl) refreshModels({ silent: true, afterHealthOk: true });
            } else {
              feedback(data.message || 'Not reachable.');
            }
          })
          .catch(function () {
            feedback('Health request failed.');
          });
      });
    }
  }

  function init() {
    var workspaceUser = initWorkspaceUserPanel();
    initTabs();
    initSessionRange();
    initSave(workspaceUser);
    initCopy();
    initTheme();
    initGenerateKey();
    initOrganizationPanel();
    initOllamaPanel();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
