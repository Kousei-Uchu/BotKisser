# Contributing to BotKisser

Thank you for helping improve the bot. This document covers the workflow, code standards, and review process.

---

## Getting started

1. **Fork** the repository and clone your fork locally.
2. Create a **feature branch** off `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `config.example.json` → `config.json` and fill in a test server's IDs.
5. Add your bot token to `.env`:
   ```
   DISCORD_TOKEN=your_test_bot_token
   ```

---

## Code style

- **Python 3.11+** — use modern syntax (`match`, `X | Y` unions, `datetime.UTC`, etc.)
- **Formatting** — 4-space indentation, 100-character line limit, consistent alignment of related assignments.
- **Imports** — stdlib first, then third-party, then local; one blank line between groups.
- **Type hints** — add them to all new functions.
- **Docstrings** — one-line docstrings for public methods that aren't self-explanatory.
- **No magic numbers** — constants at the top of the file or pulled from `config.json`.

---

## Adding a new cog

1. Create `cogs/my_feature.py`.
2. Inherit from `commands.Cog`.
3. Add the matching DB handler in `utils/db_handlers/my_feature_db.py` if you need persistence. Use the `SQLHandler` wrapper — do **not** open raw `sqlite3` connections in cogs.
4. Register the cog in `main.py`'s `load_cogs()` (it loads all `.py` files in `cogs/` automatically, so just dropping the file is enough).
5. Add the relevant section to `config.json` and document it in `wiki/config-reference.md`.

---

## Database rules

- All DB access goes through `utils/sql_handler.py`. Never call `sqlite3` directly in a cog.
- Each `execute()` call already commits — do not add extra commits or call `conn.commit()`.
- Do not call `conn.commit()`, `conn.lastrowid()`, or `cursor.execute()` — these methods do not exist on `SQLHandler`.
- Use `INSERT OR IGNORE` / `INSERT OR REPLACE` for upserts.
- Add `CREATE TABLE IF NOT EXISTS` in the DB handler's `_init_tables()` method.

---

## Pull request checklist

Before opening a PR:

- [ ] All new commands are slash commands (`@app_commands.command`).
- [ ] Permission checks use `check_command_permissions()` or the relevant cog's pattern.
- [ ] Any duration arguments are validated **before** the action is executed (ban/mute/lock pattern).
- [ ] The feature is behind a config key if it should be toggle-able.
- [ ] No hardcoded guild IDs or channel IDs (use `config.json`).
- [ ] No hardcoded bot tokens or secrets.
- [ ] New DB tables follow the existing schema conventions.
- [ ] The PR description explains *what* changed and *why*.

---

## Reporting bugs

Open a GitHub Issue with:

- What you expected to happen.
- What actually happened (include the full traceback if there is one).
- The command or event that triggered it.
- The relevant section of `config.json` (redact any real IDs if needed).

---

## Branch naming

| Type | Pattern | Example |
|---|---|---|
| New feature | `feat/short-description` | `feat/role-persist` |
| Bug fix | `fix/short-description` | `fix/ban-duration-crash` |
| Refactor | `refactor/short-description` | `refactor/leveling-db` |
| Docs | `docs/short-description` | `docs/wiki-commands` |