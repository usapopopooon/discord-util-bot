# Ephemeral VC

[![CI](https://github.com/usapopopooon/ephemeral-vc/actions/workflows/ci.yml/badge.svg)](https://github.com/usapopopooon/ephemeral-vc/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/usapopopooon/ephemeral-vc/graph/badge.svg)](https://codecov.io/gh/usapopopooon/ephemeral-vc)

Discord dynamic voice channel management bot. When users join a lobby voice channel, a personal voice channel is automatically created. The channel is deleted when everyone leaves.

## Features

- **Automatic VC Creation**: Join a lobby channel to get your own voice channel
- **Button UI Controls**: Manage your channel with buttons (no commands needed)
  - Rename channel
  - Set user limit
  - Lock/Unlock
  - Transfer ownership
  - Block/Allow users
- **Auto Cleanup**: Empty channels are automatically deleted
- **Multi-Lobby Support**: Set up multiple lobby channels per server

## Requirements

- Python 3.12
- Discord Bot Token

## Installation

### Local Development (with Make)

```bash
git clone https://github.com/yourusername/ephemeral-vc.git
cd ephemeral-vc
cp .env.example .env  # Edit .env with your Discord token
make run
```

### Local Development (Manual)

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/ephemeral-vc.git
   cd ephemeral-vc
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

3. Copy `.env.example` to `.env` and add your Discord token:
   ```bash
   cp .env.example .env
   ```

4. Run the bot:
   ```bash
   python -m src.main
   ```

### Docker

1. Copy `.env.example` to `.env` and add your Discord token

2. Run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

## Usage

### Admin Commands

| Command | Description |
|---------|-------------|
| `/lobby add` | Register current voice channel as a lobby |
| `/lobby remove` | Unregister the lobby |
| `/lobby list` | List all registered lobbies |

### User Controls

When you join a lobby and get your own channel, a control panel appears with buttons:

- **Rename**: Change the channel name
- **User Limit**: Set maximum users (0 = unlimited)
- **Lock/Unlock**: Make the channel private
- **Transfer**: Give ownership to another user
- **Block**: Kick and ban a user from your channel
- **Allow**: Allow a specific user when locked

## Development

### Make Commands

| Command | Description |
|---------|-------------|
| `make setup` | Create venv and install dependencies |
| `make run` | Run the bot |
| `make test` | Run tests |
| `make lint` | Run Ruff linter |
| `make typecheck` | Run mypy type checker |
| `make clean` | Remove venv and cache files |

### Running Tests with Coverage

```bash
.venv/bin/pytest --cov --cov-report=html
```

## License

MIT
