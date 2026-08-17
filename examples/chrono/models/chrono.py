# Authoritative for control/count semantics at one-tick granularity.
# Debounce and clock division are below this model's abstraction.
class Chrono:
    def __init__(self):
        self.count, self.running = 0, False

    def press_reset(self):            # CTL-RST-001
        self.count, self.running = 0, False

    def press_startstop(self):        # CTL-SS-001
        self.running = not self.running

    def tick(self):                   # CNT-001, one call per second
        if self.running:
            self.count = (self.count + 1) % 100  # D-0001: wrap at 99

    @property
    def bcd(self):                    # DSP-001
        return (self.count // 10, self.count % 10)
