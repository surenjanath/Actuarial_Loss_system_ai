(function () {
  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') || '' : '';
  }

  function readPipelineScript() {
    var el = document.getElementById('crew-pipeline-data');
    if (!el || !el.textContent) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return [];
    }
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify(body),
    });
  }

  var boot = document.getElementById('crew-personalization-boot');
  var modal = document.getElementById('crew-agent-modal');
  if (!boot || !modal) return;

  var pipelineUrl = boot.getAttribute('data-pipeline-url') || '';
  var resetUrl = boot.getAttribute('data-reset-url') || '';
  var modelsUrl = boot.getAttribute('data-models-url') || '';
  var pMin = parseInt(boot.getAttribute('data-pipeline-min') || '2', 10);
  var pMax = parseInt(boot.getAttribute('data-pipeline-max') || '16', 10);

  var form = document.getElementById('crew-agent-edit-form');
  var fieldId = document.getElementById('crew-edit-id');
  var fieldStep = document.getElementById('crew-edit-step-kind');
  var fieldLabel = document.getElementById('crew-edit-label');
  var fieldAvatar = document.getElementById('crew-edit-avatar');
  var fieldRole = document.getElementById('crew-edit-role');
  var fieldGoal = document.getElementById('crew-edit-goal');
  var fieldBackstory = document.getElementById('crew-edit-backstory');
  var fieldDept = document.getElementById('crew-edit-department');
  var fieldModel = document.getElementById('crew-edit-model');
  var titleEl = document.getElementById('crew-agent-edit-title');

  function reloadPage() {
    window.location.reload();
  }

  function openModal(agentId) {
    var pl = readPipelineScript();
    var row = pl.find(function (r) {
      return r.id === agentId;
    });
    if (!row) return;
    if (fieldId) fieldId.value = row.id || '';
    if (fieldStep) fieldStep.value = row.step_kind || 'generic';
    if (fieldLabel) fieldLabel.value = row.label || '';
    if (fieldAvatar) fieldAvatar.value = row.avatar || '';
    if (fieldRole) fieldRole.value = row.role || '';
    if (fieldGoal) fieldGoal.value = row.goal || '';
    if (fieldBackstory) fieldBackstory.value = row.backstory || '';
    if (fieldDept) fieldDept.value = row.department || '';
    if (fieldModel) fieldModel.value = row.ollama_model || '';
    if (titleEl) titleEl.textContent = 'Edit agent — ' + (row.role || '').slice(0, 40);
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  document.querySelectorAll('.crew-edit-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-agent-id');
      if (id) openModal(id);
    });
  });

  var closeBtn = document.getElementById('crew-agent-edit-close');
  if (closeBtn) closeBtn.addEventListener('click', closeModal);

  var cancelBtn = document.getElementById('crew-agent-cancel');
  if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

  modal.addEventListener('click', function (ev) {
    if (ev.target === modal) closeModal();
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
      closeModal();
    }
  });

  if (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var pl = readPipelineScript();
      var eid = fieldId ? fieldId.value : '';
      var updated = pl.map(function (r) {
        if (r.id !== eid) return r;
        return {
          id: r.id,
          step_kind: fieldStep ? fieldStep.value : 'generic',
          label: fieldLabel ? fieldLabel.value.trim() : '',
          avatar: fieldAvatar ? fieldAvatar.value.trim() : '',
          role: fieldRole ? fieldRole.value.trim() : '',
          goal: fieldGoal ? fieldGoal.value.trim() : '',
          backstory: fieldBackstory ? fieldBackstory.value.trim() : '',
          department: fieldDept ? fieldDept.value.trim() : '',
          ollama_model: fieldModel ? fieldModel.value.trim() : '',
        };
      });
      postJson(pipelineUrl, { action: 'set_pipeline', pipeline: updated })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'save failed');
          reloadPage();
        })
        .catch(function () {
          alert('Could not save agent.');
        });
    });
  }

  document.querySelectorAll('.crew-delete-btn').forEach(function (btn) {
    if (btn.disabled) return;
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-agent-id');
      if (!id || !confirm('Remove this agent from the pipeline?')) return;
      postJson(pipelineUrl, { action: 'delete_agent', id: id })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'delete failed');
          reloadPage();
        })
        .catch(function (e) {
          alert(e.message || 'Could not delete.');
        });
    });
  });

  var addBtn = document.getElementById('crew-add-agent');
  if (addBtn) {
    addBtn.addEventListener('click', function () {
      var pl = readPipelineScript();
      if (pl.length >= pMax) {
        alert('Maximum ' + pMax + ' agents.');
        return;
      }
      postJson(pipelineUrl, { action: 'add_agent' })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'add failed');
          reloadPage();
        })
        .catch(function (e) {
          alert(e.message || 'Could not add agent.');
        });
    });
  }

  var resetPipe = document.getElementById('crew-reset-pipeline');
  if (resetPipe) {
    resetPipe.addEventListener('click', function () {
      if (!confirm('Reset crew agents to built-in defaults?')) return;
      postJson(pipelineUrl, { action: 'reset_defaults' })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error('reset failed');
          reloadPage();
        })
        .catch(function () {
          alert('Could not reset pipeline.');
        });
    });
  }

  var resetAll = document.getElementById('reset-all-personalization');
  if (resetAll && resetUrl) {
    resetAll.addEventListener('click', function () {
      if (!confirm('Reset crew instructions and crew agent configuration to defaults?')) return;
      postJson(resetUrl, {})
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error('reset failed');
          reloadPage();
        })
        .catch(function () {
          alert('Could not reset.');
        });
    });
  }

  if (modelsUrl) {
    fetch(modelsUrl, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var dl = document.getElementById('crew-ollama-models');
        if (!dl || !data.models) return;
        data.models.forEach(function (m) {
          var name = typeof m === 'string' ? m : m && m.name ? m.name : '';
          if (!name) return;
          var opt = document.createElement('option');
          opt.value = name;
          dl.appendChild(opt);
        });
      })
      .catch(function () {});
  }
})();
