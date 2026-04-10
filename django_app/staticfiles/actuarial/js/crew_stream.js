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
  const sharedThinkingWrap = document.getElementById('crew-shared-thinking-wrap');
  const sharedReportLive = document.getElementById('crew-shared-report-live');
  const thinkingLive = document.getElementById('crew-thinking-live');
  const startQueuedBtn = document.getElementById('crew-start-queued');
  const crewRunsTbody = document.getElementById('crew-runs-tbody');
  const crewStartUrl =
    panel.dataset.crewStartUrl || panel.getAttribute('data-crew-start-url') || '';
  const crewStopUrl =
    panel.dataset.crewStopUrl || panel.getAttribute('data-crew-stop-url') || '';
  const runListUrlPanel =
    panel.dataset.runListUrl || panel.getAttribute('data-run-list-url') || '';
  const crewEventsUrlTemplate =
    panel.dataset.crewRunEventsUrlTemplate ||
    panel.getAttribute('data-crew-run-events-url-template') ||
    '';

  /** CrewAI stream chunks often report task_index 0 for every token; we route by server task_transition instead. */
  let activeStreamTaskIdx = -1;
  let currentRunId = null;
  let ws = null;
  let eventsPollTimer = null;
  let restPollSeq = 0;

  let lastTaskIdx = -1;
  let chunkCounter = 0;
  let elapsedTimer = null;
  let runStartedAt = 0;
  let exportLines = [];

  const streamBase = panel.dataset.streamUrl || '';
  const healthUrl = panel.dataset.healthUrl || '';
  const saveInstructionsUrl = panel.dataset.saveInstructionsUrl || '';
  const runLatestUrl = panel.dataset.runLatestUrl || '';
  const featureEnabled = panel.dataset.enabled === 'true';
  const globalInstructionsEl = document.getElementById('crew-global-instructions');

  const CHUNK_ACTIVITY_EVERY = 25;

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
    if (!logEl) return;
    logEl.textContent += (logEl.textContent ? '\n' : '') + line;
    logEl.scrollTop = logEl.scrollHeight;
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
    if (sharedReportLive) sharedReportLive.textContent = '';
    if (thinkingLive) thinkingLive.textContent = '';
    if (sharedThinkingWrap) sharedThinkingWrap.classList.add('hidden');
  }

  function showViz() {
    if (vizWrap) vizWrap.classList.remove('hidden');
    if (liveDocsWrap) liveDocsWrap.classList.remove('hidden');
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
    if (payload.orchestrated && sharedThinkingWrap) {
      sharedThinkingWrap.classList.remove('hidden');
    }
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
      if (unifiedDocEl) {
        const sep = unifiedDocEl.textContent ? '\n\n' : '';
        unifiedDocEl.textContent +=
          sep + '── ' + label + (payload.role ? ' — ' + payload.role : '') + ' ──\n\n';
        unifiedDocEl.scrollTop = unifiedDocEl.scrollHeight;
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

  function appendDocChunk(idx, text) {
    const card = document.querySelector('.crew-doc-card[data-task-idx="' + idx + '"]');
    if (!card) return;
    const doc = card.querySelector('[data-field="doc"]');
    if (doc) {
      doc.textContent += text;
      doc.scrollTop = doc.scrollHeight;
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
      appendDocChunk(routeIdx, bit);
      if (unifiedDocEl) {
        unifiedDocEl.textContent += bit;
        unifiedDocEl.scrollTop = unifiedDocEl.scrollHeight;
      }
      const role = payload.agent_role || '';
      appendLog((role ? '[' + role + '] ' : '') + bit);
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
    const parts = [];
    parts.push('=== Crew activity ===');
    parts.push(exportLines.join('\n'));
    parts.push('');
    parts.push('=== Audited report (deliverable) ===');
    parts.push(auditedReportEl ? auditedReportEl.textContent : '');
    parts.push('');
    parts.push('=== Shared report draft (live panel) ===');
    parts.push(sharedReportLive ? sharedReportLive.textContent : '');
    parts.push('');
    parts.push('=== Thinking panel ===');
    parts.push(thinkingLive ? thinkingLive.textContent : '');
    parts.push('');
    parts.push('=== Full transcript (all tasks) ===');
    parts.push(unifiedDocEl ? unifiedDocEl.textContent : '');
    parts.push('');
    parts.push('=== Raw stream ===');
    parts.push(logEl ? logEl.textContent : '');
    parts.push('');
    parts.push('=== Crew chain summary (raw) ===');
    parts.push(summaryEl ? summaryEl.textContent : '');
    return parts.join('\n');
  }

  function stopEventsPoll() {
    if (eventsPollTimer) {
      window.clearInterval(eventsPollTimer);
      eventsPollTimer = null;
    }
  }

  function closeStream() {
    stopElapsedTimer();
    stopEventsPoll();
    if (es) {
      es.close();
      es = null;
    }
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
      ws = null;
    }
    stopBtn.disabled = true;
    startBtn.disabled = false;
    if (startQueuedBtn) startQueuedBtn.disabled = false;
    checkHealth();
  }

  function signalServerCrewStop() {
    if (!crewStopUrl) return;
    fetch(crewStopUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: '{}',
    }).catch(function () {});
  }

  function checkHealth() {
    if (!featureEnabled) {
      healthMsg.textContent = 'Crew analysis is disabled on the server (CREW_ANALYSIS_ENABLED).';
      startBtn.disabled = true;
      if (startQueuedBtn) startQueuedBtn.disabled = true;
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
          if (startQueuedBtn) startQueuedBtn.disabled = true;
          setStatus('Disabled', 'err');
          return;
        }
        if (!data.ok) {
          healthMsg.textContent =
            data.message || 'Ollama not reachable. Check Settings → Local LLM or run `ollama serve`.';
          startBtn.disabled = true;
          if (startQueuedBtn) startQueuedBtn.disabled = true;
          setStatus('Offline', 'err');
          return;
        }
        var extra = data.session_override ? ' (session overrides)' : '';
        healthMsg.textContent =
          'Ollama OK — ' + (data.model || '') + ' @ ' + (data.ollama_url || '') + extra + '.';
        startBtn.disabled = false;
        if (startQueuedBtn) {
          if (data.crew_slot_busy) {
            startQueuedBtn.disabled = true;
            startQueuedBtn.title =
              'A crew run is already active for this session (live stream or background). Wait or use Stop.';
          } else {
            startQueuedBtn.disabled = false;
            startQueuedBtn.title = 'Queue run in background (requires qcluster + Daphne)';
          }
        }
        setStatus('Idle', null);
      })
      .catch(function () {
        healthMsg.textContent = 'Could not reach health endpoint.';
        startBtn.disabled = true;
        if (startQueuedBtn) startQueuedBtn.disabled = true;
        setStatus('Error', 'err');
      });
  }

  function handleStreamPayload(payload) {
    if (payload.type === 'status') {
      appendActivity(payload.message || '…', payload.ts || '');
      appendLog(payload.message || '');
      setStatus('Running', 'run');
      return;
    }
    if (payload.type === 'model_wait') {
      appendActivity(payload.message || 'Waiting for model…', payload.ts || '');
      appendLog(payload.message || '');
      setStatus('Running', 'run');
      return;
    }
    if (payload.type === 'run_start') {
      if (payload.run_id) {
        currentRunId = payload.run_id;
      }
      onRunStart(payload);
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
    if (payload.type === 'report_draft') {
      if (sharedReportLive) {
        sharedReportLive.textContent = payload.content || '';
      }
      if (sharedThinkingWrap) sharedThinkingWrap.classList.remove('hidden');
      appendActivity(
        'Report draft updated — step ' + (payload.task_index != null ? payload.task_index : ''),
        payload.ts || ''
      );
      return;
    }
    if (payload.type === 'thinking') {
      if (thinkingLive) {
        var sep = thinkingLive.textContent ? '\n\n—\n\n' : '';
        thinkingLive.textContent +=
          sep +
          (payload.role ? '[' + payload.role + ']\n' : '') +
          (payload.content || '');
        thinkingLive.scrollTop = thinkingLive.scrollHeight;
      }
      if (sharedThinkingWrap) sharedThinkingWrap.classList.remove('hidden');
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
      if (auditedWrap && auditedReportEl) {
        auditedWrap.classList.remove('hidden');
        auditedReportEl.textContent = fr || payload.summary || '';
      }
      if (approvalPill) {
        if (payload.pending_approval && currentRunId) {
          approvalPill.textContent = 'Pending your approval';
          approvalPill.style.color = '#fbbf24';
          approvalPill.style.background = 'rgba(251,191,36,0.12)';
        } else {
          approvalPill.textContent = 'Recorded';
          approvalPill.style.color = '#9ca3af';
          approvalPill.style.background = 'rgba(55,65,81,0.6)';
        }
      }
      if (approveBtn) {
        approveBtn.disabled = !(payload.pending_approval && currentRunId);
      }
      if (approvalMsg) {
        approvalMsg.textContent = payload.pending_approval
          ? 'Review the audited report above, then approve to lock it for your records.'
          : '';
      }
      setStatus('Done', 'ok');
      closeStream();
      loadRunsTable();
      return;
    }
    if (payload.type === 'error') {
      streamCompleted = true;
      appendActivity('Error: ' + (payload.message || 'unknown'), payload.ts || '');
      appendLog('Error: ' + (payload.message || 'unknown'));
      setStatus('Error', 'err');
      closeStream();
      loadRunsTable();
      return;
    }
  }

  function crewEventsUrlForRun(runId) {
    if (!crewEventsUrlTemplate || !runId) return '';
    return crewEventsUrlTemplate.replace(
      '00000000-0000-0000-0000-000000000000',
      String(runId)
    );
  }

  function processCrewEvent(row) {
    var p = row.payload || {};
    if (row.event_type === 'complete') {
      streamCompleted = true;
      stopEventsPoll();
      closeStream();
      loadRunsTable();
      return;
    }
    handleStreamPayload(p);
  }

  function startRestPollForRun(runId) {
    var base = crewEventsUrlForRun(runId);
    if (!base) {
      appendActivity('REST events URL missing (data-crew-run-events-url-template)', '');
      return;
    }
    stopEventsPoll();
    restPollSeq = 0;
    appendActivity('Live feed: polling REST events', '');
    function pollOnce() {
      fetch(base + (base.indexOf('?') >= 0 ? '&' : '?') + 'since=' + restPollSeq, {
        credentials: 'same-origin',
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data || !data.ok || !data.events) return;
          data.events.forEach(function (row) {
            if (row.seq > restPollSeq) {
              restPollSeq = row.seq;
            }
            processCrewEvent(row);
          });
        })
        .catch(function () {});
    }
    pollOnce();
    eventsPollTimer = window.setInterval(pollOnce, 500);
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
    if (startQueuedBtn) startQueuedBtn.disabled = true;
    appendActivity('Opening live stream…', '');
    appendLog(
      'Connecting… You should see status lines immediately; the first model tokens often take 30s–2min.'
    );

    es = new EventSource(url);

    es.onmessage = function (ev) {
      let payload;
      try {
        payload = JSON.parse(ev.data);
      } catch (e) {
        appendLog('(parse error)');
        return;
      }
      handleStreamPayload(payload);
    };

    es.onerror = function () {
      if (streamCompleted) {
        return;
      }
      if (es) {
        appendActivity('(stream ended or connection error)', '');
        appendLog('(stream ended or connection error)');
        setStatus('Error', 'err');
        closeStream();
      }
    };
  }

  function connectWebSocketForRun(runId) {
    if (!runId) return;
    if (es) {
      es.close();
      es = null;
    }
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
      ws = null;
    }
    stopEventsPoll();

    if (!window.WebSocket) {
      startRestPollForRun(runId);
      return;
    }

    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = proto + '//' + location.host + '/ws/crew/' + runId + '/';
    try {
      ws = new WebSocket(url);
    } catch (e) {
      appendActivity('WebSocket failed — falling back to REST events', '');
      startRestPollForRun(runId);
      return;
    }
    ws.onopen = function () {
      stopEventsPoll();
    };
    ws.onmessage = function (ev) {
      try {
        var row = JSON.parse(ev.data);
        processCrewEvent(row);
      } catch (err) {
        appendLog('(ws parse error)');
      }
    };
    ws.onerror = function () {
      if (streamCompleted) return;
      appendActivity('WebSocket error — falling back to REST events', '');
      try {
        ws.close();
      } catch (e) {}
      ws = null;
      startRestPollForRun(runId);
    };
  }

  function loadRunsTable() {
    if (!crewRunsTbody || !runListUrlPanel) return;
    fetch(runListUrlPanel, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.ok || !data.runs) return;
        crewRunsTbody.textContent = '';
        data.runs.forEach(function (run) {
          var tr = document.createElement('tr');
          tr.innerHTML =
            '<td class="py-1 pr-2">' +
            (run.status || '') +
            '</td><td class="py-1 pr-2">' +
            (run.topic || '—').slice(0, 40) +
            '</td><td class="py-1 pr-2">' +
            (run.created_at || '').slice(0, 19) +
            '</td><td class="py-1 font-mono text-xs">' +
            (run.id || '').slice(0, 8) +
            '…</td>';
          crewRunsTbody.appendChild(tr);
        });
      })
      .catch(function () {});
  }

  function startQueuedAnalysis() {
    if (!crewStartUrl) return;
    const topic = topicInput && topicInput.value ? topicInput.value.trim() : '';
    const instructions = globalInstructionsEl ? globalInstructionsEl.value : '';
    const mid =
      memberFocusEl && memberFocusEl.value ? String(memberFocusEl.value).trim() : '';

    function postStart() {
      fetch(crewStartUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({
          use_queue: true,
          topic: topic,
          member_id: mid || null,
        }),
      })
        .then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, data: data };
          });
        })
        .then(function (res) {
          if (!res.ok || !res.data.ok) {
            var errMsg = (res.data && res.data.error) || 'Queue start failed';
            if (res.data && res.data.hint) {
              errMsg += ' — ' + res.data.hint;
            }
            appendLog(errMsg);
            setStatus('Error', 'err');
            if (startQueuedBtn) startQueuedBtn.disabled = false;
            return;
          }
          streamCompleted = false;
          resetViz();
          showViz();
          startElapsedTimer();
          setStatus('Running', 'run');
          startBtn.disabled = true;
          if (startQueuedBtn) startQueuedBtn.disabled = true;
          stopBtn.disabled = false;
          currentRunId = res.data.run_id;
          connectWebSocketForRun(res.data.run_id);
          appendActivity('Queued background run — WebSocket live feed', '');
          loadRunsTable();
        })
        .catch(function () {
          setStatus('Error', 'err');
          if (startQueuedBtn) startQueuedBtn.disabled = false;
        });
    }

    if (!saveInstructionsUrl) {
      postStart();
      return;
    }
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
        if (!r.ok) throw new Error('save');
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || 'save');
        postStart();
      })
      .catch(function () {
        appendLog('Could not save crew instructions.');
        setStatus('Error', 'err');
      });
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
    appendLog('Saving crew instructions to session…');

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
        appendLog('Instructions saved — opening stream.');
        run();
      })
      .catch(function () {
        appendLog('Could not save crew instructions to session. Fix CSRF or try again.');
        setStatus('Error', 'err');
        startBtn.disabled = false;
      });
  }

  stopBtn.addEventListener('click', function () {
    streamCompleted = true;
    stopElapsedTimer();
    signalServerCrewStop();
    closeStream();
    setStatus('Idle', null);
  });

  startBtn.addEventListener('click', startAnalysis);
  if (startQueuedBtn) {
    startQueuedBtn.addEventListener('click', startQueuedAnalysis);
  }

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
          if (approvalPill) {
            approvalPill.textContent = 'Approved';
            approvalPill.style.color = '#4ade80';
            approvalPill.style.background = 'rgba(74,222,128,0.12)';
          }
          if (approvalMsg) {
            approvalMsg.textContent = 'Report approved and locked.';
          }
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
        if (!data.ok || !data.run) return;
        var run = data.run;
        if (run.status === 'pending_approval' && run.final_report_text) {
          if (auditedWrap) auditedWrap.classList.remove('hidden');
          if (auditedReportEl) auditedReportEl.textContent = run.final_report_text;
          currentRunId = run.id;
          if (approvalPill) {
            approvalPill.textContent = 'Pending your approval';
            approvalPill.style.color = '#fbbf24';
            approvalPill.style.background = 'rgba(251,191,36,0.12)';
          }
          if (approveBtn) approveBtn.disabled = false;
          if (approvalMsg) {
            approvalMsg.textContent =
              'Resumed pending report from last session — approve when ready.';
          }
        }
      })
      .catch(function () {});
  }

  if (memberFocusEl) {
    memberFocusEl.addEventListener('change', loadLatestRunForDisplay);
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
  loadLatestRunForDisplay();
  loadRunsTable();
})();
