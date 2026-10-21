"""backoff.py -- capped exponential reconnect delays (pure)."""

from . import constants as C


class Backoff:
    def __init__(self, initial_s=C.BACKOFF_INITIAL_S, factor=C.BACKOFF_FACTOR,
                 max_s=C.BACKOFF_MAX_S):
        self.initial_s = float(initial_s)
        self.factor = float(factor)
        self.max_s = float(max_s)
        self._next = self.initial_s

    def next(self):
        """Delay to wait now; the following one grows, up to max_s."""
        d = self._next
        self._next = min(self._next * self.factor, self.max_s)
        return d

    def reset(self):
        """After a good connection: start again from initial_s."""
        self._next = self.initial_s
