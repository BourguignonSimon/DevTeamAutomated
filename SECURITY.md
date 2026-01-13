# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of Agentic Workflow seriously. If you believe you have found a security vulnerability, please report it to us as described below.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to [your-security-email@example.com]. You should receive a response within 48 hours. If for some reason you do not, please follow up via email to ensure we received your original message.

Please include the requested information listed below (as much as you can provide) to help us better understand the nature and scope of the possible issue:

* Type of issue (e.g. buffer overflow, SQL injection, cross-site scripting, etc.)
* Full paths of source file(s) related to the manifestation of the issue
* The location of the affected source code (tag/branch/commit or direct URL)
* Any special configuration required to reproduce the issue
* Step-by-step instructions to reproduce the issue
* Proof-of-concept or exploit code (if possible)
* Impact of the issue, including how an attacker might exploit the issue

This information will help us triage your report more quickly.

## Security Best Practices

### Deployment Security

#### 1. Redis Security

**Production Deployment:**
- Always enable Redis authentication in production
- Use strong, randomly generated passwords (minimum 32 characters)
- Configure Redis to listen only on localhost or private network interfaces
- Enable TLS/SSL for Redis connections in sensitive environments
- Regularly rotate Redis passwords

```bash
# Set a strong Redis password
export REDIS_PASSWORD=$(openssl rand -base64 32)
```

**Development vs Production:**
- Development: `docker-compose up` (no authentication, for local testing only)
- Production: `docker-compose -f docker-compose.prod.yml up` (with authentication)

#### 2. LLM API Keys

**CRITICAL:** Never commit API keys to version control

- Store API keys in environment variables or secure secret management systems
- Use different API keys for development, staging, and production
- Rotate API keys regularly (recommended: every 90 days)
- Monitor API key usage for anomalies
- Revoke compromised keys immediately

**Production Setup:**
```bash
# Set LLM API keys from secure vault or environment
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="..."

# Disable test mode in production
export LLM_TEST_MODE="false"
```

#### 3. File Upload Security

The Order Intake Agent accepts file uploads. In production:

- Implement file type validation (whitelist allowed extensions)
- Set maximum file size limits (default recommendation: 10MB)
- Scan uploaded files for malware
- Store uploaded files outside the web root
- Use unique, non-guessable filenames
- Implement access controls for uploaded files

**Recommended Configuration:**
```bash
# Limit file upload size (configure in your reverse proxy/API gateway)
MAX_UPLOAD_SIZE=10485760  # 10MB in bytes

# Allowed file types
ALLOWED_EXTENSIONS=csv,xlsx,xls,pdf
```

#### 4. Network Security

**Docker Network Isolation:**
- Services communicate over internal Docker networks
- Only expose necessary ports to the host
- Use reverse proxy (nginx, Traefik) for external access
- Enable TLS/SSL for all external endpoints

**Recommended Port Exposure:**
```yaml
# Only expose application ports, not Redis
ports:
  - "8080:8080"  # Order Intake API (behind reverse proxy)
# Do NOT expose Redis port 6380 in production
```

#### 5. Environment Variables

- Never commit `.env` files to version control
- Use `.env.example` as a template only
- Rotate secrets regularly
- Use different credentials for each environment
- Consider using secret management tools (HashiCorp Vault, AWS Secrets Manager, etc.)

### Application Security

#### 1. JSON Schema Validation

All events are validated against JSON Schemas before processing. This provides:

- Protection against malformed input
- Type safety for event payloads
- Contract enforcement across services

**Security Benefit:** Invalid or malicious events are rejected and sent to the DLQ, preventing exploitation.

#### 2. Event Idempotence

The system tracks processed events to prevent duplicate execution:

- TTL-based deduplication (default: 24 hours)
- Per-consumer group isolation
- Protection against replay attacks

#### 3. Dead Letter Queue (DLQ)

Failed events are routed to a DLQ:

- Prevents system blocking
- Preserves evidence for forensics
- Limits retry amplification attacks

**Monitoring Recommendation:** Alert on DLQ growth rate exceeding thresholds.

#### 4. Distributed Locks

Critical operations use Redis-based distributed locks:

- Prevents race conditions
- TTL-based auto-release (default: 120s)
- Per-resource lock granularity

#### 5. Input Sanitization

When processing user input:

- All inputs are validated against schemas
- CSV/Excel parsing uses trusted libraries (openpyxl)
- No direct shell command execution with user input
- LLM responses are not executed as code

### Authentication & Authorization

**Current State:** The system currently operates in a trusted network environment and does not include built-in authentication.

**Production Recommendations:**

1. **API Authentication:**
   - Implement API key authentication for HTTP endpoints
   - Use JWT tokens for session management
   - Enable mTLS for service-to-service communication

2. **Authorization:**
   - Implement role-based access control (RBAC)
   - Separate read and write permissions
   - Audit all privileged operations

3. **Reverse Proxy:**
   - Use nginx, Traefik, or similar with authentication
   - Implement rate limiting (recommended: 100 requests/minute per IP)
   - Enable request logging for audit trails

### Monitoring & Logging

**Security Monitoring:**

1. **Log Collection:**
   - Centralize logs (ELK stack, Splunk, CloudWatch)
   - Retain logs for compliance requirements (minimum 90 days)
   - Protect log integrity (append-only storage)

2. **Alerting:**
   - DLQ growth exceeding thresholds
   - Redis authentication failures
   - LLM API rate limit violations
   - Unusual event patterns

3. **Metrics to Monitor:**
   - Failed authentication attempts
   - DLQ message count
   - Event processing latency
   - Redis memory usage

### Data Protection

1. **Data in Transit:**
   - Use TLS 1.2+ for all external connections
   - Enable Redis TLS in sensitive environments

2. **Data at Rest:**
   - Enable Redis persistence with encryption (RDB/AOF)
   - Encrypt sensitive file uploads
   - Regular backups with encryption

3. **Data Retention:**
   - Define retention policies for events and logs
   - Implement automated cleanup for expired data
   - Comply with GDPR/CCPA requirements

### Dependencies & Updates

1. **Dependency Management:**
   - Regularly update dependencies for security patches
   - Monitor for CVEs in dependencies
   - Use tools like `safety` or Snyk for vulnerability scanning

```bash
# Check for known vulnerabilities
pip install safety
safety check -r requirements.txt
```

2. **Container Security:**
   - Use official base images (python:3.12-slim)
   - Scan images for vulnerabilities (Docker Scan, Trivy)
   - Minimize image size (reduce attack surface)

3. **Update Policy:**
   - Critical security patches: within 24 hours
   - High severity: within 7 days
   - Medium severity: within 30 days

### Development Security

1. **Code Review:**
   - All changes require code review
   - Security-focused review for authentication, input validation, and cryptography

2. **Testing:**
   - Include security test cases
   - Test input validation with malicious inputs
   - Verify authentication and authorization logic

3. **Secrets in Development:**
   - Never commit real credentials
   - Use test mode for LLM gateway in development
   - Use weak passwords only in local development

## Incident Response

If a security incident is detected:

1. **Containment:**
   - Isolate affected systems
   - Rotate compromised credentials
   - Enable additional logging

2. **Investigation:**
   - Collect logs and evidence
   - Identify root cause
   - Assess impact

3. **Recovery:**
   - Apply patches or fixes
   - Restore from backups if necessary
   - Verify system integrity

4. **Post-Incident:**
   - Document incident and response
   - Update security controls
   - Notify affected parties if required

## Compliance

This system may process sensitive data. Ensure compliance with:

- GDPR (European Union)
- CCPA (California)
- SOC 2
- HIPAA (if processing health data)
- PCI DSS (if processing payment data)

Consult with legal and compliance teams before deploying in regulated environments.

## Security Checklist for Production

Before deploying to production, verify:

- [ ] Redis password is set and strong
- [ ] LLM_TEST_MODE is set to "false"
- [ ] LLM API keys are configured and valid
- [ ] All environment variables are set correctly
- [ ] Redis port is not exposed to public internet
- [ ] TLS/SSL is enabled for external endpoints
- [ ] File upload size limits are configured
- [ ] Monitoring and alerting are configured
- [ ] Log collection is enabled
- [ ] Backup strategy is in place
- [ ] Incident response plan is documented
- [ ] All dependencies are up to date
- [ ] Container images are scanned for vulnerabilities
- [ ] Rate limiting is enabled on public endpoints
- [ ] DLQ monitoring alerts are configured

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Redis Security Guide](https://redis.io/docs/management/security/)
- [CWE Top 25 Most Dangerous Software Weaknesses](https://cwe.mitre.org/top25/)

## Contact

For security concerns, contact: [your-security-email@example.com]

---

Last Updated: 2026-01-11
