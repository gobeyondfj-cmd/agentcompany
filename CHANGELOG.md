# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-03-15

### Added
- **Cost safety defaults**: `max_cost_usd` now defaults to $10/run, new `daily_budget_usd` defaults to $20/day
- `--budget` CLI flag on the `run` command to override daily budget
- `cost_last_24h()` method on CostTracker for rolling 24-hour spend tracking
- Daily budget enforcement in autonomous `run_goal()` loop
- Test suite: `test_config`, `test_cost_tracker`, `test_tools_registry`, `test_task`
- GitHub Actions CI (test matrix: Python 3.10-3.12) and PyPI publish workflow
- `CONTRIBUTING.md` with dev setup, testing, and PR process
- GitHub issue templates (bug report, feature request)
- PEP 561 `py.typed` marker for type checker support
- `[dev]` optional dependency group (`pytest`, `pytest-asyncio`, `pytest-cov`)
- `[blockchain]` optional dependency group (`web3`, `eth-account`)
- Budget info displayed in the autonomous mode Panel output

### Changed
- `web3` and `eth-account` moved from required to optional dependencies
- Wallet imports guarded with try/except — graceful fallback when blockchain deps not installed
- Version synced between `pyproject.toml` and `__init__.py`

### Fixed
- Version mismatch between pyproject.toml (0.4.0) and __init__.py (0.3.8)

## [0.4.0] - 2026-02-21

### Added
- **Lead prospecting tools**: `prospect_search`, `enrich_contact`, `prospect_campaign`
- **Content generation tools**: `create_blog_post`, `create_email_sequence`, `create_digital_product`
- **Browser automation tools**: `browse_page`, `extract_contacts_from_url`, `submit_form`
- Rate limits for prospecting (30/hr, 200/day) and browsing (60/hr, 500/day)

## [0.3.9] - 2026-02-20

### Added
- Interactive integration setup prompts in `init` command
- Integration menu for configuring Stripe, Email, Gumroad, Cal.com, Invoices, Landing Pages
- `--skip-integrations` flag for non-interactive init

## [0.3.8] - 2026-02-19

### Added
- **Revenue ledger**: `check_revenue`, `record_revenue`, `sync_stripe_revenue` tools
- `revenue` CLI command for unified revenue summary
- LLM retry with exponential backoff on transient errors (429, 500-503)
- `CANCELLED` task status for incomplete tasks when goal loop ends
- Non-interactive init when all flags provided (`--name`, `--provider`, `--api-key`, `--model`)

### Fixed
- Landing page generator uses company name from config instead of placeholder

## [0.3.6] - 2026-02-18

### Added
- Twitter auto-publish via Twitter API (`publish_twitter` tool)
- Vercel deploy for landing pages (`deploy_landing_page` tool)
- Rate limits for tweets (17/day) and deploys (50/day)

## [0.3.5] - 2026-02-17

### Added
- **Email tool**: Send transactional email via Resend or SendGrid
- **Stripe tools**: Create payment links with safety caps
- **CRM contacts**: Add, list, update contacts
- **Landing page generator**: Auto-generate styled HTML landing pages
- **Social media drafts**: Draft and review social posts
- Rate limiter with rolling window buckets
- `IntegrationsConfig` with all integrations disabled by default

## [0.3.4] - 2026-02-16

### Fixed
- **Preamble fix**: Track longest assistant text (`best_assistant_text`) to catch LLMs that write deliverables as chat but call `report_result("")`
- Deliverable quality scorecard tracking (substantial/partial/thin/empty)

## [0.3.3] - 2026-02-15

### Fixed
- 0-byte deliverables: export results to `.agent-company-ai/default/output/` as `.md` files
- Raised default agent iteration limit to 25

## [0.3.2] - 2026-02-14

### Fixed
- Critical FK constraint bug: tasks now persisted to DB before agent execution
- Added `--version` flag to CLI
- Fixed task display formatting

## [0.3.0] - 2026-02-13

### Added
- **ProfitEngine**: Business DNA system with 6 templates (saas, ecommerce, marketplace, agency, consulting, content)
- **Blockchain wallet**: Encrypted keystore, multi-chain support (Ethereum, Base, Arbitrum, Polygon), payment approval queue
- `profit-engine` and `wallet` CLI sub-commands

## [0.2.0] - 2026-02-12

### Added
- Multi-company support with `--company` flag and `companies`/`destroy` commands
- `setup` command with preset templates (tech_startup, agency, ecommerce, saas, consulting, content, full)
- Legacy layout migration

## [0.1.0] - 2026-02-10

### Added
- Initial release
- Core agent system with 9 preset roles (CEO, CTO, Developer, Marketer, Sales, Support, Finance, HR, Project Manager)
- Autonomous CEO mode with plan-execute-review cycles
- Web dashboard with org chart, kanban board, and chat
- 11 LLM providers (Anthropic, OpenAI, DeepSeek, Ollama, Together, Groq, and more)
- Built-in tools: web search, file I/O, code execution, shell
- SQLite storage for agents, tasks, messages, and artifacts
- Typer CLI with sub-commands
