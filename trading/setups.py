"""Zone-style trade setups: two entry zones, each with its own stop-loss and
four take-profits. After TP1 the stop moves to the entry price (break-even).

The same `Setup.step()` drives both the backtest and the live bot, so the
alerts the bot sends follow exactly the rules that were backtested.

Position management per zone: the position is split into 4 equal parts,
one part is closed at each TP. Stops are checked before targets inside a
candle (pessimistic), and a zone is not allowed to hit a target on the same
candle it was filled.
"""
import json
from dataclasses import asdict, dataclass, field

import pandas as pd

N_TP = 4


@dataclass
class Zone:
    top: float          # edge of the zone nearest to the signal price
    bottom: float       # far edge (towards the stop)
    sl: float
    tps: list
    status: str = "pending"   # pending | open | closed | cancelled
    entry: float = None
    filled_at: str = None
    tp_hit: int = 0
    be: bool = False          # stop moved to entry after TP1
    pnl: float = 0.0          # realised, in $ per 1 unit of total position
    exit_reason: str = None   # tp | sl | be | timeout | cancelled

    @property
    def stop(self) -> float:
        return self.entry if self.be else self.sl


@dataclass
class Setup:
    symbol: str
    side: int                 # 1 = BUY, -1 = SELL
    price: float              # close of the signal candle
    signal_time: str          # ISO, end of the signal candle
    expires: str              # pending zones are cancelled after this
    max_hold_hours: float
    zones: list = field(default_factory=list)
    last_time: str = None     # last processed candle (ISO)

    # --- persistence ---
    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "Setup":
        data = json.loads(text)
        data["zones"] = [Zone(**z) for z in data["zones"]]
        return cls(**data)

    @property
    def active(self) -> bool:
        return any(z.status in ("pending", "open") for z in self.zones)

    @property
    def pnl(self) -> float:
        return sum(z.pnl for z in self.zones)

    # --- simulation ---
    def _close(self, z: Zone, price: float, reason: str, events: list, i: int, ts):
        parts_left = N_TP - z.tp_hit
        z.pnl += self.side * (price - z.entry) * parts_left / N_TP
        z.status, z.exit_reason = "closed", reason
        events.append((ts, i, reason, price))

    def step(self, ts: pd.Timestamp, o: float, h: float, l: float, c: float) -> list:
        """Feed one candle (starting at `ts`). Returns events:
        (time, zone_index, kind, price) with kind in
        filled | tp1..tp4 | sl | be | timeout | cancelled."""
        events = []
        s = self.side
        for i, z in enumerate(self.zones):
            if z.status == "pending":
                # the move happened without us: price reached TP1 before the zone filled
                if (h >= z.tps[0]) if s == 1 else (l <= z.tps[0]):
                    z.status, z.exit_reason = "cancelled", "cancelled"
                    events.append((ts, i, "cancelled", None))
                    continue
                if ts >= pd.Timestamp(self.expires):
                    z.status, z.exit_reason = "cancelled", "cancelled"
                    events.append((ts, i, "cancelled", None))
                    continue
                touched = (l <= z.top) if s == 1 else (h >= z.top)
                if not touched:
                    continue
                # limit order at the zone edge; a gap through it fills at the open
                z.entry = min(o, z.top) if s == 1 else max(o, z.top)
                z.status, z.filled_at = "open", ts.isoformat()
                events.append((ts, i, "filled", z.entry))
                if (l <= z.sl) if s == 1 else (h >= z.sl):
                    self._close(z, z.sl, "sl", events, i, ts)
                continue

            if z.status != "open":
                continue
            stop = z.stop
            if (l <= stop) if s == 1 else (h >= stop):
                self._close(z, stop, "be" if z.be else "sl", events, i, ts)
                continue
            while z.tp_hit < N_TP:
                tp = z.tps[z.tp_hit]
                if not ((h >= tp) if s == 1 else (l <= tp)):
                    break
                z.pnl += s * (tp - z.entry) / N_TP
                z.tp_hit += 1
                z.be = True
                events.append((ts, i, f"tp{z.tp_hit}", tp))
            if z.tp_hit == N_TP:
                z.status, z.exit_reason = "closed", "tp"
                continue
            held = (ts - pd.Timestamp(z.filled_at)).total_seconds() / 3600
            if held >= self.max_hold_hours:
                self._close(z, c, "timeout", events, i, ts)
        self.last_time = ts.isoformat()
        return events


def build_setup(symbol: str, side: int, price: float, atr_value: float, target: float,
                signal_time: pd.Timestamp, p) -> Setup:
    """Zone 1 starts at the signal price, zone 2 sits deeper (averaging in).
    Targets are fractions of the way from the signal price to `target`
    (the middle Bollinger band); both zones share them."""
    def r(x):
        return round(float(x), 2)

    dist = max(abs(target - price), p.min_target_atr * atr_value)
    tps = [r(price + side * f * dist) for f in p.tp_frac]
    zones = []
    for offset in (0.0, p.zone2_offset_atr):
        top = price - side * offset * atr_value
        zones.append(Zone(top=r(top), bottom=r(top - side * p.zone_atr * atr_value),
                          sl=r(top - side * p.sl_atr * atr_value), tps=list(tps)))
    return Setup(
        symbol=symbol, side=side, price=r(price),
        signal_time=signal_time.isoformat(),
        expires=(signal_time + pd.Timedelta(hours=p.zone_valid_hours)).isoformat(),
        max_hold_hours=p.max_hold_hours, zones=zones)
