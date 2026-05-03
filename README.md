# BotKisser

A full-featured Discord moderation and community bot built with [discord.py](https://github.com/Rapptz/discord.py), backed by SQLite. Designed for The Den server.

---

## Features

| Module | Commands |
|---|---|
| **Moderation** | ban, unban, softban, kick, mute, unmute, warn, temprole, lock, unlock, lockdown, case, modlogs, reason, duration, modstats, notes, deafen, crisis |
| **Leveling** | level, leaderboard, setlevel, addxp, removexp, grantlevel, revokelevel |
| **Tickets** | /ticket, panel button, force-close |
| **Fireboard** | Automatic 🔥-reaction reposts, leaderboard |
| **Sticky messages** | Stick/unstick a pinned message that follows the channel |
| **Analytics** | Message counts, active-hour heatmaps, status tracking |
| **Introductions** | Structured intro DM flow, age-role assignment, Excel export |
| **Fun** | AFK, dice, coinflip, RPS, dad jokes, cat/dog images |
| **Purge** | Bulk-delete after, between, or by count |
| **Logging** | Message edits/deletes, joins/leaves, bans, role/channel changes, voice |

---

## Requirements

- Python 3.11+
- discord.py 2.x
- openpyxl (introdms Excel export)
- python-dotenv

Install everything:

```bash
pip install -r requirements.txt
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/the-den-bot.git
cd the-den-bot
```

### 2. Create your `.env` file

```
DISCORD_TOKEN=your_bot_token_here
```

**Never commit your token.** `.env` is already in `.gitignore`.

### 3. Configure the bot

Copy `config.example.json` to `config.json` and fill in your server's channel IDs, role IDs, and feature toggles. See the [Config Reference](wiki/config-reference.md) wiki page for every field.

### 4. Run the migration (first time only)

If you are upgrading from the old JSON-based version:

```bash
python migrate_json_to_sql.py
```

This copies all existing data from the JSON files into the SQLite databases and is safe to run more than once.

### 5. Start the bot

```bash
python main.py
```

---

## Project Structure

```
bot/
├── cogs/               # Feature cogs (one per module)
│   ├── moderation.py
│   ├── leveling.py
│   ├── ticket.py
│   ├── fireboard.py
│   ├── sticky.py
│   ├── analytics.py
│   ├── listeners.py
│   ├── logging.py (Logging.py)
│   ├── fun.py
│   ├── purge.py
│   └── introdms.py
├── utils/
│   ├── sql_handler.py          # Thread-safe SQLite wrapper
│   ├── config_manager.py       # JSON config loader
│   └── db_handlers/            # Per-feature DB interfaces
│       ├── moderation_db.py
│       ├── leveling_db.py
│       ├── analytics_db.py
│       ├── sticky_db.py
│       ├── ticket_db.py
│       └── fireboard_db.py
├── data/                       # SQLite databases (git-ignored)
├── config.json                 # Your server configuration
├── main.py                     # Bot entry point
└── migrate_json_to_sql.py      # One-shot data migration helper
```

---

## Configuration

All behaviour is controlled by `config.json`. Key sections:

- **`moderation`** — mute role, log channels, DM templates
- **`leveling`** — XP range, level-up message, channel, role rewards
- **`ticket`** — category, staff roles, panel channel
- **`fireboard`** — reaction emoji, threshold, output channel
- **`logging`** — per-event log channel IDs
- **`intro`** — intro channel, age roles, Excel export path
- **`analytics`** — enable/disable tracking

Full field reference: [wiki/config-reference.md](wiki/config-reference.md)

---

## Commands

All commands are slash commands. A full reference is in [wiki/commands.md](wiki/commands.md).

---

## Data storage

All persistent data lives in `data/`. The directory is git-ignored. Each feature uses its own `.db` file:

| File | Contents |
|---|---|
| `data/bot.db` | Mod logs, warnings, notes, timed actions, locked channels, persisted roles |
| `data/leveling.db` | XP and level per user per guild |
| `data/analytics.db` | Message counts, status changes, channel activity, active hours, games |
| `data/sticky.db` | Sticky message contents and channel mapping |
| `data/tickets.db` | Open and closed tickets |
| `data/fireboard.db` | Fireboard repost tracking |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

This project is private and not licensed for public redistribution.