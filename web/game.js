// The strip shown beside the League minimap in OBS: CPU on top, GPU below. Uses the gauges from common.js.
function renderGame(pc) {
  renderGauge(byId('gauge-cpu'), pc?.cpu);
  renderGauge(byId('gauge-gpu'), pc?.gpu);
  hotBorder(byId('game-cpu'), [pc?.cpu?.temp]);
  hotBorder(byId('game-gpu'), [pc?.gpu?.temp]);
}

async function refreshGame() {
  renderGame(await fetchJson('/api/pc', DATA_TIMEOUT_MS));
}

buildGauges();
startPage();

const fakeState = requestedFakeState();
if (fakeState) {
  renderGame(fakeState.pc);
} else {
  renderGame(null);
  refreshGame();
  setInterval(refreshGame, PC_REFRESH_MS);
}
