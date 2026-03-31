/* ============================================================
   КОМАНДА ГАММА — Hello World 3D
   script.js  — интерактивность, частицы, 3D-реакция на мышь
   ============================================================ */

'use strict';

/* ---- Утилита: RAF с ограничением по FPS ---- */
const fpsEl = document.getElementById('fps');
let lastTime = performance.now();
let frameCount = 0;

/* ---- DOM-узлы ---- */
const scene       = document.getElementById('scene');
const sceneInner  = document.getElementById('sceneInner');
const canvas      = document.getElementById('particlesCanvas');
const ctx         = canvas.getContext('2d');
const titleWords  = document.querySelectorAll('.title__word');

/* ============================================================
   1. МЫШЬ — 3D-поворот сцены
   ============================================================ */
let mouseX = 0, mouseY = 0;
let targetRX = 0, targetRY = 0;
let currentRX = 0, currentRY = 0;

/**
 * Обработчик движения мыши:
 * Нормализует координаты к [-1, 1] и вычисляет углы поворота.
 */
document.addEventListener('mousemove', (e) => {
  const cx = window.innerWidth  / 2;
  const cy = window.innerHeight / 2;
  mouseX = (e.clientX - cx) / cx;   // −1 … +1
  mouseY = (e.clientY - cy) / cy;   // −1 … +1

  // Обновляем CSS-переменные для кастомного курсора
  document.body.style.setProperty('--cx', e.clientX + 'px');
  document.body.style.setProperty('--cy', e.clientY + 'px');

  targetRY =  mouseX * 18;   // max ±18° по Y
  targetRX = -mouseY * 12;   // max ±12° по X
});

/** Параллакс отдельных слов заголовка */
document.addEventListener('mousemove', (e) => {
  const cx = window.innerWidth  / 2;
  const cy = window.innerHeight / 2;
  titleWords.forEach((word) => {
    const depth = parseFloat(word.dataset.depth) || 0.5;
    const dx = ((e.clientX - cx) / cx) * depth * 20;
    const dy = ((e.clientY - cy) / cy) * depth * 10;
    word.style.transform = `translateX(${dx}px) translateY(${dy}px) translateZ(0)`;
  });
});

/** Сброс при уходе курсора за пределы окна */
document.addEventListener('mouseleave', () => {
  targetRX = 0;
  targetRY = 0;
  titleWords.forEach((w) => (w.style.transform = ''));
});

/** Touch-поддержка */
document.addEventListener('touchmove', (e) => {
  const t  = e.touches[0];
  const cx = window.innerWidth  / 2;
  const cy = window.innerHeight / 2;
  targetRY =  ((t.clientX - cx) / cx) * 14;
  targetRX = -((t.clientY - cy) / cy) * 8;
}, { passive: true });

document.addEventListener('touchend', () => {
  targetRX = 0;
  targetRY = 0;
});

/* ============================================================
   2. КЛИК — взрыв частиц
   ============================================================ */
const burst = [];

document.addEventListener('click', (e) => {
  spawnBurst(e.clientX, e.clientY, 30);
});

document.addEventListener('touchstart', (e) => {
  const t = e.touches[0];
  spawnBurst(t.clientX, t.clientY, 20);
}, { passive: true });

function spawnBurst(x, y, count) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 1.5 + Math.random() * 4;
    burst.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      r: 2 + Math.random() * 3,
      life: 1,
      decay: 0.018 + Math.random() * 0.02,
      color: BURST_COLORS[Math.floor(Math.random() * BURST_COLORS.length)],
    });
  }
}

const BURST_COLORS = ['#00e5ff', '#9b30ff', '#2979ff', '#ffffff', '#7b2fff'];

/* ============================================================
   3. CANVAS — фоновые частицы-звёзды
   ============================================================ */
const PARTICLE_COUNT = 120;
const particles = [];

class Particle {
  constructor() { this.reset(true); }

  reset(initial = false) {
    this.x  = Math.random() * canvas.width;
    this.y  = initial ? Math.random() * canvas.height : -8;
    this.r  = 0.5 + Math.random() * 1.8;
    this.vy = 0.15 + Math.random() * 0.35;
    this.vx = (Math.random() - 0.5) * 0.12;
    this.opacity = 0.15 + Math.random() * 0.55;
    this.color = PARTICLE_COLORS[Math.floor(Math.random() * PARTICLE_COLORS.length)];
    // Связь с мышью
    this.mx = 0;
    this.my = 0;
  }

  update(mx, my) {
    this.y += this.vy;
    this.x += this.vx;

    // Лёгкое отталкивание от мыши
    const dx = this.x - mx;
    const dy = this.y - my;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 80 && dist > 0) {
      const force = (80 - dist) / 80 * 0.6;
      this.x += (dx / dist) * force;
      this.y += (dy / dist) * force;
    }

    if (this.y > canvas.height + 8) this.reset();
    if (this.x < -8 || this.x > canvas.width + 8) this.reset();
  }

  draw() {
    ctx.save();
    ctx.globalAlpha = this.opacity;
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
    ctx.fillStyle = this.color;
    ctx.fill();
    ctx.restore();
  }
}

const PARTICLE_COLORS = ['#ffffff', '#9b30ff', '#00e5ff', '#2979ff'];

function initParticles() {
  particles.length = 0;
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push(new Particle());
  }
}

/* ============================================================
   4. RESIZE — адаптация canvas
   ============================================================ */
function resizeCanvas() {
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
}

window.addEventListener('resize', () => {
  resizeCanvas();
  initParticles();
});

/* ============================================================
   5. ГЛАВНЫЙ ИГРОВОЙ ЦИКЛ (requestAnimationFrame)
   ============================================================ */
function lerp(a, b, t) { return a + (b - a) * t; }

function loop(now) {
  requestAnimationFrame(loop);

  /* --- FPS --- */
  frameCount++;
  const elapsed = now - lastTime;
  if (elapsed >= 800) {
    fpsEl.textContent = Math.round((frameCount / elapsed) * 1000) + ' fps';
    frameCount = 0;
    lastTime = now;
  }

  /* --- Плавный 3D-поворот (inertia) --- */
  currentRX = lerp(currentRX, targetRX, 0.08);
  currentRY = lerp(currentRY, targetRY, 0.08);
  sceneInner.style.transform =
    `rotateX(${currentRX}deg) rotateY(${currentRY}deg)`;

  /* --- Canvas: очистка --- */
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  /* --- Фоновые частицы --- */
  const mx = (mouseX + 1) / 2 * canvas.width;
  const my = (mouseY + 1) / 2 * canvas.height;

  particles.forEach((p) => {
    p.update(mx, my);
    p.draw();
  });

  /* --- Burst-частицы (клик) --- */
  for (let i = burst.length - 1; i >= 0; i--) {
    const b = burst[i];
    b.x   += b.vx;
    b.y   += b.vy;
    b.vy  += 0.08;          // гравитация
    b.life -= b.decay;

    ctx.save();
    ctx.globalAlpha = Math.max(0, b.life);
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r * b.life, 0, Math.PI * 2);
    ctx.fillStyle = b.color;
    ctx.shadowBlur = 8;
    ctx.shadowColor = b.color;
    ctx.fill();
    ctx.restore();

    if (b.life <= 0) burst.splice(i, 1);
  }
}

/* ============================================================
   6. SCROLL-WHEEL — zoom-эффект
   ============================================================ */
let scaleTarget = 1;
let scaleCurrent = 1;

window.addEventListener('wheel', (e) => {
  scaleTarget -= e.deltaY * 0.0003;
  scaleTarget = Math.min(Math.max(scaleTarget, 0.7), 1.4);
}, { passive: true });

/* Интегрируем масштаб в RAF — добавляем в конец loop */
const _origLoop = loop;
(function patchLoop() {
  const raf = requestAnimationFrame;
  window.requestAnimationFrame = function(cb) {
    return raf(cb);
  };
})();

/* Простой патч: дополним sceneInner transform масштабом */
const _baseLoop = loop;
function enhancedLoop(now) {
  /* scaleCurrent плавно → scaleTarget */
  scaleCurrent = lerp(scaleCurrent, scaleTarget, 0.07);
  sceneInner.style.transform =
    `rotateX(${currentRX}deg) rotateY(${currentRY}deg) scale(${scaleCurrent})`;
}

/* Переопределяем loop с учётом масштаба */
function mainLoop(now) {
  requestAnimationFrame(mainLoop);

  /* FPS */
  frameCount++;
  const elapsed = now - lastTime;
  if (elapsed >= 800) {
    fpsEl.textContent = Math.round((frameCount / elapsed) * 1000) + ' fps';
    frameCount = 0;
    lastTime = now;
  }

  /* Плавный 3D-поворот + scale */
  currentRX    = lerp(currentRX, targetRX, 0.08);
  currentRY    = lerp(currentRY, targetRY, 0.08);
  scaleCurrent = lerp(scaleCurrent, scaleTarget, 0.07);
  sceneInner.style.transform =
    `rotateX(${currentRX}deg) rotateY(${currentRY}deg) scale(${scaleCurrent})`;

  /* Canvas очистка */
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  /* Частицы-звёзды */
  const mx = (mouseX + 1) / 2 * canvas.width;
  const my = (mouseY + 1) / 2 * canvas.height;
  particles.forEach((p) => { p.update(mx, my); p.draw(); });

  /* Burst */
  for (let i = burst.length - 1; i >= 0; i--) {
    const b = burst[i];
    b.x   += b.vx;
    b.y   += b.vy;
    b.vy  += 0.08;
    b.life -= b.decay;

    ctx.save();
    ctx.globalAlpha = Math.max(0, b.life);
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r * b.life, 0, Math.PI * 2);
    ctx.fillStyle = b.color;
    ctx.shadowBlur = 10;
    ctx.shadowColor = b.color;
    ctx.fill();
    ctx.restore();

    if (b.life <= 0) burst.splice(i, 1);
  }
}

/* ============================================================
   7. KEYBOARD — дополнительная интерактивность
   ============================================================ */
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft')  targetRY -= 5;
  if (e.key === 'ArrowRight') targetRY += 5;
  if (e.key === 'ArrowUp')    targetRX -= 5;
  if (e.key === 'ArrowDown')  targetRX += 5;
  if (e.key === ' ')          spawnBurst(window.innerWidth / 2, window.innerHeight / 2, 40);
  if (e.key === 'r' || e.key === 'R') {
    targetRX = 0; targetRY = 0; scaleTarget = 1;
  }
});

/* ============================================================
   8. HOVER на заголовке — 3D-lift
   ============================================================ */
titleWords.forEach((word) => {
  word.addEventListener('mouseenter', () => {
    word.style.transition = 'transform 0.2s ease, filter 0.2s ease';
    word.style.filter = 'drop-shadow(0 0 40px rgba(0,229,255,0.9)) brightness(1.2)';
  });
  word.addEventListener('mouseleave', () => {
    word.style.filter = '';
  });
});

/* ============================================================
   INIT
   ============================================================ */
resizeCanvas();
initParticles();
requestAnimationFrame(mainLoop);
