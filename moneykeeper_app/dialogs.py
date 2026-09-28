"""Focused dialogs for creating and correcting ledger entries."""

from __future__ import annotations

from PyQt5.QtCore import QDate
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

from .database import Category, Transaction
from .domain import parse_ledger_date


class TransactionDialog(QDialog):
    """Collect a new transaction without exposing storage-format details."""

    def __init__(self, categories: list[Category], parent=None) -> None:
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

        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setSingleStep(1.0)
        self.amount.setGroupSeparatorShown(True)

        self.account = QComboBox()
        self.account.addItem("Budget", "budget")
        self.account.addItem("Hold", "hold")
        self.description = QLineEdit()
        self.description.setPlaceholderText("Merchant or note")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Date", self.date_edit)
        form.addRow("Category", self.category)
        form.addRow("Amount", self.amount)
        form.addRow("Pay from", self.account)
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
        if category.flow == "income":
            self.account.setToolTip("Income is allocated using the hold target settings.")
        elif category.flow == "saving":
            self.account.setToolTip("Savings withdrawals are taken from Hold.")
        else:
            self.account.setToolTip("")

    def values(self) -> tuple[str, Category, float, str, str]:
        return (
            self.date_edit.date().toString("dd/MM/yy"),
            self.categories[self.category.currentData()],
            self.amount.value(),
            self.description.text().strip(),
            self.account.currentData(),
        )

    def accept(self) -> None:
        if not self.description.text().strip():
            self.description.setFocus()
            self.description.setStyleSheet("border: 1px solid #bd5748;")
            return
        super().accept()


class EditTransactionDialog(QDialog):
    """Allow editing the date, category, amount, and description of a ledger row."""

    def __init__(
        self, transaction: Transaction, categories: list[Category], parent=None
    ) -> None:
        super().__init__(parent)
        self.transaction = transaction
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

        self.description = QLineEdit(transaction.info)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(-999_999_999.99, 999_999_999.99)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)
        self.amount.setValue(transaction.amount)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.addRow("Date", self.date_edit)
        form.addRow("Category", self.category)
        form.addRow("Amount", self.amount)
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
