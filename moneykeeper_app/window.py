"""Main Moneykeeper workspace and its four focused pages."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path

from PyQt5.QtCore import QDate, QLocale, Qt, QSettings, QTimer
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .database import Category, Database, Transaction
from .dialogs import (
    EditTransactionDialog,
    ExpenseTypeDialog,
    OpeningBalanceDialog,
    PositionDialog,
    SavingsAccountDialog,
    SavingsTransferDialog,
    TransactionDialog,
    TransferDialog,
    ValuationDialog,
)
from .domain import (
    category_spending_shares,
    monthly_category_comparison,
    parse_ledger_date,
    report_breakdown,
    transaction_balance_effect,
)
from .savings import (
    account_history,
    current_positions,
    load_savings_summaries,
    monthly_savings_gain_loss,
    total_savings_value,
)


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


def configure_decimal_input(spin: QDoubleSpinBox) -> QDoubleSpinBox:
    spin.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
    return spin


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
    def __init__(self, database: Database, on_changed, settings: QSettings) -> None:
        super().__init__()
        self.database = database
        self.on_changed = on_changed
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.transfer_button = QPushButton("Transfer Budget / Hold")
        self.transfer_button.setToolTip("Move money between Budget and Hold")
        self.transfer_button.clicked.connect(self.transfer_funds)
        actions.addWidget(self.transfer_button)
        layout.addLayout(actions)

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(12)
        layout.addLayout(self.cards_layout)

        tables = QHBoxLayout()
        tables.setSpacing(16)
        spending_section = self._section(
            "Spending by category",
            "Net category spending and share; monthly view also compares with the prior 24 months",
        )
        recent_section = self._section("Recent activity", "Latest entries in the ledger")
        self.spending_period_mode = QComboBox()
        self.spending_period_mode.addItem("Month", "month")
        self.spending_period_mode.addItem("Year", "year")
        self.spending_period_mode.addItem("Chosen period", "period")
        self.spending_month = QComboBox()
        self.spending_year = QComboBox()
        self.spending_dates = QWidget()
        dates_layout = QHBoxLayout(self.spending_dates)
        dates_layout.setContentsMargins(0, 0, 0, 0)
        self.spending_from = QDateEdit(QDate.currentDate().addDays(-29))
        self.spending_from.setCalendarPopup(True)
        self.spending_from.setDisplayFormat("d MMM yyyy")
        self.spending_from.setToolTip("Start date")
        self.spending_through = QDateEdit(QDate.currentDate())
        self.spending_through.setCalendarPopup(True)
        self.spending_through.setDisplayFormat("d MMM yyyy")
        self.spending_through.setToolTip("End date")
        self.spending_through.setMinimumDate(self.spending_from.date())
        self.spending_from.setMaximumDate(self.spending_through.date())
        dates_layout.addWidget(QLabel("From"))
        dates_layout.addWidget(self.spending_from)
        dates_layout.addWidget(QLabel("Through"))
        dates_layout.addWidget(self.spending_through)
        period_controls = QHBoxLayout()
        period_controls.addWidget(self.spending_period_mode)
        period_controls.addWidget(self.spending_month, 1)
        period_controls.addWidget(self.spending_year, 1)
        period_controls.addWidget(self.spending_dates, 2)
        spending_section.layout().addLayout(period_controls)
        self.spending_period_mode.currentIndexChanged.connect(
            self._update_spending_period_controls
        )
        self.spending_month.currentIndexChanged.connect(
            lambda _index: self._refresh_spending()
        )
        self.spending_year.currentIndexChanged.connect(
            lambda _index: self._refresh_spending()
        )
        self.spending_from.dateChanged.connect(self._spending_start_changed)
        self.spending_through.dateChanged.connect(self._spending_end_changed)
        self.spending_table = make_table(
            ["Category", "Spent", "Share", "24-mo mean", "vs mean"]
        )
        self.recent_table = make_table(["Date", "Category", "Description", "Amount"])
        self.spending_table.setMinimumHeight(360)
        self.recent_table.setMinimumHeight(360)
        spending_section.layout().addWidget(self.spending_table)
        recent_section.layout().addWidget(self.recent_table)
        tables.addWidget(spending_section, 5)
        tables.addWidget(recent_section, 6)
        layout.addLayout(tables, 1)
        self._transactions: list[Transaction] = []
        self._categories: list[Category] = []
        self._update_spending_period_controls()

    def transfer_funds(self) -> None:
        state = self.database.load_state()
        dialog = TransferDialog(float(state["budget"]), float(state["hold"]), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        source, destination, amount = dialog.values()
        try:
            self.database.transfer_funds(source, destination, amount)
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(self, "Could not transfer", str(error))
            return
        self.on_changed()

    def _update_spending_period_controls(self, *_args) -> None:
        mode = self.spending_period_mode.currentData()
        self.spending_month.setVisible(mode == "month")
        self.spending_year.setVisible(mode == "year")
        self.spending_dates.setVisible(mode == "period")
        self._refresh_spending()

    def _spending_start_changed(self, value: QDate) -> None:
        self.spending_through.setMinimumDate(value)
        self._refresh_spending()

    def _spending_end_changed(self, value: QDate) -> None:
        self.spending_from.setMaximumDate(value)
        self._refresh_spending()

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
        savings = load_savings_summaries(self.database)
        savings_value = total_savings_value(savings)
        self.cards_layout.addWidget(
            metric_card(
                "Net position",
                money(budget + hold),
                "Budget plus held funds",
                "green",
            ),
            0,
            0,
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
        savings_gain = sum(item["gain"] or 0.0 for item in savings)
        self.cards_layout.addWidget(
            metric_card(
                "Savings value",
                money(savings_value),
                f"Gain / loss {money(savings_gain)}" if savings else "No accounts tracked yet",
                "green",
            ),
            0,
            4,
        )

        today = date.today()
        self._transactions = transactions
        self._categories = categories
        selected_month = self.spending_month.currentData()
        selected_year = self.spending_year.currentData()
        months = {today.strftime("%Y-%m")}
        years = {today.year}
        for transaction in transactions:
            transaction_date = parse_ledger_date(transaction.date)
            months.add(transaction_date.strftime("%Y-%m"))
            years.add(transaction_date.year)
        self.spending_month.blockSignals(True)
        self.spending_month.clear()
        for month in sorted(months, reverse=True):
            self.spending_month.addItem(datetime_month(month), month)
        selected_index = self.spending_month.findData(selected_month)
        if selected_index >= 0:
            self.spending_month.setCurrentIndex(selected_index)
        self.spending_month.blockSignals(False)
        self.spending_year.blockSignals(True)
        self.spending_year.clear()
        for year in sorted(years, reverse=True):
            self.spending_year.addItem(str(year), year)
        selected_index = self.spending_year.findData(selected_year)
        if selected_index >= 0:
            self.spending_year.setCurrentIndex(selected_index)
        self.spending_year.blockSignals(False)
        self._refresh_spending()

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

    def _refresh_spending(self) -> None:
        mode = self.spending_period_mode.currentData()
        if not mode or self.spending_month.count() == 0:
            return
        monthly = mode == "month"
        self.spending_table.setColumnHidden(3, not monthly)
        self.spending_table.setColumnHidden(4, not monthly)
        if monthly:
            month = self.spending_month.currentData()
            year, month_number = (int(part) for part in month.split("-"))
            spending = monthly_category_comparison(
                self._transactions, self._categories, year, month_number
            )
        else:
            if mode == "year":
                year = int(self.spending_year.currentData())
                start = date(year, 1, 1)
                end = date(year, 12, 31)
            else:
                start = self.spending_from.date().toPyDate()
                end = self.spending_through.date().toPyDate()
            spending = [
                (label, amount, share, None)
                for label, amount, share in category_spending_shares(
                    self._transactions, self._categories, start, end
                )
            ]
        self.spending_table.setSortingEnabled(False)
        self.spending_table.setRowCount(len(spending))
        for row, (label, amount, share, average_share) in enumerate(spending):
            mean_text = f"{average_share:.0%}" if average_share is not None else "N/A"
            difference = share - average_share if average_share is not None else None
            difference_text = (
                f"{difference * 100:+.1f} pp" if difference is not None else "N/A"
            )
            cells = (
                QTableWidgetItem(label),
                SortableItem(money(amount), amount),
                SortableItem(f"{share:.0%}", share),
                SortableItem(mean_text, average_share),
                SortableItem(difference_text, difference),
            )
            for column, cell in enumerate(cells):
                if column > 0:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.spending_table.setItem(row, column, cell)
        self.spending_table.setSortingEnabled(True)
        self.spending_table.resizeColumnsToContents()


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
        self.filters_button = QPushButton("Filters")
        self.filters_button.setObjectName("quietButton")
        controls.addWidget(self.search, 1)
        controls.addWidget(self.category)
        controls.addWidget(self.search_button)
        controls.addWidget(self.filters_button)
        controls.addSpacing(8)
        controls.addWidget(self.edit_button)
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
        self.minimum_amount = configure_decimal_input(QDoubleSpinBox())
        self.minimum_amount.setRange(0, 999_999_999.99)
        self.minimum_amount.setDecimals(2)
        self.minimum_amount.setPrefix("Min € ")
        self.maximum_amount = configure_decimal_input(QDoubleSpinBox())
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
        dialog = TransactionDialog(
            categories, self, savings_accounts=self.database.savings_accounts()
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        date_text, category, amount, description, account = dialog.values()
        state = self.database.load_state()
        amount_value, budget_delta, hold_delta = transaction_balance_effect(
            category, amount, state, account
        )
        try:
            self.database.add_transaction(
                date_text,
                category.code,
                amount_value,
                description,
                budget_delta,
                hold_delta,
                dialog.savings_account_id(),
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
        dialog = EditTransactionDialog(
            transaction,
            self.database.categories(),
            self,
            savings_accounts=self.database.savings_accounts(),
            linked_account_id=self.database.savings_link(transaction_id),
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        date_text, kind, amount, description = dialog.values()
        try:
            self.database.update_transaction_details(
                transaction_id, date_text, kind, description, amount
            )
            self.database.set_savings_link(transaction_id, dialog.savings_account_id())
        except sqlite3.Error as error:
            QMessageBox.critical(self, "Could not update", str(error))
            return
        self.on_changed()


class ReportsPage(QWidget):
    def __init__(self, database: Database, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.settings = settings
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
        self.table.header().setSectionsMovable(True)
        self.table.header().sectionMoved.connect(self._save_category_order)
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
        categories = self.database.categories()
        saved_order = self.settings.value("reports/category_order", [])
        saved_codes = (
            [str(code) for code in saved_order]
            if isinstance(saved_order, (list, tuple))
            else []
        )
        categories_by_code = {category.code: category for category in categories}
        self.report_categories = [
            categories_by_code.pop(code)
            for code in saved_codes
            if code in categories_by_code
        ] + list(categories_by_code.values())
        self.report_rows = report_breakdown(
            transactions,
            self.report_categories,
            monthly_savings_gain_loss=monthly_savings_gain_loss(self.database),
        )
        headers = ["Period", "Net excl. savings", "Net incl. savings", "Savings gain/loss", "Total savings"] + [
            f"{category.label} ({category.code})" for category in self.report_categories
        ]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHeaderLabels(headers)
        header = self.table.header()
        was_blocked = header.blockSignals(True)
        for logical_index in range(header.count()):
            visual_index = header.visualIndex(logical_index)
            if visual_index != logical_index:
                header.moveSection(visual_index, logical_index)
        saved_columns = self.settings.value("reports/column_order", [])
        if isinstance(saved_columns, str):
            saved_columns = [saved_columns]
        keys = self._column_keys()
        wanted = [key for key in (saved_columns or []) if key in keys]
        wanted += [key for key in keys if key not in wanted]
        for visual_index, key in enumerate(wanted):
            current = header.visualIndex(keys.index(key))
            if current != visual_index:
                header.moveSection(current, visual_index)
        header.blockSignals(was_blocked)
        year_items: list[QTreeWidgetItem] = []
        current_year_item = None
        for row in self.report_rows:
            values = [
                row["period"],
                money(row["net_excl_savings"]),
                money(row["net"]),
                money(row["savings_gain_loss"]),
                money(row["total_savings"]),
            ] + [
                money(row["categories"].get(category.code, 0.0))
                for category in self.report_categories
            ]
            item = QTreeWidgetItem(values)
            item.setData(0, Qt.UserRole, row["level"])
            for column in range(1, len(values)):
                item.setTextAlignment(column, Qt.AlignRight | Qt.AlignVCenter)
            item.setForeground(1, Qt.darkGreen if row["net_excl_savings"] >= 0 else Qt.darkRed)
            item.setForeground(2, Qt.darkGreen if row["net"] >= 0 else Qt.darkRed)
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
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 140)
        self.count_label.setText(f"{len(self.report_rows):,} report periods")

    def _column_keys(self) -> list[str]:
        return ["_period", "_net_excl", "_net", "_savings", "_total_savings"] + [
            category.code for category in self.report_categories
        ]

    def _save_category_order(self, *_args) -> None:
        header = self.table.header()
        keys = self._column_keys()
        if header.count() == len(keys):
            self.settings.setValue(
                "reports/column_order",
                [keys[header.logicalIndex(visual)] for visual in range(header.count())],
            )
        category_codes = []
        for visual_index in range(header.count()):
            logical_index = header.logicalIndex(visual_index)
            category_index = logical_index - 5
            if 0 <= category_index < len(self.report_categories):
                category_codes.append(self.report_categories[category_index].code)
        self.settings.setValue("reports/category_order", category_codes)
        self.settings.sync()

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
                    ["Period", "Net excl. savings", "Net incl. savings", "Savings gain/loss", "Total savings"]
                    + [f"{category.label} ({category.code})" for category in self.report_categories]
                )
                for row in self.report_rows:
                    writer.writerow(
                        [row["period"], row["net_excl_savings"], row["net"], row["savings_gain_loss"], row["total_savings"]]
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
        spin = configure_decimal_input(QDoubleSpinBox())
        spin.setRange(-999_999_999.99, 999_999_999.99)
        spin.setDecimals(2)
        spin.setGroupSeparatorShown(True)
        spin.setKeyboardTracking(False)
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
    def __init__(self, database: Database, settings: QSettings, on_changed, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.settings = settings
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
            ("budget", "Budget position"),
            ("hold", "Hold position"),
            ("itohold", "Income directed to Hold (%)"),
            ("holdniv", "Hold target"),
            ("buffer", "Cash buffer"),
        ):
            spin = configure_decimal_input(QDoubleSpinBox())
            spin.setRange(
                0 if key == "itohold" else -999_999_999.99,
                100 if key == "itohold" else 999_999_999.99,
            )
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
        details = QLabel("Choose where Moneykeeper stores its SQLite ledger.")
        details.setObjectName("sectionNote")
        details.setWordWrap(True)
        self.database_path = QLineEdit(str(database.path))
        self.database_path.setReadOnly(True)
        self.database_path.setToolTip("The new location is used after restarting Moneykeeper.")
        self.database_browse_button = QPushButton("Browse...")
        database_row = QHBoxLayout()
        database_row.addWidget(self.database_path, 1)
        database_row.addWidget(self.database_browse_button)
        self.backup_button = QPushButton("Create database backup...")
        self.backup_button.setObjectName("quietButton")
        data_layout.addWidget(heading)
        data_layout.addWidget(details)
        data_layout.addLayout(database_row)
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
        self.database_browse_button.clicked.connect(self.choose_database_path)
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
        selected_path = Path(self.database_path.text()).expanduser()
        if not selected_path.is_absolute():
            selected_path = selected_path.resolve()
        if not selected_path.parent.exists():
            QMessageBox.warning(
                self,
                "Database folder not found",
                f"Create this folder first:\n{selected_path.parent}",
            )
            return
        current_path = self.settings.value("database/path", str(self.database.path))
        if Path(str(current_path)).expanduser().resolve() != selected_path.resolve():
            self._save_database_path(selected_path)
            QMessageBox.information(
                self,
                "Database location saved",
                "Restart Moneykeeper to use the new database location.",
            )
        self.on_changed()

    def _save_database_path(self, path: Path) -> None:
        self.settings.setValue("database/path", str(path))
        self.settings.sync()

    def choose_database_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose SQLite database",
            self.database_path.text(),
            "SQLite database (*.sqlite3 *.db);;All files (*.*)",
        )
        if path:
            selected_path = Path(path).expanduser().resolve()
            self.database_path.setText(str(selected_path))
            if selected_path.parent.exists():
                self._save_database_path(selected_path)
                QMessageBox.information(
                    self,
                    "Database location saved",
                    "Restart Moneykeeper to use the new database location.",
                )

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


class SavingsPage(QWidget):
    """Track savings and stock positions without changing the Budget or Hold balances."""

    def __init__(self, database: Database, on_changed, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.on_changed = on_changed
        self.summaries: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        self.add_account_button = QPushButton("+  Add account")
        self.add_account_button.setObjectName("primaryButton")
        self.edit_account_button = QPushButton("Edit account")
        self.delete_account_button = QPushButton("Delete account")
        self.delete_account_button.setObjectName("quietButton")
        self.move_button = QPushButton("Move between accounts")
        self.move_button.setToolTip("Move value from one savings account to another")
        self.opening_button = QPushButton("Set starting value")
        self.opening_button.setToolTip(
            "Enter what the account already holds; it is not counted as gain or loss"
        )
        self.update_button = QPushButton("Update value")
        self.update_button.setObjectName("primaryButton")
        controls.addWidget(self.add_account_button)
        controls.addWidget(self.edit_account_button)
        controls.addWidget(self.delete_account_button)
        controls.addStretch(1)
        controls.addWidget(self.move_button)
        controls.addWidget(self.opening_button)
        controls.addWidget(self.update_button)
        layout.addLayout(controls)

        accounts_section = QFrame()
        accounts_section.setObjectName("surface")
        accounts_layout = QVBoxLayout(accounts_section)
        accounts_layout.setContentsMargins(10, 10, 10, 10)
        self.accounts_table = make_table(
            ["Account", "Type", "Value", "Contributed", "Gain / loss", "Return", "Last update", "ID"]
        )
        self.accounts_table.setColumnHidden(7, True)
        self.accounts_table.setMaximumHeight(210)
        accounts_layout.addWidget(self.accounts_table)
        layout.addWidget(accounts_section)

        lower = QHBoxLayout()
        lower.setSpacing(16)
        history_section = DashboardPage._section(
            "Value history", "Fluctuation excludes the money you added or withdrew"
        )
        self.history_table = make_table(
            ["Date", "Value", "Contributed", "Gain / loss", "Fluctuation"]
        )
        history_section.layout().addWidget(self.history_table)
        lower.addWidget(history_section, 5)

        details_section = DashboardPage._section(
            "Details", "Positions and the updates you recorded"
        )
        self.tabs = QTabWidget()
        self.positions_table = make_table(["Symbol", "Name", "Quantity", "Price", "Value", "Share"])
        self.valuations_table = make_table(["Date", "Value", "Note", "ID"])
        self.valuations_table.setColumnHidden(3, True)
        self.snapshots_table = make_table(["Date", "Symbol", "Quantity", "Price", "Value", "ID"])
        self.snapshots_table.setColumnHidden(5, True)
        self.tabs.addTab(self.positions_table, "Current positions")
        self.tabs.addTab(self.valuations_table, "Value updates")
        self.tabs.addTab(self.snapshots_table, "Position updates")
        self.delete_entry_button = QPushButton("Delete selected update")
        self.delete_entry_button.setObjectName("quietButton")
        details_section.layout().addWidget(self.tabs)
        details_section.layout().addWidget(self.delete_entry_button, 0, Qt.AlignRight)
        lower.addWidget(details_section, 6)
        layout.addLayout(lower, 1)

        self.footer = QLabel()
        self.footer.setObjectName("sectionNote")
        layout.addWidget(self.footer)

        self.add_account_button.clicked.connect(self.add_account)
        self.edit_account_button.clicked.connect(self.edit_account)
        self.delete_account_button.clicked.connect(self.delete_account)
        self.move_button.clicked.connect(self.move_between_accounts)
        self.opening_button.clicked.connect(self.set_opening_balance)
        self.update_button.clicked.connect(self.update_selected)
        self.delete_entry_button.clicked.connect(self.delete_entry)
        self.accounts_table.itemSelectionChanged.connect(self._show_selected)
        self.refresh()

    def _selected_summary(self) -> dict | None:
        row = self.accounts_table.currentRow()
        if row < 0 or self.accounts_table.item(row, 7) is None:
            return None
        account_id = int(self.accounts_table.item(row, 7).text())
        return next(
            (item for item in self.summaries if item["account"].id == account_id), None
        )

    @staticmethod
    def _signed_item(value: float | None, text: str | None = None) -> SortableItem:
        item = SortableItem("-" if value is None else (text or money(value)), value)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if value is not None:
            item.setForeground(Qt.darkGreen if value >= 0 else Qt.darkRed)
        return item

    @staticmethod
    def _right(item: QTableWidgetItem) -> QTableWidgetItem:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def refresh(self) -> None:
        selected = self._selected_summary()
        selected_id = selected["account"].id if selected else None
        self.summaries = load_savings_summaries(self.database)

        self.accounts_table.blockSignals(True)
        self.accounts_table.setSortingEnabled(False)
        self.accounts_table.setRowCount(len(self.summaries))
        for row, summary in enumerate(self.summaries):
            account = summary["account"]
            value = summary["value"]
            last_update = summary["last_update"]
            cells = (
                QTableWidgetItem(account.name),
                QTableWidgetItem(
                    f"{account.kind}  ({'positions' if account.tracking == 'positions' else 'value'})"
                ),
                self._right(SortableItem("-" if value is None else money(value), value)),
                self._right(SortableItem(money(summary["contributed"]), summary["contributed"])),
                self._signed_item(summary["gain"]),
                self._signed_item(
                    summary["return"],
                    None if summary["return"] is None else f"{summary['return']:+.1%}",
                ),
                self._right(
                    SortableItem(
                        "-" if last_update is None else date_label(last_update.isoformat()),
                        last_update,
                    )
                ),
                QTableWidgetItem(str(account.id)),
            )
            for column, cell in enumerate(cells):
                self.accounts_table.setItem(row, column, cell)
        self.accounts_table.setSortingEnabled(True)
        self.accounts_table.blockSignals(False)

        target_row = 0 if self.summaries else -1
        for row in range(self.accounts_table.rowCount()):
            if int(self.accounts_table.item(row, 7).text()) == selected_id:
                target_row = row
                break
        if target_row >= 0:
            self.accounts_table.selectRow(target_row)
        self._show_selected()

        unlinked = self.database.unlinked_savings_total()
        self.footer.setText(
            f"Savings transactions not linked to an account: {money(unlinked)}. "
            "Link them from Transactions > Edit selected."
            if unlinked
            else "Savings value is tracked separately and never changes Budget or Hold."
        )

    def _fill_history(self, summary: dict) -> None:
        account = summary["account"]
        account_id = account.id
        valuations = self.database.valuations(account_id)
        snapshots = self.database.holding_snapshots(account_id)
        contributions = [
            (when, amount)
            for linked_id, when, amount in self.database.savings_contributions()
            if linked_id == account_id
        ]
        history = list(reversed(account_history(account, valuations, snapshots, contributions)))

        self.history_table.setSortingEnabled(False)
        self.history_table.setRowCount(len(history))
        for row, point in enumerate(history):
            cells = (
                SortableItem(date_label(point["date"].isoformat()), point["date"]),
                self._right(SortableItem(money(point["value"]), point["value"])),
                self._right(SortableItem(money(point["contributed"]), point["contributed"])),
                self._signed_item(point["gain"]),
                self._signed_item(point["fluctuation"]),
            )
            for column, cell in enumerate(cells):
                self.history_table.setItem(row, column, cell)
        self.history_table.setSortingEnabled(True)

        positions = current_positions(snapshots)
        holding_names = {item.id: item.name for item in self.database.savings_holdings(account_id)}
        total = sum(item.quantity * item.price for item in positions)
        self.positions_table.setSortingEnabled(False)
        self.positions_table.setRowCount(len(positions))
        for row, item in enumerate(positions):
            position_value = item.quantity * item.price
            share = position_value / total if total else 0.0
            cells = (
                QTableWidgetItem(item.symbol),
                QTableWidgetItem(holding_names.get(item.holding_id, "")),
                self._right(SortableItem(f"{item.quantity:,.6g}", item.quantity)),
                self._right(SortableItem(f"{item.price:,.4f}", item.price)),
                self._right(SortableItem(money(position_value), position_value)),
                self._right(SortableItem(f"{share:.0%}", share)),
            )
            for column, cell in enumerate(cells):
                self.positions_table.setItem(row, column, cell)
        self.positions_table.setSortingEnabled(True)

        self.valuations_table.setSortingEnabled(False)
        self.valuations_table.setRowCount(len(valuations))
        transfer_amounts = self.database.transfer_amounts()
        previous_values: dict[int, float] = {}
        deltas: dict[int, float] = {}
        for item in valuations:
            deltas[item.id] = item.value - previous_values.get(item.account_id, 0.0)
            previous_values[item.account_id] = item.value
        for row, item in enumerate(reversed(valuations)):
            if item.note == self.database.TRANSFER_NOTE:
                moved = transfer_amounts.get(item.id, deltas[item.id])
                value_cell = self._signed_item(
                    moved, f"{'+' if moved > 0 else ''}{money(moved)}"
                )
            else:
                value_cell = self._right(SortableItem(money(item.value), item.value))
            cells = (
                SortableItem(date_label(item.date), parse_ledger_date(item.date)),
                value_cell,
                QTableWidgetItem(item.note),
                QTableWidgetItem(str(item.id)),
            )
            for column, cell in enumerate(cells):
                self.valuations_table.setItem(row, column, cell)
        self.valuations_table.setSortingEnabled(True)

        self.snapshots_table.setSortingEnabled(False)
        self.snapshots_table.setRowCount(len(snapshots))
        for row, item in enumerate(reversed(snapshots)):
            cells = (
                SortableItem(date_label(item.date), parse_ledger_date(item.date)),
                QTableWidgetItem(item.symbol),
                self._right(SortableItem(f"{item.quantity:,.6g}", item.quantity)),
                self._right(SortableItem(f"{item.price:,.4f}", item.price)),
                self._right(
                    SortableItem(money(item.quantity * item.price), item.quantity * item.price)
                ),
                QTableWidgetItem(str(item.id)),
            )
            for column, cell in enumerate(cells):
                self.snapshots_table.setItem(row, column, cell)
        self.snapshots_table.setSortingEnabled(True)

    def _show_selected(self) -> None:
        summary = self._selected_summary()
        has_account = summary is not None
        self.edit_account_button.setEnabled(has_account)
        self.delete_account_button.setEnabled(has_account)
        self.update_button.setEnabled(has_account)
        self.opening_button.setEnabled(has_account)
        self.delete_entry_button.setEnabled(has_account)
        if summary is None:
            for table in (
                self.history_table,
                self.positions_table,
                self.valuations_table,
                self.snapshots_table,
            ):
                table.setRowCount(0)
            return
        positions = summary["account"].tracking == "positions"
        self.update_button.setText("Update position" if positions else "Update value")
        self.tabs.setTabEnabled(0, positions)
        self.tabs.setTabEnabled(1, not positions)
        self.tabs.setTabEnabled(2, positions)
        self.tabs.setCurrentIndex(0 if positions else 1)
        self._fill_history(summary)

    def _report_error(self, title: str, error: Exception) -> None:
        QMessageBox.critical(self, title, str(error))

    def add_account(self) -> None:
        dialog = SavingsAccountDialog(parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        name, kind, tracking = dialog.values()
        try:
            self.database.save_savings_account(name, kind, tracking)
        except (sqlite3.Error, ValueError) as error:
            self._report_error("Could not save account", error)
            return
        self.on_changed()
        for row in range(self.accounts_table.rowCount()):
            if self.accounts_table.item(row, 0).text() == name:
                self.accounts_table.selectRow(row)
                break

    def edit_account(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        account = summary["account"]
        dialog = SavingsAccountDialog(account, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        name, kind, tracking = dialog.values()
        try:
            self.database.save_savings_account(name, kind, tracking, account.id)
        except (sqlite3.Error, ValueError) as error:
            self._report_error("Could not save account", error)
            return
        self.on_changed()

    def delete_account(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        account = summary["account"]
        answer = QMessageBox.question(
            self,
            "Delete account",
            f"Delete '{account.name}' and all of its recorded values and positions?\n\n"
            "Ledger transactions are kept; only their link to this account is removed. "
            "Budget and Hold are not affected.",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.database.delete_savings_account(account.id)
        except sqlite3.Error as error:
            self._report_error("Could not delete account", error)
            return
        self.on_changed()

    def move_between_accounts(self) -> None:
        accounts = self.database.savings_accounts()
        if len(accounts) < 2:
            QMessageBox.information(
                self, "Move funds", "Add at least two savings accounts to move funds between them."
            )
            return
        summary = self._selected_summary()
        dialog = SavingsTransferDialog(
            accounts, summary["account"].id if summary else None, self
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            self.database.transfer_between_savings(*dialog.values())
        except (sqlite3.Error, ValueError) as error:
            self._report_error("Could not move funds", error)
            return
        self.on_changed()

    def set_opening_balance(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        account = summary["account"]
        dialog = OpeningBalanceDialog(
            account.name,
            account.tracking,
            self.database.opening_balance(account.id),
            self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        when, amount = dialog.values()
        try:
            self.database.set_opening_balance(account.id, when, amount)
        except (sqlite3.Error, ValueError) as error:
            self._report_error("Could not save starting value", error)
            return
        self.on_changed()

    def update_selected(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        account = summary["account"]
        try:
            if account.tracking == "positions":
                holdings = [
                    (item.symbol, item.name)
                    for item in self.database.savings_holdings(account.id)
                ]
                dialog = PositionDialog(account.name, holdings, self)
                if dialog.exec_() != QDialog.Accepted:
                    return
                symbol, name, when, quantity, price = dialog.values()
                self.database.add_holding_snapshot(
                    account.id, symbol, name, when, quantity, price
                )
            else:
                dialog = ValuationDialog(account.name, summary["value"], self)
                if dialog.exec_() != QDialog.Accepted:
                    return
                when, value, note = dialog.values()
                self.database.add_valuation(account.id, when, value, note)
        except (sqlite3.Error, ValueError) as error:
            self._report_error("Could not save update", error)
            return
        self.on_changed()

    def delete_entry(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        positions = summary["account"].tracking == "positions"
        table = self.snapshots_table if positions else self.valuations_table
        id_column = 5 if positions else 3
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Delete update", "Select an update in the list first."
            )
            return
        entry_id = int(table.item(row, id_column).text())
        try:
            if positions:
                self.database.delete_holding_snapshot(entry_id)
            else:
                self.database.delete_valuation(entry_id)
        except sqlite3.Error as error:
            self._report_error("Could not delete update", error)
            return
        self.on_changed()


class MainWindow(QMainWindow):
    PAGES = (
        ("Overview", "A clear view of your money"),
        ("Transactions", "Search and maintain the ledger"),
        ("Reports", "All-time, yearly, and monthly category totals"),
        ("Savings", "Savings and stock positions, tracked apart from Budget and Hold"),
        ("Reconciliation", "Compare your accounts with Moneykeeper"),
        ("Settings", "Allocation, display, and data"),
    )

    def __init__(self, data_directory: Path) -> None:
        super().__init__()
        self.data_directory = Path(data_directory)
        self.settings = QSettings(
            str(self.data_directory / "moneykeeper.ini"), QSettings.IniFormat
        )
        configured_database = self.settings.value(
            "database/path", str(self.data_directory / "moneykeeper.sqlite3")
        )
        self.database = Database(
            Path(str(configured_database)).expanduser(),
            self.data_directory / "moneykeeper.pickle",
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
        self.dashboard = DashboardPage(self.database, self.refresh_data, self.settings)
        self.transactions = TransactionsPage(self.database, self.refresh_data, self)
        self.reports = ReportsPage(self.database, self.settings, self)
        self.savings = SavingsPage(self.database, self.refresh_data, self)
        self.reconciliation = ReconciliationPage(self.database, self.refresh_data, self)
        self.settings_page = SettingsPage(
            self.database, self.settings, self.refresh_data, self
        )
        for page in (
            self.dashboard,
            self.transactions,
            self.reports,
            self.savings,
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
        self.savings.refresh()
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
