# LOGGING & HEALTH CHECKS

Standards for logging and health checks. These patterns apply to any project.

---

## Logging

### Principles

1. **Structured over unstructured** - JSON logs, not string concatenation
2. **Levels matter** - Use appropriate severity levels
3. **Context is king** - Include correlation IDs, user IDs, request metadata
4. **Security first** - Never log secrets, tokens, passwords, or PII

---

### Log Levels

| Level | When to Use | Examples |
|-------|-------------|----------|
| `error` | Something failed, needs attention | Unhandled exceptions, failed payments, database connection lost |
| `warn` | Something unexpected, but handled | Retry succeeded, deprecated API used, rate limit approaching |
| `info` | Normal operations worth recording | User signed in, order placed, job completed |
| `debug` | Detailed info for troubleshooting | Function entry/exit, variable values, SQL queries |

**Production:** `info` and above
**Development:** `debug` and above

---

### What to Log

#### Always Log
- Application startup and shutdown
- Authentication events (sign in, sign out, failed attempts)
- Authorization failures (access denied)
- API requests (method, path, status, duration)
- Errors with stack traces
- Background job start/complete/fail
- External service calls (API, database, cache)

#### Never Log
- Passwords or password hashes
- API keys, tokens, secrets
- Credit card numbers
- Social security numbers
- Personal health information
- Full request/response bodies (may contain PII)
- Session tokens or JWTs

#### Log Carefully (Redact if Needed)
- Email addresses (consider masking: `j***@example.com`)
- User IDs (usually OK, but consider privacy laws)
- IP addresses (may be PII under GDPR)

---

### Structured Log Format

Every log entry should be JSON with consistent fields:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "info",
  "message": "User signed in",
  "service": "api",
  "correlationId": "req-abc123",
  "userId": "user-xyz",
  "metadata": {
    "method": "magic_link",
    "duration_ms": 145
  }
}
```

#### Required Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 format, UTC |
| `level` | error, warn, info, debug |
| `message` | Human-readable description |
| `service` | Which service/app generated this |

#### Recommended Fields

| Field | Description |
|-------|-------------|
| `correlationId` | Request ID for tracing |
| `userId` | Authenticated user (if applicable) |
| `metadata` | Additional context (object) |
| `error` | Error details (for error level) |

---

### Correlation IDs

A correlation ID traces a request across services. Generate at entry point, pass through all calls.

```
Client Request
    │
    ▼
┌─────────────────────────────────────┐
│  correlationId: "req-abc123"        │
│                                     │
│  API Server (logs with req-abc123)  │
│       │                             │
│       ▼                             │
│  Database (logs with req-abc123)    │
│       │                             │
│       ▼                             │
│  External API (logs with req-abc123)│
└─────────────────────────────────────┘
```

**Implementation:**
1. Check for incoming `X-Correlation-ID` header
2. If missing, generate a new UUID
3. Attach to all log entries
4. Pass to downstream services via header
5. Return in response headers for client debugging

---

### Error Logging

Errors need extra context:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "error",
  "message": "Failed to create order",
  "service": "api",
  "correlationId": "req-abc123",
  "userId": "user-xyz",
  "error": {
    "name": "DatabaseError",
    "message": "Connection timeout",
    "stack": "DatabaseError: Connection timeout\n    at Query.run (/app/db.js:45:11)...",
    "code": "ETIMEDOUT"
  },
  "metadata": {
    "orderId": "order-456",
    "attempt": 2
  }
}
```

---

### Logger Interface

Regardless of implementation, use a consistent interface:

```typescript
interface Logger {
  debug(message: string, metadata?: object): void;
  info(message: string, metadata?: object): void;
  warn(message: string, metadata?: object): void;
  error(message: string, error?: Error, metadata?: object): void;
  
  // Create child logger with preset context
  child(context: object): Logger;
}

// Usage
const logger = createLogger({ service: 'api' });

// Per-request child logger
const reqLogger = logger.child({ 
  correlationId: req.id,
  userId: req.user?.id 
});

reqLogger.info('Processing order', { orderId: '123' });
```

---

### Library Recommendations

| Platform | Library | Notes |
|----------|---------|-------|
| Node.js | pino | Fast, JSON-native, low overhead |
| Node.js | winston | Flexible, many transports |
| Browser | Custom or loglevel | Keep it light, send to backend |
| React Native | Custom | Write to console, optionally send to backend |
| Edge Functions | Console + structured format | Keep simple, short-lived |

---

### Script-Level Logging

The project shell scripts (`run.sh`, `test.sh`, `init.sh`) produce their own logs separate from application logs.

#### Log Locations

| Script | Log File | Contents |
|--------|----------|----------|
| `run.sh` | `/tmp/${PROJECT_NAME}_backend.log` | Backend service stdout/stderr |
| `run.sh` | `/tmp/${PROJECT_NAME}_frontend.log` | Frontend service stdout/stderr |

The `PROJECT_NAME` variable is set in `scripts/project.conf`.

#### Viewing Logs During Development

```bash
# Follow backend logs
tail -f /tmp/myproject_backend.log

# Follow frontend logs  
tail -f /tmp/myproject_frontend.log

# Follow both
tail -f /tmp/myproject_*.log
```

#### Log Rotation

These development logs are stored in `/tmp` and cleared on system restart. For production:
- Use a process manager (PM2, systemd) with built-in log rotation
- Or configure your logging library to write to files with rotation
- Consider log aggregation services for multi-service deployments

---

## Health Checks

### Purpose

Health checks answer: "Is this service ready to handle requests?"

They enable:
- Load balancer routing
- Container orchestration (K8s readiness/liveness)
- Monitoring and alerting
- Deployment verification

---

### Types of Health Checks

#### 1. Liveness Check
**Question:** Is the process alive?
**Failure action:** Restart the process
**Endpoint:** `GET /health/live`

```json
{ "status": "ok" }
```

Should be fast and simple. Just confirms the process can respond.

#### 2. Readiness Check
**Question:** Can this service handle requests?
**Failure action:** Stop sending traffic (don't restart)
**Endpoint:** `GET /health/ready`

```json
{
  "status": "ok",
  "checks": {
    "database": { "status": "ok", "latency_ms": 5 },
    "cache": { "status": "ok", "latency_ms": 2 }
  }
}
```

Checks dependencies. Service might be alive but not ready (e.g., database connection lost).

#### 3. Detailed Health Check (Internal Only)
**Question:** What's the full system status?
**Audience:** Operators, debugging
**Endpoint:** `GET /health/details` (authenticated or internal only)

```json
{
  "status": "ok",
  "version": "1.2.3",
  "uptime_seconds": 86400,
  "checks": {
    "database": {
      "status": "ok",
      "latency_ms": 5,
      "connections": { "active": 10, "idle": 5, "max": 20 }
    },
    "supabase": {
      "status": "ok", 
      "latency_ms": 45
    },
    "memory": {
      "status": "ok",
      "used_mb": 256,
      "total_mb": 512
    }
  }
}
```

---

### Health Check Response Format

```typescript
interface HealthResponse {
  status: 'ok' | 'degraded' | 'error';
  checks?: Record<string, CheckResult>;
  version?: string;
  uptime_seconds?: number;
}

interface CheckResult {
  status: 'ok' | 'degraded' | 'error';
  latency_ms?: number;
  message?: string;
  [key: string]: unknown;  // Additional details
}
```

#### Status Codes

| Status | HTTP Code | Meaning |
|--------|-----------|---------|
| `ok` | 200 | Everything healthy |
| `degraded` | 200 | Partial issues, but functional |
| `error` | 503 | Not ready for traffic |

---

### What to Check

| Dependency | How to Check |
|------------|--------------|
| Database | Simple query: `SELECT 1` |
| Supabase | Query a known table or call auth endpoint |
| Redis/Cache | `PING` command |
| External API | Lightweight endpoint or HEAD request |
| File system | Check required paths exist |
| Memory | Compare usage against threshold |
| Disk | Check available space |

---

### Health Check Patterns

#### Timeouts
Each check should have a timeout. Don't let a slow dependency hang the health check.

```typescript
async function checkDatabase(): Promise<CheckResult> {
  const start = Date.now();
  try {
    await Promise.race([
      db.query('SELECT 1'),
      timeout(5000)  // 5 second timeout
    ]);
    return { 
      status: 'ok', 
      latency_ms: Date.now() - start 
    };
  } catch (error) {
    return { 
      status: 'error', 
      message: error.message,
      latency_ms: Date.now() - start
    };
  }
}
```

#### Caching
Don't hit dependencies on every health check request. Cache results for a few seconds.

```typescript
let cachedHealth: HealthResponse | null = null;
let cacheTime = 0;
const CACHE_TTL_MS = 5000;

async function getHealth(): Promise<HealthResponse> {
  if (cachedHealth && Date.now() - cacheTime < CACHE_TTL_MS) {
    return cachedHealth;
  }
  
  cachedHealth = await performHealthChecks();
  cacheTime = Date.now();
  return cachedHealth;
}
```

#### Graceful Degradation
If a non-critical dependency fails, return `degraded` not `error`.

```typescript
async function getHealth(): Promise<HealthResponse> {
  const checks = {
    database: await checkDatabase(),      // Critical
    cache: await checkCache(),            // Non-critical
    analytics: await checkAnalytics(),    // Non-critical
  };
  
  const criticalFailed = checks.database.status === 'error';
  const anyFailed = Object.values(checks).some(c => c.status === 'error');
  
  return {
    status: criticalFailed ? 'error' : anyFailed ? 'degraded' : 'ok',
    checks
  };
}
```

---

### Security Considerations

1. **Liveness endpoint** - Can be public (minimal info)
2. **Readiness endpoint** - Can be public (shows dependency status)
3. **Detailed endpoint** - Should be authenticated or internal-only

Never expose in health checks:
- Connection strings
- Credentials
- Internal IP addresses
- Sensitive configuration

---

### Verifying Health Checks

After implementing health endpoints, verify they work correctly.

#### Manual Verification

```bash
# Check liveness (should return immediately)
curl -s http://localhost:8000/health/live | jq .

# Check readiness (verifies dependencies)
curl -s http://localhost:8000/health/ready | jq .

# Check with timing
curl -w "\nTime: %{time_total}s\n" http://localhost:8000/health/ready
```

#### Automated Verification

Use the test script to verify health endpoints:

```bash
# Run health check verification
./scripts/test.sh health
```

This will:
1. Start the backend service temporarily
2. Wait for `/health/live` to respond
3. Verify `/health/ready` returns the expected format
4. Check that status is `ok`, `degraded`, or `error`
5. Shut down the service and report results

#### Startup Health Verification

The `run.sh` script automatically waits for health endpoints before declaring a service ready. This ensures:
- The service is actually responding, not just started
- Dependencies are connected
- The service can handle requests

---

## Implementation Checklist

### Logging
- [ ] Structured JSON logging configured
- [ ] Log levels defined and documented
- [ ] Correlation ID generation and propagation
- [ ] Sensitive data redaction in place
- [ ] Error logging includes stack traces
- [ ] Request/response logging (without bodies)
- [ ] Log output configured per environment

### Health Checks
- [ ] `/health/live` endpoint exists
- [ ] `/health/ready` endpoint exists
- [ ] All critical dependencies checked
- [ ] Timeouts on all dependency checks
- [ ] Response caching implemented
- [ ] Graceful degradation for non-critical deps
- [ ] Detailed health endpoint protected

---

## Quick Reference

```
Logging Levels:
  error  →  Something broke, needs attention
  warn   →  Unexpected but handled
  info   →  Normal operations
  debug  →  Troubleshooting details

Log Fields:
  timestamp, level, message, service  (required)
  correlationId, userId, metadata     (recommended)
  error { name, message, stack }      (for errors)

Health Endpoints:
  /health/live    →  Is process alive?      →  200 or 503
  /health/ready   →  Can handle requests?   →  200 or 503
  /health/details →  Full system status     →  Protected

Health Statuses:
  ok        →  All good
  degraded  →  Partial issues, still functional
  error     →  Not ready for traffic
```