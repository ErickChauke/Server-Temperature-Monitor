# Server Temperature Monitor

A Nagios check for the server room at a standby control centre. Several servers
log the temperature of their hard drives (HDDs) every half hour into a single
logger file. The room occasionally runs warm, and this check decides when that
warmth is worth alerting on.

## The check

`check_temp.sh` reads the latest readings and forms one "room number": it drops
the single hottest server's reading and averages the rest. The hottest is dropped
because one busy server can run hot on its own and would unfairly lift the average.
The room number is then compared against the limits and reported with a standard
Nagios exit code (0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN).

## The nuisance-alarm problem, and the fix

The room number tends to sit right on the warning line of 26 C, so it crosses back
and forth and sends a fresh alert every time, even when nothing has really changed.
Three years of readings showed this happening about 770 times, most of them brief.

The check calms this in two ways, both chosen from the data:

- **Hysteresis:** it warns above 26 C but only sounds the all-clear once the number
  drops below 25 C, so a small wobble no longer switches the alert on and off.
- **Persistence:** it requires two readings in a row above a limit before alerting,
  so a single odd reading is ignored.

Together these remove about 86 percent of the alert emails while still raising every
genuinely long, hot spell. The full analysis, with charts, is in the notebook.

## Configuration

All settings live in one block at the top of `check_temp.sh`:

| Setting | Meaning | Default |
|---|---|---|
| `WARN_SET` | warn above this many degrees | 26 |
| `CRIT_SET` | critical above this many degrees | 28 |
| `CLEAR_GAP` | how far below a limit the number must fall to clear | 1 |
| `PERSIST_N` | readings in a row above a limit before alerting | 2 |
| `DROP_HIGHEST` | hottest sensors set aside before averaging | 1 |
| `LOOKBACK` | rows replayed each run (48 = one day) | 48 |
| `DATA_URL` | where to download the logger file | (set by operator) |

## Usage

```bash
./check_temp.sh                    # download from DATA_URL, then check
./check_temp.sh path/to/file.csv   # check a local file, no download (useful for tests)
```

The check depends only on `bash` and `awk`, both standard on the monitoring host.

## Analysis notebook

`notebook.ipynb` builds the full understanding and justifies every setting above.
`notebook.html` is a rendered copy that opens in any browser and adapts to light or
dark viewing. The notebook reads a temperature logger file from the local, ignored
`data/` directory and writes its figures to the ignored `output/` directory.

## Command-line analysis

`temperature_analysis.py` is a standalone version of the notebook for a machine
without Jupyter. It installs anything it needs, finds the logger file
automatically (a single `.csv` or `.xlsx` beside it or in `data/`, or a path given
as an argument), and writes the same figures plus a `report.txt` into `output/`.

```bash
python temperature_analysis.py                    # auto-detect the logger file
python temperature_analysis.py path/to/file.csv   # or use a specific file
```

## Repository layout

```
check_temp.sh            the Nagios check
temperature_analysis.py  command-line version of the notebook (no Jupyter needed)
notebook.ipynb           the analysis notebook
notebook.html            rendered analysis for sharing
README.md                this file
data/                    local logger data (git-ignored)
output/                  generated figures (git-ignored)
```
