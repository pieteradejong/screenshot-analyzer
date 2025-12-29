#!/bin/bash
# =============================================================================
# Development Server Script
# =============================================================================
# Starts the development environment for detected project stacks.
#
# Usage:
#   ./scripts/run.sh [MODE] [OPTIONS]
#
# Modes:
#   all         Start all detected services (default)
#   backend     Start only backend services (Python, Rust, Go)
#   frontend    Start only frontend services (Node.js)
#   docker      Start with Docker Compose
#
# Options:
#   --help      Show this help message
# =============================================================================

# Don't use set -e because we manage process lifecycle manually

# Source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

# Health check configuration
HEALTH_CHECK_ENABLED=${HEALTH_CHECK_ENABLED:-true}
HEALTH_CHECK_TIMEOUT=${HEALTH_CHECK_TIMEOUT:-30}
HEALTH_LIVE_PATH=${HEALTH_LIVE_PATH:-/health/live}

# Process tracking
BACKEND_PID=""
FRONTEND_PID=""

# Log files
BACKEND_LOG="/tmp/${PROJECT_NAME:-project}_backend.log"
FRONTEND_LOG="/tmp/${PROJECT_NAME:-project}_frontend.log"

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

show_help() {
    echo "Usage: $0 [MODE] [OPTIONS]"
    echo ""
    echo "Start the development environment."
    echo ""
    echo "Modes:"
    echo "  all         Start all detected services (default)"
    echo "  backend     Start only backend services (Python, Rust, Go)"
    echo "  frontend    Start only frontend services (Node.js)"
    echo "  docker      Start with Docker Compose"
    echo ""
    echo "Options:"
    echo "  --help      Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  BACKEND_PORT         Port for backend server (default: 8000)"
    echo "  FRONTEND_PORT        Port for frontend server (default: 5173)"
    echo "  HEALTH_CHECK_ENABLED Wait for health endpoint (default: true)"
    echo "  HEALTH_CHECK_TIMEOUT Seconds to wait for health (default: 30)"
    echo "  HEALTH_LIVE_PATH     Health endpoint path (default: /health/live)"
    exit 0
}

MODE="all"

for arg in "$@"; do
    case $arg in
        backend|frontend|all|docker)
            MODE="$arg"
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
# CLEANUP HANDLER
# =============================================================================

cleanup() {
    echo ""
    log_step "Shutting down..."
    
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
        log_info "Backend stopped"
    fi
    
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
        log_info "Frontend stopped"
    fi
    
    exit 0
}

trap cleanup SIGINT SIGTERM

# =============================================================================
# HEALTH CHECK HELPERS
# =============================================================================

# Wait for a service to become healthy after starting
# Usage: wait_for_service_healthy "backend" $PORT $PID
wait_for_service_healthy() {
    local service_name=$1
    local port=$2
    local pid=$3
    local health_url="http://localhost:${port}${HEALTH_LIVE_PATH}"
    
    if [ "$HEALTH_CHECK_ENABLED" != "true" ]; then
        return 0
    fi
    
    log_step "Waiting for $service_name to become healthy..."
    
    local start=$(date +%s)
    local timeout=$HEALTH_CHECK_TIMEOUT
    
    while true; do
        # Check if process is still running
        if ! kill -0 "$pid" 2>/dev/null; then
            log_error "$service_name process exited unexpectedly"
            log_info "Check logs for details"
            return 1
        fi
        
        # Try health check
        if curl -sf "$health_url" > /dev/null 2>&1; then
            log_success "$service_name is healthy"
            return 0
        fi
        
        local elapsed=$(($(date +%s) - start))
        if [ $elapsed -ge $timeout ]; then
            log_warn "$service_name did not respond to health check within ${timeout}s"
            log_info "Service may still be starting or health endpoint not implemented"
            log_info "See LOGGING.md for health check implementation details"
            return 0  # Don't fail, just warn
        fi
        
        sleep 1
    done
}

# =============================================================================
# BACKEND STARTERS
# =============================================================================

start_python_backend() {
    local python_dir=$(get_python_dir)
    local venv_path=$(get_venv_path)
    
    if [ ! -d "$venv_path" ]; then
        log_error "Virtual environment not found at $venv_path"
        log_info "Run './scripts/init.sh' first"
        return 1
    fi
    
    log_step "Starting Python backend..."
    
    source "$venv_path/bin/activate"
    
    if check_port "$BACKEND_PORT"; then
        log_error "Port $BACKEND_PORT is already in use"
        deactivate
        return 1
    fi
    
    cd "$python_dir"
    
    # Determine run command
    local run_cmd=""
    if [ -n "$RUN_PYTHON_CMD" ]; then
        run_cmd="$RUN_PYTHON_CMD"
    elif [ -f "main.py" ] && grep -q "uvicorn\|fastapi" main.py 2>/dev/null; then
        run_cmd="uvicorn main:app --reload --port $BACKEND_PORT --host 0.0.0.0"
    elif [ -f "app.py" ] && grep -q "flask\|Flask" app.py 2>/dev/null; then
        run_cmd="flask run --port $BACKEND_PORT --host 0.0.0.0"
    elif [ -f "manage.py" ]; then
        run_cmd="python manage.py runserver 0.0.0.0:$BACKEND_PORT"
    elif [ -f "main.py" ]; then
        run_cmd="python main.py"
    elif [ -f "app.py" ]; then
        run_cmd="python app.py"
    else
        log_warn "No recognizable Python entry point found"
        deactivate
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    eval "$run_cmd" > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    
    cd "$PROJECT_ROOT"
    
    log_info "Python backend starting (PID: $BACKEND_PID)"
    log_info "  Log: tail -f $BACKEND_LOG"
    
    # Wait for health check
    if wait_for_service_healthy "Python backend" "$BACKEND_PORT" "$BACKEND_PID"; then
        log_info "  URL: http://localhost:$BACKEND_PORT"
    else
        return 1
    fi
}

start_rust_backend() {
    if check_port "$BACKEND_PORT"; then
        log_error "Port $BACKEND_PORT is already in use"
        return 1
    fi
    
    log_step "Starting Rust backend..."
    
    local run_cmd="${RUN_RUST_CMD:-cargo run}"
    
    eval "$run_cmd" > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    
    log_info "Rust backend starting (PID: $BACKEND_PID)"
    log_info "  Log: tail -f $BACKEND_LOG"
    
    # Wait for health check
    if wait_for_service_healthy "Rust backend" "$BACKEND_PORT" "$BACKEND_PID"; then
        log_info "  URL: http://localhost:$BACKEND_PORT"
    else
        return 1
    fi
}

start_go_backend() {
    if check_port "$BACKEND_PORT"; then
        log_error "Port $BACKEND_PORT is already in use"
        return 1
    fi
    
    log_step "Starting Go backend..."
    
    local run_cmd="${RUN_GO_CMD:-go run .}"
    
    eval "$run_cmd" > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    
    log_info "Go backend starting (PID: $BACKEND_PID)"
    log_info "  Log: tail -f $BACKEND_LOG"
    
    # Wait for health check
    if wait_for_service_healthy "Go backend" "$BACKEND_PORT" "$BACKEND_PID"; then
        log_info "  URL: http://localhost:$BACKEND_PORT"
    else
        return 1
    fi
}

# =============================================================================
# FRONTEND STARTER
# =============================================================================

start_node_frontend() {
    local node_dir=$(get_node_dir)
    local run_prefix=$(get_node_run_prefix)
    
    if [ ! -d "$node_dir/node_modules" ]; then
        log_error "node_modules not found in $node_dir"
        log_info "Run './scripts/init.sh' first"
        return 1
    fi
    
    if check_port "$FRONTEND_PORT"; then
        log_error "Port $FRONTEND_PORT is already in use"
        return 1
    fi
    
    log_step "Starting Node.js frontend..."
    
    cd "$node_dir"
    
    # Determine run command
    local run_cmd=""
    if [ -n "$RUN_NODE_CMD" ]; then
        run_cmd="$RUN_NODE_CMD"
    elif grep -q '"dev"' package.json 2>/dev/null; then
        run_cmd="$run_prefix dev"
    elif grep -q '"start"' package.json 2>/dev/null; then
        run_cmd="$run_prefix start"
    else
        log_warn "No 'dev' or 'start' script found in package.json"
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    eval "$run_cmd" > "$FRONTEND_LOG" 2>&1 &
    FRONTEND_PID=$!
    
    cd "$PROJECT_ROOT"
    
    log_info "Node.js frontend starting (PID: $FRONTEND_PID)"
    log_info "  Log: tail -f $FRONTEND_LOG"
    
    # Wait for frontend to be ready (just check if port responds)
    if [ "$HEALTH_CHECK_ENABLED" = "true" ]; then
        log_step "Waiting for frontend to become ready..."
        local start=$(date +%s)
        local ready=false
        
        while true; do
            # Check if process is still running
            if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
                log_error "Frontend process exited unexpectedly"
                return 1
            fi
            
            # Check if port is responding
            if curl -sf "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
                ready=true
                break
            fi
            
            local elapsed=$(($(date +%s) - start))
            if [ $elapsed -ge $HEALTH_CHECK_TIMEOUT ]; then
                break
            fi
            
            sleep 1
        done
        
        if [ "$ready" = true ]; then
            log_success "Frontend is ready"
        else
            log_warn "Frontend did not respond within ${HEALTH_CHECK_TIMEOUT}s"
            log_info "Service may still be starting"
        fi
    fi
    
    log_info "  URL: http://localhost:$FRONTEND_PORT"
}

# =============================================================================
# DOCKER STARTER
# =============================================================================

start_docker() {
    log_step "Starting with Docker Compose..."
    
    local compose_cmd=""
    if [ -n "$RUN_DOCKER_CMD" ]; then
        compose_cmd="$RUN_DOCKER_CMD"
    else
        compose_cmd="docker compose up"
    fi
    
    # Run in foreground for docker
    eval "$compose_cmd"
}

# =============================================================================
# MAIN
# =============================================================================

log_header "${PROJECT_NAME:-Project} - Development Server"
echo ""

case $MODE in
    docker)
        if is_docker_enabled; then
            start_docker
        else
            log_error "No Docker configuration found"
            exit 1
        fi
        ;;
    
    backend)
        if is_python_enabled; then
            start_python_backend
        elif is_rust_enabled; then
            start_rust_backend
        elif is_go_enabled; then
            start_go_backend
        else
            log_error "No backend stack detected"
            exit 1
        fi
        
        echo ""
        log_success "Backend running. Press Ctrl+C to stop"
        wait "$BACKEND_PID" 2>/dev/null || true
        ;;
    
    frontend)
        if is_node_enabled; then
            start_node_frontend
        else
            log_error "No frontend stack detected"
            exit 1
        fi
        
        echo ""
        log_success "Frontend running. Press Ctrl+C to stop"
        wait "$FRONTEND_PID" 2>/dev/null || true
        ;;
    
    all|*)
        started=false
        
        # Start backend
        if is_python_enabled; then
            start_python_backend && started=true
            echo ""
        elif is_rust_enabled; then
            start_rust_backend && started=true
            echo ""
        elif is_go_enabled; then
            start_go_backend && started=true
            echo ""
        fi
        
        # Start frontend
        if is_node_enabled; then
            start_node_frontend && started=true
            echo ""
        fi
        
        if [ "$started" = false ]; then
            log_error "No services could be started"
            log_info "Make sure you have run './scripts/init.sh' first"
            exit 1
        fi
        
        log_success "All services running. Press Ctrl+C to stop"
        echo ""
        
        # Wait for all processes
        if [ -n "$BACKEND_PID" ] && [ -n "$FRONTEND_PID" ]; then
            wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
        elif [ -n "$BACKEND_PID" ]; then
            wait "$BACKEND_PID" 2>/dev/null || true
        elif [ -n "$FRONTEND_PID" ]; then
            wait "$FRONTEND_PID" 2>/dev/null || true
        fi
        ;;
esac
