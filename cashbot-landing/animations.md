# CashBot Landing — Animation Snippets
> Стек: Vanilla JS + CSS. Тёмная тема. Градиенты #7C3AED → #2563EB. Glassmorphism. Framer-style.

---

## 1. Gradient Animated Background (Hero секция)

```html
<!-- HTML -->
<section class="hero-gradient">
  <div class="hero-noise"></div>
  <div class="hero-orb orb-1"></div>
  <div class="hero-orb orb-2"></div>
  <div class="hero-orb orb-3"></div>
  <!-- content -->
</section>
```

```css
/* CSS */
.hero-gradient {
  position: relative;
  min-height: 100vh;
  background: #0a0a0f;
  overflow: hidden;
  isolation: isolate;
}

/* Шумовая текстура поверх */
.hero-noise::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 1;
}

/* Анимированные orb-пятна */
.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
  animation: orbFloat 12s ease-in-out infinite;
}

.orb-1 {
  width: 600px; height: 600px;
  background: radial-gradient(circle, #7C3AED, transparent 70%);
  top: -200px; left: -100px;
  animation-duration: 14s;
}
.orb-2 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, #2563EB, transparent 70%);
  top: 100px; right: -150px;
  animation-duration: 10s;
  animation-delay: -4s;
}
.orb-3 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, #4F46E5, transparent 70%);
  bottom: -100px; left: 40%;
  animation-duration: 16s;
  animation-delay: -8s;
}

@keyframes orbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33%       { transform: translate(30px, -40px) scale(1.05); }
  66%       { transform: translate(-20px, 20px) scale(0.97); }
}

/* Mesh-градиент на фоне */
.hero-gradient::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 50% at 20% 30%, rgba(124,58,237,0.15) 0%, transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 70%, rgba(37,99,235,0.12) 0%, transparent 60%);
  z-index: 0;
}
```

---

## 2. Scroll-Reveal (Intersection Observer API)

```css
/* CSS — базовые состояния */
[data-reveal] {
  opacity: 0;
  transition: opacity 0.7s cubic-bezier(0.16, 1, 0.3, 1),
              transform 0.7s cubic-bezier(0.16, 1, 0.3, 1);
}

[data-reveal="fade-up"]    { transform: translateY(40px); }
[data-reveal="fade-down"]  { transform: translateY(-40px); }
[data-reveal="fade-left"]  { transform: translateX(40px); }
[data-reveal="fade-right"] { transform: translateX(-40px); }
[data-reveal="zoom-in"]    { transform: scale(0.88); }
[data-reveal="blur-in"]    { filter: blur(8px); transform: translateY(20px); }

[data-reveal].is-visible {
  opacity: 1;
  transform: translate(0) scale(1);
  filter: none;
}

/* Stagger для дочерних элементов */
[data-stagger] > * {
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1),
              transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
[data-stagger].is-visible > * {
  opacity: 1;
  transform: translateY(0);
}
[data-stagger].is-visible > *:nth-child(1) { transition-delay: 0ms; }
[data-stagger].is-visible > *:nth-child(2) { transition-delay: 100ms; }
[data-stagger].is-visible > *:nth-child(3) { transition-delay: 200ms; }
[data-stagger].is-visible > *:nth-child(4) { transition-delay: 300ms; }
[data-stagger].is-visible > *:nth-child(5) { transition-delay: 400ms; }
[data-stagger].is-visible > *:nth-child(6) { transition-delay: 500ms; }
```

```js
// JS — ScrollReveal через Intersection Observer
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      // Однократный триггер — раскомментируй если не нужен повтор
      // revealObserver.unobserve(entry.target);
    } else {
      entry.target.classList.remove('is-visible');
    }
  });
}, {
  threshold: 0.12,
  rootMargin: '0px 0px -60px 0px'
});

document.querySelectorAll('[data-reveal], [data-stagger]')
  .forEach(el => revealObserver.observe(el));

// Использование в HTML:
// <div data-reveal="fade-up">...</div>
// <div data-reveal="blur-in" style="transition-delay:200ms">...</div>
// <ul data-stagger>  <li>...</li><li>...</li>  </ul>
```

---

## 3. Floating / Parallax элементы

```html
<!-- HTML -->
<div class="parallax-scene">
  <div class="parallax-el" data-speed="0.3">💎</div>
  <div class="parallax-el" data-speed="0.6">⚡</div>
  <div class="parallax-el" data-speed="-0.2">🔮</div>
  <!-- content -->
</div>
```

```css
/* CSS */
.parallax-scene { position: relative; overflow: hidden; }

.parallax-el {
  position: absolute;
  will-change: transform;
  pointer-events: none;
  /* floating loop */
  animation: floatLoop 6s ease-in-out infinite;
}

@keyframes floatLoop {
  0%, 100% { transform: translateY(0px) rotate(0deg); }
  50%       { transform: translateY(-18px) rotate(4deg); }
}

/* Декоративные геометрические фигуры */
.deco-shape {
  position: absolute;
  border: 1px solid rgba(124, 58, 237, 0.25);
  border-radius: 50%;
  animation: shapePulse 8s ease-in-out infinite;
  pointer-events: none;
}
@keyframes shapePulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50%       { transform: scale(1.08); opacity: 0.6; }
}
```

```js
// JS — Parallax на движение мыши (плавный)
const parallaxElements = document.querySelectorAll('.parallax-el[data-speed]');
let mouseX = 0, mouseY = 0;
let currentX = 0, currentY = 0;

document.addEventListener('mousemove', e => {
  mouseX = (e.clientX / window.innerWidth  - 0.5) * 2; // -1 … 1
  mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
});

function updateParallax() {
  // Lerp — плавное догоняние курсора
  currentX += (mouseX - currentX) * 0.06;
  currentY += (mouseY - currentY) * 0.06;

  parallaxElements.forEach(el => {
    const speed = parseFloat(el.dataset.speed) * 40;
    el.style.transform = `translate(${currentX * speed}px, ${currentY * speed}px)`;
  });

  requestAnimationFrame(updateParallax);
}
requestAnimationFrame(updateParallax);

// Scroll-parallax для секций
const scrollParallaxItems = document.querySelectorAll('[data-scroll-speed]');
window.addEventListener('scroll', () => {
  const scrollY = window.scrollY;
  scrollParallaxItems.forEach(el => {
    const speed = parseFloat(el.dataset.scrollSpeed);
    el.style.transform = `translateY(${scrollY * speed}px)`;
  });
}, { passive: true });
```

---

## 4. Typewriter эффект для заголовка

```html
<!-- HTML — несколько сменяемых слов -->
<h1 class="hero-title">
  Автоматизируй
  <span class="typewriter-wrap">
    <span class="typewriter" data-words='["доход", "продажи", "конверсии", "CashFlow"]'></span>
    <span class="typewriter-cursor">|</span>
  </span>
</h1>
```

```css
/* CSS */
.typewriter-wrap {
  display: inline-flex;
  align-items: center;
  background: linear-gradient(135deg, #7C3AED, #2563EB);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.typewriter-cursor {
  display: inline-block;
  -webkit-text-fill-color: #7C3AED;
  color: #7C3AED;
  margin-left: 2px;
  animation: blink 0.9s step-end infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
```

```js
// JS — Typewriter с циклом слов
class Typewriter {
  constructor(el, words, { typeSpeed = 80, deleteSpeed = 45, pauseMs = 1800 } = {}) {
    this.el         = el;
    this.words      = words;
    this.typeSpeed  = typeSpeed;
    this.deleteSpeed = deleteSpeed;
    this.pauseMs    = pauseMs;
    this.wordIndex  = 0;
    this.charIndex  = 0;
    this.isDeleting = false;
    this.tick();
  }

  tick() {
    const word    = this.words[this.wordIndex % this.words.length];
    const current = this.isDeleting
      ? word.slice(0, --this.charIndex)
      : word.slice(0, ++this.charIndex);

    this.el.textContent = current;

    let delay = this.isDeleting ? this.deleteSpeed : this.typeSpeed;

    if (!this.isDeleting && current === word) {
      delay = this.pauseMs;
      this.isDeleting = true;
    } else if (this.isDeleting && current === '') {
      this.isDeleting = false;
      this.wordIndex++;
      delay = 300;
    }

    setTimeout(() => this.tick(), delay);
  }
}

// Инициализация
document.querySelectorAll('.typewriter').forEach(el => {
  const words = JSON.parse(el.dataset.words);
  new Typewriter(el, words);
});
```

---

## 5. Hover эффекты для карточек (Glassmorphism + Glow)

```html
<!-- HTML -->
<div class="glass-card" data-glow>
  <div class="card-glow-spot"></div>
  <div class="card-content">
    <h3>Feature Name</h3>
    <p>Description text here.</p>
  </div>
</div>
```

```css
/* CSS — Glassmorphism карточка */
.glass-card {
  position: relative;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 28px;
  overflow: hidden;
  cursor: pointer;
  transition:
    transform     0.35s cubic-bezier(0.16, 1, 0.3, 1),
    border-color  0.35s ease,
    box-shadow    0.35s ease;
}

/* Hover lift + border glow */
.glass-card:hover {
  transform: translateY(-6px) scale(1.01);
  border-color: rgba(124, 58, 237, 0.45);
  box-shadow:
    0 0 0 1px rgba(124, 58, 237, 0.2),
    0 20px 60px -10px rgba(124, 58, 237, 0.25),
    0 0 80px -20px rgba(37, 99, 235, 0.2),
    inset 0 1px 0 rgba(255,255,255,0.1);
}

/* Световое пятно под курсором (через JS) */
.card-glow-spot {
  position: absolute;
  width: 300px; height: 300px;
  border-radius: 50%;
  background: radial-gradient(circle,
    rgba(124, 58, 237, 0.18) 0%,
    transparent 70%
  );
  pointer-events: none;
  transform: translate(-50%, -50%);
  opacity: 0;
  transition: opacity 0.3s ease;
}
.glass-card:hover .card-glow-spot { opacity: 1; }

/* Shine sweep анимация при ховере */
.glass-card::after {
  content: '';
  position: absolute;
  top: -50%; left: -60%;
  width: 40%; height: 200%;
  background: linear-gradient(
    105deg,
    transparent 40%,
    rgba(255,255,255,0.06) 50%,
    transparent 60%
  );
  transform: skewX(-15deg);
  transition: left 0.6s ease;
}
.glass-card:hover::after { left: 120%; }
```

```js
// JS — Spotlight: световое пятно следует за курсором
document.querySelectorAll('[data-glow]').forEach(card => {
  const spot = card.querySelector('.card-glow-spot');
  if (!spot) return;

  card.addEventListener('mousemove', e => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    spot.style.left = `${x}px`;
    spot.style.top  = `${y}px`;

    // 3D tilt эффект
    const centerX = rect.width  / 2;
    const centerY = rect.height / 2;
    const rotateY = ((x - centerX) / centerX) * 8;
    const rotateX = ((y - centerY) / centerY) * -8;
    card.style.transform = `
      perspective(800px)
      rotateX(${rotateX}deg)
      rotateY(${rotateY}deg)
      translateY(-6px) scale(1.01)
    `;
  });

  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
});
```

---

## 6. Animated Counter для статистики

```html
<!-- HTML -->
<div class="stats-grid" data-stagger>
  <div class="stat-item" data-reveal="fade-up">
    <span class="counter" data-target="12500" data-suffix="+" data-duration="2200">0</span>
    <p>Активных пользователей</p>
  </div>
  <div class="stat-item" data-reveal="fade-up">
    <span class="counter" data-target="98.7" data-suffix="%" data-decimals="1" data-duration="1800">0</span>
    <p>Uptime гарантия</p>
  </div>
  <div class="stat-item" data-reveal="fade-up">
    <span class="counter" data-target="3.2" data-prefix="$" data-suffix="M" data-decimals="1" data-duration="2000">0</span>
    <p>Выплачено партнёрам</p>
  </div>
</div>
```

```css
/* CSS */
.stat-item {
  text-align: center;
  padding: 32px 24px;
}

.counter {
  display: block;
  font-size: clamp(2.5rem, 5vw, 4rem);
  font-weight: 800;
  background: linear-gradient(135deg, #a78bfa, #60a5fa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
  margin-bottom: 8px;
  font-variant-numeric: tabular-nums;
}
```

```js
// JS — easing + Intersection Observer триггер
function easeOutExpo(t) {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

function animateCounter(el) {
  const target   = parseFloat(el.dataset.target);
  const duration = parseInt(el.dataset.duration)  || 2000;
  const decimals = parseInt(el.dataset.decimals)  || 0;
  const prefix   = el.dataset.prefix || '';
  const suffix   = el.dataset.suffix || '';
  let startTime  = null;

  function step(timestamp) {
    if (!startTime) startTime = timestamp;
    const elapsed  = timestamp - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased    = easeOutExpo(progress);
    const value    = eased * target;

    el.textContent = prefix + value.toFixed(decimals) + suffix;

    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = prefix + target.toFixed(decimals) + suffix;
  }

  requestAnimationFrame(step);
}

// Запускаем только когда элемент попадает во viewport
const counterObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting && !entry.target.dataset.counted) {
      entry.target.dataset.counted = 'true';
      animateCounter(entry.target);
      counterObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.4 });

document.querySelectorAll('.counter').forEach(el => counterObserver.observe(el));
```

---

## 7. Particle / Blob Animated Background

### 7a. Canvas Particles (звёздное поле с линиями)

```html
<canvas id="particles-canvas" style="position:fixed;inset:0;pointer-events:none;z-index:0;opacity:0.6;"></canvas>
```

```js
// JS — Particle Network
const canvas = document.getElementById('particles-canvas');
const ctx    = canvas.getContext('2d');

let W, H, particles = [];
const CONFIG = {
  count:         80,
  maxDistance:   140,
  speed:         0.4,
  dotRadius:     1.5,
  dotColor:      '139, 92, 246',  // фиолетовый
  lineColor:     '99, 102, 241',
  bgColor:       'transparent',
};

function resize() {
  W = canvas.width  = window.innerWidth;
  H = canvas.height = window.innerHeight;
}

class Particle {
  constructor() { this.reset(); }
  reset() {
    this.x  = Math.random() * W;
    this.y  = Math.random() * H;
    this.vx = (Math.random() - 0.5) * CONFIG.speed;
    this.vy = (Math.random() - 0.5) * CONFIG.speed;
    this.r  = Math.random() * CONFIG.dotRadius + 0.5;
  }
  update() {
    this.x += this.vx;
    this.y += this.vy;
    if (this.x < 0 || this.x > W) this.vx *= -1;
    if (this.y < 0 || this.y > H) this.vy *= -1;
  }
  draw() {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${CONFIG.dotColor}, 0.7)`;
    ctx.fill();
  }
}

function init() {
  resize();
  particles = Array.from({ length: CONFIG.count }, () => new Particle());
}

function drawLines() {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx   = particles[i].x - particles[j].x;
      const dy   = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < CONFIG.maxDistance) {
        const alpha = (1 - dist / CONFIG.maxDistance) * 0.35;
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(${CONFIG.lineColor}, ${alpha})`;
        ctx.lineWidth   = 0.8;
        ctx.stroke();
      }
    }
  }
}

function loop() {
  ctx.clearRect(0, 0, W, H);
  particles.forEach(p => { p.update(); p.draw(); });
  drawLines();
  requestAnimationFrame(loop);
}

window.addEventListener('resize', () => { resize(); particles.forEach(p => p.reset()); });
init();
loop();
```

### 7b. SVG Blob с анимацией морфинга

```html
<!-- HTML — живой blob на фоне -->
<div class="blob-container" aria-hidden="true">
  <svg class="blob" viewBox="0 0 500 500" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <radialGradient id="blobGrad" cx="50%" cy="50%" r="50%">
        <stop offset="0%"   stop-color="#7C3AED" stop-opacity="0.6"/>
        <stop offset="100%" stop-color="#2563EB" stop-opacity="0"/>
      </radialGradient>
      <filter id="blobBlur">
        <feGaussianBlur stdDeviation="20"/>
      </filter>
    </defs>
    <path class="blob-path" fill="url(#blobGrad)" filter="url(#blobBlur)"/>
  </svg>
</div>
```

```css
/* CSS */
.blob-container {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.blob {
  position: absolute;
  width: 700px; height: 700px;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  opacity: 0.7;
}
```

```js
// JS — органичный морфинг blob через SVG path
function blobPath(cx, cy, r, points, randomness) {
  const step = (Math.PI * 2) / points;
  const pts  = [];
  for (let i = 0; i < points; i++) {
    const angle = step * i - Math.PI / 2;
    const rad   = r + (Math.random() - 0.5) * r * randomness;
    pts.push([
      cx + Math.cos(angle) * rad,
      cy + Math.sin(angle) * rad
    ]);
  }

  // Smooth bezier
  let d = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length; i++) {
    const curr = pts[i];
    const next = pts[(i + 1) % pts.length];
    const mx   = (curr[0] + next[0]) / 2;
    const my   = (curr[1] + next[1]) / 2;
    d += ` Q ${curr[0]},${curr[1]} ${mx},${my}`;
  }
  return d + ' Z';
}

const blobEl = document.querySelector('.blob-path');
let blobAnim;

function morphBlob() {
  const path    = blobPath(250, 250, 180, 8, 0.35);
  const keyframes = [
    { d: blobEl.getAttribute('d') || path },
    { d: path }
  ];
  blobAnim = blobEl.animate(keyframes, {
    duration: 3000 + Math.random() * 2000,
    easing: 'ease-in-out',
    fill: 'forwards'
  });
  blobAnim.onfinish = morphBlob;
}

// Инициализация первого пути
blobEl.setAttribute('d', blobPath(250, 250, 180, 8, 0.35));
morphBlob();
```

---

## Быстрый старт — всё вместе

```html
<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CashBot</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="styles.css">
</head>
<body class="bg-[#0a0a0f] text-white">
  <canvas id="particles-canvas"></canvas>

  <!-- Hero -->
  <section class="hero-gradient min-h-screen flex items-center justify-center">
    <div class="hero-orb orb-1"></div>
    <div class="hero-orb orb-2"></div>
    <div class="hero-orb orb-3"></div>
    <div class="text-center z-10 px-6">
      <h1 class="text-6xl font-black mb-6" data-reveal="blur-in">
        Автоматизируй
        <span class="typewriter-wrap block mt-2">
          <span class="typewriter" data-words='["доход","продажи","CashFlow","конверсии"]'></span>
          <span class="typewriter-cursor">|</span>
        </span>
      </h1>
    </div>
  </section>

  <!-- Features -->
  <section class="py-24 px-6">
    <div class="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6" data-stagger>
      <div class="glass-card" data-glow>
        <div class="card-glow-spot"></div>
        <div class="card-content">Карточка 1</div>
      </div>
      <div class="glass-card" data-glow>
        <div class="card-glow-spot"></div>
        <div class="card-content">Карточка 2</div>
      </div>
      <div class="glass-card" data-glow>
        <div class="card-glow-spot"></div>
        <div class="card-content">Карточка 3</div>
      </div>
    </div>
  </section>

  <!-- Stats -->
  <section class="py-20">
    <div class="stats-grid max-w-4xl mx-auto grid grid-cols-3 gap-8 text-center" data-stagger>
      <div class="stat-item">
        <span class="counter" data-target="12500" data-suffix="+">0</span>
        <p class="text-gray-400 mt-2">Пользователей</p>
      </div>
      <div class="stat-item">
        <span class="counter" data-target="98.7" data-suffix="%" data-decimals="1">0</span>
        <p class="text-gray-400 mt-2">Uptime</p>
      </div>
      <div class="stat-item">
        <span class="counter" data-prefix="$" data-target="3.2" data-suffix="M" data-decimals="1">0</span>
        <p class="text-gray-400 mt-2">Выплачено</p>
      </div>
    </div>
  </section>

  <script src="animations.js"></script>
</body>
</html>
```

> **Совет по производительности:** все анимации используют `transform` и `opacity` — они не вызывают layout reflow. `will-change: transform` добавляй только к активно анимируемым элементам, чтобы не перегрузить GPU.
