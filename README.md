# Colonist.io Game Monitoring Discord Bot

This repository provides a **Discord bot** that monitors [Colonist.io](https://colonist.io/) games and reports final player scores. It uses:

- **Selenium Wire** to intercept and modify Colonist's JavaScript in real-time, allowing us to observe the in-game state.
- **Chromium** (headless mode supported) for the Selenium driver.
- **MongoDB** for persistent storage of game states.
- **Discord.py** to run a bot that responds to commands such as `!watch #gameId` and `!gamestate #gameId`.
- **Docker** to containerize the bot and database for easy deployment.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)  
- [Setup](#setup) 
- [Usage](#usage)  
  - [Starting with Docker](#starting-the-bot)  
  - [Bot Commands](#bot-commands)
- [Notes/Troubleshooting](#notestroubleshooting)

---

## Requirements

- **Docker** (tested with Docker Desktop on Windows/macOS and Docker Engine on Linux).
- **Docker** Compose (comes bundled with Docker Desktop or install via your package manager).
- **A Discord Bot Token** (see [Setup](#setup)).

---

## Installation

1. **Clone or Download** this repository.

2. Install Docker:
  - **Windows/macOS:** Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/). Ensure that Docker Compose is also enabled.
  - **Linux:** Follow the official [Docker installation guide](https://docs.docker.com/engine/install/), then install Docker Compose:
  ```bash
  sudo apt-get update
  sudo apt-get install docker-compose
  ```
3. Create a directory for persistent MongoDB data:
  ```bash
  mkdir -p mongo_data
  ```

---

## Setup

### Get Your Discord Bot Token

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).  
2. Create a **New Application** or select an existing one.  
3. Under **Bot** in the left panel, create a Bot if you haven’t already, and copy the **Bot Token**.  
4. Invite the Bot to your server: under the **OAuth2 / URL Generator** (or **Bot** tab), select the bot permissions you need and generate an invite link. Then invite the bot to your chosen Discord server.  

### Prepare the `discord_token.txt` File

1. Create a file named `discord_token.txt` in the root of this repository.
2. Paste your Discord Bot Token into the file (do not include any extra spaces or lines).

---

## Usage

### Starting with Docker

1. Build and start the Docker containers:
  ```bash
  docker-compose up --build
  ```
  This will:
  - Build the `tournament_bot` container.
  - Start the `tournament_bot` (Discord bot) service.
  - Start the `mongo` (MongoDB) service.
2. Once the containers are running:
  - Check the bot logs using:
    ```bash
    docker-compose logs -f bot
    ```
  - Verify that the bot has connected to Discord. Look for:
  ```bash
  Bot has logged in as <YourBotName>#<ID>
  ```
3. To stop the containers:
    ```bash
    docker-compose down
    ```
  MongoDB data will persist in the `mongo_data` directory.

---

## Bot Commands

Once the bot is running and has joined your server, you can type commands into any text channel the bot can access:

- **`!watch #<gameId>`**
  - Example: `!watch #myGameRoom` 
  - Tells the bot to start monitoring the specified Colonist.io game (i.e., https://colonist.io/#myGameRoom). The bot will run a Selenium instance in the background, poll the game, and intercept JavaScript to track changes.
    - Once the game ends (or times out), the bot will post final scores.

- **`!gamestate #<gameId>`**
  - Example: `!gamestate #myGameRoom`
  - Shows the current victory point totals if the game is still running, or the final scores if the game has ended. 
    - If no data is available yet (e.g., the bot just started watching and the game hasn’t loaded fully), you’ll see a message about having no state info yet.

---

## Notes/Troubleshooting

### MongoDB Data Persistence

MongoDB data is stored in the `mongo_data` directory on your host machine. Ensure that this directory exists before starting the containers. If you need to back up or restore your data, simply copy or replace the contents of this directory.

### Docker-Specific Issues
  - If the containers fail to start, check the Docker logs for errors:
  ```bash
  docker-compose logs
  ```
  - If you encounter issues with Chrome or ChromeDriver versions, ensure the `Dockerfile` is using compatible versions of `chromium` and `chromium-driver`.

### General Bot Issues
  - Timeouts: By default, the monitor gives up after 5 minutes (`max_wait_seconds = 300`) of no state changes. You can increase this limit in `game_monitor.py`.
  - Running Multiple Games: The bot supports concurrent monitoring. Each `!watch #<gameId>` runs in its own thread.
  - Final Scores: Colonist’s structure can change over time. If you’re not seeing final stats, ensure that the data we read in `self.end_game_state` matches what the site actually provides.

  ---

  ## Security
  - Keep your token private. Do not commit `discord_token.txt` or your token into a public repository.
  - Use environment variables or Docker secrets for sensitive data in production environments.