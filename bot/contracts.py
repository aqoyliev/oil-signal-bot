"""Broker contract specifications (spec item 26).

Spec item 26 is explicit: *do not assume WTI and Brent have identical contract
specifications*. They often do not, and they differ between brokers as well —
the same "USOIL" is 1000 barrels a lot at one broker and 100 at another, which
changes position size by a factor of ten.

The trader is on MT5. The authoritative numbers come from his own terminal:

    Market Watch -> right-click the symbol -> Specification

and the four fields that matter are Contract size, Volume minimum, Volume step
and Digits. Until those are in hand, `UNCONFIRMED` below holds the values that
are most common for MT5 oil CFDs, and `confirmed=False` makes every position
size derived from them carry that caveat instead of pretending to be exact.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Contract:
    symbol: str             # the bot's name for it
    mt5_symbol: str         # what the terminal calls it (brokers differ)
    contract_size: float    # units (barrels) per 1.00 lot
    min_lot: float
    lot_step: float
    digits: int             # price decimals
    confirmed: bool = False  # True only once read from the trader's terminal

    @property
    def tick(self) -> float:
        return 10 ** -self.digits

    def value_per_price_unit(self, lots: float) -> float:
        """Account currency gained per 1.00 of price movement."""
        return lots * self.contract_size

    def lots_for_risk(self, risk_amount: float, sl_distance: float) -> float:
        """Spec item 26: Position Size = Risk Amount / Stop Loss Distance,
        converted into lots through the contract size, then rounded *down* onto
        the broker's volume step — rounding up would risk more than allowed."""
        if sl_distance <= 0:
            raise ValueError("stop-loss distance must be positive")
        raw_units = risk_amount / sl_distance          # barrels
        lots = raw_units / self.contract_size
        stepped = (lots // self.lot_step) * self.lot_step
        return round(stepped, 8) if stepped >= self.min_lot else 0.0

    def risk_for_lots(self, lots: float, sl_distance: float) -> float:
        """What the rounded position actually risks — what the log should show."""
        return lots * self.contract_size * sl_distance

    def min_risk(self, sl_distance: float) -> float:
        """The smallest amount this contract can risk at all.

        One minimum lot of a 1000-barrel contract with a $0.70 stop risks $7,
        whatever the account holds. This is the floor that makes small accounts
        unable to take a trade at a small risk percentage.
        """
        return self.min_lot * self.contract_size * sl_distance

    def min_balance_for(self, risk_pct: float, sl_distance: float) -> float:
        """Smallest balance at which `risk_pct` can be respected on this stop.

        Below it the only options are to risk more than allowed or to skip the
        trade. Spec items 24-26 leave no room for the first, so the bot skips —
        `lots_for_risk` returns 0.0 and the caller must treat that as no trade.
        """
        return 100.0 * self.min_risk(sl_distance) / risk_pct


# Most common MT5 oil CFD specification. Replace from the trader's terminal.
UNCONFIRMED = {
    "WTI": Contract("WTI", "XTIUSD", contract_size=1000.0, min_lot=0.01,
                    lot_step=0.01, digits=2, confirmed=False),
    "BRENT": Contract("BRENT", "XBRUSD", contract_size=1000.0, min_lot=0.01,
                      lot_step=0.01, digits=2, confirmed=False),
}

CONTRACTS = dict(UNCONFIRMED)


def get(symbol: str) -> Contract:
    try:
        return CONTRACTS[symbol]
    except KeyError:
        raise KeyError(f"no contract specification for {symbol!r}") from None


def all_confirmed() -> bool:
    """False while any size is still a guess — the signal message and the
    backtest report both say so when this is False."""
    return all(c.confirmed for c in CONTRACTS.values())
