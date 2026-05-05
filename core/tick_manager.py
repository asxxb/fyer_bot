class TickManager:

    def __init__(self):

        self.live_ticks = {}

    def update_tick(self, symbol, ltp):

        self.live_ticks[symbol] = {
            "ltp": ltp,
            "time": datetime.now()
        }

    def get_ltp(self, symbol):

        tick = self.live_ticks.get(symbol)

        if not tick:
            return None

        return tick["ltp"]