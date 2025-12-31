#!/bin/bash
# =============================================================================
# Project Initialization Script
# =============================================================================
# Sets up the development environment from a fresh clone.
# Detects project stacks automatically and installs dependencies.
#
# Usage:
#   ./scripts/init.sh [OPTIONS]
#
# Options:
#   --no-clean    Skip cleanup of existing artifacts
#   --help        Show this help message
# =============================================================================

set -e  # Exit on error

# Source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

SKIP_CLEAN=true   # Default: don't clean (idempotent)
FORCE_REINSTALL=false

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Initialize the project development environment."
    echo ""
    echo "Options:"
    echo "  --force       Force reinstall (clean and rebuild everything)"
    echo "  --clean       Clean existing artifacts before installing"
    echo "  --help        Show this help message"
    echo ""
    echo "By default, this script is idempotent:"
    echo "  - Skips venv creation if it already exists"
    echo "  - Skips dependency install if packages are present"
    echo ""
    echo "Use --force to start fresh."
    exit 0
}

for arg in "$@"; do
    case $arg in
        --force|-f)
            FORCE_REINSTALL=true
            SKIP_CLEAN=false
            shift
            ;;
        --clean)
            SKIP_CLEAN=false
            shift
            ;;
        --no-clean)
            SKIP_CLEAN=true
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            log_error "Unknown option: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# =============================================================================
# MAIN
# =============================================================================

log_header "${PROJECT_NAME:-Project} - Initialization"
echo ""

print_detected_stacks

# =============================================================================
# CLEANUP
# =============================================================================

if [ "$SKIP_CLEAN" = false ]; then
    log_step "Cleaning existing artifacts..."
    
    # Python cleanup
    if is_python_enabled; then
        local_venv=$(get_venv_path)
        if [ -d "$local_venv" ]; then
            echo "  Removing $local_venv..."
            rm -rf "$local_venv"
        fi
        
        # Remove Python caches
        echo "  Removing Python caches..."
        find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find "$PROJECT_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
        find "$PROJECT_ROOT" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
        find "$PROJECT_ROOT" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
        find "$PROJECT_ROOT" -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
        find "$PROJECT_ROOT" -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    fi
    
    # Node.js cleanup
    if is_node_enabled; then
        local_node_dir=$(get_node_dir)
        
        if [ -d "$local_node_dir/node_modules" ]; then
            echo "  Removing $local_node_dir/node_modules..."
            rm -rf "$local_node_dir/node_modules"
        fi
        
        if [ -d "$local_node_dir/dist" ]; then
            echo "  Removing $local_node_dir/dist..."
            rm -rf "$local_node_dir/dist"
        fi
        
        if [ -d "$local_node_dir/.vite" ]; then
            echo "  Removing $local_node_dir/.vite..."
            rm -rf "$local_node_dir/.vite"
        fi
        
        if [ -d "$local_node_dir/.next" ]; then
            echo "  Removing $local_node_dir/.next..."
            rm -rf "$local_node_dir/.next"
        fi
    fi
    
    # Rust cleanup
    if is_rust_enabled && check_command cargo; then
        echo "  Running cargo clean..."
        cargo clean 2>/dev/null || true
    fi
    
    # Go cleanup
    if is_go_enabled && check_command go; then
        echo "  Cleaning Go cache..."
        go clean -cache 2>/dev/null || true
    fi
    
    log_success "Cleanup complete"
    echo ""
fi

# =============================================================================
# PYTHON INITIALIZATION
# =============================================================================

if is_python_enabled; then
    log_header "Python Setup"
    
    require_command python3 "Install Python 3 from https://python.org"
    
    local_venv=$(get_venv_path)
    local_python_dir=$(get_python_dir)
    local_requirements=$(get_python_requirements)
    
    # Check if virtual environment already exists
    if [ "$FORCE_REINSTALL" = false ] && [ -d "$local_venv" ] && [ -f "$local_venv/bin/activate" ]; then
        log_info "Virtual environment already exists at $local_venv"
        VENV_EXISTED=true
    else
        # Create virtual environment
        log_step "Creating virtual environment..."
        python3 -m venv "$local_venv"
        log_success "Virtual environment created at $local_venv"
        VENV_EXISTED=false
    fi
    
    # Activate venv
    source "$local_venv/bin/activate"
    
    # Check if dependencies are already installed (skip check if --force)
    DEPS_INSTALLED=false
    if [ "$FORCE_REINSTALL" = false ] && [ "$VENV_EXISTED" = true ]; then
        if [ -n "$local_requirements" ] && [ -f "$local_requirements" ]; then
            # Check if all requirements are satisfied
            if pip freeze 2>/dev/null | grep -q .; then
                # Quick check: see if key packages are installed
                if pip show easyocr &>/dev/null && pip show torch &>/dev/null; then
                    log_info "Python dependencies appear to be installed"
                    DEPS_INSTALLED=true
                fi
            fi
        fi
    fi
    
    if [ "$DEPS_INSTALLED" = false ]; then
        log_step "Installing Python dependencies..."
        
        # Upgrade pip
        pip install --upgrade pip --quiet
        
        # Install from requirements or pyproject.toml
        if [ -n "$INIT_PYTHON_CMD" ]; then
            eval "$INIT_PYTHON_CMD"
        elif [ -n "$local_requirements" ] && [ -f "$local_requirements" ]; then
            pip install -r "$local_requirements"
        elif [ -f "$local_python_dir/pyproject.toml" ]; then
            pip install -e "$local_python_dir"
        elif [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
            pip install -e "$PROJECT_ROOT"
        else
            log_warn "No requirements.txt or pyproject.toml found"
        fi
        
        log_success "Python dependencies installed"
    else
        log_success "Python environment ready (no changes needed)"
    fi
    
    deactivate
    echo ""
fi

# =============================================================================
# NODE.JS INITIALIZATION
# =============================================================================

if is_node_enabled; then
    log_header "Node.js Setup"
    
    local_node_dir=$(get_node_dir)
    local_pm=$(get_node_package_manager)
    local_install_cmd=$(get_node_install_cmd)
    
    require_command "$local_pm" "Install from https://nodejs.org"
    
    log_step "Installing Node.js dependencies with $local_pm..."
    
    cd "$local_node_dir"
    
    if [ -n "$INIT_NODE_CMD" ]; then
        eval "$INIT_NODE_CMD"
    else
        eval "$local_install_cmd"
    fi
    
    cd "$PROJECT_ROOT"
    
    log_success "Node.js dependencies installed"
    echo ""
fi

# =============================================================================
# RUST INITIALIZATION
# =============================================================================

if is_rust_enabled; then
    log_header "Rust Setup"
    
    require_command cargo "Install from https://rustup.rs"
    
    log_step "Building Rust project..."
    
    if [ -n "$INIT_RUST_CMD" ]; then
        eval "$INIT_RUST_CMD"
    else
        cargo build
    fi
    
    log_success "Rust project built"
    echo ""
fi

# =============================================================================
# GO INITIALIZATION
# =============================================================================

if is_go_enabled; then
    log_header "Go Setup"
    
    require_command go "Install from https://go.dev"
    
    log_step "Downloading Go dependencies..."
    
    if [ -n "$INIT_GO_CMD" ]; then
        eval "$INIT_GO_CMD"
    else
        go mod download
    fi
    
    log_success "Go dependencies downloaded"
    echo ""
fi

# =============================================================================
# DOCKER INITIALIZATION
# =============================================================================

if is_docker_enabled; then
    log_header "Docker Setup"
    
    if check_command docker; then
        log_step "Building Docker images..."
        
        if [ -n "$INIT_DOCKER_CMD" ]; then
            eval "$INIT_DOCKER_CMD"
        elif [ -f "$PROJECT_ROOT/docker-compose.yml" ] || [ -f "$PROJECT_ROOT/docker-compose.yaml" ] || \
             [ -f "$PROJECT_ROOT/compose.yml" ] || [ -f "$PROJECT_ROOT/compose.yaml" ]; then
            docker compose build
        elif [ -f "$PROJECT_ROOT/Dockerfile" ]; then
            docker build -t "${PROJECT_NAME:-project}" .
        fi
        
        log_success "Docker images built"
    else
        log_warn "Docker detected but docker command not available"
    fi
    echo ""
fi

# =============================================================================
# COMPLETE
# =============================================================================

log_header "Initialization Complete"
echo ""
echo "Next steps:"
echo "  1. Run './scripts/test.sh' to verify setup"
echo "  2. Run './scripts/run.sh' to start the development server"
echo ""
