#!/usr/bin/env python3
"""Command-line twin of notebook.ipynb - the server room temperature analysis.

This runs the same analysis as the Jupyter notebook, but from a plain terminal on
a machine that only has Python installed. It installs any missing packages by
itself, finds the logger file automatically (a single .csv or .xlsx beside this
script or in a data/ folder next to it, or a path given on the command line),
and writes every figure and a text report into an output/ folder beside it.

Usage:
    python temperature_analysis.py                 # auto-detect the logger file
    python temperature_analysis.py path/to/file.csv   # use a specific file
"""

# ===========================================================================
# Bootstrap - install and import the third-party packages the notebook uses
# ===========================================================================
import os
import sys
import glob
import argparse
import subprocess


def ensure(import_name, pip_name=None):
    """Import a package, installing it with pip first if it is missing."""
    try:
        __import__(import_name)
    except ImportError:
        print(f"installing missing package: {pip_name or import_name} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name or import_name])
        __import__(import_name)


# The notebook imports numpy, pandas and matplotlib; openpyxl is only needed if
# the input is an .xlsx, so it is installed later, on demand, inside load_table.
for _package in ("numpy", "pandas", "matplotlib"):
    ensure(_package)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")             # headless backend: write image files, never open a window
import matplotlib.pyplot as plt

# ===========================================================================
# Paths and small helpers (the script's equivalents of notebook plumbing)
# ===========================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")   # every chart is saved in this folder
SLUG = "duvha_temp"                               # short prefix put on each chart's file name


class Tee:
    """Write to several streams at once, so console output is also saved to a file."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def safe_relpath(path, start):
    """Relative path for display, falling back to the full path across drives (Windows)."""
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return path


def _list_data_files(folder):
    """The .csv/.xlsx files in a folder, ignoring Excel lock files (~$...)."""
    files = sorted(glob.glob(os.path.join(folder, "*.csv"))
                   + glob.glob(os.path.join(folder, "*.xlsx")))
    return [f for f in files if not os.path.basename(f).startswith("~$")]


def _auto_detect_or_none():
    """The single .csv/.xlsx from the first search folder that has exactly one
    (beside the script, then its data/ folder). Exits if a folder has several."""
    for folder in (SCRIPT_DIR, os.path.join(SCRIPT_DIR, "data")):
        matches = _list_data_files(folder)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            sys.exit("error: several data files found in "
                     f"{folder}; pass one explicitly:\n  " + "\n  ".join(matches))
    return None


def find_input_file(cli_path):
    """Locate the logger file. A path argument wins when it exists; if it does not,
    fall back to the single .csv/.xlsx beside the script or in its data/ folder."""
    if cli_path and os.path.isfile(cli_path):
        return cli_path

    detected = _auto_detect_or_none()
    if cli_path:   # a name was given but it was not found on disk
        if detected:
            print(f"note: '{cli_path}' not found; using the only data file available: "
                  f"{os.path.basename(detected)}")
            return detected
        sys.exit(f"error: file not found: {cli_path}, and no .csv or .xlsx found nearby "
                 "to fall back to")
    if detected:
        return detected
    sys.exit("error: no .csv or .xlsx found beside the script or in data/; "
             "pass a path as an argument")


def load_table(path):
    """Read the logger file into a table, choosing the reader by file type."""
    if path.lower().endswith(".xlsx"):
        ensure("openpyxl")            # pandas needs openpyxl to read .xlsx
        return pd.read_excel(path)
    return pd.read_csv(path)


def save_figure(figure, name):
    """Save a chart to output/ under the site slug (the notebook showed it inline)."""
    path = os.path.join(OUTPUT_DIR, f"{SLUG}_{name}.png")
    figure.savefig(path, dpi=120, bbox_inches="tight")
    print(f"saved {safe_relpath(path, SCRIPT_DIR)}")
    plt.close(figure)


# ===========================================================================
# The analysis - the notebook's code cells, ported in order
# ===========================================================================
def run_analysis(input_path):
    # --- Config (notebook cell 8) ------------------------------------------
    DROP_HIGHEST = 1   # how many of the hottest servers to set aside before averaging
    WARN_SET = 26.0    # the average must go above this to raise a warning
    CRIT_SET = 28.0    # above this it is treated as critical
    CLEAR_GAP = 1.0    # only sound the all-clear once the average drops this far below the line
    PERSIST_N = 2      # how many readings in a row must be over the line before alarming

    print("Config loaded.")
    print(f"  data source  : {safe_relpath(os.path.dirname(input_path), SCRIPT_DIR)}/")
    print(f"  charts saved : {os.path.basename(OUTPUT_DIR)}/{SLUG}_*.png")
    print(f"  warn above {WARN_SET} C, critical above {CRIT_SET} C")
    print(f"  all-clear below {WARN_SET - CLEAR_GAP} C, after {PERSIST_N} readings in a row")

    # --- Loading the data (notebook cell 10) -------------------------------
    raw = load_table(input_path)
    raw.columns = [str(name).strip() for name in raw.columns]

    # The first column is the timestamp; every column after it is one server. The
    # servers are relabelled Server 1, Server 2, ... so no internal hostname appears.
    TIME_COL = raw.columns[0]
    original_sensor_cols = [name for name in raw.columns if name != TIME_COL]
    SENSOR_COLS = [f"Server {i + 1}" for i in range(len(original_sensor_cols))]
    raw = raw.rename(columns=dict(zip(original_sensor_cols, SENSOR_COLS)))

    print(f"Rows in the file : {len(raw):,}")
    print(f"Servers detected : {len(SENSOR_COLS)}")
    for name in SENSOR_COLS:
        print(f"  - {name}")
    print(raw.head())

    # --- Getting the data ready (notebook cell 12) -------------------------
    for name in SENSOR_COLS:
        raw[name] = pd.to_numeric(raw[name], errors="coerce")
    raw["timestamp"] = pd.to_datetime(
        raw[TIME_COL].astype(str).str.strip(), format="%Y%m%d %H:%M", errors="coerce"
    )
    print("Readings are now numbers and timestamps are now dates.")
    print(f"Period covered: {raw['timestamp'].min():%Y-%m-%d} to {raw['timestamp'].max():%Y-%m-%d}")

    # --- Any problems in the data? (notebook cell 14) ----------------------
    missing_per_sensor = raw[SENSOR_COLS].isna().sum()
    rows_any_missing = raw[SENSOR_COLS].isna().any(axis=1).sum()
    duplicate_rows = raw.duplicated().sum()
    off_grid = (~raw["timestamp"].dt.minute.isin([0, 30])).sum()

    print(f"Rows with a missing reading : {rows_any_missing}")
    print(f"Duplicate rows              : {duplicate_rows}")
    print(f"Off-schedule timestamps     : {off_grid}")
    print("Missing readings per server:")
    for name, count in missing_per_sensor.items():
        print(f"  {name}: {count}")

    # --- Data coverage chart (notebook cells 16 + 18) ----------------------
    readings_per_day = (
        raw.dropna(subset=["timestamp"])
           .set_index("timestamp")
           .resample("D").size()
    )
    readings_per_month = readings_per_day.resample("MS").sum()
    days_in_month = readings_per_day.resample("MS").size()
    full_coverage_per_month = days_in_month * 48   # 48 half-hours make a full day

    figure, axis = plt.subplots(figsize=(11, 4))
    axis.bar(readings_per_month.index, readings_per_month.values,
             width=20, color="steelblue", label="readings received")
    axis.plot(full_coverage_per_month.index, full_coverage_per_month.values,
              color="gray", linestyle="--", label="full coverage (48 per day)")
    axis.set_title("Data coverage by month")
    axis.set_ylabel("readings per month")
    axis.legend(loc="lower left")
    figure.autofmt_xdate()
    save_figure(figure, "coverage")

    # --- Reproducing the alarm's own number (notebook cell 21) -------------
    temperatures = raw[SENSOR_COLS].values
    sorted_low_to_high = np.sort(temperatures, axis=1)
    kept = sorted_low_to_high[:, :-DROP_HIGHEST]   # every column except the hottest
    raw["room_temp"] = np.nanmean(kept, axis=1)    # average of the rest, ignoring blanks

    room_temp = raw["room_temp"]
    share_over_warn = (room_temp > WARN_SET).mean() * 100

    print(f"Lowest room reading  : {room_temp.min():.1f} C")
    print(f"Typical (median)     : {room_temp.median():.1f} C")
    print(f"Highest room reading : {room_temp.max():.1f} C")
    print(f"Share above {WARN_SET:.0f} C     : {share_over_warn:.1f}%")

    # --- Confirming the limits (notebook cell 24) --------------------------
    for limit, label in [(WARN_SET, "warning, above 26"),
                         (CRIT_SET, "critical actually used, above 28"),
                         (32.0, "the unused 32 setting")]:
        above = room_temp > limit
        print(f"{label:<34}: {above.sum():>6,} readings  ({above.mean() * 100:.2f}%)")

    # --- Where the room number spends its time (notebook cell 27) ----------
    figure, axis = plt.subplots(figsize=(11, 4))
    bands = np.arange(21, 36, 0.5)
    axis.hist(room_temp.dropna(), bins=bands, color="steelblue", edgecolor="white")
    axis.axvline(WARN_SET, color="orange", linestyle="--", linewidth=2, label=f"warning ({WARN_SET:.0f} C)")
    axis.axvline(CRIT_SET, color="red", linestyle="--", linewidth=2, label=f"critical ({CRIT_SET:.0f} C)")
    axis.set_title("Where the room number spends its time")
    axis.set_xlabel("room number (degrees C)")
    axis.set_ylabel("number of readings")
    axis.legend()
    save_figure(figure, "distribution")

    # --- The flapping, made visible (notebook cell 30) ---------------------
    room_over_time = pd.Series(room_temp.values, index=raw["timestamp"]).sort_index()
    above_line = room_over_time > WARN_SET
    crossings = above_line & ~above_line.shift(1, fill_value=False)

    crossings_per_week = crossings.resample("W").sum()
    busiest_week_end = crossings_per_week.idxmax()
    window = room_over_time.loc[busiest_week_end - pd.Timedelta(days=7):busiest_week_end]
    print(f"Flappiest week ends {busiest_week_end:%Y-%m-%d}, with {int(crossings_per_week.max())} crossings")

    figure, axis = plt.subplots(figsize=(11, 4))
    axis.plot(window.index, window.values, color="steelblue", marker=".", label="room number")
    axis.axhline(WARN_SET, color="orange", linestyle="--", label="warning (26 C)")
    axis.set_title(f"The room number crossing 26, week ending {busiest_week_end:%Y-%m-%d}")
    axis.set_ylabel("room number (degrees C)")
    axis.legend()
    figure.autofmt_xdate()
    save_figure(figure, "flapping_week")

    # --- How long does each breach last? (notebook cell 33) ----------------
    above = room_over_time > WARN_SET
    run_id = (above != above.shift()).cumsum()
    runs = above.groupby(run_id).agg(state="first", length="size")
    breach_lengths = runs.loc[runs["state"], "length"]

    total = len(breach_lengths)
    single = (breach_lengths <= 1).sum()
    under_hour = (breach_lengths <= 2).sum()
    print(f"Breach episodes (times the room went over 26): {total}")
    print(f"  just one reading (<= 30 min)   : {single} ({single / total * 100:.0f}%)")
    print(f"  an hour or less  (<= 2 readings): {under_hour} ({under_hour / total * 100:.0f}%)")
    print(f"  median length: {breach_lengths.median():.0f} readings ({breach_lengths.median() * 0.5:.1f} hours)")

    hours = breach_lengths * 0.5
    buckets = pd.cut(hours, bins=[0, 0.5, 1, 3, 1000],
                     labels=["30 min", "1 hour", "1 to 3 hours", "over 3 hours"])
    counts = buckets.value_counts().reindex(["30 min", "1 hour", "1 to 3 hours", "over 3 hours"])

    figure, axis = plt.subplots(figsize=(9, 4))
    axis.bar(counts.index, counts.values, color="steelblue")
    axis.set_title("How long each breach of 26 lasts")
    axis.set_ylabel("number of breach episodes")
    save_figure(figure, "breach_lengths")

    # --- The alarm-counting rules (notebook cell 36) -----------------------
    def count_hysteresis(values, warn, clear):
        """Alarm turns on above `warn`, and only off once it drops below `clear`."""
        alarms, alarmed = 0, False
        for value in values:
            if not alarmed and value > warn:
                alarmed, alarms = True, alarms + 1
            elif alarmed and value < clear:
                alarmed = False
        return alarms

    def count_persistence(values, warn, n):
        """Alarm needs `n` readings in a row above `warn` before it fires."""
        alarms, run, armed = 0, 0, True
        for value in values:
            if value > warn:
                run += 1
                if run >= n and armed:
                    alarms, armed = alarms + 1, False
            else:
                run, armed = 0, True
        return alarms

    def count_combined(values, warn, clear, n):
        """Both rules together: needs `n` in a row to fire, clears below `clear`."""
        alarms, alarmed, run = 0, False, 0
        for value in values:
            run = run + 1 if value > warn else 0
            if not alarmed and run >= n:
                alarmed, alarms = True, alarms + 1
            elif alarmed and value < clear:
                alarmed = False
        return alarms

    print("Three alarm-counting rules defined.")

    # --- How many emails does each rule send? (notebook cell 38) -----------
    values = room_over_time.values
    clear_line = WARN_SET - CLEAR_GAP   # 26 - 1 = 25

    baseline = int((above_line & ~above_line.shift(1, fill_value=False)).sum())

    labels = ["current", "hysteresis", "persistence", "combined"]
    alarm_counts = [
        baseline,
        count_hysteresis(values, WARN_SET, clear_line),
        count_persistence(values, WARN_SET, PERSIST_N),
        count_combined(values, WARN_SET, clear_line, PERSIST_N),
    ]
    for label, count in zip(labels, alarm_counts):
        print(f"{label:<12}: {count} alarm emails")

    figure, axis = plt.subplots(figsize=(9, 4))
    axis.bar(labels, alarm_counts, color=["gray", "steelblue", "steelblue", "seagreen"])
    axis.set_title("Alarm emails over three years, by rule")
    axis.set_ylabel("number of alarm emails")
    for x, count in enumerate(alarm_counts):
        axis.text(x, count, str(count), ha="center", va="bottom")
    save_figure(figure, "fix_comparison")

    # --- Fine-tuning the settings (notebook cell 41) -----------------------
    print(f"{'clear below':>12} | {'N=2':>5} {'N=3':>5} {'N=4':>5}")
    print("-" * 34)
    for gap in [0.5, 1.0, 1.5, 2.0]:
        row = [count_combined(values, WARN_SET, WARN_SET - gap, n) for n in (2, 3, 4)]
        print(f"{WARN_SET - gap:>12} | {row[0]:>5} {row[1]:>5} {row[2]:>5}")


# ===========================================================================
# Entry point
# ===========================================================================
def main(cli_path=None):
    input_path = find_input_file(cli_path)   # resolve first: a bad path errors before any output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, "report.txt")
    original_stdout = sys.stdout
    report_file = open(report_path, "w", encoding="utf-8")
    sys.stdout = Tee(original_stdout, report_file)
    try:
        run_analysis(input_path)
    finally:
        sys.stdout = original_stdout
        report_file.close()
    print(f"Done. Figures and report written to {safe_relpath(OUTPUT_DIR, SCRIPT_DIR)}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Command-line twin of the temperature notebook.")
    parser.add_argument("input", nargs="?", help="optional path to the .csv or .xlsx logger file")
    args = parser.parse_args()
    main(args.input)
