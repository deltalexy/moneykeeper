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
            """
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
        return Transaction(cursor.lastrowid, date, kind, amount, info)

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
