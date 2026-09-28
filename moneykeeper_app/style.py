"""A restrained green-and-coral palette for the ledger workspace."""

APP_STYLE = """
QMainWindow, QWidget#appBackground {
    background: #f1f5f2;
    color: #20342f;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 10pt;
}
QFrame#sidebar {
    background: #183b34;
    border: 0;
}
QLabel#brand {
    color: #f4f8f5;
    font-size: 16pt;
    font-weight: 700;
}
QLabel#brandTag {
    color: #a8c2b7;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#sidebarFoot {
    color: #a8c2b7;
    border-top: 1px solid #34574e;
    padding-top: 14px;
    font-size: 9pt;
    line-height: 1.5;
}
QPushButton#navButton {
    color: #c4d5ce;
    background: transparent;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 3px;
    padding: 12px 12px;
    text-align: left;
    font-weight: 600;
}
QPushButton#navButton:hover {
    color: #ffffff;
    background: #244b42;
}
QPushButton#navButton:checked {
    color: #ffffff;
    background: #2a5147;
    border-left-color: #e89172;
}
QLabel#pageTitle {
    color: #183b34;
    font-size: 23pt;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #203c35;
    font-size: 12pt;
    font-weight: 700;
}
QLabel#sectionNote, QLabel#metricDetail {
    color: #74847d;
    font-size: 9pt;
}
QLabel#metricHeading {
    color: #77877f;
    font-size: 8pt;
    font-weight: 700;
}
QLabel#metricValue {
    color: #203c35;
    font-size: 19pt;
    font-weight: 700;
}
QLabel#summaryValue {
    color: #203c35;
    font-size: 12pt;
    font-weight: 700;
}
QLabel#summaryValue[tone="positive"] { color: #257357; }
QLabel#summaryValue[tone="negative"] { color: #bd5748; }
QFrame#surface, QFrame#metricCard {
    background: #ffffff;
    border: 1px solid #dce5df;
    border-radius: 6px;
}
QFrame#metricCard[accent="green"] { border-top: 3px solid #258164; }
QFrame#metricCard[accent="coral"] { border-top: 3px solid #dc795e; }
QFrame#metricCard[accent="blue"] { border-top: 3px solid #4c8b88; }
QFrame#metricCard[accent="gold"] { border-top: 3px solid #d2a34d; }
QPushButton {
    background: #ffffff;
    color: #315148;
    border: 1px solid #d1ddd6;
    border-radius: 4px;
    padding: 8px 12px;
    font-weight: 600;
}
QPushButton:hover { background: #f0f6f2; border-color: #9db8aa; }
QPushButton:pressed { background: #e4eee8; }
QPushButton#primaryButton {
    background: #23775d;
    color: #ffffff;
    border: 1px solid #23775d;
    padding: 9px 16px;
}
QPushButton#primaryButton:hover { background: #1b644d; }
QPushButton#quietButton { background: #edf4ef; border-color: #dce8df; }
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    color: #20342f;
    border: 1px solid #d2ddd6;
    border-radius: 4px;
    padding: 8px 9px;
    selection-background-color: #75a994;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus {
    border: 1px solid #4d9478;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f6f9f7;
    color: #2e4039;
    border: 0;
    selection-background-color: #e2f0e9;
    selection-color: #183b34;
    gridline-color: transparent;
}
QHeaderView::section {
    background: #f2f6f3;
    color: #64766d;
    border: 0;
    border-bottom: 1px solid #dce5df;
    padding: 10px 8px;
    font-weight: 700;
    font-size: 8pt;
}
QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid #edf1ee; }
QTableWidget::item:selected { background: #e2f0e9; color: #183b34; }
QScrollBar:vertical { background: #f0f4f1; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #b6c9bf; min-height: 26px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #8eaa9b; }
QScrollBar:horizontal { background: #f0f4f1; height: 11px; margin: 0; }
QScrollBar::handle:horizontal { background: #b6c9bf; min-width: 26px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: #8eaa9b; }
QStatusBar { background: #f1f5f2; color: #728179; border-top: 1px solid #dde5df; }
QDialog { background: #f7faf8; }
"""
