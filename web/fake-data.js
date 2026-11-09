// Pretend readings for testing the look of the page. Pick one with ?state=hot etc.
// Without ?state= in the address, the page shows real data instead.
const FAKE_NORMAL = {
  clock: { time: '20:44', date: 'Sunday, 25 October 2026' },
  claude: {
    five_hour: { used: 23.5, resets_at: Date.now() / 1000 + 2.5 * 3600 },
    seven_day: { used: 41, resets_at: Date.now() / 1000 + 3.2 * 86400 },
  },
  music: { status: 'playing', title: 'Midnight Circuit', artist: 'Nova Lights', position: '2:14', duration: '3:48', percent: 59, fakeArt: true },
  openrouter: {
    online: true,
    credits: 12.40,
    spent: 3.10,
    days: [['M', 0.32], ['T', 0.51], ['W', 0.18], ['T', 0.64], ['F', 0.40], ['S', 0.73], ['S', 0.32]],
    lastUpdated: '18:02',
  },
  pc: {
    cpu: { temp: 52, usage: 18, clock: 4.60 },
    gpu: { temp: 61, usage: 34, clock: 2.14 },
    vram: { used: 5.4, total: 16 },
    ram: { used: 14.2, total: 32 },
  },
};

const FAKE_OFFLINE_OPENROUTER = { online: false, credits: null, spent: null, days: [], lastUpdated: '18:02' };

const FAKE_STATES = {
  normal: FAKE_NORMAL,
  hot: {
    ...FAKE_NORMAL,
    claude: {
      five_hour: { used: 96, resets_at: Date.now() / 1000 + 0.4 * 3600 },
      seven_day: { used: 88, resets_at: Date.now() / 1000 + 1.5 * 86400 },
    },
    pc: {
      cpu: { temp: 79, usage: 92, clock: 4.70 },
      gpu: { temp: 88, usage: 99, clock: 2.87 },
      vram: { used: 15.1, total: 16 },
      ram: { used: 24.8, total: 32 },
    },
  },
  paused: { ...FAKE_NORMAL, music: { ...FAKE_NORMAL.music, status: 'paused' } },
  idle: { ...FAKE_NORMAL, music: { status: 'idle' } },
  offline: { ...FAKE_NORMAL, openrouter: FAKE_OFFLINE_OPENROUTER },
  // Every data source down at once: only the clock is left.
  down: {
    ...FAKE_NORMAL,
    claude: null,
    music: { status: 'down' },
    openrouter: { ...FAKE_OFFLINE_OPENROUTER, lastUpdated: null },
    pc: null,
  },
};
