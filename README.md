# Colonist.io Game Monitoring Discord Bot

This repository provides a **Discord bot** that monitors [Colonist.io](https://colonist.io/) games and reports final player scores. It uses:

- **Selenium Wire** to intercept and modify Colonist's JavaScript in real-time, allowing us to observe the in-game state.  
- **Firefox** (headless mode supported) for the Selenium driver.  
- **Discord.py** to run a bot that responds to commands such as `!watch #gameId` and `!gamestate #gameId`.

---

## Table of Contents

- [Requirements](#requirements)  
- [Installation](#installation)  
- [Setup](#setup)  
- [Usage](#usage)  
  - [Starting the Bot](#starting-the-bot)  
  - [Bot Commands](#bot-commands)
- [Notes/Troubleshooting](#notestroubleshooting)

---

## Requirements

- **Python 3.7+** (tested on 3.9 and 3.10, but other versions may work).  
- **Geckodriver** (the Firefox driver for Selenium).  
  - On Linux, you can usually install with your package manager (`apt-get install firefox-geckodriver` on Ubuntu, for example).  
  - On macOS, install via [Homebrew](https://brew.sh/) with `brew install geckodriver`.  
  - On Windows, download from [Mozilla’s GitHub](https://github.com/mozilla/geckodriver/releases) and place `geckodriver.exe` in your PATH.  
- **A Discord Bot Token** (see [Setup](#setup) below).  
- **Firefox** installed. The code uses the default Firefox browser for Selenium.

---

## Installation

1. **Clone or Download** this repository.

2. In the folder containing `main.py`, **install required Python dependencies**. For example:
   ```bash
   pip install selenium-wire discord.py
   ```
3. Verify that Geckodriver is installed and in your PATH by running:
   ```bash
   geckodriver --version
   ```
4. (Optional) Create a virtual environment (recommended) to avoid version conflicts:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # or
    venv\Scripts\activate     # On Windows
    
    pip install selenium-wire discord.py
    ```
## Setup

### Get Your Discord Bot Token

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).  
2. Create a **New Application** or select an existing one.  
3. Under **Bot** in the left panel, create a Bot if you haven’t already, and copy the **Bot Token**.  
4. Invite the Bot to your server: under the **OAuth2 / URL Generator** (or **Bot** tab), select the bot permissions you need and generate an invite link. Then invite the bot to your chosen Discord server.  
5. In production, keep your token **private**. For safety, store it in an environment variable:
   ```bash
   export DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
   ```
   On Windows, you might do:
   ```bash
   $env:DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
   ```

Alternatively, you can paste the token directly into the code in main.py, but this is not recommended for production use.

## Usage

### Starting the Bot

1. Make sure your environment is activated (if using a virtual environment).
2. Run the main.py script:
    ```bash
    python main.py
    ```
3. If you’re storing your token as an environment variable, ensure it’s set before running. Otherwise, replace the line in main.py where we do:
    ```bash
    token = os.environ.get("DISCORD_TOKEN", "<YOUR_DISCORD_BOT_TOKEN_HERE>")
    ```
    with your actual token (not recommended for public repos).

## Bot Commands

Once the bot is running and has joined your server, you can type commands into any text channel the bot can access:

- **`!watch #<gameId>`**
  - Example: `!watch #myGameRoom` 
  - Tells the bot to start monitoring the specified Colonist.io game (i.e., https://colonist.io/#myGameRoom). The bot will run a Selenium instance in the background, poll the game, and intercept JavaScript to track changes.
    - Once the game ends (or times out), the bot will post final scores.

- **!gamestate #<gameId>**
  - Example: !gamestate #myGameRoom
  - Shows the current victory point totals if the game is still running, or the final scores if the game has ended. 
    - If no data is available yet (e.g., the bot just started watching and the game hasn’t loaded fully), you’ll see a message about having no state info yet.

## Notes/Troubleshooting
  - Timeouts: By default, the monitor gives up after 5 minutes (max_wait_seconds = 300) of no state changes. You can increase this limit in game_monitor.py.
  - Running Multiple Games: The bot supports concurrent monitoring. Each !watch #<gameId> runs in its own thread.
  - Final Scores: Colonist’s structure can change over time. If you’re not seeing final stats, ensure that the data we read in self.end_game_state matches what the site actually provides.
  - Geckodriver Issues: If you see errors about Firefox or Geckodriver not found, confirm they’re installed and in your system PATH.
  - Keep the Last 100 Games: main.py stores only the 100 most recent completed games in its history (completed_history dictionary). Old entries are dropped automatically.
  - Security: Don’t commit your Discord token into a public repository. Always keep the token private or in environment variables.
