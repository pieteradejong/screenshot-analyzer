# LLM-ENHANCED PROJECT FRAMEWORK

A framework for developing software projects with LLM assistance (Cursor, Claude, Copilot, etc.). This document establishes the structure, conventions, and contracts that enable effective human-LLM collaboration.

---

## Core Principles

### 1. Explicit Context Over Implicit Knowledge

LLMs don't retain context between sessions. Everything the LLM needs to know must be written down:

- **Architecture decisions** - Why things are structured the way they are
- **Conventions** - How code should be written
- **Current state** - What's been built, what's in progress

### 2. Deployable Iterations

Never let the project exist in a broken state. Every change should:

- Pass all tests
- Be deployable (even if incomplete)
- Build on a working foundation

### 3. Verification Over Trust

LLMs make mistakes. Every output must be verifiable:

- Automated tests for code
- Scripts that validate setup
- Clear acceptance criteria

### 4. Three Scripts Rule Everything

Every project has exactly three entry points:

| Script | Purpose | Contract |
|--------|---------|----------|
| `init.sh` | Setup from zero | Exit 0 = ready to develop |
| `test.sh` | Verify everything | Exit 0 = safe to deploy |
| `run.sh` | Start development | Runs all services |

These scripts are the source of truth. If it's not in a script, it doesn't exist.

---

## Required Documents

Every LLM-enhanced project must have these documents at the root level. The LLM should read these before making any changes.

### 1. ROADMAP.md

**Purpose:** Define what we're building and in what order.

**Must include:**
- Project overview (one paragraph)
- Phased build plan with clear boundaries
- Each phase must have:
  - Goal (one sentence)
  - Deliverables (checklist)
  - Acceptance criteria (how to verify)
  - Definition of done

**Template:**
```markdown
# ROADMAP

## Project Overview
[One paragraph describing what this project is]

## Phases

### Phase 0: [Foundation]
**Goal:** [One sentence]

#### Deliverables
- [ ] Item 1
- [ ] Item 2

#### Acceptance Criteria
\`\`\`bash
./init.sh   # Completes with exit 0
./test.sh   # Completes with exit 0
\`\`\`

#### Definition of Done
- [ ] Verification 1
- [ ] Verification 2

### Phase 1: [Next Phase]
...
```

---

### 2. ARCHITECTURE.md

**Purpose:** Explain how the system is structured and why.

**Must include:**
- High-level structure (directory layout)
- Component responsibilities
- Data flow
- Key technical decisions with rationale
- Patterns to follow
- Anti-patterns to avoid

**Template:**
```markdown
# ARCHITECTURE

## Overview
[How the pieces fit together]

## Structure
\`\`\`
├── src/
│   ├── [component]/    # [responsibility]
│   └── [component]/    # [responsibility]
└── ...
\`\`\`

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| [Area] | [Choice] | [Why] |

## Patterns
[Patterns the LLM should follow]

## Anti-Patterns
[Things the LLM should NOT do]
```

---

### 3. CONVENTIONS.md

**Purpose:** Define how code should be written.

**Must include:**
- Language-specific style rules
- Naming conventions (files, functions, variables)
- Import ordering
- Error handling patterns
- Testing patterns
- Git conventions

**Template:**
```markdown
# CONVENTIONS

## General Principles
1. [Principle]
2. [Principle]

## [Language] Conventions

### Naming
- Files: [pattern]
- Functions: [pattern]
- Variables: [pattern]

### Imports
[Order and grouping]

### Error Handling
[Pattern to follow]

## Testing
[How tests should be structured]

## Git
[Commit message format, branch naming]
```

---

### 4. LOGGING.md (Recommended)

**Purpose:** Define logging and health check standards.

**Must include:**
- Log levels and when to use each
- Structured log format
- What to log vs what NOT to log (security)
- Correlation ID strategy
- Health check endpoints and response formats

**Why it matters:**
- Debugging production issues requires good logs
- Health checks enable reliable deployments
- Consistent logging makes issues easier to find

See the standalone LOGGING.md template for full details.

---

### 5. PHASE_N_TASKS.md

**Purpose:** Detailed task breakdown for current phase.

**Must include:**
- Task list with checkboxes
- Code snippets and file contents where helpful
- Verification steps for each task
- Final verification checklist

**Template:**
```markdown
# Phase [N]: [Name] - Task Breakdown

**Goal:** [From ROADMAP]

**Definition of Done:** [From ROADMAP]

---

## Task [N].1: [Name]

### Description
[What needs to be done]

### Files to Create/Modify
- [ ] `path/to/file.ext`

### Implementation
\`\`\`[language]
[Code snippet if helpful]
\`\`\`

### Verification
\`\`\`bash
[How to verify this task is complete]
\`\`\`

---

## Task [N].2: [Name]
...

---

## Final Verification Checklist

Before marking Phase [N] complete:

- [ ] Verification 1
- [ ] Verification 2
- [ ] `./test.sh` passes
```

---

## Required Scripts

### init.sh

**Purpose:** Take a fresh clone to a fully working development environment.

**Contract:**
- Exit 0 = ready to develop
- Exit 1 = clear error message explaining what's wrong

**Must handle:**
1. Check all prerequisites (languages, tools, versions)
2. Install dependencies
3. Setup environment (copy example configs, prompt for values)
4. Initialize services (databases, etc.)
5. Verify setup is complete

**Template:**
```bash
#!/bin/bash
set -e

echo "🚀 Initializing project..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check prerequisites
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}❌ $1 is not installed${NC}"
        echo "   Install: $2"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} $1 found"
}

echo "📋 Checking prerequisites..."
check_command "node" "https://nodejs.org"
# Add more checks as needed

# Install dependencies
echo "📦 Installing dependencies..."
# [package manager install command]

# Setup environment
if [ ! -f .env.local ]; then
    echo "🔧 Creating .env.local..."
    cp .env.example .env.local
    echo -e "${YELLOW}⚠️  Update .env.local with your values${NC}"
fi

# Initialize services
echo "🗄️ Initializing services..."
# [service initialization]

# Verify
echo "✅ Verifying setup..."
# [verification commands]

echo ""
echo -e "${GREEN}✅ Initialization complete!${NC}"
```

---

### test.sh

**Purpose:** Verify everything works and is safe to deploy.

**Contract:**
- Exit 0 = safe to deploy
- Exit 1 = do not deploy, here's what failed

**Must handle:**
1. Linting
2. Type checking (if applicable)
3. Unit tests
4. Integration tests
5. Security audit
6. Any other verification

**Flags to support:**
- `--ci` - Stricter mode for CI (no prompts, fail on warnings)
- `--quick` - Skip slow tests (for rapid development feedback)

**Template:**
```bash
#!/bin/bash
set -e

echo "🧪 Running tests..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Parse flags
CI_MODE=false
QUICK_MODE=false

for arg in "$@"; do
    case $arg in
        --ci) CI_MODE=true ;;
        --quick) QUICK_MODE=true ;;
    esac
done

FAILED=0

run_check() {
    local name=$1
    local command=$2
    
    echo ""
    echo "Running: $name..."
    if eval $command; then
        echo -e "${GREEN}✓${NC} $name passed"
    else
        echo -e "${RED}❌ $name failed${NC}"
        FAILED=1
    fi
}

run_check "Lint" "[lint command]"
run_check "Type Check" "[typecheck command]"

if [ "$QUICK_MODE" = false ]; then
    run_check "Unit Tests" "[test command]"
    run_check "Integration Tests" "[integration test command]"
fi

run_check "Security Audit" "[audit command]"

# Summary
echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
fi
```

---

### run.sh

**Purpose:** Start the complete development environment.

**Contract:**
- Starts all services needed for development
- Provides clear output about what's running and where

**Flags to support:**
- Component-specific flags (e.g., `--web`, `--api`, `--mobile`)
- `--all` - Everything (default)

**Template:**
```bash
#!/bin/bash

echo "🏃 Starting development environment..."

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse arguments
RUN_ALL=true
# Add component flags as needed

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $(jobs -p) 2>/dev/null
}
trap cleanup EXIT

# Start services
echo ""
echo -e "${GREEN}Starting services...${NC}"
echo -e "${YELLOW}Service 1:${NC} http://localhost:XXXX"
echo -e "${YELLOW}Service 2:${NC} http://localhost:YYYY"
echo ""

# Run services (in parallel if multiple)
([command 1]) &
([command 2]) &

wait
```

---

## LLM Interaction Patterns

### Starting a Session

Always begin by having the LLM read the core documents:

```
Read ROADMAP.md, ARCHITECTURE.md, and CONVENTIONS.md to understand
this project. Then read PHASE_N_TASKS.md for current work.
```

### Giving Instructions

Be specific about scope:

```
# Good
"Implement Task 2.3 from PHASE_2_TASKS.md. Follow the patterns in 
ARCHITECTURE.md for database access."

# Bad
"Add user authentication"
```

### After Each Change

Verify before moving on:

```
"Run ./test.sh and fix any failures before continuing"
```

### Ending a Session

Update documentation:

```
"Update PHASE_N_TASKS.md to reflect completed work. Check off 
finished tasks and note any blockers."
```

---

## Project Lifecycle

### Starting a New Project

1. Create the four required documents (ROADMAP, ARCHITECTURE, CONVENTIONS, PHASE_0_TASKS)
2. Create the three scripts (init.sh, test.sh, run.sh) - even if minimal
3. Verify the foundation: `./init.sh && ./test.sh && ./run.sh`

### During Development

1. Work through PHASE_N_TASKS.md task by task
2. Run `./test.sh` after each significant change
3. Never merge code that breaks `./test.sh`
4. Update task checkboxes as work completes

### Completing a Phase

1. Run full verification checklist in PHASE_N_TASKS.md
2. Ensure `./test.sh` passes completely
3. Create PHASE_N+1_TASKS.md for next phase
4. Update ROADMAP.md if scope has changed

### Onboarding New Contributors (Human or LLM)

1. Clone repository
2. Run `./init.sh`
3. Read ROADMAP.md, ARCHITECTURE.md, CONVENTIONS.md
4. Run `./test.sh` to verify setup
5. Run `./run.sh` to start development
6. Read current PHASE_N_TASKS.md for active work

---

## Quality Gates

### Before Committing

- [ ] `./test.sh --quick` passes
- [ ] New code follows CONVENTIONS.md
- [ ] No `TODO` comments without issue references

### Before Merging

- [ ] `./test.sh` passes (full suite)
- [ ] Documentation updated if needed
- [ ] Another human has reviewed (not just LLM)

### Before Deploying

- [ ] `./test.sh --ci` passes
- [ ] All acceptance criteria for current phase met
- [ ] No known regressions

---

## Anti-Patterns

### Document Drift

**Problem:** Documents become outdated.
**Solution:** Update documents as part of the task, not after.

### Implicit Knowledge

**Problem:** "The LLM should know that..."
**Solution:** If it's not written down, it doesn't exist. Add it to a document.

### Big Bang Changes

**Problem:** Large changes that break many things at once.
**Solution:** Small, incremental changes that pass tests at each step.

### Trusting Without Verifying

**Problem:** Assuming LLM output is correct.
**Solution:** Run tests. Check the output. Verify behavior.

### Skipping Documentation

**Problem:** "I'll document it later."
**Solution:** No code is complete until its documentation is complete.

---

## Checklist: Is Your Project LLM-Ready?

### Required
- [ ] ROADMAP.md exists and defines all phases
- [ ] ARCHITECTURE.md explains system structure
- [ ] CONVENTIONS.md defines code standards
- [ ] PHASE_N_TASKS.md exists for current phase
- [ ] `init.sh` works from fresh clone
- [ ] `test.sh` verifies everything
- [ ] `run.sh` starts development environment
- [ ] All three scripts exit 0 on a fresh clone
- [ ] A new contributor (human or LLM) can start in <10 minutes

### Recommended for Production
- [ ] LOGGING.md defines logging standards
- [ ] Health check endpoints exist
- [ ] Structured logging implemented
- [ ] Correlation IDs for request tracing

---

## Quick Reference

```
Document Purpose:
  ROADMAP.md        → What are we building?
  ARCHITECTURE.md   → How is it structured?
  CONVENTIONS.md    → How do we write code?
  LOGGING.md        → How do we log and monitor?
  PHASE_N_TASKS.md  → What do we do next?

Script Purpose:
  init.sh  → Setup    → Exit 0 = ready
  test.sh  → Verify   → Exit 0 = safe to deploy  
  run.sh   → Develop  → Starts everything

Health Endpoints:
  /health/live   → Is process alive?
  /health/ready  → Can handle requests?

Session Flow:
  1. LLM reads all docs
  2. Work through tasks
  3. test.sh after each change
  4. Update task checkboxes
  5. Repeat
```
