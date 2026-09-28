"""Small, side-effect-free helpers for ledger display and balance rules."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Iterable

from .database import Category, DEFAULT_CATEGORIES, Transaction

CATEGORY_LABELS = {code: label for code, label, _flow, _account in DEFAULT_CATEGORIES}
DEFAULT_CATEGORY_MAP = {
    code: Category(code, label, flow, account)
    for code, label, flow, account in DEFAULT_CATEGORIES
}


def category_label(kind: str) -> str:
    return CATEGORY_LABELS.get(kind, f"Category {kind}")


def parse_ledger_date(value: str) -> date:
    for pattern in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized transaction date: {value}")


def storage_date(value: date) -> str:
    return value.isoformat()


def transaction_balance_effect(
    category: Category | str,
    amount: float,
    state: dict,
    account: str | None = None,
) -> tuple[float, float, float]:
    """Return (stored amount, budget delta, hold delta) for a positive input."""
    amount = round(abs(amount), 2)
    definition = (
        category
        if isinstance(category, Category)
        else DEFAULT_CATEGORY_MAP.get(
            category, Category(category, category_label(category), "expense", "budget")
        )
    )
    if definition.flow == "income":
        hold = float(state["hold"])
        target = float(state["holdniv"])
        share_rate = float(state["itohold"]) / 100
        if hold >= target:
            to_hold = amount * share_rate
        elif hold + amount <= target:
            to_hold = amount
        else:
            to_hold = target - hold + (hold + amount - target) * share_rate
        to_hold = round(to_hold, 2)
        return amount, round(amount - to_hold, 2), to_hold
    if definition.flow == "saving":
        return amount, 0.0, -amount
    if (account or definition.account) == "hold":
        return -amount, 0.0, -amount
    return -amount, -amount, 0.0


def monthly_summary(transactions: Iterable[Transaction]) -> list[dict]:
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "expenses": 0.0, "savings": 0.0}
    )
    for transaction in transactions:
        month = parse_ledger_date(transaction.date).strftime("%Y-%m")
        values = grouped[month]
        if transaction.kind == "I":
            values["income"] += transaction.amount
        elif transaction.kind == "S":
            values["savings"] += transaction.amount
        elif transaction.amount < 0:
            values["expenses"] += abs(transaction.amount)

    return [
        {
            "month": month,
            **{key: round(value, 2) for key, value in values.items()},
            "net": round(values["income"] - values["expenses"], 2),
        }
        for month, values in sorted(grouped.items(), reverse=True)
    ]


def report_breakdown(
    transactions: Iterable[Transaction],
    categories: Iterable[Category],
    selected_year: int | None = None,
) -> list[dict]:
    """Build total, yearly, and monthly category totals like the original report."""
    category_map = {category.code: category for category in categories}
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    nets: dict[str, float] = defaultdict(float)
    year_months: dict[int, set[str]] = defaultdict(set)
    years: set[int] = set()

    for transaction in transactions:
        transaction_date = parse_ledger_date(transaction.date)
        year = transaction_date.year
        if selected_year is not None and year != selected_year:
            continue
        year_key = str(year)
        month_key = transaction_date.strftime("%m/%Y")
        years.add(year)
        year_months[year].add(month_key)
        category = category_map.get(
            transaction.kind,
            Category(transaction.kind, category_label(transaction.kind), "expense", "budget"),
        )
        totals["total"][transaction.kind] += transaction.amount
        totals[year_key][transaction.kind] += transaction.amount
        totals[month_key][transaction.kind] += transaction.amount
        net_effect = 0.0 if category.flow == "saving" else transaction.amount
        nets["total"] += net_effect
        nets[year_key] += net_effect
        nets[month_key] += net_effect

    periods: list[tuple[str, str]] = [("Selected period total" if selected_year else "All time", "total")]
    for year in sorted(years, reverse=True):
        year_key = str(year)
        periods.append((f"Year {year}", year_key))
        periods.extend(
            (month_key, month_key)
            for month_key in sorted(year_months[year], reverse=True)
        )

    return [
        {
            "period": label,
            "level": "total" if key == "total" else "year" if key.isdigit() else "month",
            "net": round(nets[key], 2),
            "categories": {
                category.code: round(totals[key].get(category.code, 0.0), 2)
                for category in category_map.values()
            },
        }
        for label, key in periods
    ]
