"""Focused dialogs for creating and correcting ledger entries."""

from __future__ import annotations

from PyQt5.QtCore import QDate, QLocale
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QVBoxLayout,
)

from .database import Category, SavingsAccount, Transaction
from .domain import parse_ledger_date

SAVINGS_KINDS = ("Savings account", "Brokerage", "Fund", "Pension", "Crypto", "Other")


def configure_decimal_input(spin: QDoubleSpinBox) -> QDoubleSpinBox:
    spin.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
    return spin


def savings_account_picker(
    accounts: list[SavingsAccount], selected_id: int | None = None
) -> QComboBox:
    picker = QComboBox()
    picker.addItem("Not linked to an account", None)
    for account in accounts:
        picker.addItem(account.name, account.id)
    index = picker.findData(selected_id)
    picker.setCurrentIndex(max(index, 0))
    return picker


class TransactionDialog(QDialog):
    """Collect a new transaction without exposing storage-format details."""

    def __init__(
        self,
        categories: list[Category],
        parent=None,
        savings_accounts: list[SavingsAccount] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New transaction")
        self.setMinimumWidth(400)
        self.categories = {category.code: category for category in categories}

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd, d MMM yyyy")

        self.category = QComboBox()
        for category in categories:
            self.category.addItem(f"{category.label}  -  {category.code}", category.code)
        self.category.currentIndexChanged.connect(self._update_account_choice)

        self.amount = configure_decimal_input(QDoubleSpinBox())
        self.amount.setRange(-999_999_999.99, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setSingleStep(1.0)
        self.amount.setGroupSeparatorShown(True)

        self.account = QComboBox()
        self.account.addItem("Budget", "budget")
        self.account.addItem("Hold", "hold")
        self.savings_account = savings_account_picker(savings_accounts or [])
        self.description = QLineEdit()
        self.description.setPlaceholderText("Merchant or note")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Date", self.date_edit)
        form.addRow("Category", self.category)
        form.addRow("Amount", self.amount)
        form.addRow("Pay from", self.account)
        form.addRow("Savings account", self.savings_account)
        form.addRow("Description", self.description)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self._update_account_choice()

    def _update_account_choice(self) -> None:
        category = self.categories[self.category.currentData()]
        self.account.setEnabled(category.flow == "expense")
        self.account.setCurrentIndex(self.account.findData(category.account))
        self.savings_account.setEnabled(category.flow == "saving")
        self.savings_account.setToolTip(
            "Link this deposit or withdrawal to a tracked savings account."
        )
        if category.flow == "income":
            self.account.setToolTip("Income is allocated using the hold target settings.")
        elif category.flow == "saving":
            self.account.setToolTip("Savings withdrawals are taken from Hold.")
        else:
            self.account.setToolTip("")

    def savings_account_id(self) -> int | None:
        category = self.categories[self.category.currentData()]
        return self.savings_account.currentData() if category.flow == "saving" else None

    def values(self) -> tuple[str, Category, float, str, str]:
        return (
            self.date_edit.date().toString("dd/MM/yy"),
            self.categories[self.category.currentData()],
            self.amount.value(),
            self.description.text().strip(),
            self.account.currentData(),
        )

    def accept(self) -> None:
        if self.amount.value() == 0:
            self.amount.setFocus()
            return
        if not self.description.text().strip():
            self.description.setFocus()
            self.description.setStyleSheet("border: 1px solid #bd5748;")
            return
        super().accept()


class TransferDialog(QDialog):
    """Move money between the Budget and Hold positions."""

    def __init__(self, budget: float, hold: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Transfer between Budget and Hold")
        self.setMinimumWidth(400)

        self.direction = QComboBox()
        self.direction.addItem(f"Budget  →  Hold   (Budget € {budget:,.2f})", ("budget", "hold"))
        self.direction.addItem(f"Hold  →  Budget   (Hold € {hold:,.2f})", ("hold", "budget"))

        self.amount = configure_decimal_input(QDoubleSpinBox())
        self.amount.setRange(0.01, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setSingleStep(1.0)
        self.amount.setGroupSeparatorShown(True)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Direction", self.direction)
        form.addRow("Amount", self.amount)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def values(self) -> tuple[str, str, float]:
        source, destination = self.direction.currentData()
        return source, destination, self.amount.value()


class SavingsAccountDialog(QDialog):
    """Create or rename a tracked savings or investment account."""

    def __init__(self, account: SavingsAccount | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New savings account" if account is None else "Edit savings account")
        self.setMinimumWidth(420)

        self.name = QLineEdit(account.name if account else "")
        self.name.setPlaceholderText("For example, Broker or Savings book")
        self.kind = QComboBox()
        for kind in SAVINGS_KINDS:
            self.kind.addItem(kind, kind)
        if account:
            index = self.kind.findData(account.kind)
            if index >= 0:
                self.kind.setCurrentIndex(index)
        self.tracking = QComboBox()
        self.tracking.addItem("Total value  -  enter the balance now and then", "balance")
        self.tracking.addItem("Positions  -  stocks and funds as quantity x price", "positions")
        if account:
            self.tracking.setCurrentIndex(self.tracking.findData(account.tracking))
            self.tracking.setEnabled(False)
            self.tracking.setToolTip("The tracking method cannot change after creation.")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Name", self.name)
        form.addRow("Type", self.kind)
        form.addRow("Tracking", self.tracking)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return self.name.text().strip(), self.kind.currentData(), self.tracking.currentData()

    def accept(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            return
        super().accept()


class ValuationDialog(QDialog):
    """Record what a total-value savings account is worth on a date."""

    def __init__(self, account_name: str, last_value: float | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Update value - {account_name}")
        self.setMinimumWidth(400)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd, d MMM yyyy")
        self.value = configure_decimal_input(QDoubleSpinBox())
        self.value.setRange(0, 999_999_999.99)
        self.value.setDecimals(2)
        self.value.setGroupSeparatorShown(True)
        if last_value is not None:
            self.value.setValue(last_value)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Date", self.date_edit)
        form.addRow("Total value", self.value)
        form.addRow("Note", self.note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, float, str]:
        return (
            self.date_edit.date().toString("yyyy-MM-dd"),
            self.value.value(),
            self.note.text().strip(),
        )


class SavingsTransferDialog(QDialog):
    """Move value from one savings account to another."""

    def __init__(self, accounts: list[SavingsAccount], selected_id: int | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Move between savings accounts")
        self.setMinimumWidth(420)

        self.source = QComboBox()
        self.destination = QComboBox()
        for account in accounts:
            self.source.addItem(account.name, account.id)
            self.destination.addItem(account.name, account.id)
        index = self.source.findData(selected_id)
        if index >= 0:
            self.source.setCurrentIndex(index)
        self.destination.setCurrentIndex(1 if self.destination.count() > 1 and index <= 0 else 0)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd, d MMM yyyy")
        self.amount = configure_decimal_input(QDoubleSpinBox())
        self.amount.setRange(0.01, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)

        hint = QLabel(
            "Budget and Hold are not affected and no gain or loss is recorded. Position "
            "accounts need their positions updated separately."
        )
        hint.setWordWrap(True)
        hint.setObjectName("sectionNote")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("From", self.source)
        form.addRow("To", self.destination)
        form.addRow("Date", self.date_edit)
        form.addRow("Amount", self.amount)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, int, str, float]:
        return (
            self.source.currentData(),
            self.destination.currentData(),
            self.date_edit.date().toString("yyyy-MM-dd"),
            self.amount.value(),
        )

    def accept(self) -> None:
        if self.source.currentData() == self.destination.currentData():
            self.destination.setFocus()
            return
        super().accept()


class OpeningBalanceDialog(QDialog):
    """Set the value a savings account already holds, without counting it as gain."""

    def __init__(
        self,
        account_name: str,
        tracking: str,
        current: tuple[str, float] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Starting value - {account_name}")
        self.setMinimumWidth(440)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd, d MMM yyyy")
        self.amount = configure_decimal_input(QDoubleSpinBox())
        self.amount.setRange(0, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)
        if current:
            parsed = QDate.fromString(current[0], "yyyy-MM-dd")
            if parsed.isValid():
                self.date_edit.setDate(parsed)
            self.amount.setValue(current[1])

        hint = QLabel(
            "The value this account already had when you started tracking it. It counts as "
            "money put in, so it is not shown as gain or loss. Set 0 to remove it."
            + (
                "\nRecord your positions with the same date so their value matches."
                if tracking == "positions"
                else ""
            )
        )
        hint.setWordWrap(True)
        hint.setObjectName("sectionNote")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("As of", self.date_edit)
        form.addRow("Starting value", self.amount)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, float]:
        return self.date_edit.date().toString("yyyy-MM-dd"), self.amount.value()


class PositionDialog(QDialog):
    """Record a stock or fund position as quantity and price on a date."""

    def __init__(
        self, account_name: str, holdings: list[tuple[str, str]], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Update position - {account_name}")
        self.setMinimumWidth(420)
        self.names = dict(holdings)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd, d MMM yyyy")
        self.symbol = QComboBox()
        self.symbol.setEditable(True)
        self.symbol.setInsertPolicy(QComboBox.NoInsert)
        for symbol, _name in holdings:
            self.symbol.addItem(symbol)
        self.symbol.setCurrentText("")
        self.symbol.lineEdit().setPlaceholderText("Ticker, for example VWCE")
        self.symbol.currentTextChanged.connect(self._fill_name)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Optional name")
        self.quantity = configure_decimal_input(QDoubleSpinBox())
        self.quantity.setRange(0, 999_999_999.0)
        self.quantity.setDecimals(6)
        self.quantity.setToolTip("Total number of units held after this update; 0 means sold.")
        self.price = configure_decimal_input(QDoubleSpinBox())
        self.price.setRange(0, 999_999_999.0)
        self.price.setDecimals(4)
        self.price.setGroupSeparatorShown(True)
        self.total = QLabel("€ 0.00")

        for spin in (self.quantity, self.price):
            spin.valueChanged.connect(self._update_total)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Date", self.date_edit)
        form.addRow("Symbol", self.symbol)
        form.addRow("Name", self.name)
        form.addRow("Quantity held", self.quantity)
        form.addRow("Price per unit", self.price)
        form.addRow("Position value", self.total)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _fill_name(self, symbol: str) -> None:
        name = self.names.get(symbol.strip().upper())
        if name is not None and not self.name.text():
            self.name.setText(name)

    def _update_total(self) -> None:
        self.total.setText(f"€ {self.quantity.value() * self.price.value():,.2f}")

    def values(self) -> tuple[str, str, str, float, float]:
        return (
            self.symbol.currentText().strip().upper(),
            self.name.text().strip(),
            self.date_edit.date().toString("yyyy-MM-dd"),
            self.quantity.value(),
            self.price.value(),
        )

    def accept(self) -> None:
        if not self.symbol.currentText().strip():
            self.symbol.setFocus()
            return
        super().accept()


class EditTransactionDialog(QDialog):
    """Allow editing the date, category, amount, and description of a ledger row."""

    def __init__(
        self,
        transaction: Transaction,
        categories: list[Category],
        parent=None,
        savings_accounts: list[SavingsAccount] | None = None,
        linked_account_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.transaction = transaction
        self.categories = {category.code: category for category in categories}
        self.setWindowTitle(f"Edit transaction - {transaction.id}")
        self.setMinimumWidth(400)

        parsed_date = parse_ledger_date(transaction.date)
        self.date_edit = QDateEdit(QDate(parsed_date.year, parsed_date.month, parsed_date.day))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd, d MMM yyyy")

        self.category = QComboBox()
        for category in categories:
            self.category.addItem(f"{category.label}  -  {category.code}", category.code)
        index = self.category.findData(transaction.kind)
        if index >= 0:
            self.category.setCurrentIndex(index)
        self.category.currentIndexChanged.connect(self._update_savings_choice)

        self.description = QLineEdit(transaction.info)
        self.amount = configure_decimal_input(QDoubleSpinBox())
        self.amount.setRange(-999_999_999.99, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)
        self.amount.setValue(transaction.amount)
        self.savings_account = savings_account_picker(
            savings_accounts or [], linked_account_id
        )

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Date", self.date_edit)
        form.addRow("Category", self.category)
        form.addRow("Amount", self.amount)
        form.addRow("Savings account", self.savings_account)
        form.addRow("Description", self.description)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._update_savings_choice()

    def _update_savings_choice(self) -> None:
        category = self.categories.get(self.category.currentData())
        self.savings_account.setEnabled(category is not None and category.flow == "saving")

    def savings_account_id(self) -> int | None:
        return self.savings_account.currentData() if self.savings_account.isEnabled() else None

    def values(self) -> tuple[str, str, float, str]:
        return (
            self.date_edit.date().toString("dd/MM/yy"),
            self.category.currentData(),
            self.amount.value(),
            self.description.text().strip(),
        )

    def accept(self) -> None:
        if not self.description.text().strip():
            self.description.setFocus()
            self.description.setStyleSheet("border: 1px solid #bd5748;")
            return
        super().accept()


class ExpenseTypeDialog(QDialog):
    """Create or rename an expense type without changing its stored code."""

    def __init__(self, category: Category | None = None, parent=None) -> None:
        super().__init__(parent)
        self.category = category
        self.setWindowTitle("New expense type" if category is None else "Edit expense type")
        self.setMinimumWidth(380)

        self.code = QLineEdit(category.code if category else "")
        self.code.setMaxLength(8)
        if category:
            self.code.setReadOnly(True)
        else:
            self.code.setPlaceholderText("For example, H1")
        self.label = QLineEdit(category.label if category else "")
        self.account = QComboBox()
        self.account.addItem("Budget", "budget")
        self.account.addItem("Hold", "hold")
        if category:
            self.account.setCurrentIndex(self.account.findData(category.account))

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Stable code", self.code)
        form.addRow("Expense type", self.label)
        form.addRow("Default account", self.account)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> Category:
        return Category(
            self.code.text().strip().upper(),
            self.label.text().strip(),
            "expense",
            self.account.currentData(),
        )

    def accept(self) -> None:
        code = self.code.text().strip()
        label = self.label.text().strip()
        if not code or not code.replace("_", "").isalnum() or not label:
            self.code.setFocus() if not code or not code.replace("_", "").isalnum() else self.label.setFocus()
            return
        super().accept()
