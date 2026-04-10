(function () {
  function readData() {
    var el = document.getElementById('chart-data');
    if (!el || !el.textContent) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return [];
    }
  }

  var gridColor = 'rgba(55, 65, 81, 0.35)';
  var tickColor = '#6b7280';

  function baseChartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: tickColor, boxWidth: 10, padding: 8, font: { size: 11 } },
        },
      },
      elements: {
        line: { borderWidth: 2, tension: 0.25 },
        point: { radius: 0, hoverRadius: 4 },
        bar: { borderRadius: 3, maxBarThickness: 36 },
      },
    };
  }

  function scaleXY(extra) {
    var x = {
      ticks: { color: tickColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
      grid: { color: gridColor },
    };
    var y = Object.assign(
      {
        ticks: { color: tickColor },
        grid: { color: gridColor },
      },
      extra || {},
    );
    return { x: x, y: y };
  }

  function init() {
    var data = readData();
    if (!data.length || typeof Chart === 'undefined') return;

    var years = data.map(function (d) {
      return String(d.year);
    });

    var ctx1 = document.getElementById('chart-area');
    if (ctx1) {
      new Chart(ctx1, {
        type: 'line',
        data: {
          labels: years,
          datasets: [
            {
              label: 'Incurred Losses',
              data: data.map(function (d) {
                return d.incurred;
              }),
              borderColor: '#2ac8eb',
              backgroundColor: 'rgba(42, 200, 235, 0.12)',
              fill: true,
              order: 2,
            },
            {
              label: 'Earned Premium',
              data: data.map(function (d) {
                return d.premium;
              }),
              borderColor: '#8b5cf6',
              backgroundColor: 'rgba(139, 92, 246, 0.12)',
              fill: true,
              order: 1,
            },
          ],
        },
        options: Object.assign({}, baseChartOptions(), {
          scales: scaleXY({
            ticks: {
              color: tickColor,
              callback: function (value) {
                return '$' + (value / 1000000).toFixed(0) + 'M';
              },
            },
          }),
        }),
      });
    }

    var ctx2 = document.getElementById('chart-bar-lr');
    if (ctx2) {
      new Chart(ctx2, {
        type: 'bar',
        data: {
          labels: years,
          datasets: [
            {
              label: 'Loss Ratio',
              data: data.map(function (d) {
                return d.lossRatio;
              }),
              backgroundColor: 'rgba(42, 200, 235, 0.75)',
              order: 2,
              yAxisID: 'y',
            },
            {
              type: 'line',
              label: 'Target 68%',
              data: data.map(function () {
                return 68;
              }),
              borderColor: '#ef4444',
              borderDash: [6, 4],
              pointRadius: 0,
              pointHoverRadius: 0,
              fill: false,
              order: 1,
              yAxisID: 'y',
            },
          ],
        },
        options: Object.assign({}, baseChartOptions(), {
          scales: {
            x: {
              ticks: { color: tickColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 },
              grid: { color: gridColor },
            },
            y: {
              id: 'y',
              beginAtZero: true,
              suggestedMax: 100,
              ticks: {
                color: tickColor,
                callback: function (v) {
                  return v + '%';
                },
              },
              grid: { color: gridColor },
            },
          },
        }),
      });
    }

    var ctx3 = document.getElementById('chart-line-claims');
    if (ctx3) {
      new Chart(ctx3, {
        type: 'line',
        data: {
          labels: years,
          datasets: [
            {
              label: 'Reported Claims',
              data: data.map(function (d) {
                return d.claims;
              }),
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              fill: true,
            },
          ],
        },
        options: Object.assign({}, baseChartOptions(), {
          scales: scaleXY({
            ticks: {
              color: tickColor,
              callback: function (v) {
                if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
                if (v >= 1e3) return (v / 1e3).toFixed(0) + 'k';
                return v;
              },
            },
          }),
        }),
      });
    }

    var ctx4 = document.getElementById('chart-bar-reserve');
    if (ctx4) {
      var reserves = data.map(function (d) {
        return d.reserve;
      });
      var rLo = Math.min.apply(null, reserves.concat([1]));
      var rHi = Math.max.apply(null, reserves.concat([1]));
      var span = rHi - rLo || 0.1;
      var pad = Math.max(0.04, span * 0.25);

      new Chart(ctx4, {
        type: 'bar',
        data: {
          labels: years,
          datasets: [
            {
              label: 'Reserve Adequacy',
              data: reserves,
              backgroundColor: 'rgba(16, 185, 129, 0.75)',
              order: 2,
              yAxisID: 'y',
            },
            {
              type: 'line',
              label: 'Adequate (1.0)',
              data: data.map(function () {
                return 1.0;
              }),
              borderColor: '#2ac8eb',
              borderDash: [6, 4],
              pointRadius: 0,
              pointHoverRadius: 0,
              fill: false,
              order: 1,
              yAxisID: 'y',
            },
          ],
        },
        options: Object.assign({}, baseChartOptions(), {
          scales: {
            x: {
              ticks: { color: tickColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 },
              grid: { color: gridColor },
            },
            y: {
              id: 'y',
              min: rLo - pad,
              max: rHi + pad,
              ticks: {
                color: tickColor,
                callback: function (v) {
                  return Number(v).toFixed(2);
                },
              },
              grid: { color: gridColor },
            },
          },
        }),
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
