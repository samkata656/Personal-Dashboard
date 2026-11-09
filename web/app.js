// Draws the whole dashboard from one object of readings. A missing reading shows as a dash.
// Helpers, colors and the gauges live in common.js.
const MIN_BAR_HEIGHT = 8;
const CLOCK_REFRESH_MS = 1000;
const MUSIC_REFRESH_MS = 1000;
// The server asks OpenRouter every 5 minutes. The page checks the server's latest answer more often.
const OPENROUTER_REFRESH_MS = 30000;
// The server asks Anthropic every 5 minutes; checking the server often picks up new numbers quickly.
const CLAUDE_REFRESH_MS = 5000;
const DAY_MS = 24 * 60 * 60 * 1000;

const sofiaDate = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Sofia', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
});
const sofiaWeekdayTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Sofia', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

// The longest dates don't fit at full size, so only those shrink to stay on one line.
function fitDate() {
  const date = byId('clock-date');
  date.style.fontSize = '';
  if (date.scrollWidth > date.clientWidth) {
    date.style.fontSize = `${Math.floor(60 * date.clientWidth / date.scrollWidth)}px`;
  }
}

function renderClock(clock) {
  setText('clock-time', clock.time);
  setText('clock-date', clock.date);
  fitDate();
}

function readClock(now) {
  const part = Object.fromEntries(sofiaDate.formatToParts(now).map(({ type, value }) => [type, value]));
  return {
    time: sofiaTime.format(now),
    date: `${part.weekday}, ${part.day} ${part.month} ${part.year}`,
  };
}

function tickClock() {
  const clock = readClock(new Date());
  const changed = clock.time !== byId('clock-time').textContent
    || clock.date !== byId('clock-date').textContent;
  if (changed) renderClock(clock);
}

// Within a day only the time is needed; further off, the weekday too.
function formatReset(resetsAt, now) {
  const when = resetsAt * 1000;
  return `Resets ${(when - now < DAY_MS ? sofiaTime : sofiaWeekdayTime).format(new Date(when))}`;
}

function renderUsage(name, usage, now) {
  const known = isNumber(usage?.used) && isNumber(usage?.resets_at);
  setText(`${name}-used`, known ? `${Math.round(usage.used)}%` : DASH);
  setText(`${name}-reset`, known ? formatReset(usage.resets_at, now) : '');
  byId(`${name}-fill`).style.width = known ? `${Math.min(Math.max(usage.used, 0), 100)}%` : '0';
}

function renderClaude(claude) {
  const now = Date.now();
  renderUsage('claude-session', claude?.five_hour, now);
  renderUsage('claude-week', claude?.seven_day, now);
}

function renderArt(music) {
  const image = byId('music-art-image');
  setVisible(byId('music-art-fake'), Boolean(music.fakeArt));
  setVisible(image, Boolean(music.artUrl));
  setVisible(byId('music-art-none'), !music.fakeArt && !music.artUrl, 'flex');

  // Only load the picture again when the song's picture has actually changed.
  if (music.artUrl && image.getAttribute('src') !== music.artUrl) {
    image.src = music.artUrl;
  }
}

function renderMusic(music) {
  const hasTrack = music.status === 'playing' || music.status === 'paused';
  const paused = music.status === 'paused';

  setVisible(byId('music-track'), hasTrack);
  setVisible(byId('music-idle'), !hasTrack);

  if (!hasTrack) {
    const down = music.status === 'down';
    setText('music-idle-title', down ? DASH : 'Nothing playing');
    setText('music-idle-subtitle', down ? '' : 'Waiting for music');
    return;
  }

  setVisible(byId('music-icon-play'), !paused);
  setVisible(byId('music-icon-pause'), paused);
  setVisible(byId('music-paused-label'), paused);

  renderArt(music);
  byId('music-art').style.opacity = paused ? 0.4 : 1;

  setText('music-title', music.title);
  byId('music-title').style.color = paused ? 'var(--text-dim)' : 'var(--text)';
  setText('music-artist', music.artist);

  setText('music-position', music.position ?? DASH);
  setText('music-duration', music.duration ?? DASH);

  const fill = byId('music-fill');
  fill.style.width = `${music.percent ?? 0}%`;
  fill.style.background = paused ? 'var(--paused-fill)' : ACCENT;
  fill.style.boxShadow = paused ? 'none' : '0 0 12px var(--music-glow)';
}

function formatMoney(amount) {
  if (!isNumber(amount)) return DASH;
  return `${amount < 0 ? '-' : ''}$${Math.abs(amount).toFixed(2)}`;
}

function renderOpenRouter(openrouter) {
  const online = openrouter.online;
  const color = online ? ACCENT : FAINT;

  byId('or-icon').style.stroke = color;
  setVisible(byId('or-offline'), !online, 'flex');
  setVisible(byId('or-online'), online, 'flex');
  setVisible(byId('or-last-updated'), !online && openrouter.lastUpdated);

  const credits = byId('or-credits');
  credits.textContent = formatMoney(openrouter.credits);
  credits.style.color = color;
  credits.style.textShadow = online ? `0 0 22px ${ACCENT_GLOW}` : 'none';
  setVisible(byId('or-left'), isNumber(openrouter.credits));

  if (!online) {
    setText('or-last-updated', `Last updated ${openrouter.lastUpdated}`);
    return;
  }

  setText('or-spend', formatMoney(openrouter.spent));

  const highest = Math.max(...openrouter.days.map(([, amount]) => amount), 0);
  const bars = byId('or-bars');
  bars.replaceChildren(...openrouter.days.map(([day, amount], index) => {
    const column = document.createElement('div');
    column.className = 'or-bar-column';
    if (index === openrouter.days.length - 1) column.classList.add('today');

    const bar = document.createElement('div');
    bar.className = 'or-bar';
    // Even a tiny amount stays visible next to a much bigger day.
    bar.style.height = `${amount > 0 ? Math.max(Math.round(amount / highest * 110), MIN_BAR_HEIGHT) : 0}px`;

    const label = document.createElement('div');
    label.className = 'or-bar-day';
    label.textContent = day;

    column.append(bar, label);
    return column;
  }));
}

function renderPc(pc) {
  renderGauge(byId('gauge-cpu'), pc?.cpu);
  renderGauge(byId('gauge-gpu'), pc?.gpu);
  hotBorder(byId('pc'), [pc?.cpu?.temp, pc?.gpu?.temp]);
  renderMemory('vram', pc?.vram);
  renderMemory('ram', pc?.ram);
}

function renderMemory(name, memory) {
  const used = memory?.used;
  const total = memory?.total;
  const known = isNumber(used) && isNumber(total);
  setText(`${name}-used`, known ? used.toFixed(1) : DASH);
  setText(`${name}-total`, known ? `/ ${Math.round(total)} GB` : '');
  byId(`${name}-fill`).style.width = known ? `${(used / total * 100).toFixed(1)}%` : '0';
}

async function refreshPc() {
  renderPc(await fetchJson('/api/pc', DATA_TIMEOUT_MS));
}

function formatTime(seconds) {
  if (!isNumber(seconds)) return null;
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total / 60) % 60;
  const secs = String(total % 60).padStart(2, '0');
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${secs}` : `${minutes}:${secs}`;
}

function musicView(music) {
  const { position, duration } = music;
  return {
    ...music,
    position: formatTime(position),
    duration: formatTime(duration),
    percent: isNumber(position) && duration > 0 ? position / duration * 100 : 0,
    artUrl: music.art_id ? `/api/music/art?id=${music.art_id}` : null,
  };
}

async function refreshMusic() {
  const music = await fetchJson('/api/music', DATA_TIMEOUT_MS);
  renderMusic(music ? musicView(music) : { status: 'down' });
}

async function refreshOpenRouter() {
  const openrouter = await fetchJson('/api/openrouter', 5000);
  if (!openrouter) {
    renderOpenRouter({ online: false, credits: null, lastUpdated: null });
    return;
  }
  const updated = openrouter.last_updated;
  renderOpenRouter({ ...openrouter, lastUpdated: updated ? sofiaTime.format(new Date(updated * 1000)) : null });
}

async function refreshClaude() {
  renderClaude(await fetchJson('/api/claude', DATA_TIMEOUT_MS));
}

function startLive() {
  tickClock();
  setInterval(tickClock, CLOCK_REFRESH_MS);

  renderPc(null);
  refreshPc();
  setInterval(refreshPc, PC_REFRESH_MS);

  renderMusic({ status: 'idle' });
  refreshMusic();
  setInterval(refreshMusic, MUSIC_REFRESH_MS);

  renderOpenRouter({ online: false, credits: null, lastUpdated: null });
  refreshOpenRouter();
  setInterval(refreshOpenRouter, OPENROUTER_REFRESH_MS);

  renderClaude(null);
  refreshClaude();
  setInterval(refreshClaude, CLAUDE_REFRESH_MS);
}

function render(state) {
  renderClock(state.clock);
  renderClaude(state.claude);
  renderMusic(state.music);
  renderOpenRouter(state.openrouter);
  renderPc(state.pc);
}

buildGauges();
startPage();
document.fonts.ready.then(fitDate);

const fakeState = requestedFakeState();
if (fakeState) {
  render(fakeState);
} else {
  startLive();
}
