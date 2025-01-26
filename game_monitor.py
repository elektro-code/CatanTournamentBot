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
    def __init__(self, db=None):
        """
        :param db: Optional reference to a MongoDB database object
        """
        self.db = db

        self.options = Options()
        self.driver = None

        self.monitoring = False
        self.game_id = None
        self.end_game_state = None
        self.player_names = {}

        # We'll still keep an in-memory state log, but we'll also store to DB
        self.state_log = []

        self.monitor_thread = None
        self.latest_update_time = 0
        self.max_wait_seconds = 300  # 5 minutes

    def start_driver(self):
        """Set up the Selenium Wire driver with the appropriate options and response interceptor."""
        self.driver = webdriver.Firefox(options=self.options)
        self.driver.scopes = [r'.*colonist\.io.*\.js(\?.*)?$']
        self.driver.response_interceptor = expose_game_data

    def headless(self):
        """Configure headless mode. Must be called before start_driver()."""
        if self.driver is None:
            self.options.headless = True
            self.options.add_argument('--headless')
            self.options.add_argument('--no-sandbox')
            self.options.add_argument('--disable-gpu')

    def watch_game(self, game_id: str):
        """
        Start watching a Colonist.io game in a background daemon thread.
        """
        if self.monitoring:
            print("Already monitoring a game.")
            return

        self.game_id = game_id
        self.monitoring = True

        self.monitor_thread = threading.Thread(target=self._monitor_game, daemon=True)
        self.monitor_thread.start()

    def _monitor_game(self):
        """
        Internal method to track the game. Polls ~20 times/second.
        """
        try:
            url = f"https://colonist.io/{self.game_id}"
            self.driver.get(url)

            # Wait for uiGameManager
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
                print("Game not found or uiGameManager undefined.")
                self.monitoring = False
                return

            self.latest_update_time = time.time()

            # Grab initial states
            prev_current_state = self.driver.execute_script("return window.uiGameManager.gameController.currentState;")
            prev_game_state = self.driver.execute_script("return window.uiGameManager.gameState;")

            self.player_names = self.get_player_names(prev_game_state)
            self.state_log.append((prev_current_state, prev_game_state))
            self._store_game_state(prev_current_state, prev_game_state)

            while True:
                curr_game_state = self.driver.execute_script("return window.uiGameManager.gameState;")
                if curr_game_state.get('isGameOver'):
                    # The game ended
                    time.sleep(1)
                    self.end_game_state = self.driver.execute_script("return window.endGameState;")

                    # Also store final end game state in DB
                    if self.db and self.end_game_state:
                        self.db.game_states.insert_one({
                            "game_id": self.game_id,
                            "timestamp": time.time(),
                            "current_state": "END",
                            "game_state": self.end_game_state,
                            "is_final": True
                        })
                    break
                else:
                    curr_current_state = self.driver.execute_script("return window.uiGameManager.gameController.currentState;")
                    if curr_current_state != prev_current_state:
                        # State changed => log it, store it
                        self.latest_update_time = time.time()
                        self.state_log.append((curr_current_state, curr_game_state))
                        self._store_game_state(curr_current_state, curr_game_state)

                        prev_current_state = curr_current_state
                        prev_game_state = curr_game_state

                    elapsed = time.time() - self.latest_update_time
                    if elapsed > self.max_wait_seconds:
                        print(json.dumps({"error": "Timed out waiting for game to end."}))
                        break

                time.sleep(0.05)

        except Exception as exc:
            print(json.dumps({"error": str(exc)}))
            traceback.print_exc()
        finally:
            self.monitoring = False
            if self.driver:
                self.driver.quit()

    def _store_game_state(self, current_state, game_state):
        """Insert the current game state into MongoDB, if available."""
        if self.db:
            self.db.game_states.insert_one({
                "game_id": self.game_id,
                "timestamp": time.time(),
                "current_state": current_state,
                "game_state": game_state,
                "is_final": False
            })

    def get_player_names(self, game_state: dict):
        """
        Return a dict mapping color -> username.
        """
        names = {}
        if not game_state:
            return names
        players = game_state.get('players', [])
        for p in players:
            color = p['state']['color']
            username = p['userState'].get('username', f"Color{color}")
            names[color] = username
        return names

    @staticmethod
    def _calc_victory_points(vp_dict: dict):
        """
        Colonist stores victory points in a dict (string -> int).
        Key '0' => 1x, '1' => 2x, etc., but you can adapt as needed.
        """
        multipliers = {'0': 1, '1': 2, '2': 1, '3': 2, '4': 2}
        pts = 0
        for key, multiplier in multipliers.items():
            pts += vp_dict.get(key, 0) * multiplier
        return pts

    def _calculate_victory_points(self, game_state):
        """
        Return {username: vps}
        """
        output = {}
        players = game_state.get('players', [])
        for player in players:
            username = player['userState'].get('username', "Unknown")
            vp_dict = player['state'].get('victoryPointsState', {})
            pts = self._calc_victory_points(vp_dict)
            output[username] = pts
        return output


def get_status(monitor: ColonistMonitor):
    """
    Helper to retrieve current victory points from the last known game_state.
    """
    if monitor.state_log:
        return monitor._calculate_victory_points(monitor.state_log[-1][1])
    return None


def main():
    """
    If you want to run `game_monitor.py` standalone for testing:
      python game_monitor.py <gameId>
    """
    if len(sys.argv) < 2:
        print("Usage: python game_monitor.py <gameId>")
        sys.exit(1)

    game_id = sys.argv[1]
    monitor = ColonistMonitor()
    monitor.headless()
    monitor.start_driver()
    monitor.watch_game(game_id)

    while monitor.monitoring:
        time.sleep(1)

    if monitor.end_game_state:
        output = {}
        for color_str, info in monitor.end_game_state['players'].items():
            vps = monitor._calc_victory_points(info.get('victoryPoints', {}))
            color_int = int(color_str)
            name = monitor.player_names.get(color_int, f"Color{color_int}")
            output[name] = vps
        print("Final results:", output)
    else:
        print("No final end_game_state found or monitoring timed out.")


if __name__ == "__main__":
    main()
