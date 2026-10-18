"""SQLite access for Moneykeeper's balances and transaction ledger."""

from __future__ import annotations

import json
import pickle
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_STATE: dict[str, Any] = {
    "budget": 0.0,
    "hold": 0.0,
    "itohold": 0.0,
    "holdniv": 0.0,
    "buffer": 0.0,
    "zicht": 0.0,
    "mastercard": 0.0,
    "bpaid": 0.0,
    "cash": 0.0,
    "inhouse": 0.0,
    "cheques": 0.0,
    "achterkomend": 0.0,
    "achterinfo": "",
    "controledatum": "",
    "reconciliation_labels": {
        "zicht": "Current account",
        "mastercard": "Credit card",
        "bpaid": "Meal card",
        "cash": "Cash",
        "inhouse": "At home",
        "cheques": "Cheques",
        "achterkomend": "Expected in",
    },
}

DEFAULT_CATEGORIES = (
    ("A", "Recurring", "expense", "budget"),
    ("B", "Major payments", "expense", "hold"),
    ("C", "Gifts", "expense", "budget"),
    ("I", "Income", "income", "auto"),
    ("L", "Living", "expense", "budget"),
    ("N", "Mobility", "expense", "hold"),
    ("R", "Other", "expense", "budget"),
    ("S", "Savings", "saving", "hold"),
    ("U", "Personal", "expense", "budget"),
)


@dataclass(frozen=True)
class Transaction:
    id: int
    date: str
    kind: str
    amount: float
    info: str


@dataclass(frozen=True)
class Category:
    code: str
    label: str
    flow: str
    account: str


@dataclass(frozen=True)
class SavingsAccount:
    id: int
    name: str
    kind: str
    tracking: str  # "balance" (total value) or "positions" (quantity x price)


@dataclass(frozen=True)
class SavingsValuation:
    id: int
    account_id: int
    date: str
    value: float
    note: str


@dataclass(frozen=True)
class SavingsHolding:
    id: int
    account_id: int
    symbol: str
    name: str


@dataclass(frozen=True)
class HoldingSnapshot:
    id: int
    holding_id: int
    account_id: int
    symbol: str
    date: str
    quantity: float
    price: float


class RestrictedUnpickler(pickle.Unpickler):
    """Load only primitive legacy values; pickle globals are never permitted."""

    def find_class(self, module: str, name: str) -> Any:
        raise pickle.UnpicklingError("Legacy data contains an unsupported object")


class Database:
    """Small repository around the existing SQLite schema."""

    def __init__(self, path: Path, legacy_path: Path | None = None) -> None:
        self.path = Path(path)
        self.connection = sqlite3.connect(str(self.path), timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._create_schema()
        self._import_legacy_once(legacy_path)

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                kind TEXT NOT NULL,
                amount REAL NOT NULL,
                info TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                code TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                flow TEXT NOT NULL CHECK(flow IN ('expense', 'income', 'saving')),
                account TEXT NOT NULL CHECK(account IN ('budget', 'hold', 'auto'))
            );
            CREATE TABLE IF NOT EXISTS savings_accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                kind TEXT NOT NULL,
                tracking TEXT NOT NULL CHECK(tracking IN ('balance', 'positions'))
            );
            CREATE TABLE IF NOT EXISTS savings_valuations (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                value REAL NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS savings_holdings (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                symbol TEXT NOT NULL COLLATE NOCASE,
                name TEXT NOT NULL DEFAULT '',
                UNIQUE(account_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS savings_holding_snapshots (
                id INTEGER PRIMARY KEY,
                holding_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS savings_openings (
                account_id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                amount REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS savings_transfers (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                from_account_id INTEGER NOT NULL,
                to_account_id INTEGER NOT NULL,
                amount REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS savings_links (
                transaction_id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL
            );
            """
        )
        transfer_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(savings_transfers)")
        }
        for column in ("from_valuation_id", "to_valuation_id"):
            if column not in transfer_columns:
                self.connection.execute(
                    f"ALTER TABLE savings_transfers ADD COLUMN {column} INTEGER"
                )
        self.connection.executemany(
            "INSERT OR IGNORE INTO categories(code, label, flow, account) VALUES (?, ?, ?, ?)",
            DEFAULT_CATEGORIES,
        )
        self.connection.commit()

    def _import_legacy_once(self, legacy_path: Path | None) -> None:
        imported = self.connection.execute(
            "SELECT 1 FROM metadata WHERE key='legacy_imported'"
        ).fetchone()
        if imported:
            return
        existing_rows = self.connection.execute(
            "SELECT 1 FROM transactions LIMIT 1"
        ).fetchone()
        if existing_rows:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO metadata(key, value) VALUES ('legacy_imported', '1')"
                )
            return

        legacy: dict[str, Any] = {}
        if legacy_path is not None and legacy_path.exists():
            with legacy_path.open("rb") as legacy_file:
                value = RestrictedUnpickler(legacy_file).load()
            if not isinstance(value, dict):
                raise ValueError("Legacy pickle must contain a dictionary")
            legacy = value

        with self.connection:
            for key, default in DEFAULT_STATE.items():
                self.connection.execute(
                    "INSERT OR IGNORE INTO app_state(key, value) VALUES (?, ?)",
                    (key, json.dumps(legacy.get(key, default))),
                )

            for line in legacy.get("log", "").splitlines():
                if not line:
                    continue
                fields = line.split("\t", 4)
                if len(fields) != 5:
                    raise ValueError("Invalid transaction row in legacy pickle")
                transaction_id, date, kind, amount, info = fields
                self.connection.execute(
                    """INSERT INTO transactions(id, date, kind, amount, info)
                       VALUES (?, ?, ?, ?, ?)""",
                    (int(transaction_id), date, kind, float(amount), info),
                )
            self.connection.execute(
                "INSERT INTO metadata(key, value) VALUES ('legacy_imported', '1')"
            )

    def load_state(self) -> dict[str, Any]:
        state = dict(DEFAULT_STATE)
        for row in self.connection.execute("SELECT key, value FROM app_state"):
            if row["key"] in state:
                state[row["key"]] = json.loads(row["value"])
        return state

    def categories(self, flow: str | None = None) -> list[Category]:
        if flow:
            rows = self.connection.execute(
                "SELECT code, label, flow, account FROM categories WHERE flow=? ORDER BY label COLLATE NOCASE",
                (flow,),
            )
        else:
            rows = self.connection.execute(
                "SELECT code, label, flow, account FROM categories ORDER BY label COLLATE NOCASE"
            )
        return [Category(**dict(row)) for row in rows]

    def save_category(self, category: Category) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO categories(code, label, flow, account) VALUES (?, ?, ?, ?)
                   ON CONFLICT(code) DO UPDATE SET label=excluded.label,
                       flow=excluded.flow, account=excluded.account""",
                (category.code, category.label, category.flow, category.account),
            )

    def delete_category(self, code: str) -> None:
        used = self.connection.execute(
            "SELECT 1 FROM transactions WHERE kind=? LIMIT 1", (code,)
        ).fetchone()
        if used:
            raise ValueError("A category used by ledger entries cannot be deleted")
        with self.connection:
            self.connection.execute("DELETE FROM categories WHERE code=?", (code,))

    def save_state(self, state: dict[str, Any]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES (?, ?)",
                [(key, json.dumps(value)) for key, value in state.items()],
            )

    def add_transaction(
        self,
        date: str,
        kind: str,
        amount: float,
        info: str,
        budget_delta: float = 0.0,
        hold_delta: float = 0.0,
        savings_account_id: int | None = None,
    ) -> Transaction:
        """Write a ledger row and its balance effects as one atomic commit."""
        with self.connection:
            state = self.load_state()
            state["budget"] = round(float(state["budget"]) + budget_delta, 2)
            state["hold"] = round(float(state["hold"]) + hold_delta, 2)
            cursor = self.connection.execute(
                "INSERT INTO transactions(date, kind, amount, info) VALUES (?, ?, ?, ?)",
                (date, kind, amount, info),
            )
            self.connection.executemany(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES (?, ?)",
                [(key, json.dumps(state[key])) for key in ("budget", "hold")],
            )
            if savings_account_id is not None:
                self.connection.execute(
                    "INSERT OR REPLACE INTO savings_links(transaction_id, account_id) VALUES (?, ?)",
                    (cursor.lastrowid, savings_account_id),
                )
        return Transaction(cursor.lastrowid, date, kind, amount, info)

    # Savings tracking never changes the budget or hold positions.
    def savings_accounts(self) -> list[SavingsAccount]:
        rows = self.connection.execute(
            "SELECT id, name, kind, tracking FROM savings_accounts ORDER BY name COLLATE NOCASE"
        )
        return [SavingsAccount(**dict(row)) for row in rows]

    def save_savings_account(
        self, name: str, kind: str, tracking: str, account_id: int | None = None
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("An account needs a name")
        if tracking not in ("balance", "positions"):
            raise ValueError("Unknown tracking mode")
        try:
            with self.connection:
                if account_id is None:
                    cursor = self.connection.execute(
                        "INSERT INTO savings_accounts(name, kind, tracking) VALUES (?, ?, ?)",
                        (name, kind, tracking),
                    )
                    return int(cursor.lastrowid)
                self.connection.execute(
                    "UPDATE savings_accounts SET name=?, kind=? WHERE id=?",
                    (name, kind, account_id),
                )
                return account_id
        except sqlite3.IntegrityError as error:
            raise ValueError("A savings account with this name already exists") from error

    def delete_savings_account(self, account_id: int) -> None:
        with self.connection:
            self.connection.execute(
                """DELETE FROM savings_holding_snapshots WHERE holding_id IN
                   (SELECT id FROM savings_holdings WHERE account_id=?)""",
                (account_id,),
            )
            self.connection.execute(
                "DELETE FROM savings_holdings WHERE account_id=?", (account_id,)
            )
            self.connection.execute(
                "DELETE FROM savings_valuations WHERE account_id=?", (account_id,)
            )
            self.connection.execute(
                "DELETE FROM savings_links WHERE account_id=?", (account_id,)
            )
            self.connection.execute(
                "DELETE FROM savings_openings WHERE account_id=?", (account_id,)
            )
            # Keep the other side's contribution so its gain stays correct; 0 means "deleted".
            self.connection.execute(
                "UPDATE savings_transfers SET from_account_id=0 WHERE from_account_id=?",
                (account_id,),
            )
            self.connection.execute(
                "UPDATE savings_transfers SET to_account_id=0 WHERE to_account_id=?",
                (account_id,),
            )
            self.connection.execute(
                "DELETE FROM savings_accounts WHERE id=?", (account_id,)
            )

    def transfer_between_savings(
        self, from_id: int, to_id: int, date: str, amount: float
    ) -> None:
        """Move value between two savings accounts without touching Budget or Hold.

        The amount leaves the source's contributed capital and joins the destination's,
        so neither account shows a gain or loss. Total-value accounts get a matching
        valuation; position accounts must have their positions updated by hand.
        """
        amount = round(amount, 2)
        if amount <= 0:
            raise ValueError("The amount must be greater than zero")
        if from_id == to_id:
            raise ValueError("Choose two different accounts")
        accounts = {
            row["id"]: row["tracking"]
            for row in self.connection.execute(
                "SELECT id, tracking FROM savings_accounts WHERE id IN (?, ?)",
                (from_id, to_id),
            )
        }
        if len(accounts) != 2:
            raise ValueError("Unknown savings account")
        with self.connection:
            transfer_id = self.connection.execute(
                """INSERT INTO savings_transfers(date, from_account_id, to_account_id, amount)
                   VALUES (?, ?, ?, ?)""",
                (date, from_id, to_id, amount),
            ).lastrowid
            for account_id, sign, column in (
                (from_id, -1, "from_valuation_id"),
                (to_id, 1, "to_valuation_id"),
            ):
                if accounts[account_id] != "balance":
                    continue
                row = self.connection.execute(
                    """SELECT value FROM savings_valuations
                       WHERE account_id=? AND date<=? ORDER BY date DESC, id DESC LIMIT 1""",
                    (account_id, date),
                ).fetchone()
                base = float(row["value"]) if row else 0.0
                valuation_id = self.connection.execute(
                    "INSERT INTO savings_valuations(account_id, date, value, note) VALUES (?, ?, ?, ?)",
                    (account_id, date, round(base + sign * amount, 2), self.TRANSFER_NOTE),
                ).lastrowid
                self.connection.execute(
                    f"UPDATE savings_transfers SET {column}=? WHERE id=?",
                    (valuation_id, transfer_id),
                )

    OPENING_NOTE = "Starting value"
    TRANSFER_NOTE = "Transfer"

    def opening_balance(self, account_id: int) -> tuple[str, float] | None:
        row = self.connection.execute(
            "SELECT date, amount FROM savings_openings WHERE account_id=?", (account_id,)
        ).fetchone()
        return (row["date"], row["amount"]) if row else None

    def set_opening_balance(self, account_id: int, date: str, amount: float) -> None:
        """Set the value an account already had, which is not counted as gain or loss.

        The amount counts as capital contributed, so the gain starts at zero. Total-value
        accounts also get a matching valuation; position accounts take their value from
        the positions you record on or after this date. An amount of 0 clears it.
        """
        amount = round(amount, 2)
        if amount < 0:
            raise ValueError("A starting value cannot be negative")
        account = self.connection.execute(
            "SELECT tracking FROM savings_accounts WHERE id=?", (account_id,)
        ).fetchone()
        if account is None:
            raise ValueError("Unknown savings account")
        with self.connection:
            self.connection.execute(
                "DELETE FROM savings_valuations WHERE account_id=? AND note=?",
                (account_id, self.OPENING_NOTE),
            )
            if amount == 0:
                self.connection.execute(
                    "DELETE FROM savings_openings WHERE account_id=?", (account_id,)
                )
                return
            self.connection.execute(
                "INSERT OR REPLACE INTO savings_openings(account_id, date, amount) VALUES (?, ?, ?)",
                (account_id, date, amount),
            )
            if account["tracking"] == "balance":
                self.connection.execute(
                    "INSERT INTO savings_valuations(account_id, date, value, note) VALUES (?, ?, ?, ?)",
                    (account_id, date, amount, self.OPENING_NOTE),
                )

    def add_valuation(self, account_id: int, date: str, value: float, note: str = "") -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO savings_valuations(account_id, date, value, note) VALUES (?, ?, ?, ?)",
                (account_id, date, round(value, 2), note),
            )

    def valuations(self, account_id: int | None = None) -> list[SavingsValuation]:
        query = "SELECT id, account_id, date, value, note FROM savings_valuations"
        parameters: tuple = ()
        if account_id is not None:
            query += " WHERE account_id=?"
            parameters = (account_id,)
        rows = self.connection.execute(query + " ORDER BY date, id", parameters)
        return [SavingsValuation(**dict(row)) for row in rows]

    def transfer_amounts(self) -> dict[int, float]:
        """Map a transfer's valuation id to the signed amount it moved."""
        amounts: dict[int, float] = {}
        for row in self.connection.execute(
            "SELECT from_valuation_id, to_valuation_id, amount FROM savings_transfers"
        ):
            if row["from_valuation_id"] is not None:
                amounts[int(row["from_valuation_id"])] = -row["amount"]
            if row["to_valuation_id"] is not None:
                amounts[int(row["to_valuation_id"])] = row["amount"]
        return amounts

    def delete_valuation(self, valuation_id: int) -> None:
        """Delete a valuation along with the contribution it represents."""
        with self.connection:
            row = self.connection.execute(
                "SELECT account_id, date, note FROM savings_valuations WHERE id=?",
                (valuation_id,),
            ).fetchone()
            if row is not None and row["note"] == self.OPENING_NOTE:
                self.connection.execute(
                    "DELETE FROM savings_openings WHERE account_id=? AND date=?",
                    (row["account_id"], row["date"]),
                )
            elif row is not None and row["note"] == self.TRANSFER_NOTE:
                for side, column in (
                    ("from_account_id", "from_valuation_id"),
                    ("to_account_id", "to_valuation_id"),
                ):
                    linked = self.connection.execute(
                        f"SELECT 1 FROM savings_transfers WHERE {column}=?", (valuation_id,)
                    ).fetchone()
                    if linked:
                        self.connection.execute(
                            f"UPDATE savings_transfers SET {side}=0 WHERE {column}=?",
                            (valuation_id,),
                        )
                        break
                else:
                    # Transfers recorded before valuation ids were stored: match by account and date.
                    for side, column in (
                        ("from_account_id", "from_valuation_id"),
                        ("to_account_id", "to_valuation_id"),
                    ):
                        legacy = self.connection.execute(
                            f"""SELECT id FROM savings_transfers
                                WHERE {side}=? AND date=? AND {column} IS NULL
                                ORDER BY id LIMIT 1""",
                            (row["account_id"], row["date"]),
                        ).fetchone()
                        if legacy:
                            self.connection.execute(
                                f"UPDATE savings_transfers SET {side}=0 WHERE id=?",
                                (legacy["id"],),
                            )
                            break
            self.connection.execute(
                "DELETE FROM savings_valuations WHERE id=?", (valuation_id,)
            )

    def savings_holdings(self, account_id: int | None = None) -> list[SavingsHolding]:
        query = "SELECT id, account_id, symbol, name FROM savings_holdings"
        parameters: tuple = ()
        if account_id is not None:
            query += " WHERE account_id=?"
            parameters = (account_id,)
        rows = self.connection.execute(query + " ORDER BY symbol COLLATE NOCASE", parameters)
        return [SavingsHolding(**dict(row)) for row in rows]

    def add_holding_snapshot(
        self,
        account_id: int,
        symbol: str,
        name: str,
        date: str,
        quantity: float,
        price: float,
    ) -> None:
        """Record a position's quantity and price, creating the holding if needed."""
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("A position needs a symbol")
        if quantity < 0 or price < 0:
            raise ValueError("Quantity and price cannot be negative")
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO savings_holdings(account_id, symbol, name) VALUES (?, ?, ?)",
                (account_id, symbol, name.strip()),
            )
            holding = self.connection.execute(
                "SELECT id, name FROM savings_holdings WHERE account_id=? AND symbol=?",
                (account_id, symbol),
            ).fetchone()
            if name.strip() and holding["name"] != name.strip():
                self.connection.execute(
                    "UPDATE savings_holdings SET name=? WHERE id=?",
                    (name.strip(), holding["id"]),
                )
            self.connection.execute(
                """INSERT INTO savings_holding_snapshots(holding_id, date, quantity, price)
                   VALUES (?, ?, ?, ?)""",
                (holding["id"], date, quantity, price),
            )

    def holding_snapshots(self, account_id: int | None = None) -> list[HoldingSnapshot]:
        query = """SELECT s.id, s.holding_id, h.account_id, h.symbol, s.date, s.quantity, s.price
                   FROM savings_holding_snapshots s
                   JOIN savings_holdings h ON h.id = s.holding_id"""
        parameters: tuple = ()
        if account_id is not None:
            query += " WHERE h.account_id=?"
            parameters = (account_id,)
        rows = self.connection.execute(query + " ORDER BY s.date, s.id", parameters)
        return [HoldingSnapshot(**dict(row)) for row in rows]

    def delete_holding_snapshot(self, snapshot_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM savings_holding_snapshots WHERE id=?", (snapshot_id,)
            )

    def savings_contributions(self) -> list[tuple[int, str, float]]:
        """Return (account id, ledger date, amount) for linked Savings transactions."""
        rows = self.connection.execute(
            """SELECT l.account_id, t.date, t.amount
               FROM savings_links l
               JOIN transactions t ON t.id = l.transaction_id
               JOIN categories c ON c.code = t.kind
               WHERE c.flow = 'saving'"""
        )
        contributions = [(row["account_id"], row["date"], row["amount"]) for row in rows]
        openings = self.connection.execute(
            "SELECT account_id, date, amount FROM savings_openings"
        )
        contributions.extend(
            (row["account_id"], row["date"], row["amount"]) for row in openings
        )
        for row in self.connection.execute(
            "SELECT date, from_account_id, to_account_id, amount FROM savings_transfers"
        ):
            contributions.append((row["from_account_id"], row["date"], -row["amount"]))
            contributions.append((row["to_account_id"], row["date"], row["amount"]))
        return contributions

    def unlinked_savings_total(self) -> float:
        row = self.connection.execute(
            """SELECT COALESCE(SUM(t.amount), 0) AS total
               FROM transactions t
               JOIN categories c ON c.code = t.kind
               LEFT JOIN savings_links l ON l.transaction_id = t.id
               WHERE c.flow = 'saving' AND l.transaction_id IS NULL"""
        ).fetchone()
        return round(float(row["total"]), 2)

    def savings_link(self, transaction_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT account_id FROM savings_links WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()
        return int(row["account_id"]) if row else None

    def set_savings_link(self, transaction_id: int, account_id: int | None) -> None:
        with self.connection:
            if account_id is None:
                self.connection.execute(
                    "DELETE FROM savings_links WHERE transaction_id=?", (transaction_id,)
                )
            else:
                self.connection.execute(
                    "INSERT OR REPLACE INTO savings_links(transaction_id, account_id) VALUES (?, ?)",
                    (transaction_id, account_id),
                )

    def transfer_funds(self, source: str, destination: str, amount: float) -> None:
        """Move money between the budget and hold positions without a ledger entry."""
        if {source, destination} != {"budget", "hold"}:
            raise ValueError("Transfers must be between Budget and Hold")
        amount = round(amount, 2)
        if amount <= 0:
            raise ValueError("The transfer amount must be greater than zero")
        with self.connection:
            state = self.load_state()
            state[source] = round(float(state[source]) - amount, 2)
            state[destination] = round(float(state[destination]) + amount, 2)
            self.connection.executemany(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES (?, ?)",
                [(key, json.dumps(state[key])) for key in ("budget", "hold")],
            )

    def transactions(self) -> list[Transaction]:
        rows = self.connection.execute(
            "SELECT id, date, kind, amount, info FROM transactions ORDER BY id DESC"
        )
        return [Transaction(**dict(row)) for row in rows]

    def search_transactions(self, term: str = "", kind: str = "") -> list[Transaction]:
        clauses: list[str] = []
        parameters: list[str] = []
        if term.strip():
            clauses.append(
                "(date LIKE ? OR kind LIKE ? OR info LIKE ? OR CAST(amount AS TEXT) LIKE ?)"
            )
            pattern = f"%{term.strip()}%"
            parameters.extend((pattern, pattern, pattern, pattern))
        if kind:
            clauses.append("kind = ?")
            parameters.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            "SELECT id, date, kind, amount, info FROM transactions"
            + where
            + " ORDER BY id DESC",
            parameters,
        )
        return [Transaction(**dict(row)) for row in rows]

    def update_transaction_details(
        self, transaction_id: int, date: str, kind: str, info: str, amount: float
    ) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE transactions SET date=?, kind=?, info=?, amount=? WHERE id=?",
                (date, kind, info, amount, transaction_id),
            )

    def save_reconciliation(self, state: dict[str, Any], adjustment: float) -> None:
        updated_state = dict(state)
        updated_state["budget"] = round(float(state["budget"]) + adjustment, 2)
        with self.connection:
            self.connection.executemany(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES (?, ?)",
                [(key, json.dumps(value)) for key, value in updated_state.items()],
            )

    def transaction_count(self) -> int:
        return int(self.connection.execute("SELECT count(*) FROM transactions").fetchone()[0])

    def backup_to(self, destination_path: Path) -> None:
        destination = sqlite3.connect(str(destination_path))
        try:
            self.connection.backup(destination)
        finally:
            destination.close()

    def close(self) -> None:
        self.connection.close()
