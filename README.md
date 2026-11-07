# PHPwarriors
UAB project for UABtheHack 2026

## Python environment

The project uses a Python **virtual environment** (venv): a private folder holding its own Python and packages, kept apart from the rest of your system.

The venv lives in `.venv/` and is **not committed to git**. It holds thousands of files that only work on the machine that created them. The repository has only `requirements.txt`, the list of packages, and everyone builds their own venv from it.

### First-time setup

From the project folder:

```bash
python3 -m venv .venv                  # create the venv in .venv/
source .venv/bin/activate              # activate it (macOS / Linux)
pip install -r requirements.txt        # install the project's packages
```

On Windows, activate with `.venv\Scripts\activate` instead.

Once the venv is active, your prompt starts with `(.venv)`, and `python` / `pip` use the project's own copies.

### Everyday use

```bash
source .venv/bin/activate    # each time you open a new terminal
jupyter lab                  # or run whatever you need
deactivate                   # when you're done
```

### Adding a package

```bash
pip install <package>
pip freeze > requirements.txt
```

Then commit `requirements.txt` so the rest of the team gets the package too. Teammates pick it up with `pip install -r requirements.txt`.

## What git ignores

`.gitignore` keeps these out of the repository:

- **Virtual environments:** `.venv/`, `venv/`, `env/`, and the `bin/`, `lib/`, `include/`, `share/` and `etc/` folders a venv creates when it's made directly in the project root (`python3 -m venv .`)
- **Secrets:** `.env` files (commit a `.env.example` template instead)
- **Generated files:** `__pycache__/`, build output, test and linter caches, Jupyter checkpoints
- **Personal files:** editor settings (`.vscode/`, `.idea/`) and macOS `.DS_Store`

## Committed the venv by mistake?

If `git status` or a commit shows thousands of files under `.venv/`, `bin/` or `lib/`:

**Not pushed yet:** undo the last commit. Your files stay on disk:

```bash
git reset HEAD~1
```

**Already pushed:** stop tracking the files without deleting them, then commit:

```bash
git rm -r --cached .venv
git commit -m "chore: stop tracking venv"
```

Check that `.gitignore` lists the venv folder first, or git will pick it up again on the next `git add .`.

## DuckDB database

`migra_duckdb.py` loads everything in `paquet/` (CSVs, `cobertura.json` and the scenarios) into one DuckDB file, `dades/paquet.duckdb`. The CSVs stay the source of truth, and the verifier (`python -m horaris`) still reads them directly. The database is rebuilt from scratch on every run and is not committed to git.

```bash
python migra_duckdb.py       # (re)build dades/paquet.duckdb
```

Tables: `sessions`, `aules`, `activitats`, `proposta_partida`, `plans`, `calendari`, `cobertura`, `escenaris`, `escenari_aules_tancades`, `escenari_alumnes`, `escenari_cancellades`, `escenari_sessions_extra`.

Types: dates are `DATE`, `HH:MM` times are `TIME`, counts are `INTEGER`, 0/1 flags (`ordinaria`, `sense_espai`) are `BOOLEAN`, and `|`-separated fields (`docents`, `plans`, `titulacions_curs`, `aules_addicionals_partida`, `aules_partida`) are lists (`VARCHAR[]`). Codes such as `codi` and `pla` stay as text.

Querying from Python:

```python
import duckdb
con = duckdb.connect("dades/paquet.duckdb", read_only=True)
con.execute("""
    SELECT tipus, count(*) AS sense_aula
    FROM sessions
    WHERE aula_partida IS NULL AND NOT sense_espai
    GROUP BY tipus
""").df()
```

Note: DuckDB 2.0 removed `fetchone()` / `fetchall()` on `con.sql(...)` relations. Use `con.execute(...).fetchone()` or `.df()` instead.
