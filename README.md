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
