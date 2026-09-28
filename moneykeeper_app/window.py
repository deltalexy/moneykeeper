"""Main Moneykeeper workspace and its four focused pages."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path

from PyQt5.QtCore import QDate, Qt, QSettings, QTimer
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QTextEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .database import Category, Database, Transaction
from .dialogs import EditTransactionDialog, ExpenseTypeDialog, TransactionDialog
from .domain import monthly_summary, parse_ledger_date, report_breakdown, transaction_balance_effect


class SortableItem(QTableWidgetItem):
    """A table cell that sorts by its underlying date or numeric value."""

    def __init__(self, text: str, sort_value=None) -> None:
        super().__init__(text)
        self.sort_value = sort_value

    def __lt__(self, other) -> bool:
        if self.sort_value is not None and isinstance(other, SortableItem):
            if other.sort_value is not None:
                return self.sort_value < other.sort_value
        return super().__lt__(other)


def money(value: float) -> str:
    value = float(value)
    sign = "-" if value < 0 else ""
    return f"{sign}€ {abs(value):,.2f}"


def date_label(value: str) -> str:
    try:
        return parse_ledger_date(value).strftime("%d %b %Y")
    except ValueError:
        return value


def make_table(headers: list[str], parent=None) -> QTableWidget:
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSortingEnabled(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setShowGrid(False)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    return table


def metric_card(title: str, value: str, detail: str, accent: str = "green") -> QFrame:
    card = QFrame()
    card.setObjectName("metricCard")
    card.setProperty("accent", accent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(7)
    heading = QLabel(title.upper())
    heading.setObjectName("metricHeading")
    amount = QLabel(value)
    amount.setObjectName("metricValue")
    subtitle = QLabel(detail)
    subtitle.setObjectName("metricDetail")
    layout.addWidget(heading)
    layout.addWidget(amount)
    layout.addWidget(subtitle)
    return card


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(12)
        layout.addLayout(self.cards_layout)

        tables = QHBoxLayout()
        tables.setSpacing(16)
        monthly_section = self._section("Monthly movement", "Income, spending, and net movement")
        recent_section = self._section("Recent activity", "Latest entries in the ledger")
        self.monthly_table = make_table(["Month", "Income", "Spending", "Saved", "Net"])
        self.recent_table = make_table(["Date", "Category", "Description", "Amount"])
        self.monthly_table.setMinimumHeight(360)
        self.recent_table.setMinimumHeight(360)
        monthly_section.layout().addWidget(self.monthly_table)
        recent_section.layout().addWidget(self.recent_table)
        tables.addWidget(monthly_section, 5)
        tables.addWidget(recent_section, 6)
        layout.addLayout(tables, 1)

    @staticmethod
    def _section(title: str, subtitle: str) -> QFrame:
        section = QFrame()
        section.setObjectName("surface")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        note = QLabel(subtitle)
        note.setObjectName("sectionNote")
        layout.addWidget(heading)
        layout.addWidget(note)
        return section

    def refresh(
        self, state: dict, transactions: list[Transaction], categories: list[Category]
    ) -> None:
        category_labels = {category.code: category.label for category in categories}
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        budget = float(state["budget"])
        hold = float(state["hold"])
        self.cards_layout.addWidget(
            metric_card("Net position", money(budget + hold), "Budget plus held funds", "green"), 0, 0
        )
        self.cards_layout.addWidget(
            metric_card("Budget", money(budget), "Available for day-to-day spending", "coral"), 0, 1
        )
        self.cards_layout.addWidget(
            metric_card("On hold", money(hold), f"Target {money(float(state['holdniv']))}", "blue"), 0, 2
        )
        self.cards_layout.addWidget(
            metric_card("Ledger", f"{len(transactions):,}", "Recorded transactions", "gold"), 0, 3
        )

        summaries = monthly_summary(transactions)[:12]
        self.monthly_table.setSortingEnabled(False)
        self.monthly_table.setRowCount(len(summaries))
        for row, item in enumerate(summaries):
            values = (
                datetime_month(item["month"]),
                money(item["income"]),
                money(item["expenses"]),
                money(item["savings"]),
                money(item["net"]),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column > 0:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.monthly_table.setItem(row, column, cell)
        self.monthly_table.setSortingEnabled(True)
        self.monthly_table.resizeColumnsToContents()

        latest = transactions[:10]
        self.recent_table.setSortingEnabled(False)
        self.recent_table.setRowCount(len(latest))
        for row, transaction in enumerate(latest):
            cells = (
                SortableItem(date_label(transaction.date), parse_ledger_date(transaction.date)),
                QTableWidgetItem(f"{category_labels.get(transaction.kind, transaction.kind)}  -  {transaction.kind}"),
                QTableWidgetItem(transaction.info),
                SortableItem(money(transaction.amount), transaction.amount),
            )
            for column, cell in enumerate(cells):
                if column == 3:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.recent_table.setItem(row, column, cell)
            self.recent_table.item(row, 3).setForeground(
                Qt.darkGreen if transaction.amount >= 0 else Qt.darkRed
            )
        self.recent_table.setSortingEnabled(True)
        self.recent_table.resizeColumnsToContents()


def datetime_month(month: str) -> str:
    return date.fromisoformat(f"{month}-01").strftime("%b %Y")


class TransactionsPage(QWidget):
    def __init__(self, database: Database, on_changed, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.on_changed = on_changed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search descriptions, dates, amounts...")
        self.search.setClearButtonEnabled(True)
        self.category = QComboBox()
        self._load_category_filter()
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("quietButton")
        self.edit_button = QPushButton("Edit selected")
        self.add_button = QPushButton("+  Add transaction")
        self.add_button.setObjectName("primaryButton")
        self.filters_button = QPushButton("Filters")
        self.filters_button.setObjectName("quietButton")
        controls.addWidget(self.search, 1)
        controls.addWidget(self.category)
        controls.addWidget(self.search_button)
        controls.addWidget(self.filters_button)
        controls.addSpacing(8)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.add_button)
        layout.addLayout(controls)

        self.filters_panel = QFrame()
        self.filters_panel.setObjectName("surface")
        filter_layout = QHBoxLayout(self.filters_panel)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        self.from_enabled = QCheckBox("From")
        self.from_date = QDateEdit(QDate.currentDate())
        self.from_date.setCalendarPopup(True)
        self.through_enabled = QCheckBox("Through")
        self.through_date = QDateEdit(QDate.currentDate())
        self.through_date.setCalendarPopup(True)
        self.minimum_amount = QDoubleSpinBox()
        self.minimum_amount.setRange(0, 999_999_999.99)
        self.minimum_amount.setDecimals(2)
        self.minimum_amount.setPrefix("Min € ")
        self.maximum_amount = QDoubleSpinBox()
        self.maximum_amount.setRange(0, 999_999_999.99)
        self.maximum_amount.setDecimals(2)
        self.maximum_amount.setPrefix("Max € ")
        filter_layout.addWidget(self.from_enabled)
        filter_layout.addWidget(self.from_date)
        filter_layout.addWidget(self.through_enabled)
        filter_layout.addWidget(self.through_date)
        filter_layout.addWidget(self.minimum_amount)
        filter_layout.addWidget(self.maximum_amount)
        self.filters_panel.hide()
        layout.addWidget(self.filters_panel)

        section = QFrame()
        section.setObjectName("surface")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(10, 10, 10, 10)
        self.table = make_table(["Date", "Category", "Description", "Amount", "ID"])
        self.table.setColumnHidden(4, True)
        self.table.setColumnWidth(0, 125)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 420)
        self.table.setColumnWidth(3, 145)
        section_layout.addWidget(self.table)
        layout.addWidget(section, 1)
        self.count_label = QLabel()
        self.count_label.setObjectName("sectionNote")
        layout.addWidget(self.count_label)

        self.search_button.clicked.connect(self.refresh)
        self.search.returnPressed.connect(self.refresh)
        self.category.currentIndexChanged.connect(self.refresh)
        self.filters_button.clicked.connect(
            lambda: self.filters_panel.setVisible(not self.filters_panel.isVisible())
        )
        self.from_enabled.toggled.connect(self.refresh)
        self.through_enabled.toggled.connect(self.refresh)
        self.minimum_amount.valueChanged.connect(self.refresh)
        self.maximum_amount.valueChanged.connect(self.refresh)
        self.from_date.dateChanged.connect(self.refresh)
        self.through_date.dateChanged.connect(self.refresh)
        self.add_button.clicked.connect(self.add_transaction)
        self.edit_button.clicked.connect(self.edit_selected)
        self.table.doubleClicked.connect(self.edit_selected)
        self.refresh()

    def refresh(self) -> None:
        self._load_category_filter()
        transactions = self.database.search_transactions(
            self.search.text(), self.category.currentData()
        )
        start_date = self.from_date.date().toPyDate() if self.from_enabled.isChecked() else None
        end_date = self.through_date.date().toPyDate() if self.through_enabled.isChecked() else None
        minimum = self.minimum_amount.value()
        maximum = self.maximum_amount.value()
        transactions = [
            transaction
            for transaction in transactions
            if (start_date is None or parse_ledger_date(transaction.date) >= start_date)
            and (end_date is None or parse_ledger_date(transaction.date) <= end_date)
            and (minimum == 0 or abs(transaction.amount) >= minimum)
            and (maximum == 0 or abs(transaction.amount) <= maximum)
        ]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(transactions))
        category_labels = {
            category.code: category.label for category in self.database.categories()
        }
        for row, transaction in enumerate(transactions):
            date_item = SortableItem(
                date_label(transaction.date), parse_ledger_date(transaction.date)
            )
            date_item.setData(Qt.UserRole, transaction.id)
            category_item = QTableWidgetItem(
                f"{category_labels.get(transaction.kind, transaction.kind)}  -  {transaction.kind}"
            )
            description_item = QTableWidgetItem(transaction.info)
            amount_item = SortableItem(money(transaction.amount), transaction.amount)
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amount_item.setForeground(Qt.darkGreen if transaction.amount >= 0 else Qt.darkRed)
            for column, item in enumerate((date_item, category_item, description_item, amount_item)):
                self.table.setItem(row, column, item)
            self.table.setItem(row, 4, QTableWidgetItem(str(transaction.id)))
        self.table.setSortingEnabled(True)
        self.count_label.setText(f"{len(transactions):,} transactions shown")

    def _load_category_filter(self) -> None:
        selected_code = self.category.currentData()
        categories = self.database.categories()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("All categories", "")
        for category in categories:
            self.category.addItem(f"{category.label}  -  {category.code}", category.code)
        selected_index = self.category.findData(selected_code or "")
        self.category.setCurrentIndex(max(0, selected_index))
        self.category.blockSignals(False)

    def add_transaction(self) -> None:
        categories = self.database.categories()
        dialog = TransactionDialog(categories, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        date_text, category, amount, description, account = dialog.values()
        state = self.database.load_state()
        amount_value, budget_delta, hold_delta = transaction_balance_effect(
            category, amount, state, account
        )
        try:
            self.database.add_transaction(
                date_text, category.code, amount_value, description, budget_delta, hold_delta
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(self, "Could not save", str(error))
            return
        self.on_changed()

    def edit_selected(self, *_args) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        transaction_id = int(self.table.item(row, 4).text())
        transaction = next(
            item for item in self.database.transactions() if item.id == transaction_id
        )
        dialog = EditTransactionDialog(transaction, self.database.categories(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        date_text, kind, amount, description = dialog.values()
        try:
            self.database.update_transaction_details(
                transaction_id, date_text, kind, description, amount
            )
        except sqlite3.Error as error:
            QMessageBox.critical(self, "Could not update", str(error))
            return
        self.on_changed()


class ReportsPage(QWidget):
    def __init__(self, database: Database, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.report_rows: list[dict] = []
        self.report_categories: list[Category] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        controls = QHBoxLayout()
        self.export_button = QPushButton("Export CSV...")
        self.export_button.setObjectName("quietButton")
        controls.addStretch(1)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)

        section = QFrame()
        section.setObjectName("surface")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(10, 10, 10, 10)
        self.table = QTreeWidget()
        self.table.setColumnCount(2)
        self.table.setHeaderLabels(["Period", "Net"])
        self.table.setAlternatingRowColors(True)
        self.table.setUniformRowHeights(True)
        self.table.setRootIsDecorated(True)
        self.table.setItemsExpandable(True)
        self.table.setSortingEnabled(False)
        self.table.header().setStretchLastSection(True)
        section_layout.addWidget(self.table)
        layout.addWidget(section, 1)
        self.count_label = QLabel()
        self.count_label.setObjectName("sectionNote")
        layout.addWidget(self.count_label)

        self.export_button.clicked.connect(self.export_csv)
        self.refresh()

    def refresh(self) -> None:
        transactions = self.database.transactions()
        self.report_categories = self.database.categories()
        self.report_rows = report_breakdown(transactions, self.report_categories)
        headers = ["Period", "Net"] + [
            f"{category.label} ({category.code})" for category in self.report_categories
        ]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHeaderLabels(headers)
        year_items: list[QTreeWidgetItem] = []
        current_year_item = None
        for row in self.report_rows:
            values = [row["period"], money(row["net"])] + [
                money(row["categories"].get(category.code, 0.0))
                for category in self.report_categories
            ]
            item = QTreeWidgetItem(values)
            item.setData(0, Qt.UserRole, row["level"])
            for column in range(1, len(values)):
                item.setTextAlignment(column, Qt.AlignRight | Qt.AlignVCenter)
            item.setForeground(1, Qt.darkGreen if row["net"] >= 0 else Qt.darkRed)
            if row["level"] in ("total", "year"):
                for column in range(len(values)):
                    font = item.font(column)
                    font.setBold(True)
                    item.setFont(column, font)
            if row["level"] == "month":
                if current_year_item is not None:
                    current_year_item.addChild(item)
            else:
                self.table.addTopLevelItem(item)
                if row["level"] == "year":
                    current_year_item = item
                    year_items.append(item)
                else:
                    current_year_item = None
        if year_items:
            year_items[0].setExpanded(True)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 140)
        self.count_label.setText(f"{len(self.report_rows):,} report periods")

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report",
            str(self.database.path.with_name("moneykeeper-report.csv")),
            "CSV file (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as report_file:
                writer = csv.writer(report_file)
                writer.writerow(
                    ["Period", "Net"]
                    + [f"{category.label} ({category.code})" for category in self.report_categories]
                )
                for row in self.report_rows:
                    writer.writerow(
                        [row["period"], row["net"]]
                        + [row["categories"].get(category.code, 0.0) for category in self.report_categories]
                    )
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Report exported", f"Report saved to:\n{path}")


class ReconciliationPage(QWidget):
    ACCOUNT_FIELDS = (
        ("zicht", "Current account"),
        ("mastercard", "Credit card"),
        ("bpaid", "Meal card"),
        ("cash", "Cash"),
        ("inhouse", "At home"),
        ("cheques", "Cheques"),
        ("achterkomend", "Expected in"),
    )

    def __init__(self, database: Database, on_changed, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.on_changed = on_changed
        self.inputs: dict[str, QDoubleSpinBox] = {}
        self.label_inputs: dict[str, QLineEdit] = {}
        self.memo = QTextEdit()
        self.memo.setMinimumHeight(100)
        self.total_label = QLabel()
        self.expected_label = QLabel()
        self.difference_label = QLabel()
        self.date_label = QLabel()
        self.saved_label = QLabel("All changes saved")
        self.saved_label.setObjectName("sectionNote")
        self._loading = False
        self._dirty = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._save_pending)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        accounts = QFrame()
        accounts.setObjectName("surface")
        form = QFormLayout(accounts)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        for key, label in self.ACCOUNT_FIELDS:
            label_input = QLineEdit(label)
            label_input.setMinimumWidth(150)
            self.label_inputs[key] = label_input
            spin = self._money_input()
            self.inputs[key] = spin
            spin.valueChanged.connect(self._schedule_save)
            label_input.textChanged.connect(self._schedule_save)
            form.addRow(label_input, spin)
        form.addRow("Notes", self.memo)
        self.memo.textChanged.connect(self._schedule_save)
        root.addWidget(accounts, 2)

        summary = QFrame()
        summary.setObjectName("surface")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(24, 24, 24, 24)
        summary_layout.setSpacing(14)
        heading = QLabel("Reconciliation")
        heading.setObjectName("sectionTitle")
        summary_layout.addWidget(heading)
        summary_layout.addWidget(self._summary_line("Counted total", self.total_label))
        summary_layout.addWidget(self._summary_line("Moneykeeper total", self.expected_label))
        summary_layout.addWidget(self._summary_line("Difference", self.difference_label))
        summary_layout.addWidget(self._summary_line("Last applied", self.date_label))
        summary_layout.addStretch(1)
        self.apply_button = QPushButton("Apply difference to Budget")
        self.apply_button.setObjectName("primaryButton")
        summary_layout.addWidget(self.saved_label)
        summary_layout.addWidget(self.apply_button)
        root.addWidget(summary, 1)

        self.apply_button.clicked.connect(self.apply_difference)

    @staticmethod
    def _money_input() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-999_999_999.99, 999_999_999.99)
        spin.setDecimals(2)
        spin.setGroupSeparatorShown(True)
        return spin

    @staticmethod
    def _summary_line(title: str, value: QLabel) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName("sectionNote")
        value.setObjectName("summaryValue")
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(value)
        return row

    def refresh(self, state: dict) -> None:
        labels = state.get("reconciliation_labels", {})
        self._loading = True
        try:
            for key, spin in self.inputs.items():
                self.label_inputs[key].setText(
                    str(labels.get(key, dict(self.ACCOUNT_FIELDS)[key]))
                )
                spin.setValue(float(state[key]))
            self.memo.setPlainText(str(state["achterinfo"]))
            self.date_label.setText(str(state["controledatum"]) or "Not yet applied")
            self._dirty = False
            self._save_timer.stop()
            self.saved_label.setText("All changes saved")
        finally:
            self._loading = False
        self._recalculate()

    def _recalculate(self, *_args) -> None:
        state = self.database.load_state()
        counted = sum(spin.value() for spin in self.inputs.values()) - float(state["buffer"])
        expected = float(state["budget"]) + float(state["hold"])
        difference = round(counted - expected, 2)
        self.total_label.setText(money(counted))
        self.expected_label.setText(money(expected))
        self.difference_label.setText(money(difference))
        self.difference_label.setProperty("tone", "positive" if difference >= 0 else "negative")
        self.difference_label.style().unpolish(self.difference_label)
        self.difference_label.style().polish(self.difference_label)

    def _state_from_inputs(self) -> dict:
        state = self.database.load_state()
        for key, spin in self.inputs.items():
            state[key] = spin.value()
        state["reconciliation_labels"] = {
            key: label.text().strip() or dict(self.ACCOUNT_FIELDS)[key]
            for key, label in self.label_inputs.items()
        }
        state["achterinfo"] = self.memo.toPlainText().strip()
        return state

    def _schedule_save(self, *_args) -> None:
        if self._loading:
            return
        self._dirty = True
        self.saved_label.setText("Saving...")
        self._recalculate()
        self._save_timer.start()

    def _save_pending(self) -> None:
        if not self._dirty:
            return
        self.database.save_state(self._state_from_inputs())
        self._dirty = False
        self.saved_label.setText("Saved automatically")
        self.on_changed()

    def flush_pending_changes(self) -> None:
        self._save_timer.stop()
        if self._dirty:
            self.database.save_state(self._state_from_inputs())
            self._dirty = False
            self.saved_label.setText("Saved automatically")

    def apply_difference(self) -> None:
        self._save_timer.stop()
        state = self._state_from_inputs()
        counted = sum(spin.value() for spin in self.inputs.values()) - float(state["buffer"])
        expected = float(state["budget"]) + float(state["hold"])
        adjustment = round(counted - expected, 2)
        state["controledatum"] = date.today().strftime("%d/%m/%y")
        self.database.save_reconciliation(state, adjustment)
        self._dirty = False
        self.on_changed()


class SettingsPage(QWidget):
    def __init__(self, database: Database, on_changed, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.on_changed = on_changed
        self.inputs: dict[str, QDoubleSpinBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        financial = QFrame()
        financial.setObjectName("surface")
        form = QFormLayout(financial)
        form.setContentsMargins(24, 22, 24, 22)
        form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        for key, label in (
            ("itohold", "Income directed to Hold (%)"),
            ("holdniv", "Hold target"),
            ("buffer", "Cash buffer"),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(0, 100 if key == "itohold" else 999_999_999.99)
            spin.setDecimals(2)
            spin.setGroupSeparatorShown(True)
            self.inputs[key] = spin
            form.addRow(label, spin)
        self.save_button = QPushButton("Save preferences")
        self.save_button.setObjectName("primaryButton")
        form.addRow(self.save_button)
        top_row.addWidget(financial, 1)

        data_section = QFrame()
        data_section.setObjectName("surface")
        data_layout = QVBoxLayout(data_section)
        data_layout.setContentsMargins(24, 22, 24, 22)
        data_layout.setSpacing(12)
        heading = QLabel("Local data")
        heading.setObjectName("sectionTitle")
        details = QLabel(
            f"SQLite ledger\n{database.path}\n\n"
            "The database and settings file are stored beside the launcher. "
            "Keep one app instance open at a time while the folder syncs."
        )
        details.setObjectName("sectionNote")
        details.setWordWrap(True)
        self.backup_button = QPushButton("Create database backup...")
        self.backup_button.setObjectName("quietButton")
        data_layout.addWidget(heading)
        data_layout.addWidget(details)
        data_layout.addStretch(1)
        data_layout.addWidget(self.backup_button)
        top_row.addWidget(data_section, 1)
        root.addLayout(top_row)

        category_section = QFrame()
        category_section.setObjectName("surface")
        category_layout = QVBoxLayout(category_section)
        category_layout.setContentsMargins(18, 16, 18, 16)
        category_layout.setSpacing(10)
        category_heading = QLabel("Expense types")
        category_heading.setObjectName("sectionTitle")
        category_note = QLabel("Names and default account are editable; existing transaction codes stay stable.")
        category_note.setObjectName("sectionNote")
        self.category_table = make_table(["Expense type", "Code", "Default account"])
        self.category_table.setMaximumHeight(240)
        self.category_table.setColumnWidth(0, 280)
        self.category_table.setColumnWidth(1, 100)
        category_actions = QHBoxLayout()
        self.add_category_button = QPushButton("Add type")
        self.edit_category_button = QPushButton("Edit selected")
        self.delete_category_button = QPushButton("Delete selected")
        category_actions.addWidget(self.add_category_button)
        category_actions.addWidget(self.edit_category_button)
        category_actions.addWidget(self.delete_category_button)
        category_actions.addStretch(1)
        category_layout.addWidget(category_heading)
        category_layout.addWidget(category_note)
        category_layout.addWidget(self.category_table)
        category_layout.addLayout(category_actions)
        root.addWidget(category_section, 1)

        self.save_button.clicked.connect(self.save_settings)
        self.backup_button.clicked.connect(self.create_backup)
        self.add_category_button.clicked.connect(self.add_expense_type)
        self.edit_category_button.clicked.connect(self.edit_expense_type)
        self.delete_category_button.clicked.connect(self.delete_expense_type)
        self.category_table.doubleClicked.connect(self.edit_expense_type)

    def refresh(self, state: dict) -> None:
        for key, spin in self.inputs.items():
            spin.setValue(float(state[key]))
        categories = self.database.categories("expense")
        self.category_table.setSortingEnabled(False)
        self.category_table.setRowCount(len(categories))
        for row, category in enumerate(categories):
            self.category_table.setItem(row, 0, QTableWidgetItem(category.label))
            self.category_table.setItem(row, 1, QTableWidgetItem(category.code))
            self.category_table.setItem(
                row, 2, QTableWidgetItem("Hold" if category.account == "hold" else "Budget")
            )
        self.category_table.setSortingEnabled(True)

    def _selected_expense_type(self):
        row = self.category_table.currentRow()
        if row < 0:
            return None
        code = self.category_table.item(row, 1).text()
        return next(
            category
            for category in self.database.categories("expense")
            if category.code == code
        )

    def add_expense_type(self) -> None:
        dialog = ExpenseTypeDialog(parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        category = dialog.values()
        if any(item.code == category.code for item in self.database.categories()):
            QMessageBox.warning(self, "Code already used", "Choose a new stable category code.")
            return
        self.database.save_category(category)
        self.on_changed()

    def edit_expense_type(self) -> None:
        category = self._selected_expense_type()
        if category is None:
            return
        dialog = ExpenseTypeDialog(category, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self.database.save_category(dialog.values())
        self.on_changed()

    def delete_expense_type(self) -> None:
        category = self._selected_expense_type()
        if category is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete expense type",
            f"Delete '{category.label}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.database.delete_category(category.code)
        except ValueError as error:
            QMessageBox.warning(self, "Type is in use", str(error))
            return
        self.on_changed()

    def save_settings(self) -> None:
        state = self.database.load_state()
        state.update({key: spin.value() for key, spin in self.inputs.items()})
        self.database.save_state(state)
        self.on_changed()

    def create_backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Create SQLite backup",
            str(self.database.path.with_name("moneykeeper-backup.sqlite3")),
            "SQLite database (*.sqlite3 *.db)",
        )
        if not path:
            return
        try:
            self.database.backup_to(Path(path))
        except sqlite3.Error as error:
            QMessageBox.critical(self, "Backup failed", str(error))
            return
        QMessageBox.information(self, "Backup created", f"Database backup saved to:\n{path}")


class MainWindow(QMainWindow):
    PAGES = (
        ("Overview", "A clear view of your money"),
        ("Transactions", "Search and maintain the ledger"),
        ("Reports", "All-time, yearly, and monthly category totals"),
        ("Reconciliation", "Compare your accounts with Moneykeeper"),
        ("Settings", "Allocation, display, and data"),
    )

    def __init__(self, data_directory: Path) -> None:
        super().__init__()
        self.data_directory = Path(data_directory)
        self.database = Database(
            self.data_directory / "moneykeeper.sqlite3",
            self.data_directory / "moneykeeper.pickle",
        )
        self.settings = QSettings(
            str(self.data_directory / "moneykeeper.ini"), QSettings.IniFormat
        )
        self.setWindowTitle("Moneykeeper")
        self.setMinimumSize(1060, 680)
        self.resize(1420, 900)

        central = QWidget()
        central.setObjectName("appBackground")
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = self._build_sidebar()
        outer.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 24, 30, 24)
        content_layout.setSpacing(20)
        self.header_title = QLabel(self.PAGES[0][0])
        self.header_title.setObjectName("pageTitle")
        self.header_subtitle = QLabel(self.PAGES[0][1])
        self.header_subtitle.setObjectName("sectionNote")
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_box.addWidget(self.header_title)
        title_box.addWidget(self.header_subtitle)
        header = QHBoxLayout()
        header.addLayout(title_box)
        header.addStretch(1)
        self.add_button = QPushButton("+  New transaction")
        self.add_button.setObjectName("primaryButton")
        header.addWidget(self.add_button)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.transactions = TransactionsPage(self.database, self.refresh_data, self)
        self.reports = ReportsPage(self.database, self)
        self.reconciliation = ReconciliationPage(self.database, self.refresh_data, self)
        self.settings_page = SettingsPage(
            self.database, self.refresh_data, self
        )
        for page in (
            self.dashboard,
            self.transactions,
            self.reports,
            self.reconciliation,
            self.settings_page,
        ):
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, 1)
        outer.addWidget(content, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("SQLite ledger ready")

        self.add_button.clicked.connect(self.transactions.add_transaction)
        for index, button in enumerate(self.nav_buttons):
            button.clicked.connect(lambda _checked=False, page=index: self.navigate(page))
        self.refresh_data()
        self.navigate(0)
        geometry = self.settings.value("windows/main/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 24, 18, 20)
        layout.setSpacing(8)
        brand = QLabel("MONEYKEEPER")
        brand.setObjectName("brand")
        tag = QLabel("PERSONAL LEDGER")
        tag.setObjectName("brandTag")
        layout.addWidget(brand)
        layout.addWidget(tag)
        layout.addSpacing(30)
        self.nav_buttons: list[QPushButton] = []
        for index, (title, _subtitle) in enumerate(self.PAGES):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setProperty("pageIndex", index)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        accent = QLabel("SQLITE LEDGER\nOne source of truth")
        accent.setObjectName("sidebarFoot")
        layout.addWidget(accent)
        return sidebar

    def navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.header_title.setText(self.PAGES[index][0])
        self.header_subtitle.setText(self.PAGES[index][1])
        for page_index, button in enumerate(self.nav_buttons):
            button.setChecked(page_index == index)
        if index == 1:
            self.transactions.refresh()
        elif index == 2:
            self.reports.refresh()

    def refresh_data(self) -> None:
        state = self.database.load_state()
        transactions = self.database.transactions()
        categories = self.database.categories()
        self.dashboard.refresh(state, transactions, categories)
        self.reports.refresh()
        self.reconciliation.refresh(state)
        self.settings_page.refresh(state)
        self.transactions.refresh()
        self.statusBar().showMessage(
            f"{len(transactions):,} transactions  |  Net position {money(float(state['budget']) + float(state['hold']))}",
            5000,
        )

    def closeEvent(self, event) -> None:
        self.reconciliation.flush_pending_changes()
        self.settings.setValue("windows/main/geometry", self.saveGeometry())
        self.settings.sync()
        self.database.close()
        super().closeEvent(event)
