# AgentCompany

**Spin up an AI agent company - a business run by AI agents, managed by you.**

AgentCompany lets a solo entrepreneur create a virtual company staffed entirely by AI agents. Each agent has a specific business role (CEO, CTO, Developer, Marketer, etc.), they collaborate on tasks, and you manage everything through a CLI or web dashboard.

## Quick Start

```bash
pip install agentcompany
```

### 1. Initialize your company

```bash
agentcompany init --name "My AI Startup"
```

### 2. Configure your LLM provider

Edit `.agentcompany/config.yaml`:

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
agentcompany hire ceo --name Alice
agentcompany hire cto --name Bob
agentcompany hire developer --name Carol
agentcompany hire marketer --name Dave
```

### 4. Run autonomously

Give the CEO a goal and watch the company run:

```bash
agentcompany run "Build a landing page for our new product"
```

The CEO will break down the goal, delegate tasks to the team, and agents will collaborate to deliver results.

## Commands

| Command | Description |
|---------|-------------|
| `agentcompany init` | Initialize a new company |
| `agentcompany hire <role>` | Hire an agent |
| `agentcompany fire <name>` | Remove an agent |
| `agentcompany team` | List all agents |
| `agentcompany assign "<task>"` | Assign a task |
| `agentcompany tasks` | Show the task board |
| `agentcompany chat <name>` | Chat with an agent |
| `agentcompany run "<goal>"` | Autonomous mode |
| `agentcompany broadcast "<msg>"` | Message all agents |
| `agentcompany dashboard` | Launch web dashboard |
| `agentcompany status` | Company overview |
| `agentcompany roles` | List available roles |

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
agentcompany dashboard --port 8420
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
# .agentcompany/roles/custom_analyst.yaml
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
