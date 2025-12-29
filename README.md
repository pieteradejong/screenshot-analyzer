# General Project Template

A stack-agnostic project template with standardized scripts for initialization, development, and testing.

## Quick Start

```bash
# 1. Initialize the project (install dependencies)
./scripts/init.sh

# 2. Run tests to verify everything works
./scripts/test.sh

# 3. Start the development server
./scripts/run.sh
```

## Scripts

All scripts are located in the `scripts/` directory and auto-detect your project's tech stack.

### `./scripts/init.sh`

Sets up the development environment from a fresh clone.

```bash
./scripts/init.sh              # Full initialization
./scripts/init.sh --no-clean   # Skip cleanup step (faster)
./scripts/init.sh --help       # Show help
```

**What it does:**
- Detects project stacks (Python, Node.js, Rust, Go, Docker)
- Cleans existing build artifacts
- Creates virtual environments
- Installs all dependencies

### `./scripts/run.sh`

Starts the development environment.

```bash
./scripts/run.sh               # Start all services
./scripts/run.sh backend       # Start backend only
./scripts/run.sh frontend      # Start frontend only
./scripts/run.sh docker        # Start with Docker Compose
./scripts/run.sh --help        # Show help
```

**Environment variables:**
- `BACKEND_PORT` - Backend server port (default: 8000)
- `FRONTEND_PORT` - Frontend dev server port (default: 5173)

### `./scripts/test.sh`

Runs tests, linting, and type checking.

```bash
./scripts/test.sh              # Run all checks
./scripts/test.sh --quick      # Fast mode (skip type-check, format)
./scripts/test.sh backend      # Backend tests only
./scripts/test.sh frontend     # Frontend tests only
./scripts/test.sh lint         # Linting only
./scripts/test.sh format       # Format checking only
./scripts/test.sh type-check   # Type checking only
./scripts/test.sh --help       # Show help
```

**Exit codes:**
- `0` - All checks passed (safe to deploy)
- `1` - One or more checks failed

## Supported Stacks

The scripts automatically detect and support:

| Stack | Detection | Init | Run | Test |
|-------|-----------|------|-----|------|
| Python | `requirements.txt`, `pyproject.toml` | venv + pip | uvicorn/flask/django | pytest |
| Node.js | `package.json` | npm/yarn/pnpm | dev script | vitest/jest |
| Rust | `Cargo.toml` | cargo build | cargo run | cargo test |
| Go | `go.mod` | go mod download | go run | go test |
| Docker | `Dockerfile`, `docker-compose.yml` | docker compose build | docker compose up | - |

## Configuration

Create `scripts/project.conf` to customize behavior:

```bash
# Project name (used in logs)
PROJECT_NAME="My Project"

# Override auto-detection
ENABLE_PYTHON=true      # auto | true | false
ENABLE_NODE=true

# Directory locations
PYTHON_DIR="backend"
NODE_DIR="frontend"

# Package manager
NODE_PACKAGE_MANAGER="pnpm"   # npm | yarn | pnpm

# Ports
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Custom commands
RUN_PYTHON_CMD="uvicorn main:app --reload"
TEST_PYTHON_CMD="pytest -v"
```

See `scripts/project.conf` for all available options.

## Project Structure

```
your-project/
├── scripts/
│   ├── _common.sh      # Shared utilities
│   ├── project.conf    # Configuration (optional)
│   ├── init.sh         # Setup script
│   ├── run.sh          # Dev server script
│   └── test.sh         # Test suite script
├── backend/            # Python/Rust/Go code (optional)
├── frontend/           # Node.js code (optional)
└── README.md
```

## Workflow

### Before Starting Work
1. Read project documentation (ROADMAP.md, ARCHITECTURE.md, etc.)
2. Run `./scripts/test.sh` to confirm project is healthy

### During Development
1. Make small, incremental changes
2. After each change: `./scripts/test.sh --quick`
3. Fix failures before continuing

### After Completing Work
1. Run full `./scripts/test.sh`
2. Ensure all checks pass before committing

## License

MIT
