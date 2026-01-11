# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Package distribution configuration with `pyproject.toml`
- MIT License file for open source distribution
- Comprehensive `.gitignore` and `.dockerignore` files
- `.env.example` documenting all required environment variables
- `requirements-dev.txt` for development dependencies
- Test coverage reporting with pytest-cov
- Production Docker Compose configuration (`docker-compose.prod.yml`) with:
  - Redis authentication enabled
  - LLM test mode disabled
  - Resource limits and health checks
  - Proper restart policies
  - Service replicas for scalability
- `SECURITY.md` with comprehensive security best practices
- `CHANGELOG.md` to track version history
- CI/CD pipeline configuration for automated testing and deployment

### Changed
- Updated `pytest.ini` to include coverage reporting configuration
- Enhanced documentation with security considerations

### Fixed
- Verified QuestionStore has `create_question` and `close_question` methods
- Confirmed orchestrator DLQ signature matches core implementation
- Validated state machine transitions (READY → IN_PROGRESS for dispatch)

## [0.1.0] - 2026-01-11

### Added
- Event-driven workflow automation toolkit built on Redis Streams
- Strict JSON Schema validation (Draft 2020-12) for all events
- Orchestrator service with state machine and backlog management
- Schema validation consumer service
- 8 specialized worker agents:
  - Time Waste Worker
  - Cost Worker
  - Friction Worker
  - Scenario Worker
  - Requirements Manager Worker
  - Dev Worker
  - Test Worker
  - Order Intake Agent
- LLM Gateway with multi-provider support:
  - Anthropic Claude
  - OpenAI GPT
  - Google Gemini
- Core infrastructure modules:
  - Redis Streams client with consumer groups
  - Idempotence tracking per consumer group
  - Dead-letter queue (DLQ) for failed events
  - Distributed locks for critical sections
  - Retry logic with configurable max attempts
  - Pending message reclaim via XAUTOCLAIM
- Backlog store with Redis-backed persistence
- Question store for clarification loops
- State machine with validated transitions
- Human-in-the-loop clarification workflow
- Definition-of-Done (DoD) enforcement
- Namespace support for multi-tenancy
- 25+ JSON Schema event definitions
- Comprehensive test suite with 31 test files
- Docker Compose orchestration for 13 services
- Interactive demo scripts:
  - Happy path demo
  - Failure/retry/DLQ demo
  - Clarification loop demo
  - HTTP gateway demo
- Web UI for project submission and question answering
- Extensive documentation:
  - README with quickstart guide
  - Complete API reference (DOCUMENTATION.md)
  - Step-by-step usage guide (TOOL_USAGE.md)
  - AI agent team designs (EPIC5_AI_AGENT_TEAMS.md)
  - LLM integration guide (AI_AGENT_SOLUTION.md)
  - Verification report (VERIFICATION_REPORT.md)

### Core Features
- **Reliability**: Idempotence, retry, DLQ, pending reclaim
- **Scalability**: Consumer groups, multiple workers, namespace isolation
- **Flexibility**: Domain-agnostic design with preset namespaces
- **Observability**: Correlation IDs, causation tracking, trace logging
- **Safety**: Schema validation, state machine enforcement, DoD checks

### Supported Domains
- Audit operations (default)
- Healthcare workflows
- Financial services
- Manufacturing processes
- DevSecOps reviews
- CI/CD pipelines

## [0.0.1] - Initial Development

### Added
- Initial project structure
- Core Redis Streams integration
- Basic event processing
- Proof of concept workers

---

## Release Notes

### Version 0.1.0

This is the first beta release of Agentic Workflow, a general-purpose event-driven workflow automation toolkit. The system is production-ready for internal deployments with the following considerations:

**Ready for Production:**
- ✅ Core infrastructure is stable and tested
- ✅ Reliability patterns implemented (idempotence, retry, DLQ)
- ✅ Comprehensive test coverage
- ✅ Docker containerization with health checks
- ✅ Detailed documentation

**Production Deployment Requirements:**
- Configure Redis authentication (see `docker-compose.prod.yml`)
- Set LLM API keys and disable test mode
- Enable monitoring and alerting
- Configure backups for Redis data
- Review security best practices in `SECURITY.md`

**Known Limitations:**
- No built-in authentication/authorization (deploy behind authenticated reverse proxy)
- No built-in multi-tenancy isolation (use separate deployments or namespace isolation)
- Limited observability metrics (integrate with external monitoring)

### Migration Guide

Not applicable for initial release.

### Deprecations

None for initial release.

---

## Contributing

When adding entries to this changelog:

1. Add unreleased changes under `[Unreleased]` section
2. Use the following categories:
   - `Added` for new features
   - `Changed` for changes in existing functionality
   - `Deprecated` for soon-to-be removed features
   - `Removed` for now removed features
   - `Fixed` for any bug fixes
   - `Security` for security-related changes
3. When cutting a new release, move unreleased changes to a new version section
4. Follow semantic versioning for version numbers

---

For more information, see:
- [README.md](README.md) - Project overview and quickstart
- [SECURITY.md](SECURITY.md) - Security practices and policies
- [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) - Complete API reference
