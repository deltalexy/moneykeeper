# Moneykeeper

A single-user PyQt5 ledger backed by SQLite.

## Run

Keep the existing shortcut pointed at `moneykeeper.pyw`. The launcher resolves the app directory from its own location, so its working directory does not matter.

## Build a Windows executable

Install the desktop dependency and the packager once:

```powershell
python -m pip install PyQt5 pyinstaller
```

Then build the single-file executable:

```powershell
python build_exe.py
```

The result is `dist\Moneykeeper.exe`. Keep `moneykeeper.sqlite3` and `moneykeeper.ini` beside the executable; the packaged app stores its data there. The `build` and `dist` folders are generated output.

## Build the installer

Install [Inno Setup 6](https://jrsoftware.org/isinfo.php), then run:

```powershell
python build_exe.py --installer
```

This builds the executable first and creates `installer\Moneykeeper-Setup.exe`. The installer uses a per-user location under `%LOCALAPPDATA%`, so it does not require administrator access. It creates Start Menu and Desktop shortcuts. User data is not removed when the application is uninstalled.

## Project layout

- `moneykeeper.pyw` starts the desktop app.
- `moneykeeper.ico` is the application and shortcut icon.
- `build_exe.py` builds the executable and optionally the installer.
- `Moneykeeper.iss` defines the Inno Setup installer.
- `moneykeeper_app/database.py` owns SQLite reads and atomic writes.
- `moneykeeper_app/domain.py` contains category labels, date parsing, summaries, and balance rules.
- `moneykeeper_app/dialogs.py` contains transaction entry and metadata-edit dialogs.
- `moneykeeper_app/window.py` contains the overview, transaction ledger, reports, reconciliation, and settings pages.
- `moneykeeper_app/style.py` defines the shared interface theme.

## Data and sync

`moneykeeper.sqlite3` and `moneykeeper.ini` are kept beside the launcher by default. The database file can be changed from **Settings > Local data > Browse...**; restart Moneykeeper after saving the new location. The selected path is stored in the INI file, while the existing window geometry setting is preserved. The original `moneykeeper.pickle` is retained as an untouched archive. A restricted, one-time importer reads it only when the database has no existing ledger rows.

The Settings page can also adjust the current Budget and Hold positions. Monetary inputs accept a period as the decimal point, for example `12.34`.

Use **Settings > Create database backup** before major edits. Because file-sync services do not coordinate simultaneous SQLite writers, close Moneykeeper on one device and let its sync finish before opening it on another. Do not run two copies against the synced folder at the same time.

## Ledger behavior

New income is allocated between Budget and Hold using the configured Hold target and percentage. Savings entries withdraw from Hold. Other expense categories debit the selected account. Expense labels and default accounts can be edited in Settings; stable category codes keep existing ledger rows intact. The Reports page shows all-time, yearly, and monthly totals by category, with savings displayed separately and excluded from net totals as in the original report. Reconciliation account names, amounts, and multiline notes save automatically after editing. Transaction amounts can be edited in the ledger; as in the original log editor, editing a historical amount updates reports but does not retroactively recalculate Budget or Hold.
