// Shared by the dashboard (app.js) and the game-time page (game.js): helpers, colors and the CPU/GPU gauges.
const DASH = '—';
// Colors come from the theme in styles.css, so switching themes repaints everything at once.
const ACCENT = 'var(--accent)';
const ACCENT_GLOW = 'var(--accent-glow)';
const ORANGE = 'var(--orange)';
const RED = 'var(--red)';
const LINE = 'var(--line)';
const FAINT = 'var(--text-faint)';
const GAUGE_LENGTH = 439.82; // length of the gauge's arc, used to fill it part-way
const HOT_TEMP = 75;
const PC_REFRESH_MS = 2000;
const DATA_TIMEOUT_MS = 1900;  // Long enough that a busy moment doesn't flash dashes on screen.
const THEME_REFRESH_MS = 2000;

const sofiaTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Sofia', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

const byId = (id) => document.getElementById(id);
const isNumber = (value) => typeof value === 'number';

function setText(id, text) {
  byId(id).textContent = text;
}

function setVisible(element, visible, display = '') {
  element.style.display = visible ? display : 'none';
}

function temperatureColor(temp) {
  if (temp > 85) return RED;
  if (temp > HOT_TEMP) return ORANGE;
  return ACCENT;
}

// Returns null if the server or its data source can't answer in time, so the widget shows dashes.
async function fetchJson(path, timeoutMs) {
  try {
    const response = await fetch(path, { signal: AbortSignal.timeout(timeoutMs) });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

// If the server can't answer, the page simply keeps the colors it already has.
async function refreshTheme() {
  const answer = await fetchJson('/api/theme', DATA_TIMEOUT_MS);
  if (answer) document.documentElement.dataset.theme = answer.theme;
}

const GAUGE_HTML = `
  <div class="gauge-label"></div>
  <div class="gauge-dial">
    <svg width="320" height="180" viewBox="0 0 320 180" aria-hidden="true">
      <path class="gauge-track" d="M 20 160 A 140 140 0 0 1 300 160"/>
      <path class="gauge-value" d="M 20 160 A 140 140 0 0 1 300 160"/>
    </svg>
    <div class="gauge-temp"></div>
  </div>
  <div class="gauge-usage">
    <div class="bar gauge-usage-bar"><div class="bar-fill gauge-usage-fill"></div></div>
    <div class="gauge-usage-value"></div>
  </div>
  <div class="gauge-clock">
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" class="icon-dim" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>
    <div class="gauge-clock-value"><span class="gauge-clock-number"></span> <span class="gauge-clock-unit">GHz</span></div>
  </div>`;

function buildGauges() {
  for (const gauge of [byId('gauge-cpu'), byId('gauge-gpu')]) {
    gauge.innerHTML = GAUGE_HTML;
    gauge.querySelector('.gauge-label').textContent = gauge.dataset.label;
  }
}

function renderGauge(gauge, reading) {
  const temp = reading?.temp;
  const usage = reading?.usage;
  const clock = reading?.clock;
  const hasTemp = isNumber(temp);
  const color = hasTemp ? temperatureColor(temp) : FAINT;

  const value = gauge.querySelector('.gauge-value');
  value.style.display = hasTemp ? '' : 'none';
  value.style.stroke = color;
  value.style.strokeDasharray = `${(Math.min(temp, 100) / 100 * GAUGE_LENGTH).toFixed(1)} ${GAUGE_LENGTH}`;

  const glow = hasTemp && temp > HOT_TEMP ? color : ACCENT_GLOW;
  gauge.querySelector('svg').style.filter = hasTemp ? `drop-shadow(0 0 10px ${glow})` : 'none';

  const tempText = gauge.querySelector('.gauge-temp');
  tempText.textContent = hasTemp ? `${Math.round(temp)}°` : DASH;
  tempText.style.color = color;

  gauge.querySelector('.gauge-usage-fill').style.width = `${isNumber(usage) ? usage : 0}%`;
  gauge.querySelector('.gauge-usage-value').textContent = isNumber(usage) ? `${Math.round(usage)}%` : DASH;

  gauge.querySelector('.gauge-clock-number').textContent = isNumber(clock) ? clock.toFixed(2) : DASH;
  setVisible(gauge.querySelector('.gauge-clock-unit'), isNumber(clock));
}

// The panel's border lights up orange or red when what's inside it runs hot.
function hotBorder(element, temps) {
  const known = temps.filter(isNumber);
  const hottest = known.length ? Math.max(...known) : 0;
  element.style.borderColor = hottest > HOT_TEMP ? temperatureColor(hottest) : LINE;
}

// Keeps the page at its true size, and only shrinks it to fit a smaller window.
function fitToWindow() {
  const stage = byId('stage');
  const width = stage.offsetWidth;
  const height = stage.offsetHeight;
  const scale = Math.min(1, window.innerWidth / width, window.innerHeight / height);
  stage.style.transform = `scale(${scale})`;
  stage.style.left = `${(window.innerWidth - width * scale) / 2}px`;
  stage.style.top = `${(window.innerHeight - height * scale) / 2}px`;
}

// Adding ?state=hot (or normal, paused, idle, offline, down) to the address shows fake data.
function requestedFakeState() {
  const name = new URLSearchParams(window.location.search).get('state');
  return name ? (FAKE_STATES[name] ?? FAKE_STATES.normal) : null;
}

function startPage() {
  fitToWindow();
  window.addEventListener('resize', fitToWindow);
  refreshTheme();
  setInterval(refreshTheme, THEME_REFRESH_MS);
}
