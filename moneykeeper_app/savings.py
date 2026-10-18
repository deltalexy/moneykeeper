"""Valuation, contribution, and fluctuation maths for savings and stock accounts.

Nothing here touches the budget or hold positions: savings value is tracked on its own.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from .database import (
    Database,
    HoldingSnapshot,
    SavingsAccount,
    SavingsValuation,
)
from .domain import parse_ledger_date


def _iso(value: str) -> date:
    return date.fromisoformat(value)


def _latest_snapshots(
    snapshots: Iterable[HoldingSnapshot], as_of: date
) -> dict[int, HoldingSnapshot]:
    latest: dict[int, HoldingSnapshot] = {}
    for snapshot in snapshots:
        when = _iso(snapshot.date)
        if when > as_of:
            continue
        current = latest.get(snapshot.holding_id)
        if current is None or (when, snapshot.id) >= (_iso(current.date), current.id):
            latest[snapshot.holding_id] = snapshot
    return latest


def _positions_value(snapshots: Iterable[HoldingSnapshot], as_of: date) -> float | None:
    """Sum the latest quantity x price per holding on or before ``as_of``."""
    latest = _latest_snapshots(snapshots, as_of)
    if not latest:
        return None
    return round(sum(item.quantity * item.price for item in latest.values()), 2)


def _balance_value(valuations: Iterable[SavingsValuation], as_of: date) -> float | None:
    chosen: SavingsValuation | None = None
    for valuation in valuations:
        if _iso(valuation.date) > as_of:
            continue
        if chosen is None or (_iso(valuation.date), valuation.id) >= (
            _iso(chosen.date),
            chosen.id,
        ):
            chosen = valuation
    return None if chosen is None else round(chosen.value, 2)


def account_value_at(
    account: SavingsAccount,
    as_of: date,
    valuations: Iterable[SavingsValuation],
    snapshots: Iterable[HoldingSnapshot],
) -> float | None:
    """Return the account value on a date, or None when nothing was recorded yet."""
    if account.tracking == "positions":
        return _positions_value(snapshots, as_of)
    return _balance_value(valuations, as_of)


def contributed_at(contributions: Iterable[tuple[str, float]], as_of: date) -> float:
    """Net deposits minus withdrawals (ledger dates) up to and including ``as_of``."""
    return round(
        sum(amount for when, amount in contributions if parse_ledger_date(when) <= as_of),
        2,
    )


def account_summary(
    account: SavingsAccount,
    valuations: list[SavingsValuation],
    snapshots: list[HoldingSnapshot],
    contributions: list[tuple[str, float]],
    as_of: date | None = None,
) -> dict:
    """Current value, contributed capital, and gain or loss for one account."""
    as_of = as_of or date.today()
    value = account_value_at(account, as_of, valuations, snapshots)
    contributed = contributed_at(contributions, as_of)
    dates = [_iso(item.date) for item in valuations if _iso(item.date) <= as_of]
    dates += [_iso(item.date) for item in snapshots if _iso(item.date) <= as_of]
    gain = None if value is None else round(value - contributed, 2)
    return {
        "account": account,
        "value": value,
        "contributed": contributed,
        "gain": gain,
        "return": gain / contributed if gain is not None and contributed > 0 else None,
        "last_update": max(dates) if dates else None,
    }


def account_history(
    account: SavingsAccount,
    valuations: list[SavingsValuation],
    snapshots: list[HoldingSnapshot],
    contributions: list[tuple[str, float]],
) -> list[dict]:
    """Chronological value points with the market fluctuation between them.

    Fluctuation is the change in value minus the money you added or withdrew in
    between, so deposits are never mistaken for market gains.
    """
    if account.tracking == "positions":
        dates = {_iso(item.date) for item in snapshots}
    else:
        dates = {_iso(item.date) for item in valuations}

    history: list[dict] = []
    previous_value = 0.0
    previous_contributed = 0.0
    for when in sorted(dates):
        value = account_value_at(account, when, valuations, snapshots)
        if value is None:
            continue
        contributed = contributed_at(contributions, when)
        history.append(
            {
                "date": when,
                "value": value,
                "contributed": contributed,
                "gain": round(value - contributed, 2),
                "fluctuation": round(
                    (value - previous_value) - (contributed - previous_contributed), 2
                ),
            }
        )
        previous_value = value
        previous_contributed = contributed
    return history


def current_positions(
    snapshots: Iterable[HoldingSnapshot], as_of: date | None = None
) -> list[HoldingSnapshot]:
    """Latest snapshot per holding, hiding positions that have been fully sold."""
    as_of = as_of or date.today()
    return sorted(
        (item for item in _latest_snapshots(snapshots, as_of).values() if item.quantity > 0),
        key=lambda item: item.symbol,
    )


def load_savings_summaries(database: Database, as_of: date | None = None) -> list[dict]:
    """Summaries for every savings account, read from the database."""
    valuations = database.valuations()
    snapshots = database.holding_snapshots()
    contributions = database.savings_contributions()
    summaries = []
    for account in database.savings_accounts():
        summaries.append(
            account_summary(
                account,
                [item for item in valuations if item.account_id == account.id],
                [item for item in snapshots if item.account_id == account.id],
                [
                    (when, amount)
                    for account_id, when, amount in contributions
                    if account_id == account.id
                ],
                as_of,
            )
        )
    return summaries


def monthly_savings_gain_loss(database: Database) -> dict[str, float]:
    """Return recorded savings and investment fluctuations grouped by month."""
    valuations = database.valuations()
    snapshots = database.holding_snapshots()
    contributions = database.savings_contributions()
    monthly: dict[str, float] = {}

    for account in database.savings_accounts():
        history = account_history(
            account,
            [item for item in valuations if item.account_id == account.id],
            [item for item in snapshots if item.account_id == account.id],
            [
                (when, amount)
                for account_id, when, amount in contributions
                if account_id == account.id
            ],
        )
        for point in history:
            month = point["date"].strftime("%m/%Y")
            monthly[month] = monthly.get(month, 0.0) + point["fluctuation"]

    return {month: round(amount, 2) for month, amount in monthly.items()}


def total_savings_value(summaries: Iterable[dict]) -> float:
    return round(sum(item["value"] or 0.0 for item in summaries), 2)
