(function () {
  const panel = document.getElementById('crew-analysis-panel');
  if (!panel) return;

  const statusEl = document.getElementById('crew-status-pill');
  const healthMsg = document.getElementById('crew-health-msg');
  const logEl = document.getElementById('crew-log');
  const summaryEl = document.getElementById('crew-summary');
  const topicInput = document.getElementById('crew-topic');
  const startBtn = document.getElementById('crew-start');
  const stopBtn = document.getElementById('crew-stop');
  const vizWrap = document.getElementById('crew-viz-wrap');
  const liveDocsWrap = document.getElementById('crew-live-docs');
  const boardModel = document.getElementById('crew-board-model');
  const elapsedEl = document.getElementById('crew-elapsed');
  const activityLogEl = document.getElementById('crew-activity-log');
  const copyBtn = document.getElementById('crew-log-copy');
  const downloadBtn = document.getElementById('crew-log-download');
  const unifiedDocEl = document.getElementById('crew-live-doc-unified');
  const auditedWrap = document.getElementById('crew-audited-wrap');
  const auditedReportEl = document.getElementById('crew-audited-report');
  const approvalPill = document.getElementById('crew-approval-pill');
  const approveBtn = document.getElementById('crew-approve-btn');
  const approvalMsg = document.getElementById('crew-approval-msg');
  const memberFocusEl = document.getElementById('crew-member-focus');
  const boardReportWrap = document.getElementById('crew-board-report-wrap');
  const boardReportLive = document.getElementById('crew-board-report-live');
  const boardReportLabel = document.getElementById('crew-board-report-live-label');
  const boardOpenEl = document.getElementById('crew-board-open');
  const workflowHandoffWrap = document.getElementById('crew-workflow-handoff-wrap');
  const workflowHandoffMsg = document.getElementById('crew-workflow-handoff-msg');
  const workflowHandoffSnippet = document.getElementById('crew-workflow-handoff-snippet');
  const workflowPrefillBtn = document.getElementById('crew-workflow-prefill-topic');
  const pastRunsList = document.getElementById('crew-past-runs-list');
  const pastRunsRefresh = document.getElementById('crew-past-runs-refresh');
  const reviewBanner = document.getElementById('crew-review-banner');
  const pdfDownload = document.getElementById('crew-pdf-download');

  /** CrewAI stream chunks often report task_index 0 for every token; we route by server task_transition instead. */
  let activeStreamTaskIdx = -1;
  let currentRunId = null;

  let lastTaskIdx = -1;
  let chunkCounter = 0;
  let elapsedTimer = null;
  let runStartedAt = 0;
  let exportLines = [];

  const streamBase = panel.dataset.streamUrl || '';
  const healthUrl = panel.dataset.healthUrl || '';
  const saveInstructionsUrl = panel.dataset.saveInstructionsUrl || '';
  const runLatestUrl = panel.dataset.runLatestUrl || '';
  const runListUrl = panel.dataset.runListUrl || '';
  const featureEnabled = panel.dataset.enabled === 'true';
  const globalInstructionsEl = document.getElementById('crew-global-instructions');

  const CHUNK_ACTIVITY_EVERY = 25;

  /** In-memory stream buffers — updating DOM with textContent+= each token freezes the tab (quadratic reflow). */
  let streamBufLog = '';
  let streamBufUnified = '';
  let streamBufDocs = {};
  let streamFlushScheduled = false;

  function resetStreamBuffers() {
    streamBufLog = '';
    streamBufUnified = '';
    streamBufDocs = {};
    streamFlushScheduled = false;
  }

  function flushStreamBuffersSync() {
    streamFlushScheduled = false;
    if (logEl) {
      logEl.textContent = streamBufLog;
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (unifiedDocEl) {
      unifiedDocEl.textContent = streamBufUnified;
      unifiedDocEl.scrollTop = unifiedDocEl.scrollHeight;
    }
    Object.keys(streamBufDocs).forEach(function (idx) {
      var card = document.querySelector('.crew-doc-card[data-task-idx="' + idx + '"]');
      if (!card) return;
      var doc = card.querySelector('[data-field="doc"]');
      if (doc) {
        doc.textContent = streamBufDocs[idx] || '';
        doc.scrollTop = doc.scrollHeight;
      }
    });
  }

  function scheduleStreamFlush() {
    if (streamFlushScheduled) return;
    streamFlushScheduled = true;
    requestAnimationFrame(function () {
      streamFlushScheduled = false;
      flushStreamBuffersSync();
    });
  }

  function csrfToken() {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') || '' : '';
  }

  let es = null;
  let streamCompleted = false;

  function setStatus(text, tone) {
    statusEl.textContent = text;
    statusEl.style.color = '#e5e7eb';
    statusEl.style.background = 'rgba(55,65,81,0.6)';
    if (tone === 'run') {
      statusEl.style.background = 'rgba(42,200,235,0.15)';
      statusEl.style.color = '#2ac8eb';
    } else if (tone === 'ok') {
      statusEl.style.background = 'rgba(74,222,128,0.12)';
      statusEl.style.color = '#4ade80';
    } else if (tone === 'err') {
      statusEl.style.background = 'rgba(248,113,113,0.12)';
      statusEl.style.color = '#f87171';
    }
  }

  function formatElapsed(ms) {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m + ':' + (sec < 10 ? '0' : '') + sec;
  }

  function startElapsedTimer() {
    stopElapsedTimer();
    runStartedAt = Date.now();
    if (elapsedEl) elapsedEl.textContent = '0:00';
    elapsedTimer = window.setInterval(function () {
      if (elapsedEl) elapsedEl.textContent = formatElapsed(Date.now() - runStartedAt);
    }, 500);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      window.clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function appendExportLine(line) {
    exportLines.push(line);
  }

  function appendLog(line) {
    streamBufLog += (streamBufLog ? '\n' : '') + line;
    scheduleStreamFlush();
  }

  function appendActivity(line, ts) {
    if (!activityLogEl) return;
    const row = document.createElement('div');
    row.className = 'crew-activity-row';
    const t = document.createElement('span');
    t.className = 'crew-ts';
    t.textContent = ts || '';
    const msg = document.createElement('span');
    msg.className = 'crew-activity-msg';
    msg.textContent = line;
    row.appendChild(t);
    row.appendChild(msg);
    activityLogEl.appendChild(row);
    activityLogEl.scrollTop = activityLogEl.scrollHeight;
    appendExportLine((ts ? '[' + ts + '] ' : '') + line);
  }

  function resetViz() {
    lastTaskIdx = -1;
    chunkCounter = 0;
    exportLines = [];
    stopElapsedTimer();
    resetStreamBuffers();
    if (vizWrap) vizWrap.classList.add('hidden');
    if (liveDocsWrap) liveDocsWrap.classList.add('hidden');
    if (boardModel) boardModel.textContent = '';
    if (activityLogEl) activityLogEl.textContent = '';
    if (copyBtn) copyBtn.disabled = true;
    if (downloadBtn) downloadBtn.disabled = true;

    document.querySelectorAll('.crew-org-node').forEach(function (node) {
      node.classList.remove('is-active', 'is-done', 'is-idle');
      node.classList.add('is-idle');
      const st = node.querySelector('[data-field="state"]');
      if (st) st.textContent = '—';
    });

    document.querySelectorAll('.crew-doc-card').forEach(function (card) {
      card.classList.remove('is-active', 'is-done');
      const doc = card.querySelector('[data-field="doc"]');
      const badge = card.querySelector('[data-field="badge"]');
      const ts = card.querySelector('[data-field="ts"]');
      if (doc) doc.textContent = '';
      if (badge) badge.textContent = '—';
      if (ts) ts.textContent = '';
    });
    activeStreamTaskIdx = -1;
    if (unifiedDocEl) unifiedDocEl.textContent = '';
    currentRunId = null;
    if (auditedWrap) auditedWrap.classList.add('hidden');
    if (auditedReportEl) auditedReportEl.textContent = '';
    if (approvalPill) {
      approvalPill.textContent = '—';
      approvalPill.style.color = '#9ca3af';
      approvalPill.style.background = 'rgba(55,65,81,0.6)';
    }
    if (approveBtn) approveBtn.disabled = true;
    if (approvalMsg) approvalMsg.textContent = '';
    if (boardReportLive) boardReportLive.textContent = '';
    if (boardOpenEl) {
      boardOpenEl.classList.add('hidden');
      boardOpenEl.removeAttribute('href');
    }
    if (boardReportWrap) boardReportWrap.classList.add('hidden');
    if (workflowHandoffWrap) workflowHandoffWrap.classList.add('hidden');
    if (workflowHandoffMsg) workflowHandoffMsg.textContent = '';
    if (workflowHandoffSnippet) workflowHandoffSnippet.textContent = '';
    if (workflowPrefillBtn) {
      workflowPrefillBtn.dataset.prefillTopic = '';
      workflowPrefillBtn.dataset.fallbackSnippet = '';
      workflowPrefillBtn.disabled = true;
    }
    if (reviewBanner) reviewBanner.classList.add('hidden');
    if (pdfDownload) pdfDownload.classList.add('hidden');
    document.querySelectorAll('.crew-past-run-row').forEach(function (el) {
      el.classList.remove('crew-past-run-row--active');
    });
  }

  function showViz() {
    if (vizWrap) vizWrap.classList.remove('hidden');
    if (liveDocsWrap) liveDocsWrap.classList.remove('hidden');
    if (boardReportWrap) boardReportWrap.classList.remove('hidden');
    if (boardReportLive && !boardReportLive.textContent) {
      boardReportLive.textContent =
        '(Waiting for initial report, executive, revision, or audited report steps — the shared board report will stream here.)';
    }
  }

  function applyWorkflowHandoff(wh) {
    if (!workflowHandoffWrap || !workflowHandoffMsg || !workflowHandoffSnippet) return;
    if (!wh || !wh.needs_rework) {
      workflowHandoffWrap.classList.add('hidden');
      workflowHandoffMsg.textContent = '';
      workflowHandoffSnippet.textContent = '';
      if (workflowPrefillBtn) {
        workflowPrefillBtn.dataset.prefillTopic = '';
        workflowPrefillBtn.dataset.fallbackSnippet = '';
        workflowPrefillBtn.disabled = true;
      }
      return;
    }
    workflowHandoffWrap.classList.remove('hidden');
    var src = wh.source_step_kind ? String(wh.source_step_kind) : '';
    workflowHandoffMsg.textContent =
      'A prior step suggests rework before you rely on this run.' + (src ? ' (source: ' + src + ')' : '');
    var snip = (wh.snippet || '').trim();
    workflowHandoffSnippet.textContent = snip;
    var topic = wh.prefill_topic ? String(wh.prefill_topic).trim() : '';
    if (workflowPrefillBtn) {
      workflowPrefillBtn.dataset.prefillTopic = topic;
      var fb = '';
      if (!topic && snip) {
        fb = snip.replace(/\s+/g, ' ').trim().slice(0, 480);
      }
      workflowPrefillBtn.dataset.fallbackSnippet = fb;
      workflowPrefillBtn.disabled = !(topic || fb);
    }
  }

  function crewRunDetailUrl(runId) {
    return '/api/crew/runs/' + encodeURIComponent(runId) + '/';
  }

  function crewRunDeleteUrl(runId) {
    return '/api/crew/runs/' + encodeURIComponent(runId) + '/delete/';
  }

  function clearAuditedIfShowingRun(runId) {
    if (String(currentRunId) !== String(runId)) return;
    currentRunId = null;
    if (auditedWrap) auditedWrap.classList.add('hidden');
    if (auditedReportEl) auditedReportEl.textContent = '';
    if (approvalPill) {
      approvalPill.textContent = '—';
      approvalPill.style.color = '#9ca3af';
      approvalPill.style.background = 'rgba(55,65,81,0.6)';
    }
    if (approveBtn) approveBtn.disabled = true;
    if (approvalMsg) approvalMsg.textContent = '';
    if (pdfDownload) pdfDownload.classList.add('hidden');
    if (reviewBanner) reviewBanner.classList.add('hidden');
    if (boardOpenEl) {
      boardOpenEl.classList.add('hidden');
      boardOpenEl.removeAttribute('href');
    }
  }

  function deleteRun(runId) {
    if (!window.confirm('Delete this run permanently? Step outputs and PDFs will be removed.')) return;
    fetch(crewRunDeleteUrl(runId), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: '{}',
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, json: j };
        });
      })
      .then(function (x) {
        if (!x.ok || !x.json.ok) {
          window.alert(x.json && x.json.error ? x.json.error : 'Could not delete run.');
          return;
        }
        clearAuditedIfShowingRun(runId);
        loadRunList();
      })
      .catch(function () {
        window.alert('Could not delete run.');
      });
  }

  function updateReviewBanner(status) {
    if (!reviewBanner) return;
    if (status === 'pending_approval') reviewBanner.classList.remove('hidden');
    else reviewBanner.classList.add('hidden');
  }

  function updatePdfLink(run) {
    if (!pdfDownload) return;
    if (run && run.status === 'approved' && run.has_approved_pdf) {
      pdfDownload.href = '/api/crew/runs/' + encodeURIComponent(run.id) + '/pdf/';
      pdfDownload.classList.remove('hidden');
    } else {
      pdfDownload.classList.add('hidden');
    }
  }

  function highlightPastRunRow(runId) {
    var s = runId != null ? String(runId) : '';
    document.querySelectorAll('.crew-past-run-row').forEach(function (el) {
      var on = el.dataset.runId === s;
      el.classList.toggle('crew-past-run-row--active', on);
      if (on) {
        el.style.borderColor = 'rgba(42,200,235,0.65)';
        el.style.background = 'rgba(42,200,235,0.12)';
      } else {
        el.style.borderColor = 'rgba(55,65,81,0.7)';
        el.style.background = 'rgba(31,41,55,0.55)';
      }
    });
  }

  function applyRunToAuditedPanel(run, opts) {
    opts = opts || {};
    if (!run) return;
    var text = run.final_report_text || '';
    if (run.status === 'failed' && run.error_message && !String(text).trim()) {
      text = run.error_message;
    }
    if (!String(text).trim() && run.status !== 'running') {
      text = '(No report body.)';
    }
    if (auditedWrap) auditedWrap.classList.remove('hidden');
    if (auditedReportEl) auditedReportEl.textContent = text;
    currentRunId = run.id;

    if (approvalPill) {
      if (run.status === 'pending_approval') {
        approvalPill.textContent = 'Pending your approval';
        approvalPill.style.color = '#fbbf24';
        approvalPill.style.background = 'rgba(251,191,36,0.12)';
      } else if (run.status === 'approved') {
        approvalPill.textContent = 'Approved';
        approvalPill.style.color = '#4ade80';
        approvalPill.style.background = 'rgba(74,222,128,0.12)';
      } else if (run.status === 'failed') {
        approvalPill.textContent = 'Failed';
        approvalPill.style.color = '#f87171';
        approvalPill.style.background = 'rgba(248,113,113,0.12)';
      } else if (run.status === 'running') {
        approvalPill.textContent = 'Running';
        approvalPill.style.color = '#2ac8eb';
        approvalPill.style.background = 'rgba(42,200,235,0.12)';
      } else {
        approvalPill.textContent = run.status || '—';
        approvalPill.style.color = '#9ca3af';
        approvalPill.style.background = 'rgba(55,65,81,0.6)';
      }
    }

    if (approveBtn) {
      approveBtn.disabled = !(run.status === 'pending_approval' && currentRunId);
    }

    if (approvalMsg && !opts.suppressMsg) {
      if (run.status === 'pending_approval') {
        approvalMsg.textContent =
          'Review the audited report above, then approve to generate the locked PDF.';
      } else if (run.status === 'approved') {
        approvalMsg.textContent = 'Approved — you can download the PDF.';
      } else {
        approvalMsg.textContent = '';
      }
    }

    updateReviewBanner(run.status);
    updatePdfLink(run);

    if (run.workflow_handoff) {
      applyWorkflowHandoff(run.workflow_handoff);
    } else {
      applyWorkflowHandoff({});
    }

    if (run.id) highlightPastRunRow(String(run.id));
  }

  function loadRunList() {
    if (!runListUrl || !pastRunsList) return;
    var mid =
      memberFocusEl && memberFocusEl.value ? String(memberFocusEl.value).trim() : '';
    var u = runListUrl + (mid ? '?member_id=' + encodeURIComponent(mid) : '');
    fetch(u, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.ok || !data.runs) return;
        pastRunsList.textContent = '';
        if (!data.runs.length) {
          pastRunsList.textContent = 'No runs yet for this filter.';
          return;
        }
        data.runs.forEach(function (run) {
          var wrap = document.createElement('div');
          wrap.style.cssText =
            'display:flex;gap:0.35rem;align-items:stretch;margin-bottom:0.35rem;width:100%;';
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'crew-past-run-row';
          btn.dataset.runId = run.id;
          btn.style.cssText =
            'flex:1;min-width:0;text-align:left;padding:0.4rem 0.55rem;border-radius:4px;border:1px solid rgba(55,65,81,0.7);cursor:pointer;background:rgba(31,41,55,0.55);color:#e5e7eb;font-size:12px;';
          var topic = (run.topic || '').trim();
          if (topic.length > 80) topic = topic.slice(0, 78) + '…';
          var when = run.created_at || '';
          btn.textContent = when + ' · ' + (run.status || '') + (topic ? ' · ' + topic : '');
          btn.addEventListener('click', function () {
            loadRunDetail(run.id);
          });
          var delBtn = document.createElement('button');
          delBtn.type = 'button';
          delBtn.className = 'crew-past-run-delete';
          delBtn.setAttribute('aria-label', 'Delete run');
          delBtn.title = 'Delete run';
          delBtn.style.cssText =
            'flex-shrink:0;width:2rem;padding:0;border-radius:4px;border:1px solid rgba(127,29,29,0.5);cursor:pointer;background:rgba(127,29,29,0.2);color:#fca5a5;font-size:14px;line-height:1;';
          delBtn.textContent = '×';
          delBtn.addEventListener('click', function (ev) {
            ev.stopPropagation();
            ev.preventDefault();
            deleteRun(run.id);
          });
          wrap.appendChild(btn);
          wrap.appendChild(delBtn);
          pastRunsList.appendChild(wrap);
        });
        if (currentRunId) highlightPastRunRow(String(currentRunId));
      })
      .catch(function () {});
  }

  function loadRunDetail(runId) {
    fetch(crewRunDetailUrl(runId), { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.ok || !data.run) return;
        applyRunToAuditedPanel(data.run, {});
      })
      .catch(function () {});
  }

  function refreshBoardDisplayLink(runId) {
    if (!runId || !boardOpenEl) return;
    fetch('/api/crew/runs/' + encodeURIComponent(runId) + '/', {
      credentials: 'same-origin',
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.board_url && boardOpenEl) {
          boardOpenEl.href = data.board_url;
          boardOpenEl.classList.remove('hidden');
        }
      })
      .catch(function () {});
  }

  function onReportDraft(payload) {
    if (boardReportLive) {
      boardReportLive.textContent = payload.content || '';
      boardReportLive.scrollTop = boardReportLive.scrollHeight;
    }
    if (boardReportLabel) {
      var phase = payload.phase === 'step_end' ? 'Step complete' : 'Streaming';
      boardReportLabel.textContent =
        phase +
        ' · ' +
        (payload.label || 'Task') +
        (payload.role ? ' — ' + payload.role : '') +
        (payload.step_kind ? ' · ' + payload.step_kind : '');
    }
    if (boardReportWrap) boardReportWrap.classList.remove('hidden');
    appendActivity(
      'Board report updated' +
        (payload.task_index != null ? ' (task ' + payload.task_index + ')' : ''),
      payload.ts || ''
    );
  }

  function setPipelineAllQueued() {
    document.querySelectorAll('.crew-org-node').forEach(function (node, i) {
      node.classList.remove('is-active', 'is-done');
      node.classList.add('is-idle');
      const st = node.querySelector('[data-field="state"]');
      if (st) st.textContent = i === 0 ? 'Next' : 'Queued';
    });
  }

  function onRunStart(payload) {
    showViz();
    if (copyBtn) copyBtn.disabled = false;
    if (downloadBtn) downloadBtn.disabled = false;
    if (boardModel && payload.model) {
      boardModel.textContent = payload.model;
    }
    setPipelineAllQueued();
    appendActivity('Run started (model: ' + (payload.model || '') + ')', payload.ts || '');
    if (payload.agents && payload.agents.length) {
      payload.agents.forEach(function (a) {
        const n = document.querySelector('.crew-org-node[data-task-idx="' + a.task_index + '"]');
        if (n && a.label) {
          const lab = n.querySelector('.crew-org-label');
          if (lab) lab.textContent = a.label;
          const role = n.querySelector('.crew-org-role');
          if (role && a.role) {
            role.textContent = a.role.length > 42 ? a.role.slice(0, 40) + '…' : a.role;
          }
        }
      });
    }
  }

  function setDocBadge(idx, text) {
    const card = document.querySelector('.crew-doc-card[data-task-idx="' + idx + '"]');
    if (!card) return;
    const badge = card.querySelector('[data-field="badge"]');
    if (badge) badge.textContent = text;
  }

  function setDocTs(idx, ts) {
    const card = document.querySelector('.crew-doc-card[data-task-idx="' + idx + '"]');
    if (!card) return;
    const el = card.querySelector('[data-field="ts"]');
    if (el && ts) el.textContent = ts;
  }

  function onTaskTransition(payload) {
    const idx = payload.task_index;
    const phase = payload.phase;
    const label = payload.label || 'Task ' + idx;
    const ts = payload.ts || '';

    if (phase === 'start') {
      activeStreamTaskIdx = idx;
      {
        const sep = streamBufUnified ? '\n\n' : '';
        streamBufUnified +=
          sep + '── ' + label + (payload.role ? ' — ' + payload.role : '') + ' ──\n\n';
        scheduleStreamFlush();
      }
      appendActivity('→ ' + label + ' — started (' + (payload.role || '') + ')', ts);
      document.querySelectorAll('.crew-org-node').forEach(function (n) {
        const i = parseInt(n.getAttribute('data-task-idx'), 10);
        const st = n.querySelector('[data-field="state"]');
        n.classList.remove('is-active', 'is-done', 'is-idle');
        if (i < idx) {
          n.classList.add('is-done');
          if (st) st.textContent = 'Done';
        } else if (i === idx) {
          n.classList.add('is-active');
          if (st) st.textContent = 'Writing…';
        } else {
          n.classList.add('is-idle');
          if (st) st.textContent = 'Queued';
        }
      });
      document.querySelectorAll('.crew-doc-card').forEach(function (card) {
        const i = parseInt(card.getAttribute('data-task-idx'), 10);
        card.classList.remove('is-active', 'is-done');
        if (i < idx) card.classList.add('is-done');
        else if (i === idx) {
          card.classList.add('is-active');
          setDocBadge(i, 'Writing…');
          setDocTs(i, ts);
        } else {
          setDocBadge(i, 'Queued');
        }
      });
    } else if (phase === 'end') {
      appendActivity('← ' + label + ' — finished', ts);
      const node = document.querySelector('.crew-org-node[data-task-idx="' + idx + '"]');
      if (node) {
        node.classList.remove('is-active');
        node.classList.add('is-done');
        const st = node.querySelector('[data-field="state"]');
        if (st) st.textContent = 'Done';
      }
      const card = document.querySelector('.crew-doc-card[data-task-idx="' + idx + '"]');
      if (card) {
        card.classList.remove('is-active');
        card.classList.add('is-done');
        setDocBadge(idx, 'Done');
      }
    }
  }

  function onChunk(payload) {
    const rawIdx =
      typeof payload.task_index === 'number' ? payload.task_index : parseInt(payload.task_index, 10) || 0;
    const routeIdx = activeStreamTaskIdx >= 0 ? activeStreamTaskIdx : rawIdx;
    if (rawIdx !== lastTaskIdx) {
      lastTaskIdx = rawIdx;
    }
    const bit = payload.content || '';
    if (bit) {
      streamBufDocs[routeIdx] = (streamBufDocs[routeIdx] || '') + bit;
      streamBufUnified += bit;
      const role = payload.agent_role || '';
      streamBufLog += (streamBufLog ? '\n' : '') + (role ? '[' + role + '] ' : '') + bit;
      scheduleStreamFlush();
    }

    chunkCounter += 1;
    if (
      payload.chunk_type === 'tool_call' ||
      (payload.tool_name && String(payload.tool_name).length > 0)
    ) {
      const tn = payload.tool_name || 'tool';
      const prev = payload.tool_arguments_preview || '';
      appendActivity('Tool: ' + tn + (prev ? ' — ' + prev.slice(0, 160) : ''), payload.ts || '');
    } else if (bit && chunkCounter % CHUNK_ACTIVITY_EVERY === 0) {
      const preview = bit.replace(/\s+/g, ' ').trim().slice(0, 120);
      appendActivity(
        '[chunk #' + chunkCounter + ' stream_task ' + routeIdx + '] ' + preview + (bit.length > 120 ? '…' : ''),
        payload.ts || ''
      );
    }
  }

  function onRunComplete() {
    document.querySelectorAll('.crew-org-node').forEach(function (node) {
      node.classList.remove('is-active', 'is-idle');
      node.classList.add('is-done');
      const st = node.querySelector('[data-field="state"]');
      if (st) st.textContent = 'Done';
    });
    document.querySelectorAll('.crew-doc-card').forEach(function (card) {
      card.classList.remove('is-active');
      card.classList.add('is-done');
      const idx = parseInt(card.getAttribute('data-task-idx'), 10);
      setDocBadge(idx, 'Done');
    });
  }

  function buildExportText() {
    flushStreamBuffersSync();
    const parts = [];
    parts.push('=== Crew activity ===');
    parts.push(exportLines.join('\n'));
    parts.push('');
    parts.push('=== Audited report (deliverable) ===');
    parts.push(auditedReportEl ? auditedReportEl.textContent : '');
    parts.push('');
    parts.push('=== Board report (live panel) ===');
    parts.push(boardReportLive ? boardReportLive.textContent : '');
    parts.push('');
    parts.push('=== Full transcript (all tasks) ===');
    parts.push(streamBufUnified || (unifiedDocEl ? unifiedDocEl.textContent : ''));
    parts.push('');
    parts.push('=== Raw stream ===');
    parts.push(streamBufLog || (logEl ? logEl.textContent : ''));
    parts.push('');
    parts.push('=== Crew chain summary (raw) ===');
    parts.push(summaryEl ? summaryEl.textContent : '');
    return parts.join('\n');
  }

  function closeStream() {
    stopElapsedTimer();
    if (es) {
      es.close();
      es = null;
    }
    stopBtn.disabled = true;
    startBtn.disabled = false;
  }

  function checkHealth() {
    if (!featureEnabled) {
      healthMsg.textContent = 'Crew analysis is disabled on the server (CREW_ANALYSIS_ENABLED).';
      startBtn.disabled = true;
      setStatus('Disabled', 'err');
      return;
    }
    setStatus('Connecting', 'run');
    healthMsg.textContent = '';
    fetch(healthUrl, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.enabled) {
          healthMsg.textContent = data.message || 'Feature disabled.';
          startBtn.disabled = true;
          setStatus('Disabled', 'err');
          return;
        }
        if (!data.ok) {
          healthMsg.textContent =
            data.message || 'Ollama not reachable. Check Settings → Local LLM or run `ollama serve`.';
          startBtn.disabled = true;
          setStatus('Offline', 'err');
          return;
        }
        var extra = data.session_override ? ' (saved overrides)' : '';
        healthMsg.textContent =
          'Ollama OK — ' + (data.model || '') + ' @ ' + (data.ollama_url || '') + extra + '.';
        startBtn.disabled = false;
        setStatus('Idle', null);
      })
      .catch(function () {
        healthMsg.textContent = 'Could not reach health endpoint.';
        startBtn.disabled = true;
        setStatus('Error', 'err');
      });
  }

  function openEventSource(topic) {
    let url = streamBase;
    const params = new URLSearchParams();
    if (topic) params.set('topic', topic);
    const mid =
      memberFocusEl && memberFocusEl.value ? String(memberFocusEl.value).trim() : '';
    if (mid) params.set('member_id', mid);
    const qs = params.toString();
    url += qs ? '?' + qs : '';

    if (logEl) logEl.textContent = '';
    summaryEl.textContent = '';
    streamCompleted = false;
    resetViz();
    showViz();
    startElapsedTimer();
    chunkCounter = 0;
    lastTaskIdx = -1;
    setStatus('Running', 'run');
    startBtn.disabled = true;
    stopBtn.disabled = false;

    es = new EventSource(url);

    es.onmessage = function (ev) {
      let payload;
      try {
        payload = JSON.parse(ev.data);
      } catch (e) {
        appendLog('(parse error)');
        return;
      }
      if (payload.type === 'run_start') {
        if (payload.run_id) {
          currentRunId = payload.run_id;
        }
        onRunStart(payload);
        if (payload.run_id) {
          refreshBoardDisplayLink(payload.run_id);
        }
        return;
      }
      if (payload.type === 'report_draft') {
        onReportDraft(payload);
        return;
      }
      if (payload.type === 'task_transition') {
        onTaskTransition(payload);
        return;
      }
      if (payload.type === 'chunk') {
        onChunk(payload);
        return;
      }
      if (payload.type === 'result') {
        streamCompleted = true;
        appendActivity('Run complete — final summary received', payload.ts || '');
        onRunComplete();
        summaryEl.textContent = payload.summary || '';
        var fr = payload.final_report || '';
        if (payload.run_id) {
          currentRunId = payload.run_id;
        }
        applyRunToAuditedPanel(
          {
            id: payload.run_id || currentRunId,
            status: payload.pending_approval ? 'pending_approval' : 'approved',
            final_report_text: fr || payload.summary || '',
            has_approved_pdf: false,
          },
          {}
        );
        setStatus('Done', 'ok');
        flushStreamBuffersSync();
        closeStream();
        window.setTimeout(function () {
          loadLatestRunForDisplay();
          loadRunList();
        }, 400);
        return;
      }
      if (payload.type === 'error') {
        streamCompleted = true;
        appendActivity('Error: ' + (payload.message || 'unknown'), payload.ts || '');
        appendLog('Error: ' + (payload.message || 'unknown'));
        setStatus('Error', 'err');
        flushStreamBuffersSync();
        closeStream();
      }
    };

    es.onerror = function () {
      if (streamCompleted) {
        return;
      }
      if (es) {
        appendActivity('(stream ended or connection error)', '');
        appendLog('(stream ended or connection error)');
        setStatus('Error', 'err');
        flushStreamBuffersSync();
        closeStream();
      }
    };
  }

  function startAnalysis() {
    const topic = topicInput && topicInput.value ? topicInput.value.trim() : '';
    const instructions = globalInstructionsEl ? globalInstructionsEl.value : '';

    function run() {
      openEventSource(topic);
    }

    if (!saveInstructionsUrl) {
      run();
      return;
    }

    if (logEl) logEl.textContent = '';
    summaryEl.textContent = '';

    fetch(saveInstructionsUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({ global_instructions: instructions }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('save instructions');
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || 'save');
        run();
      })
      .catch(function () {
        appendLog('Could not save crew instructions. Fix CSRF or try again.');
        setStatus('Error', 'err');
        startBtn.disabled = false;
      });
  }

  stopBtn.addEventListener('click', function () {
    streamCompleted = true;
    stopElapsedTimer();
    flushStreamBuffersSync();
    closeStream();
    setStatus('Idle', null);
  });

  startBtn.addEventListener('click', startAnalysis);

  if (approveBtn) {
    approveBtn.addEventListener('click', function () {
      if (!currentRunId) return;
      approveBtn.disabled = true;
      fetch('/api/crew/runs/' + encodeURIComponent(currentRunId) + '/approve/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
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
            if (approvalMsg) {
              approvalMsg.textContent = (res.data && res.data.error) || 'Could not approve.';
            }
            approveBtn.disabled = false;
            return;
          }
          if (res.data.run) {
            applyRunToAuditedPanel(res.data.run, {});
          }
          loadRunList();
        })
        .catch(function () {
          if (approvalMsg) approvalMsg.textContent = 'Network error.';
          approveBtn.disabled = false;
        });
    });
  }

  function loadLatestRunForDisplay() {
    if (!runLatestUrl) return;
    var mid =
      memberFocusEl && memberFocusEl.value ? String(memberFocusEl.value).trim() : '';
    var u = runLatestUrl + (mid ? '?member_id=' + encodeURIComponent(mid) : '');
    fetch(u, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.ok || !data.run) {
          return;
        }
        var run = data.run;
        applyRunToAuditedPanel(run, {});
        if (run.status === 'pending_approval' && approvalMsg) {
          approvalMsg.textContent =
            'Resumed pending report — review above, then approve to save the PDF.';
        }
      })
      .catch(function () {});
  }

  if (memberFocusEl) {
    memberFocusEl.addEventListener('change', function () {
      loadRunList();
      loadLatestRunForDisplay();
    });
  }

  if (pastRunsRefresh) {
    pastRunsRefresh.addEventListener('click', function () {
      loadRunList();
    });
  }

  if (workflowPrefillBtn && topicInput) {
    workflowPrefillBtn.addEventListener('click', function () {
      var t = workflowPrefillBtn.dataset.prefillTopic || '';
      if (!t) t = workflowPrefillBtn.dataset.fallbackSnippet || '';
      if (t) {
        topicInput.value = t;
        topicInput.focus();
      }
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      const t = buildExportText();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).catch(function () {});
      }
    });
  }

  if (downloadBtn) {
    downloadBtn.addEventListener('click', function () {
      const t = buildExportText();
      const blob = new Blob([t], { type: 'text/plain;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'crew-run-' + new Date().toISOString().replace(/[:.]/g, '-') + '.txt';
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  checkHealth();
  loadRunList();
  loadLatestRunForDisplay();
})();
