#!/usr/bin/env python3
import sys
import time
import json
import traceback
import threading

from seleniumwire import webdriver
from selenium.webdriver.firefox.options import Options

from colonist_intercept import expose_game_data


class ColonistMonitor:
    def __init__(self):
        # -- Initialize Firefox options --
        self.options = Options()
        self.driver = None

        # Monitoring state
        self.monitoring = False
        self.game_id = None
        self.end_game_state = None
        self.player_names = None

        # Keep a log of observed states:
        # each item in state_log is a tuple: (current_state, game_state)
        self.state_log = []

        # Thread that does the monitoring work
        self.monitor_thread = None

        # Track when we last saw a change in game state
        self.latest_update_time = 0

        # How long to wait (in seconds) for a state change before timing out
        self.max_wait_seconds = 300  # 5 minutes

    def start_driver(self):
        """Set up the Selenium Wire driver with the appropriate options and response interceptor."""
        self.driver = webdriver.Firefox(options=self.options)
        self.driver.scopes = [r'.*colonist\.io.*\.js(\?.*)?$']  # Restrict interception
        self.driver.response_interceptor = expose_game_data

    def headless(self):
        """Configure Firefox to run headless (must be called before start_driver)."""
        if self.driver is None:
            self.options.headless = True
            self.options.add_argument('--headless')
            self.options.add_argument('--no-sandbox')
            self.options.add_argument('--disable-gpu')

    def watch_game(self, game_id: str):
        """
        Start watching a Colonist.io game in a background daemon thread.
        The argument game_id represents the tail of the URL (e.g., "myGameRoom" -> https://colonist.io/myGameRoom).
        """
        if self.monitoring:
            print("Already monitoring a game. Please wait for it to finish or stop it before starting another game.")
            return

        self.game_id = game_id
        self.monitoring = True

        # Create and start a daemon thread to monitor the game
        self.monitor_thread = threading.Thread(target=self._monitor_game, daemon=True)
        self.monitor_thread.start()

    def _monitor_game(self):
        """
        Internal method that performs the actual monitoring in a loop.
        Polls 20 times per second, checks for game end or timeout.
        """
        try:
            url = f"https://colonist.io/{self.game_id}"

            # Attempt to navigate to the Colonist game page
            self.driver.get(url)

            # Wait for uiGameManager to be defined (up to 30 seconds)
            defined = False
            attempts = 0
            max_attempts = 30
            while not defined and attempts < max_attempts:
                try:
                    self.driver.execute_script("return window.uiGameManager.gameController.currentState;")
                    defined = True
                except:
                    attempts += 1
                    time.sleep(1)

            if not defined:
                print("Game not found or uiGameManager is not defined.")
                self.monitoring = False
                return

            # Record the current time (for timeouts)
            self.latest_update_time = time.time()

            # Check initial state
            prev_current_state = self.driver.execute_script("return window.uiGameManager.gameController.currentState;")
            
            prev_game_state = self.driver.execute_script("return window.uiGameManager.gameState;")
            self.player_names = self.get_player_names(prev_game_state)
            self.state_log.append((prev_current_state, prev_game_state))

            # Poll loop
            while True:
                # Check the gameState to see if the game is over
                curr_game_state = self.driver.execute_script("return window.uiGameManager.gameState;")
                if curr_game_state.get('isGameOver'):
                    # Wait a moment, then read final state (scores, etc.)
                    time.sleep(1)
                    self.end_game_state = self.driver.execute_script("return window.endGameState;")
                    # Calculate victory points and output JSON
                    break
                else:
                    # Check if currentState changed
                    curr_current_state = self.driver.execute_script("return window.uiGameManager.gameController.currentState;")
                    if curr_current_state != prev_current_state:
                        # State changed => update log/time
                        self.latest_update_time = time.time()
                        self.state_log.append((curr_current_state, curr_game_state))
                        prev_current_state = curr_current_state
                        prev_game_state = curr_game_state

                    # Check for timeout (no changes for self.max_wait_seconds)
                    elapsed = time.time() - self.latest_update_time
                    if elapsed > self.max_wait_seconds:
                        print(json.dumps({"error": "Timed out waiting for game to end."}))
                        break

                # Sleep ~ 1/20th of a second
                time.sleep(0.05)

        except Exception as exc:
            print(json.dumps({"error": str(exc)}))
            traceback.print_exc()
        finally:
            # Mark monitoring as done, close driver
            self.monitoring = False
            if self.driver:
                self.driver.quit()

    def get_player_names(self, prev_game_state: dict):
        self.player_names = {}
        for player in prev_game_state['players']:
            self.player_names[player['state']['color']] = player['userState']['username']
    
    @staticmethod
    def _calc_victory_points(state: dict):
        multipliers = {'0': 1, '1': 2, '2': 1, '3': 2, '4': 2}
        pts = 0
        for key, multiplier in multipliers.items():
            pts += state.get(key, 0) * multiplier
        return pts

    def _calculate_victory_points(self, game_state):
        """
        Given a game_state from Colonist, return a dictionary of {username: victory_points}.
        """
        output = {}
        players = game_state.get('players', [])
        for player in players:
            username = player['userState']['username']
            pts = self._calc_victory_points(player['state']['victoryPointsState'])
            output[username] = pts
        return output

def get_status(monitor: ColonistMonitor):
    if len(monitor.state_log) > 0:
        return monitor._calculate_victory_points(monitor.state_log[-1][1])

def main():
    if len(sys.argv) < 2:
        print("Usage: python game_monitor.py <gameId>")
        sys.exit(1)

    game_id = sys.argv[1]

    # Create the monitor, configure headless mode if desired
    monitor = ColonistMonitor()
    monitor.headless()
    monitor.start_driver()

    # Start watching the game
    monitor.watch_game(game_id)

    # Wait for monitoring to finish
    while monitor.monitoring:
        time.sleep(1)

    if len(monitor.state_log) > 0:
        monitor.get_player_names(monitor.state_log[-1][1])

        output = {}
        for player_color, info in monitor.end_game_state['players'].items():
            player_name = monitor.player_names.get(int(player_color))
            vps = monitor._calc_victory_points(info['victoryPoints'])
            output[player_name] = vps
        
        print(output)

if __name__ == "__main__":
    main()
