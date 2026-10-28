"""framestate.py -- what the ingest does with a frame it cannot decode.

Pure: no network, no logging.  A small table-driven state machine, in the
style of the other constants-and-tables modules: the state is the number of
bad frames in a row; the table maps (state, event) -> (next state, actions).

    event      good_frame          bad_frame
    state
    0          0   reset           1   count
    1          0   reset           2   count
    ...        ...                 ...
    N-1        0   reset           N   count, disconnect
    N          0   reset           N   count, disconnect     (N = BAD_FRAME_LIMIT)

* good_frame: any frame that decoded (even one Sandbells then rejects or
  ignores, e.g. a sand.panel/v1 heartbeat) puts the count back to 0.
* bad_frame: count it; the link is only dropped by the Nth in a row.

    guard = FrameGuard()
    actions = guard.feed(C.FRAME_BAD)       # -> ("count",) or ("count", "disconnect")
"""

from . import constants as C


def build_table(limit=C.BAD_FRAME_LIMIT):
    """{(state, event): (next_state, actions)} for states 0..limit."""
    table = {}
    for state in range(limit + 1):
        nxt = min(state + 1, limit)
        table[(state, C.FRAME_GOOD)] = (0, (C.ACT_RESET,))
        table[(state, C.FRAME_BAD)] = (nxt, _BAD_ACTIONS[nxt == limit])
    return table


_BAD_ACTIONS = {False: (C.ACT_COUNT,), True: (C.ACT_COUNT, C.ACT_DISCONNECT)}


class FrameGuard:
    def __init__(self, limit=C.BAD_FRAME_LIMIT):
        self.limit = int(limit)
        self.table = build_table(self.limit)
        self.state = 0                    # bad frames in a row

    def feed(self, event):
        """Apply one event; returns the actions of that table row."""
        self.state, actions = self.table[(self.state, event)]
        return actions

    def reset(self):
        """A new connection starts clean."""
        self.state = 0
