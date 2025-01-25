import os
import time
import json
import discord
import asyncio
import traceback

from discord.ext import commands
from game_monitor import ColonistMonitor, get_status


# ---------------------------
# Configuration
# ---------------------------
BOT_PREFIX = "!"
MAX_HISTORY = 100  # Keep only the last 100 completed games

# ---------------------------
# Global Stores
# ---------------------------
# Active monitors: game_id -> { "monitor": ColonistMonitor, "channel_id": int }
active_monitors = {}

# Completed games (history): game_id -> { "results": dict, "timestamp": float, "channel_id": int }
completed_history = {}
recent_game_ids = []  # used to track order and keep size <= MAX_HISTORY

# ---------------------------
# Bot Setup
# ---------------------------
intents = discord.Intents.default()
intents.message_content = True  # Needed if you want to read message content in on_message, etc.
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)


# ---------------------------
# Utility Functions
# ---------------------------
def store_completed_game(game_id: str, results: tuple, channel_id: int):
    """
    Store completed game results in the global history.
    Enforce that only the last MAX_HISTORY games are kept.
    """
    completed_history[game_id] = {
        "results": results,
        "timestamp": time.time(),
        "channel_id": channel_id,
    }
    recent_game_ids.append(game_id)

    if len(recent_game_ids) > MAX_HISTORY:
        # Remove the oldest game in the list
        oldest_id = recent_game_ids.pop(0)
        completed_history.pop(oldest_id, None)


async def post_final_results(game_id: str):
    """
    Once a game ends, fetch final results from the ColonistMonitor
    and post them to the original channel. Also store them in history.
    """
    try:
        monitor_info = active_monitors.pop(game_id, None)
        if not monitor_info:
            return

        channel_id = monitor_info["channel_id"]
        channel = bot.get_channel(channel_id)
        if not channel:
            return  # Can't find channel, might have been deleted or bot lacks permissions

        monitor = monitor_info["monitor"]
        end_game_state = monitor.end_game_state

        # If the end_game_state never populated or is None, the game might have failed
        if not end_game_state or "players" not in end_game_state:
            # Possibly a load failure or time out
            await channel.send(f"Game **{game_id}** ended, but we couldn't retrieve final scores (timed out or error).")
            store_completed_game(game_id, {}, channel_id)
            return

        # Build the final results from the end_game_state
        final_results = []
        if len(monitor.state_log) > 0:
            monitor.get_player_names(monitor.state_log[-1][1])
        for color_str, player_info in end_game_state['players'].items():
            print(player_info)
            color_int = int(color_str)
            username = monitor.player_names.get(color_int, f"Color{color_int}")
            winner = player_info.get('winningPlayer', False)
            vps = monitor._calc_victory_points(player_info['victoryPoints'])
            final_results.append((username, vps, winner))
        
        # Store in global history
        store_completed_game(game_id, final_results, channel_id)

        # Format a response
        lines = []
        for user, vps, winner in final_results:
            lines.append(f"{user}: {vps} points" if not winner else f"**{user}**: {vps} points")
        msg = f"**Game {game_id}** has ended! Final scores:\n" + "\n".join(lines)
        await channel.send(msg)
    
    except Exception as e:
        print(f"Error in post_final_results for game {game_id}: {e}")
        traceback.print_exc()
        # Optionally send a Discord message to the channel about the error

async def monitor_cleanup_loop():
    """
    Background task that periodically checks if any monitored games
    have completed. If completed, we retrieve final results and post them.
    """
    await bot.wait_until_ready()
    while not bot.is_closed():
        # We can check which monitors have finished by checking the .monitoring flag
        # or by simply seeing if the thread ended (ColonistMonitor sets .monitoring = False).
        ended_game_ids = []
        for gid, info in list(active_monitors.items()):
            monitor = info["monitor"]
            if not monitor.monitoring:
                # This means the game ended or load failed. We'll collect results.
                msg = f"**Game {gid}** has ended!"
                channel_id = info["channel_id"]
                channel = bot.get_channel(channel_id)
                await channel.send(msg)
                ended_game_ids.append(gid)

        # For each ended game, post final results
        for gid in ended_game_ids:
            await post_final_results(gid)

        await asyncio.sleep(5)  # Check every 5 seconds


# ---------------------------
# Bot Commands
# ---------------------------
@bot.command(name="watch")
async def watch_game(ctx, game_id: str):
    """
    Usage: !watch #<gameId>
    Start watching a Colonist.io game in a background daemon thread.
    """
    # In case the user typed "!watch #ABC", we can strip the '#' if present
    if game_id.startswith("#"):
        game_id = game_id[1:]

    if game_id in active_monitors:
        await ctx.send(f"Already watching game **{game_id}**.")
        return

    # If game is in completed history, we also consider that "ended"
    # but let's allow re-watch if you want. That's your choice.
    # For simplicity, let's just say "it's in history"
    if game_id in completed_history:
        await ctx.send(f"Game **{game_id}** is already in completed history.")
        return

    # Create the monitor, configure headless mode, and start it
    monitor = ColonistMonitor()
    monitor.headless()
    monitor.start_driver()
    monitor.watch_game(game_id)

    # Store reference
    active_monitors[game_id] = {
        "monitor": monitor,
        "channel_id": ctx.channel.id,
    }

    await ctx.send(f"Started watching Colonist.io game: **{game_id}**")


@bot.command(name="gamestate")
async def game_state(ctx, game_id: str):
    """
    Usage: !gamestate #<gameId>
    Retrieve current game state (victory points).
    - If the game is still active, returns the latest known state.
    - If the game has ended, returns final results from history.
    - If not found, indicates an error.
    """
    if game_id.startswith("#"):
        game_id = game_id[1:]

    # Check active monitors first
    if game_id in active_monitors:
        monitor = active_monitors[game_id]["monitor"]
        status = get_status(monitor)  # uses the _calculate_victory_points on the last known game_state
        if status:
            # Format a response
            lines = [f"**{user}**: {vps} points" for user, vps in status.items()]
            msg = f"Current victory points for **{game_id}**:\n" + "\n".join(lines)
            await ctx.send(msg)
        else:
            await ctx.send(f"Game **{game_id}** is active, but we have no state info yet.")
        return

    # Check completed history
    if game_id in completed_history:
        results = completed_history[game_id]["results"]
        if not results:
            await ctx.send(f"Game **{game_id}** ended, but no final scores available.")
            return
        # Format a response
        lines = []
        for user, vps, winner in results:
            lines.append(f"{user}: {vps} points" if not winner else f"**{user}**: {vps} points")
        msg = f"Final victory points for **{game_id}**:\n" + "\n".join(lines)       
        await ctx.send(msg)
        return

    # Otherwise, not found
    await ctx.send(f"Game **{game_id}** is neither active nor in history.")


# ---------------------------
# Bot Events
# ---------------------------
@bot.event
async def on_ready():
    print(f"Bot has logged in as {bot.user}")
    # Start the cleanup task
    bot.loop.create_task(monitor_cleanup_loop())


# ---------------------------
# Main Entry
# ---------------------------
if __name__ == "__main__":
    # Retrieve your bot token (recommended to store in ENV variable)
    token = os.environ.get("DISCORD_TOKEN", "<YOUR_DISCORD_BOT_TOKEN_HERE>")

    # Run the bot
    bot.run(token)
