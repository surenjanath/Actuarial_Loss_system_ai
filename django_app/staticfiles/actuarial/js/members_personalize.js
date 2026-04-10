(function () {
  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') || '' : '';
  }

  var boot = document.getElementById('member-personalization-boot');
  var editDataEl = document.getElementById('member-edit-data');
  var modal = document.getElementById('member-edit-modal');
  if (!boot || !modal) return;

  var customizeUrl = boot.getAttribute('data-customize-url') || '';
  var resetUrl = boot.getAttribute('data-reset-url') || '';

  var editData = {};
  try {
    editData = editDataEl ? JSON.parse(editDataEl.textContent || '{}') : {};
  } catch (e) {
    editData = {};
  }

  var form = document.getElementById('member-edit-form');
  var fieldId = document.getElementById('edit-member-id');
  var fieldName = document.getElementById('edit-name');
  var fieldAvatar = document.getElementById('edit-avatar');
  var fieldRole = document.getElementById('edit-role');
  var fieldDept = document.getElementById('edit-department');
  var fieldSpec = document.getElementById('edit-specialization');
  var fieldNotes = document.getElementById('edit-notes');
  var fieldAi = document.getElementById('edit-ai-instructions');
  var titleEl = document.getElementById('member-edit-title');

  function openModal(memberId) {
    var d = editData[memberId] || {};
    fieldId.value = memberId;
    if (fieldName) fieldName.value = d.name || '';
    if (fieldAvatar) fieldAvatar.value = d.avatar || '';
    if (fieldRole) fieldRole.value = d.role || '';
    if (fieldDept) fieldDept.value = d.department || '';
    if (fieldSpec) fieldSpec.value = d.specialization || '';
    if (fieldNotes) fieldNotes.value = d.notes || '';
    if (fieldAi) fieldAi.value = d.ai_instructions || '';
    if (titleEl) {
      titleEl.textContent = 'Personalize — ' + (d.name || 'Member');
    }
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
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

  document.querySelectorAll('.member-edit-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-member-id');
      if (id) openModal(id);
    });
  });

  var closeBtn = document.getElementById('member-edit-close');
  if (closeBtn) closeBtn.addEventListener('click', closeModal);

  modal.addEventListener('click', function (ev) {
    if (ev.target === modal) closeModal();
  });
  var dialog = modal.querySelector('.member-modal-dialog');
  if (dialog) {
    dialog.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }

  if (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var id = fieldId.value;
      if (!id) return;
      var payload = {
        id: id,
        name: fieldName ? fieldName.value : '',
        role: fieldRole ? fieldRole.value : '',
        department: fieldDept ? fieldDept.value : '',
        avatar: fieldAvatar ? fieldAvatar.value : '',
        specialization: fieldSpec ? fieldSpec.value : '',
        notes: fieldNotes ? fieldNotes.value : '',
        ai_instructions: fieldAi ? fieldAi.value : '',
      };
      postJson(customizeUrl, payload)
        .then(function (r) {
          if (!r.ok) throw new Error('Save failed');
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'Save failed');
          window.location.reload();
        })
        .catch(function () {
          alert('Could not save personalization. Check your session and try again.');
        });
    });
  }

  var revertBtn = document.getElementById('member-edit-revert');
  if (revertBtn) {
    revertBtn.addEventListener('click', function () {
      var id = fieldId.value;
      if (!id || !window.confirm('Revert this member to default roster values?')) return;
      postJson(customizeUrl, { action: 'clear_member', id: id })
        .then(function (r) {
          if (!r.ok) throw new Error('Revert failed');
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'Revert failed');
          window.location.reload();
        })
        .catch(function () {
          alert('Could not revert member.');
        });
    });
  }

  var resetAll = document.getElementById('reset-all-personalization');
  if (resetAll) {
    resetAll.addEventListener('click', function () {
      if (!window.confirm('Clear all personalized names, crew instructions, and AI notes for this session?')) return;
      postJson(resetUrl, {})
        .then(function (r) {
          if (!r.ok) throw new Error('Reset failed');
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'Reset failed');
          window.location.reload();
        })
        .catch(function () {
          alert('Could not reset personalization.');
        });
    });
  }
})();
