# Personal Dashboard

An always-on dashboard for a small second monitor (built for a 10.5" 1920×1280 screen), shown through OBS Studio.

![Dashboard design](Gaming%20Side%20Monitor%20Dashboard-png/Normal.png)

It shows:

- **Clock and date**
- **Claude plan usage**: the 5-hour session and weekly limits, with reset times
- **Now playing**: song, artist, cover art and progress, from Windows' media controls (Spotify, browsers, etc.)
- **OpenRouter**: credits left and spending over the last 7 days
- **PC stats**: CPU and GPU temperature, load and clock speed, plus VRAM and RAM

While League of Legends is running, OBS switches to a **Minimap** scene, with the game's minimap next to a CPU/GPU strip. It switches back when the game closes.

If one data source is down, only that widget shows "—". Everything else keeps working.

## How it works

```
Windows media controls ─┐
LibreHardwareMonitor ───┤
OpenRouter API ─────────┼──> Python server (127.0.0.1:8787) ──> web page ──> OBS Browser Source ──> monitor
Anthropic usage API ────┘            │
                                     └──> OBS WebSocket (scene switching)
```

- `server/` is a small Python server that uses only the standard library, plus `winrt` for media info. It collects the data and serves the page.
- `web/` holds the page itself: plain HTML, CSS and JavaScript, no build step.
- Secrets stay in `.env` on your PC. The page never sees them.

## Requirements

- **Windows 10 or 11**
- **Python 3.10+**
- **OBS Studio 30+**, which has the WebSocket server built in
- **[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)** with its web server turned on (Options → Remote Web Server → port 8085), for the PC stats
- An **OpenRouter management key**, for the OpenRouter widget (optional)
- **Claude** (desktop app or Claude Code) signed in on the same PC, for the Claude usage bars (optional)

## Setup

1. **Get the code and install the packages**

   ```bash
   git clone https://github.com/samkata656/Personal-Dashboard.git
   cd Personal-Dashboard
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

2. **Add your secrets**

   Copy `.env.example` to `.env` and fill it in:

   ```
   OPENROUTER_MANAGEMENT_KEY=your OpenRouter management key (openrouter.ai → Settings → Management Keys)
   OBS_WEBSOCKET_PASSWORD=your OBS WebSocket password (OBS → Tools → WebSocket Server Settings)
   ```

   `.env` is in `.gitignore`, so it never gets committed. You can edit it while the server runs.

3. **Start the server**

   ```bash
   .venv\Scripts\python server\main.py
   ```

   Then open <http://localhost:8787> to check it.

4. **Set up OBS**

   - Set the canvas and output resolution to **1920×1280**.
   - Make a scene called **`Dashboard`** with a Browser Source at `http://localhost:8787`, sized 1920×1280.
   - Optional: make a scene called **`Minimap`** with a Game Capture of League (cropped to the minimap) and a Browser Source at `http://localhost:8787/game.html`, sized 640×1280.
   - Right-click the scene preview → **Fullscreen Projector** → pick the side monitor.

   Scene names must match exactly, including capital letters. To keep the dashboard on screen during games, set `MINIMAP_DURING_GAMES = False` in `server/obs_switcher.py`.

5. **Start it at login (optional)**

   Put a shortcut in your Startup folder (`Win+R` → `shell:startup`):

   - **Target:** `<project folder>\.venv\Scripts\pythonw.exe "<project folder>\server\autostart.py"`
   - **Start in:** `<project folder>`

   At login it starts the server with no window and then opens OBS minimized to the tray. The server's messages go to `data/dashboard.log`.

## Make it fit your PC

Some values are set for the original hardware and location:

| What | Where |
|---|---|
| CPU/GPU sensor names (Intel CPU, AMD GPU) | `server/pc_stats.py`. Open `http://localhost:8085/data.json` to find your own sensor IDs. |
| CPU/GPU names on the gauges | `web/index.html` and `web/game.html` |
| Time zone (`Europe/Sofia`) | `web/common.js` and `web/app.js` |
| OBS install path | `server/autostart.py` |
| Game that triggers the Minimap scene | `GAME_PROCESS` in `server/obs_switcher.py` |

## Extras

- **Colors:** open <http://localhost:8787/colors.html> to switch between the black-and-white and neon themes. The dashboard follows within 2 seconds.
- **Test the look with fake data:** add `?state=normal`, `hot`, `paused`, `idle`, `offline` or `down` to the address, for example `http://localhost:8787/?state=hot`.
- **Claude Code status line (optional backup):** Claude Code can also send its usage readings to the dashboard. Add this to `~/.claude/settings.json`:

  ```json
  "statusLine": {
    "type": "command",
    "command": "<project folder>/.venv/Scripts/python.exe -B <project folder>/server/claude_statusline.py"
  }
  ```

## About the Claude usage numbers

The server reads the Claude login that the Claude apps save in `~/.claude/.credentials.json`. Every 5 minutes it uses that login to ask Anthropic for your plan usage. If Anthropic asks it to slow down, it waits longer each time, up to 30 minutes. The login is only ever sent to `api.anthropic.com`. It never reaches the page, the log or this repository.

This uses an **unofficial** Anthropic endpoint, the same one Claude's own usage screen uses. It may change or stop working without notice.

## Security

- The server only listens on this PC (`127.0.0.1` and `::1`), so other devices on your network can't reach it.
- It only answers requests sent to `localhost`, `127.0.0.1` or `[::1]`. This stops websites from reading the dashboard through "DNS rebinding".
- It only serves files from `web/`, so `.env` and everything else stay private.
- The color switch only accepts JSON requests, which other websites can't send to it.

## Tests

```bash
cd server
..\.venv\Scripts\python -m unittest test_autostart test_obs test_openrouter test_music test_pc_stats test_theme test_claude_usage test_main
```

## Credits

Fonts: [Orbitron](https://github.com/theleagueof/orbitron) and [Exo 2](https://github.com/googlefonts/Exo-2.0), both under the SIL Open Font License (see `web/fonts/`).
