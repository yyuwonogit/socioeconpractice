# socioeconpractice

This README sets the layout and rules of the repository, and CLAUDE.md makes every Claude session follow this README.

## Layout

```
socioeconpractice/
├── README.md                    layout and rules
├── CLAUDE.md                    tells every Claude session to follow README.md
├── requirements.txt             pinned packages for .venv
├── .gitignore                   excludes .venv, caches and Office lock files
├── .venv/                       built on each machine, never committed
├── .inbox/                      drop folder, emptied by Claude
├── .outbox/
│   └── YYYYMMDD_<delivery>/     one folder per delivery
├── reference/                   papers, reports, method notes
├── raw/
│   └── <topic>/                 one folder per topic
│       ├── YYYYMMDD_<source>.xlsx
│       └── YYYYMMDD_<download>.py
├── data/
│   └── YYYYMMDD_<dataset>/
│       ├── YYYYMMDD_<build>.py
│       └── YYYYMMDD_<dataset>.csv
└── analysis/
    └── YYYYMMDD_<analysis>/
        ├── YYYYMMDD_<analysis>.py
        ├── YYYYMMDD_<figure>.png
        └── YYYYMMDD_<table>.csv
```

| Folder | Holds | Scripts |
|---|---|---|
| `reference/` | Papers, reports and method notes | None |
| `raw/<topic>/` | Source files as received, never edited | A download script sits beside the files it fetched |
| `data/YYYYMMDD_<dataset>/` | Cleaned or derived datasets | The build script sits beside its output and reads `raw/` or other `data/` folders |
| `analysis/YYYYMMDD_<analysis>/` | Figures and tables | The script sits beside its outputs and reads `data/` only |

## Naming

- Every work file and work folder starts with `YYYYMMDD` and an underscore, then lowercase words joined by hyphens, as in `20261102_gdp-per-capita.csv`.
- The date is the Jakarta date (UTC+7) on which the item was created or filed.
- The date in a name stays fixed after later edits, and git records those edits.
- Sorting folders like `raw/<topic>/` and control files like `README.md` have no date prefix, and topic folder names use lowercase words joined by hyphens.

## Scripts

- Every `.py` file sits in the folder of the data it writes, and every script finds other files by paths relative to its own location.
- An `import` statement cannot load a `.py` file whose name starts with a digit, so each script defines its own parameters and functions at the top.
- Files in `raw/` are never edited, and a cleaned version of a raw file goes to a new folder in `data/`.
- Every script starts from the header below, and every step in a script carries a comment that states its purpose.

```python
from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Parameters

# Functions

# Steps
```

## .inbox and .outbox

- You drop files into `.inbox` from a clone on your PC or through the Upload files page on github.com.
- Claude moves each file to `reference/` or a `raw/<topic>/` folder and adds the date prefix to its name.
- Claude creates each topic folder in `raw/` when the first file on that topic arrives.
- The commit message records each original filename, and git keeps that original filename in the file's history.
- Claude checks `.inbox` at the start of each session and asks you about any file whose topic is unclear.
- Each delivery goes in a new `.outbox/YYYYMMDD_<name>/` folder, and Claude pushes that folder to GitHub.

## Environment

`.venv` sits at the repository root, and each machine builds its own `.venv` from `requirements.txt`. The pinned numpy and scipy versions require Python 3.12 or later.

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Linux or macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Scripts run with the `.venv` Python, as in `.venv\Scripts\python.exe data\YYYYMMDD_<dataset>\YYYYMMDD_<build>.py` on Windows.
