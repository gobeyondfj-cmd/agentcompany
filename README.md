# Agent Company AI

**Spin up an AI agent company - a business run by AI agents, managed by you.**

Agent Company AI lets a solo entrepreneur create a virtual company staffed entirely by AI agents. Each agent has a specific business role (CEO, CTO, Developer, Marketer, etc.), they collaborate on tasks, and you manage everything through a CLI or web dashboard.

## Quick Start

```bash
pip install agent-company-ai
```

### 1. Initialize your company

```bash
agent-company-ai init --name "My AI Startup"
```

You'll be prompted to choose an LLM provider (Anthropic, OpenAI, DeepSeek, Ollama, and more).

### 2. One-command setup

Spin up a full team from a preset template:

```bash
agent-company-ai setup tech_startup --name "Acme AI"
agent-company-ai setup saas --name "CloudCo" --provider anthropic
agent-company-ai setup --list  # see all presets
```

**Available presets:** `tech_startup` (6 agents), `agency` (6), `ecommerce` (7), `saas` (9), `consulting` (6), `content` (5), `full` (10 — all departments)

### 3. Or hire agents individually

```bash
agent-company-ai hire ceo --name Alice
agent-company-ai hire cto --name Bob
agent-company-ai hire developer --name Carol
agent-company-ai hire marketer --name Dave
```

### 4. Define your business model

Tell your agents how the company makes money:

```bash
agent-company-ai profit-engine setup --template saas
```

This injects your business DNA into every agent's decision-making. See [ProfitEngine](#profitengine--business-dna) below.

### 5. Run autonomously

Give the CEO a goal and watch the company run:

```bash
agent-company-ai run "Build a landing page for our new product"
```

The CEO will break down the goal, delegate tasks to the team, and agents will collaborate to deliver results.

```bash
# With limits
agent-company-ai run "Launch MVP" --cycles 3 --timeout 600 --max-tasks 20
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize a new company |
| `setup <preset>` | Set up a full company from a template |
| `hire <role>` | Hire an agent |
| `fire <name>` | Remove an agent |
| `team` | List all agents |
| `assign "<task>"` | Assign a task |
| `tasks` | Show the task board |
| `chat <name>` | Chat with an agent |
| `run "<goal>"` | Autonomous mode |
| `broadcast "<msg>"` | Message all agents |
| `dashboard` | Launch web dashboard |
| `status` | Company overview |
| `output` | List deliverables produced by agents |
| `roles` | List available roles |
| `companies` | List all companies in this directory |
| `destroy` | Permanently delete a company |
| `profit-engine <cmd>` | Configure business model DNA ([details](#profitengine--business-dna)) |
| `wallet <cmd>` | Manage blockchain wallet ([details](#blockchain-wallet)) |

### Global Options

| Flag | Description |
|------|-------------|
| `--company` / `-C` | Company slug to operate on (default: `default`) |

You can also set the company via environment variable:

```bash
export AGENT_COMPANY_NAME=my-startup
agent-company-ai team  # operates on my-startup
```

## ProfitEngine — Business DNA

ProfitEngine lets you define your company's business model — how it earns money, who it serves, and what matters most. This "business DNA" is injected into **every agent's system prompt** and into the **CEO's goal loop**, so all decisions align with your business model.

### Setup

Start from a preset template or from scratch:

```bash
# Interactive wizard with a preset
agent-company-ai profit-engine setup --template saas

# Fully interactive — choose a template then customize each field
agent-company-ai profit-engine setup
```

The wizard walks you through 8 fields:

| Field | What it defines |
|-------|----------------|
| **Mission** | The company's core purpose |
| **Revenue Streams** | How the company makes money |
| **Target Customers** | Who the ideal customers are |
| **Pricing Model** | How products/services are priced |
| **Competitive Edge** | What sets the company apart |
| **Key Metrics** | What metrics define success |
| **Cost Priorities** | Where money should be spent first |
| **Additional Context** | Any other business context |

### Templates

6 preset templates to start from:

| Template | Business Model |
|----------|---------------|
| `saas` | SaaS (Software as a Service) — recurring subscriptions |
| `ecommerce` | E-Commerce — online retail |
| `marketplace` | Marketplace / Platform — transaction fees |
| `agency` | Agency / Services — project and retainer fees |
| `consulting` | Consulting — advisory and engagement fees |
| `content` | Content / Media — ads, subscriptions, licensing |

```bash
agent-company-ai profit-engine templates  # list all templates
```

### Commands

| Command | Description |
|---------|-------------|
| `profit-engine setup` | Interactive wizard to configure business DNA |
| `profit-engine show` | Display current DNA |
| `profit-engine edit <field>` | Edit a single field |
| `profit-engine templates` | List available preset templates |
| `profit-engine disable` | Disable DNA injection (config preserved) |

### How it works

Once configured, the business DNA is automatically:

- **Appended to every agent's system prompt** — so developers, marketers, sales, and support all understand the business model
- **Injected into the CEO's planning and review tasks** — so autonomous mode goals are planned and evaluated through the lens of your business model

The DNA is stored in `config.yaml` under the `profit_engine` key. No new database tables — just config.

```yaml
# .agent-company-ai/default/config.yaml
profit_engine:
  enabled: true
  mission: "Build and scale a SaaS product..."
  revenue_streams: "Monthly/annual subscriptions..."
  target_customers: "SMB to enterprise..."
  pricing_model: "Tiered subscription pricing..."
  competitive_edge: "Product-led growth..."
  key_metrics: "MRR/ARR, churn rate, LTV:CAC..."
  cost_priorities: "Engineering first..."
  additional_context: ""
```

### Dashboard API

| Endpoint | Description |
|----------|-------------|
| `GET /api/profit-engine` | Return current ProfitEngine config |
| `POST /api/profit-engine` | Update fields and save to config |
| `GET /api/profit-engine/templates` | List all templates with content |

## Blockchain Wallet

Built-in Ethereum wallet with multi-chain support. Agents can request payments (with human approval), and you can send tokens directly from the CLI.

### Setup

```bash
agent-company-ai wallet create
```

Creates an encrypted keystore (password-protected). One address works across all supported chains.

### Supported Chains

| Chain | Native Token |
|-------|-------------|
| Ethereum | ETH |
| Base | ETH |
| Arbitrum | ETH |
| Polygon | MATIC |

### Commands

| Command | Description |
|---------|-------------|
| `wallet create` | Generate a new wallet with encrypted keystore |
| `wallet address` | Show the company wallet address |
| `wallet balance` | Show balances across all chains |
| `wallet balance --chain base` | Show balance on a specific chain |
| `wallet send <amount> --to <addr> --chain <chain>` | Send native tokens (requires password) |
| `wallet payments` | Show the payment approval queue |
| `wallet approve <id>` | Approve and send a pending payment |
| `wallet reject <id>` | Reject a pending payment |

### Agent Payments

Agents with wallet tools (`check_balance`, `get_wallet_address`, `list_payments`, `request_payment`) can request payments during task execution. All payment requests go into an approval queue — nothing is sent without your explicit approval.

```bash
# Check pending payments
agent-company-ai wallet payments --status pending

# Approve a payment
agent-company-ai wallet approve abc123

# Reject a payment
agent-company-ai wallet reject abc123
```

### Dashboard API

| Endpoint | Description |
|----------|-------------|
| `GET /api/wallet/balance` | Balances (optional `?chain=` filter) |
| `GET /api/wallet/address` | Wallet address |
| `GET /api/wallet/payments` | Payment queue (optional `?status=` filter) |

## Multi-Company Support

Run multiple independent companies in the same directory. Each company gets its own config, database, and agents:

```bash
# Default company
agent-company-ai init --name "Acme AI"
agent-company-ai hire ceo --name Alice

# Create a second company
agent-company-ai -C my-startup init --name "My Startup" --provider anthropic
agent-company-ai -C my-startup hire ceo --name Bob

# List all companies
agent-company-ai companies

# Destroy a company
agent-company-ai destroy --company my-startup
agent-company-ai destroy --yes  # destroy default, skip confirmation
```

**Directory layout:**
```
.agent-company-ai/
    default/
        config.yaml
        company.db
    my-startup/
        config.yaml
        company.db
```

Existing single-company setups are automatically migrated into `default/` on first access.

## Available Roles

| Role | Title | Reports To |
|------|-------|------------|
| `ceo` | Chief Executive Officer | Owner |
| `cto` | Chief Technology Officer | CEO |
| `developer` | Software Developer | CTO |
| `marketer` | Head of Marketing | CEO |
| `sales` | Head of Sales | CEO |
| `support` | Customer Support Lead | CEO |
| `finance` | CFO / Finance | CEO |
| `hr` | Head of HR | CEO |
| `project_manager` | Project Manager | CEO |

## LLM Providers

Supports 11 providers out of the box:

| Provider | Models | API Key Env Var |
|----------|--------|-----------------|
| **Anthropic** (default) | Claude Sonnet 4.5, etc. | `ANTHROPIC_API_KEY` |
| **OpenAI** | GPT-4o, etc. | `OPENAI_API_KEY` |
| **DeepSeek** | DeepSeek-R1 | `DEEPSEEK_API_KEY` |
| **MiMo** | MiMo-7B-RL | `DEEPSEEK_API_KEY` |
| **Kimi** | Kimi-K2 | `MOONSHOT_API_KEY` |
| **Qwen** | Qwen-Max | `DASHSCOPE_API_KEY` |
| **MiniMax** | MiniMax-M1 | `MINIMAX_API_KEY` |
| **Ollama** | Llama 3.1, etc. | None (local) |
| **Together** | Llama, Mixtral, etc. | `TOGETHER_API_KEY` |
| **Groq** | Fast open-source inference | `GROQ_API_KEY` |
| **OpenAI-compatible** | Any endpoint | Custom |

Configure different providers per agent:

```yaml
llm:
  default_provider: anthropic
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-5-20250929
  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o
    base_url: https://api.openai.com/v1  # or any compatible endpoint

agents:
  - name: Alice
    role: ceo
    provider: anthropic
  - name: Bob
    role: developer
    provider: openai
```

## Web Dashboard

```bash
agent-company-ai dashboard --port 8420
```

Features:
- **Org Chart** - Visual company hierarchy
- **Agent Roster** - See all agents and their roles
- **Task Board** - Kanban-style task management
- **Chat** - Talk directly to any agent
- **Activity Feed** - Real-time event stream via WebSocket
- **Autonomous Mode** - Set goals and monitor progress from the UI
- **Cost Tracker** - Real-time API cost breakdown by agent and model
- **ProfitEngine** - View and edit business DNA from the dashboard
- **Wallet** - Check balances and view payment queue

## Built-in Agent Tools

Agents have access to these tools based on their role:

| Tool | Description |
|------|-------------|
| **web_search** | Search the web via DuckDuckGo (no API key needed) |
| **read_file** / **write_file** | File operations in the workspace (sandboxed) |
| **code_exec** | Execute Python code (restricted builtins) |
| **shell** | Run shell commands (30s timeout, dangerous patterns blocked) |
| **delegate_task** | Delegate work to other agents |
| **report_result** | Submit task results |
| **check_balance** | Check wallet balance (wallet-enabled agents) |
| **get_wallet_address** | Get company wallet address (wallet-enabled agents) |
| **list_payments** | View payment queue (wallet-enabled agents) |
| **request_payment** | Request a payment — goes to approval queue (wallet-enabled agents) |

## Autonomous Mode

The company runs in CEO-driven cycles:

1. **Plan** - CEO breaks the goal into tasks and delegates to the team
2. **Execute** - Agents work on tasks in parallel waves
3. **Review** - CEO evaluates progress and decides: DONE, CONTINUE, or FAILED
4. **Loop** - Repeat until goal achieved or limits reached

When ProfitEngine is enabled, the CEO factors business DNA into every planning and review decision.

**Configurable limits** (in `config.yaml` or via CLI flags):
- `max_cycles: 5` — CEO review loops
- `max_waves_per_cycle: 10` — parallel execution waves per cycle
- `max_total_tasks: 50` — hard cap on tasks
- `max_time_seconds: 3600` — wall-clock timeout
- `max_cost_usd: 0.0` — spending cap (0 = unlimited)

## Custom Roles

Create custom roles by adding YAML files:

```yaml
# .agent-company-ai/roles/custom_analyst.yaml
name: analyst
title: "Data Analyst"
description: "Analyzes data and creates reports"
system_prompt: |
  You are a data analyst at {company_name}.
  Your expertise: data analysis, visualization, reporting.
  Team: {team_members}
  Delegates: {delegates}
default_tools:
  - code_exec
  - file_io
can_delegate_to: []
reports_to: cto
```

## Donate

If this project is useful to you, consider supporting development:

**ETH:** `0x0448F896Fc878DF56046Aa0090D05Dd01F28b338`

## Enterprise Customization & Consulting

**"We build AI agent workforce for your company"**

- **Implementation fee:** $10k-100k+
- **Ongoing support:** $2k-10k/month

Please contact gobeyondfj@gmail.com

## License

MIT
