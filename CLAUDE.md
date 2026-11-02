# CLAUDE.md

@README.md

README.md holds the layout and rules of this repository, and every file you create, move or rename here follows README.md.

## Today's date for names

Names use the Jakarta date (UTC+7), and this command prints the Jakarta date on Windows, Linux and macOS.

```
python -c "from datetime import datetime, timedelta, timezone; print(datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d'))"
```

## .inbox

At the start of every session, run `git pull` and list `.inbox`. File every item in `.inbox` except `.gitkeep` with these steps.

1. Papers, reports and method notes go to `reference/`, and source data goes to `raw/<topic>/`.
2. Use an existing topic folder when one fits, and create a new topic folder with a lowercase hyphenated name when none fits.
3. Rename the file to `YYYYMMDD_<description>.<ext>` with today's Jakarta date and the original extension.
4. The description uses lowercase words joined by hyphens and keeps the meaning of the original filename.
5. Move the file with `git mv` when git tracks it, and with `mv` followed by `git add` when git does not track it.
6. Ask the user before moving any file whose destination or topic is unclear.
7. Commit with a message that lists each original filename and its new path, and push the commit.

Leave `.inbox/.gitkeep` in place.

## .outbox

When the user asks for a delivery, create `.outbox/YYYYMMDD_<name>/` with today's Jakarta date. The deliverable inside the folder carries a `YYYYMMDD_<name>` filename. Zip a folder with `python -m zipfile -c <zip-file> <folder>`, which adds the folder's contents recursively. Commit and push the delivery, and give the user its path.

## Scripts and environment

- Put each `.py` file in the folder of the data it writes, and start the file from the header in README.md.
- Never edit files in `raw/`.
- Scripts in `analysis/` read from `data/` only.
- Every build script in `data/` follows Cleaning and checking in README.md: open each raw file before declaring its `READ_CONTEXT`, and write the CSV and metadata JSON only after all checks pass.
- After changing a build script or a raw file it reads, rerun every build script in `data/`, review `git diff data/`, and tell the user about any new entry in a metadata `checks.flags`.
- Run scripts with the `.venv` Python, and build `.venv` from `requirements.txt` when `.venv` is missing.
- Install a new package into `.venv`, and add the package to `requirements.txt` with its version pinned.
