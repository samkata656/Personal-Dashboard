// The color switch: clicking a button tells the server, and the dashboard follows within 2 seconds.
const options = document.querySelectorAll('[data-theme-choice]');
const message = document.getElementById('switch-message');

function showTheme(theme) {
  document.documentElement.dataset.theme = theme;
  for (const option of options) {
    option.setAttribute('aria-pressed', String(option.dataset.themeChoice === theme));
  }
}

async function chooseTheme(theme) {
  message.textContent = '';
  try {
    const response = await fetch('/api/theme', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme }),
    });
    if (!response.ok) throw new Error(response.statusText);
    showTheme(theme);
  } catch {
    message.textContent = "Couldn't change the colors. Check that the dashboard is running, then try again.";
  }
}

async function start() {
  for (const option of options) {
    option.addEventListener('click', () => chooseTheme(option.dataset.themeChoice));
  }
  try {
    const response = await fetch('/api/theme');
    showTheme((await response.json()).theme);
  } catch {
    message.textContent = "Couldn't read the current colors. Check that the dashboard is running, then reload this page.";
  }
}

start();
