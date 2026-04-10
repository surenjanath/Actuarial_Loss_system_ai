/**
 * Particle field — tuned for smooth main-thread scrolling (fewer particles, FPS cap, pause off-screen).
 */
(function () {
  var BASE_PARTICLES = 900;
  var REDUCED_PARTICLES = 280;
  var MAX_DIST = 90;
  var MAX_DIST_SQ = MAX_DIST * MAX_DIST;
  /** ~36fps cap — leaves headroom for layout & scroll */
  var MIN_FRAME_MS = 28;
  var state = {
    animationId: null,
    particles: [],
    mouse: { x: -9999, y: -9999 },
    canvas: null,
    ctx: null,
    data: [],
    targetLossRatio: 0.68,
    dpr: 1,
    resizeTimer: null,
    onVis: null,
    onResize: null,
    io: null,
    ioVisible: true,
    lastFrameTs: 0,
  };

  function particleBudget() {
    try {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return REDUCED_PARTICLES;
    } catch (e) {}
    return BASE_PARTICLES;
  }

  function parseParticleData() {
    var el = document.getElementById('particle-data');
    if (!el || !el.textContent) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return [];
    }
  }

  function generateParticles() {
    var canvas = state.canvas;
    if (!canvas || !state.data.length) return [];
    var particles = [];
    var width = canvas.width / state.dpr;
    var height = canvas.height / state.dpr;
    var data = state.data;
    var count = particleBudget();
    var perYear = Math.max(24, Math.floor(count / data.length));

    data.forEach(function (year, yearIndex) {
      var riskMultiplier = year.lossRatio / state.targetLossRatio;
      var baseY = height * 0.3 + (yearIndex / data.length) * height * 0.5;

      for (var i = 0; i < perYear; i++) {
        var noise1 = Math.sin(i * 0.1 + yearIndex) * 30;
        var noise2 = Math.cos(i * 0.05 + year.accidentYear) * 20;
        var noise3 = Math.sin(i * 0.2 - yearIndex * 0.5) * 15;
        var x = (i / perYear) * width + noise1 + noise3;
        var y = baseY + noise2 + (Math.random() - 0.5) * 60 * riskMultiplier;

        particles.push({
          x: x,
          y: y,
          baseX: x,
          baseY: y,
          size: Math.random() * 2 + 0.5,
          speedX: (Math.random() - 0.5) * 0.3,
          speedY: (Math.random() - 0.5) * 0.3,
          opacity: Math.random() * 0.6 + 0.2,
          riskLevel: riskMultiplier,
        });
      }
    });
    return particles;
  }

  function applyCanvasSize() {
    var canvas = state.canvas;
    if (!canvas) return;
    var parent = canvas.parentElement;
    if (!parent) return;
    var rawDpr = window.devicePixelRatio || 1;
    state.dpr = Math.min(2, Math.max(1, rawDpr));
    canvas.width = Math.floor(parent.clientWidth * state.dpr);
    canvas.height = Math.floor(parent.clientHeight * state.dpr);
    canvas.style.width = parent.clientWidth + 'px';
    canvas.style.height = parent.clientHeight + 'px';
    var ctx = state.ctx;
    if (ctx) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(state.dpr, state.dpr);
    }
    state.particles = generateParticles();
  }

  function resizeCanvas() {
    if (state.resizeTimer) clearTimeout(state.resizeTimer);
    state.resizeTimer = setTimeout(function () {
      state.resizeTimer = null;
      applyCanvasSize();
    }, 120);
  }

  function animate(ts) {
    if (document.hidden || !state.ioVisible) {
      state.animationId = null;
      return;
    }


    ts = ts || 0;
    if (state.lastFrameTs && ts - state.lastFrameTs < MIN_FRAME_MS) {
      state.animationId = requestAnimationFrame(animate);
      return;
    }
    state.lastFrameTs = ts;

    var canvas = state.canvas;
    var ctx = state.ctx;
    if (!canvas || !ctx) return;
    var w = canvas.width / state.dpr;
    var h = canvas.height / state.dpr;
    ctx.clearRect(0, 0, w, h);

    var mx = state.mouse.x;
    var my = state.mouse.y;
    var plist = state.particles;
    var i;
    var p;
    var dx;
    var dy;
    var distSq;
    var distance;
    var force;

    for (i = 0; i < plist.length; i++) {
      p = plist[i];
      p.x += p.speedX;
      p.y += p.speedY;

      dx = mx - p.x;
      dy = my - p.y;
      distSq = dx * dx + dy * dy;
      if (distSq < MAX_DIST_SQ && distSq > 1e-6) {
        distance = Math.sqrt(distSq);
        force = (MAX_DIST - distance) / MAX_DIST;
        p.x -= (dx / distance) * force * 1.6;
        p.y -= (dy / distance) * force * 1.6;
      }

      p.x += (p.baseX - p.x) * 0.02;
      p.y += (p.baseY - p.y) * 0.02;

      var riskColor =
        p.riskLevel > 1.2 ? '255, 100, 100' : p.riskLevel > 1.0 ? '255, 200, 100' : '42, 200, 235';

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + riskColor + ', ' + p.opacity + ')';
      ctx.fill();
    }

    state.animationId = requestAnimationFrame(animate);
  }

  var mouseRaf = null;
  function onMouseMove(e) {
    var canvas = state.canvas;
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    var nx = (e.clientX - rect.left) * (canvas.width / rect.width / state.dpr);
    var ny = (e.clientY - rect.top) * (canvas.height / rect.height / state.dpr);
    if (mouseRaf) return;
    mouseRaf = requestAnimationFrame(function () {
      mouseRaf = null;
      state.mouse.x = nx;
      state.mouse.y = ny;
    });
  }

  function onVisibilityChange() {
    if (document.hidden) {
      if (state.animationId) {
        cancelAnimationFrame(state.animationId);
        state.animationId = null;
      }
    } else if (state.canvas && state.ctx && state.ioVisible && !state.animationId) {
      state.lastFrameTs = 0;
      animate();
    }
  }

  function onIntersect(entries) {
    var vis = entries[0] && entries[0].isIntersecting;
    state.ioVisible = vis;
    if (!vis) {
      if (state.animationId) {
        cancelAnimationFrame(state.animationId);
        state.animationId = null;
      }
    } else if (state.canvas && state.ctx && !document.hidden && !state.animationId) {
      state.lastFrameTs = 0;
      animate();
    }
  }

  window.initParticleCloud = function (canvasEl, dataOverride, targetLossRatio) {
    state.canvas = canvasEl;
    state.ctx = canvasEl ? canvasEl.getContext('2d', { alpha: true, desynchronized: true }) : null;
    state.data = dataOverride || parseParticleData();
    if (typeof targetLossRatio === 'number') state.targetLossRatio = targetLossRatio;

    if (!state.ctx || !state.data.length) return;

    if (state.onResize) window.removeEventListener('resize', state.onResize);
    if (state.onVis) document.removeEventListener('visibilitychange', state.onVis);
    if (state.io) {
      state.io.disconnect();
      state.io = null;
    }

    state.onResize = resizeCanvas;
    state.onVis = onVisibilityChange;
    window.addEventListener('resize', state.onResize);
    document.addEventListener('visibilitychange', state.onVis);

    applyCanvasSize();
    canvasEl.addEventListener('mousemove', onMouseMove, { passive: true });

    state.ioVisible = true;
    if (typeof IntersectionObserver !== 'undefined') {
      state.io = new IntersectionObserver(onIntersect, { root: null, rootMargin: '100px', threshold: 0 });
      state.io.observe(canvasEl);
    }

    if (state.animationId) cancelAnimationFrame(state.animationId);
    state.lastFrameTs = 0;
    animate();
  };

  window.setParticleTargetLossRatio = function (ratio) {
    state.targetLossRatio = ratio;
    state.particles = generateParticles();
  };

  window.destroyParticleCloud = function () {
    if (state.animationId) cancelAnimationFrame(state.animationId);
    state.animationId = null;
    if (state.resizeTimer) clearTimeout(state.resizeTimer);
    if (state.onResize) window.removeEventListener('resize', state.onResize);
    if (state.onVis) document.removeEventListener('visibilitychange', state.onVis);
    state.onResize = null;
    state.onVis = null;
    if (state.io) {
      state.io.disconnect();
      state.io = null;
    }
    if (state.canvas) state.canvas.removeEventListener('mousemove', onMouseMove);
  };
})();
