import os
import time
import json
import discord
import asyncio
import traceback

from discord.ext import commands
from game_monitor import ColonistMonitor, get_status

# --- MongoDB Setup ---
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["colonist_db"]  # choose any database name you like

# Try reading the Discord token from the file
DISCORD_TOKEN = None
TOKEN_FILE = "discord_token.txt"
try:
    with open(TOKEN_FILE, "r") as f:
        DISCORD_TOKEN = f.read().strip()
except Exception as e:
    print(f"Error reading token from file '{TOKEN_FILE}': {e}")
    DISCORD_TOKEN = None

# ---------------------------
# Configuration
# ---------------------------
BOT_PREFIX = "!"
MAX_HISTORY = 100  # Keep only the last 100 completed games in memory if you want

# ---------------------------
# Global Stores (Memory) [Optional]
# ---------------------------
active_monitors = {}
completed_history = {}
recent_game_ids = []

# ---------------------------
# Bot Setup
# ---------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)


# ---------------------------
# Utility Functions
# ---------------------------
def store_completed_game(game_id: str, results: tuple, channel_id: int):
    """
    Store completed game results in the global in-memory history (optional).
    Also store in Mongo if you want.
    """
    completed_history[game_id] = {
        "results": results,
        "timestamp": time.time(),
        "channel_id": channel_id,
    }
    recent_game_ids.append(game_id)
    if len(recent_game_ids) > MAX_HISTORY:
        oldest_id = recent_game_ids.pop(0)
        completed_history.pop(oldest_id, None)

    # Optionally store final results into Mongo as well
    db.completed_games.insert_one({
        "game_id": game_id,
        "results": results,
        "timestamp": time.time(),
        "channel_id": channel_id
    })


async def post_final_results(game_id: str):
    """
    Once a game ends, fetch final results from the ColonistMonitor
    and post them to the original channel.
    """
    try:
        monitor_info = active_monitors.pop(game_id, None)
        if not monitor_info:
            return

        channel_id = monitor_info["channel_id"]
        channel = bot.get_channel(channel_id)
        if not channel:
            return  # Can't find channel

        monitor = monitor_info["monitor"]
        end_game_state = monitor.end_game_state

        if not end_game_state or "players" not in end_game_state:
            # Possibly a load failure or time out
            await channel.send(f"Game **{game_id}** ended, but no final scores were retrieved.")
            store_completed_game(game_id, {}, channel_id)
            return

        # Build the final results
        final_results = []
        if len(monitor.state_log) > 0:
            monitor.get_player_names(monitor.state_log[-1][1])
        for color_str, player_info in end_game_state['players'].items():
            color_int = int(color_str)
            username = monitor.player_names.get(color_int, f"Color{color_int}")
            winner = player_info.get('winningPlayer', False)
            vps = monitor._calc_victory_points(player_info['victoryPoints'])
            final_results.append((username, vps, winner))
        
        # Store in global history (optional) and in DB
        store_completed_game(game_id, final_results, channel_id)

        # Format a response
        lines = []
        for user, vps, winner in final_results:
            if winner:
                lines.append(f"**{user}**: {vps} points (Winner!)")
            else:
                lines.append(f"{user}: {vps} points")

        msg = f"**Game {game_id}** has ended! Final scores:\n" + "\n".join(lines)
        await channel.send(msg)
    
    except Exception as e:
        print(f"Error in post_final_results for game {game_id}: {e}")
        traceback.print_exc()


async def monitor_cleanup_loop():
    """
    Background task to periodically check if any monitored games have completed.
    If completed, post final results and remove from active monitors.
    """
    await bot.wait_until_ready()
    while not bot.is_closed():
        ended_game_ids = []
        for gid, info in list(active_monitors.items()):
            monitor = info["monitor"]
            if not monitor.monitoring:
                # The game ended or timed out
                channel_id = info["channel_id"]
                channel = bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"**Game {gid}** has ended!")
                ended_game_ids.append(gid)

        for gid in ended_game_ids:
            await post_final_results(gid)

        await asyncio.sleep(5)


# ---------------------------
# Bot Commands
# ---------------------------
@bot.command(name="watch")
async def watch_game(ctx, game_id: str):
    """
    Usage: !watch #<gameId>
    Start watching a Colonist.io game in a background thread.
    """
    if game_id.startswith("#"):
        game_id = game_id[1:]

    if game_id in active_monitors:
        await ctx.send(f"Already watching game **{game_id}**.")
        return

    if game_id in completed_history:
        await ctx.send(f"Game **{game_id}** is already completed.")
        return

    monitor = ColonistMonitor(db)  # Pass the db to your monitor
    monitor.headless()
    monitor.start_driver()
    monitor.watch_game(game_id)

    active_monitors[game_id] = {
        "monitor": monitor,
        "channel_id": ctx.channel.id,
    }
    await ctx.send(f"Started watching Colonist.io game: **{game_id}**")


@bot.command(name="gamestate")
async def game_state(ctx, game_id: str):
    """
    Usage: !gamestate #<gameId>
    Retrieve current game state or final results.
    """
    if game_id.startswith("#"):
        game_id = game_id[1:]

    # Check active monitors first
    if game_id in active_monitors:
        monitor = active_monitors[game_id]["monitor"]
        status = get_status(monitor)
        if status:
            lines = [f"**{user}**: {vps} points" for user, vps in status.items()]
            msg = f"Current victory points for **{game_id}**:\n" + "\n".join(lines)
            await ctx.send(msg)
        else:
            await ctx.send(f"Game **{game_id}** is active, no state info yet.")
        return

    # Check completed history in memory
    if game_id in completed_history:
        results = completed_history[game_id]["results"]
        if not results:
            await ctx.send(f"Game **{game_id}** ended, but no final scores available.")
            return
        lines = []
        for user, vps, winner in results:
            if winner:
                lines.append(f"**{user}**: {vps} points (Winner!)")
            else:
                lines.append(f"{user}: {vps} points")
        msg = f"Final victory points for **{game_id}**:\n" + "\n".join(lines)
        await ctx.send(msg)
        return

    # Check DB if not in memory (optional if you want to support queries after memory is lost)
    found_in_db = db.completed_games.find_one({"game_id": game_id})
    if found_in_db:
        results = found_in_db.get("results", [])
        if not results:
            await ctx.send(f"Game **{game_id}** ended, but no final scores available (DB).")
            return
        lines = []
        for user, vps, winner in results:
            if winner:
                lines.append(f"**{user}**: {vps} points (Winner!)")
            else:
                lines.append(f"{user}: {vps} points")
        msg = f"Final victory points for **{game_id}** (from DB):\n" + "\n".join(lines)
        await ctx.send(msg)
        return

    await ctx.send(f"Game **{game_id}** not found in memory or DB.")


@bot.event
async def on_ready():
    print(f"Bot has logged in as {bot.user}")
    bot.loop.create_task(monitor_cleanup_loop())


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("No token found in 'discord_token.txt'. Exiting.")
        exit(1)
    bot.run(DISCORD_TOKEN)