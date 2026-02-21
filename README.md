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

### 2. Configure your LLM provider

Edit `.agent-company-ai/config.yaml`:

```yaml
company:
  name: "My AI Startup"
llm:
  default_provider: anthropic
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-5-20250929
  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o
```

### 3. Hire your team

```bash
agent-company-ai hire ceo --name Alice
agent-company-ai hire cto --name Bob
agent-company-ai hire developer --name Carol
agent-company-ai hire marketer --name Dave
```

### 4. Run autonomously

Give the CEO a goal and watch the company run:

```bash
agent-company-ai run "Build a landing page for our new product"
```

The CEO will break down the goal, delegate tasks to the team, and agents will collaborate to deliver results.

## Commands

| Command | Description |
|---------|-------------|
| `agent-company-ai init` | Initialize a new company |
| `agent-company-ai hire <role>` | Hire an agent |
| `agent-company-ai fire <name>` | Remove an agent |
| `agent-company-ai team` | List all agents |
| `agent-company-ai assign "<task>"` | Assign a task |
| `agent-company-ai tasks` | Show the task board |
| `agent-company-ai chat <name>` | Chat with an agent |
| `agent-company-ai run "<goal>"` | Autonomous mode |
| `agent-company-ai broadcast "<msg>"` | Message all agents |
| `agent-company-ai dashboard` | Launch web dashboard |
| `agent-company-ai status` | Company overview |
| `agent-company-ai roles` | List available roles |

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

## Web Dashboard

Launch the dashboard:

```bash
agent-company-ai dashboard --port 8420
```

Features:
- **Org Chart** - Visual company hierarchy
- **Agent Roster** - See all agents and their roles
- **Task Board** - Kanban-style task management
- **Chat** - Talk directly to any agent
- **Activity Feed** - Real-time event stream
- **Autonomous Mode** - Set goals from the UI

## Multi-Provider LLM Support

Configure different LLM providers per agent:

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

## Built-in Tools

Agents have access to these tools based on their role:

- **web_search** - Search the web for information
- **read_file / write_file / list_files** - File operations in the workspace
- **code_exec** - Execute Python code
- **shell** - Run shell commands
- **delegate_task** - Delegate work to other agents
- **report_result** - Submit task results

## License

MIT
