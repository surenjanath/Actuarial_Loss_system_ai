(function () {
  function readDashboardData() {
    var el = document.getElementById('dashboard-data');
    if (!el || !el.textContent) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return [];
    }
  }

  function calculateVulnerabilityProbability(data, targetLossRatio, wI, wT, wR) {
    return data.map(function (year) {
      var lossRatioScore = Math.min(100, (year.lossRatio / targetLossRatio) * 50);
      var trendScore = year.trend === 'up' ? 30 : year.trend === 'stable' ? 15 : 5;
      var reserveScore = Math.min(50, (1 / year.reserveAdequacy) * 40);
      return parseFloat((lossRatioScore * wI + trendScore * wT + reserveScore * wR).toFixed(2));
    });
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  }

  function formatNumber(value) {
    return new Intl.NumberFormat('en-US').format(Math.round(value));
  }

  function formatPercentage(value) {
    return (value * 100).toFixed(2) + '%';
  }

  function trendArrow(t) {
    if (t === 'up') return '↑';
    if (t === 'down') return '↓';
    return '→';
  }

  function trendClass(t) {
    if (t === 'up') return 'text-red';
    if (t === 'down') return 'text-green';
    return 'text-gray-400';
  }

  var selectedYear = null;
  var actuarialData = readDashboardData();

  function getCurrentProbs() {
    var targetLoss = parseFloat(document.getElementById('input-target').value);
    var wI = parseFloat(document.getElementById('input-wi').value);
    var wT = parseFloat(document.getElementById('input-wt').value);
    var wR = parseFloat(document.getElementById('input-wr').value);
    var probs = calculateVulnerabilityProbability(actuarialData, targetLoss, wI, wT, wR);
    var maxProb = Math.max.apply(null, probs.concat([1]));
    return { probs: probs, maxProb: maxProb };
  }

  /** Pixels reserved below chart area for year label + spacing */
  var PROB_BAR_BOTTOM_RESERVE = 22;
  /** Pixels reserved above bar (tooltip breathing room inside stack) */
  var PROB_BAR_TOP_RESERVE = 26;

  function getMaxBarPx() {
    var wrap = document.getElementById('prob-bars-container');
    if (!wrap || wrap.clientHeight < 24) return 120;
    var h = wrap.clientHeight;
    var usable = h - PROB_BAR_BOTTOM_RESERVE - PROB_BAR_TOP_RESERVE;
    return Math.max(48, Math.min(420, usable));
  }

  function renderProbBars(probs, maxProb) {
    var container = document.getElementById('prob-bars');
    if (!container) return;
    var maxBarPx = getMaxBarPx();
    container.innerHTML = '';
    actuarialData.forEach(function (year, index) {
      var probability = probs[index] || 0;
      var isHighRisk = probability > 50;
      var col = document.createElement('div');
      col.className = 'prob-bar-col';
      col.dataset.year = String(year.accidentYear);
      col.setAttribute('role', 'button');
      col.setAttribute('tabindex', '0');
      col.setAttribute('aria-label', 'Year ' + year.accidentYear + ', vulnerability ' + probability.toFixed(1) + ' percent');

      var inner = document.createElement('div');
      inner.className = 'prob-bar-stack';

      var tip = document.createElement('div');
      tip.className = 'prob-bar-tooltip';
      tip.textContent = probability.toFixed(1) + '%';
      inner.appendChild(tip);

      var bar = document.createElement('div');
      bar.className = 'prob-bar-fill ' + (isHighRisk ? 'grad-cyan' : 'grad-gray');
      var barH = maxProb > 0 ? (probability / maxProb) * maxBarPx : 0;
      bar.style.height = barH + 'px';
      bar.style.width = '100%';
      bar.style.maxWidth = '30px';
      inner.appendChild(bar);

      col.appendChild(inner);

      var ylabel = document.createElement('div');
      ylabel.className = 'prob-bar-year';
      if (selectedYear === year.accidentYear) ylabel.classList.add('selected');
      ylabel.textContent = String(year.accidentYear);
      col.appendChild(ylabel);

      function toggleYear() {
        selectedYear = selectedYear === year.accidentYear ? null : year.accidentYear;
        var cur = getCurrentProbs();
        renderYearDetails();
        renderProbBars(cur.probs, cur.maxProb);
      }

      col.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleYear();
      });
      col.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggleYear();
        }
      });

      container.appendChild(col);
    });

    var tl = document.getElementById('threshold-line');
    if (tl && maxProb > 0) {
      var lineBottom = (50 / maxProb) * maxBarPx;
      tl.style.bottom = Math.min(lineBottom, maxBarPx) + 'px';
    }
  }

  function refreshAfterClear() {
    var cur = getCurrentProbs();
    renderProbBars(cur.probs, cur.maxProb);
  }

  function renderYearDetails() {
    var panel = document.getElementById('year-details');
    if (!panel) return;
    if (selectedYear == null) {
      panel.classList.add('hidden');
      panel.innerHTML = '';
      return;
    }
    var year = actuarialData.find(function (y) {
      return y.accidentYear === selectedYear;
    });
    if (!year) return;
    var targetLoss = parseFloat(document.getElementById('input-target').value);
    var cur = getCurrentProbs();
    var yIdx = actuarialData.findIndex(function (y) {
      return y.accidentYear === selectedYear;
    });
    var vulnNow = yIdx >= 0 && cur.probs[yIdx] != null ? cur.probs[yIdx].toFixed(2) + '%' : '—';
    var dev =
      year.developmentFactor != null
        ? Number(year.developmentFactor).toFixed(3)
        : '—';
    panel.classList.remove('hidden');
    panel.innerHTML =
      '<div class="year-detail-head">' +
      '<div><h3 class="text-sm uppercase-track text-gray-400 mb-0">Accident year ' +
      selectedYear +
      '</h3>' +
      '<p class="text-xs text-gray-500 mb-0 mt-1">Model vulnerability (current weights): <strong class="text-gray-300">' +
      vulnNow +
      '</strong></p></div>' +
      '<button type="button" class="year-detail-close" aria-label="Close details">&times;</button>' +
      '</div>' +
      '<div class="year-detail-grid year-detail-grid--wide">' +
      '<div><div class="year-detail-cell__label">Reported claims</div><div class="year-detail-cell__value">' +
      formatNumber(year.reportedClaims) +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">Earned premium</div><div class="year-detail-cell__value">' +
      formatCurrency(year.earnedPremium) +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">Paid losses</div><div class="year-detail-cell__value">' +
      formatCurrency(year.paidLosses) +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">Incurred losses</div><div class="year-detail-cell__value">' +
      formatCurrency(year.incurredLosses) +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">Loss ratio</div><div class="year-detail-cell__value ' +
      (year.lossRatio > targetLoss ? 'text-red' : 'text-green') +
      '">' +
      formatPercentage(year.lossRatio) +
      '</div></div>' +
      '</div>' +
      '<div class="year-detail-grid year-detail-grid--wide" style="margin-top:0.65rem;">' +
      '<div><div class="year-detail-cell__label">Reserve adequacy</div><div class="year-detail-cell__value">' +
      year.reserveAdequacy.toFixed(2) +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">Development factor</div><div class="year-detail-cell__value">' +
      dev +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">YoY trend</div><div class="year-detail-cell__value ' +
      trendClass(year.trend) +
      '">' +
      trendArrow(year.trend) +
      ' ' +
      year.trend +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">Risk score</div><div class="year-detail-cell__value">' +
      (year.riskScore != null ? Number(year.riskScore).toFixed(1) : '—') +
      '</div></div>' +
      '<div><div class="year-detail-cell__label">vs target LR</div><div class="year-detail-cell__value text-gray-300">' +
      (year.lossRatio > targetLoss ? 'Above' : 'At or below') +
      ' ' +
      (targetLoss * 100).toFixed(1) +
      '%' +
      '</div></div>' +
      '</div>';
  }

  var refreshQueued = false;
  function scheduleComputeAndRefresh() {
    if (refreshQueued) return;
    refreshQueued = true;
    requestAnimationFrame(function () {
      refreshQueued = false;
      computeAndRefresh();
    });
  }

  function computeAndRefresh() {
    var targetLoss = parseFloat(document.getElementById('input-target').value);
    var wI = parseFloat(document.getElementById('input-wi').value);
    var wT = parseFloat(document.getElementById('input-wt').value);
    var wR = parseFloat(document.getElementById('input-wr').value);

    var probs = calculateVulnerabilityProbability(actuarialData, targetLoss, wI, wT, wR);
    var maxProb = Math.max.apply(null, probs.concat([1]));
    var avgVuln = probs.reduce(function (a, b) {
      return a + b;
    }, 0) / probs.length;

    var avgEl = document.getElementById('avg-risk-val');
    if (avgEl) avgEl.textContent = avgVuln.toFixed(2) + '%';
    var issuesEl = document.getElementById('metric-issues');
    if (issuesEl) issuesEl.textContent = formatNumber(Math.floor(avgVuln * 10));
    var healthEl = document.getElementById('metric-health');
    if (healthEl) healthEl.textContent = (100 - avgVuln).toFixed(1) + '%';

    var above50 = probs.filter(function (p) {
      return p > 50;
    }).length;
    var vulnSum = document.getElementById('vuln-threshold-summary');
    if (vulnSum) {
      vulnSum.textContent =
        above50 +
        ' of ' +
        probs.length +
        ' accident years are above the 50% reference line (same scale as bar height).';
    }
    var vulnRange = document.getElementById('vuln-range-hint');
    if (vulnRange && probs.length) {
      var minP = Math.min.apply(null, probs);
      var maxP = Math.max.apply(null, probs);
      vulnRange.textContent =
        'Range ' +
        minP.toFixed(1) +
        '–' +
        maxP.toFixed(1) +
        '% at current weights (portfolio avg ' +
        avgVuln.toFixed(1) +
        '%).';
    }

    if (typeof window.setParticleTargetLossRatio === 'function') {
      window.setParticleTargetLossRatio(targetLoss);
    }

    renderProbBars(probs, maxProb);
    renderYearDetails();

    var lt = document.getElementById('lbl-target');
    if (lt) lt.textContent = 'Target loss ratio: ' + (targetLoss * 100).toFixed(1) + '%';
    var lwi = document.getElementById('lbl-wi');
    if (lwi) lwi.textContent = 'Incurred weight: ' + (wI * 100).toFixed(0) + '%';
    var lwt = document.getElementById('lbl-wt');
    if (lwt) lwt.textContent = 'Trend weight: ' + (wT * 100).toFixed(0) + '%';
    var lwr = document.getElementById('lbl-wr');
    if (lwr) lwr.textContent = 'Reserve weight: ' + (wR * 100).toFixed(0) + '%';
  }

  function clearYearSelection() {
    if (selectedYear == null) return;
    selectedYear = null;
    renderYearDetails();
    refreshAfterClear();
  }

  function init() {
    if (!actuarialData.length) return;

    var lu = document.getElementById('last-updated');
    if (lu) {
      lu.textContent =
        'Last updated: ' +
        new Date().toLocaleString(undefined, {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        });
    }

    var targetEl = document.getElementById('input-target');
    var targetLoss = targetEl ? parseFloat(targetEl.value) : 0.68;

    var canvas = document.getElementById('particle-canvas');
    if (canvas && typeof window.initParticleCloud === 'function') {
      window.initParticleCloud(canvas, null, targetLoss);
    }

    var yearPanel = document.getElementById('year-details');
    if (yearPanel) {
      yearPanel.addEventListener('click', function (e) {
        if (e.target.closest('.year-detail-close')) {
          clearYearSelection();
        }
      });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') clearYearSelection();
    });

    document.getElementById('input-wi').addEventListener('input', function (e) {
      var nv = parseFloat(e.target.value);
      document.getElementById('input-wt').value = ((1 - nv) * 0.5).toFixed(2);
      document.getElementById('input-wr').value = ((1 - nv) * 0.5).toFixed(2);
      scheduleComputeAndRefresh();
    });
    ['input-target', 'input-wt', 'input-wr'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('input', scheduleComputeAndRefresh);
    });

    computeAndRefresh();

    var probWrap = document.getElementById('prob-bars-container');
    if (probWrap && typeof ResizeObserver !== 'undefined') {
      var roTimer = null;
      var ro = new ResizeObserver(function () {
        if (roTimer) clearTimeout(roTimer);
        roTimer = setTimeout(function () {
          roTimer = null;
          if (!actuarialData.length) return;
          var cur = getCurrentProbs();
          renderProbBars(cur.probs, cur.maxProb);
        }, 140);
      });
      ro.observe(probWrap);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
