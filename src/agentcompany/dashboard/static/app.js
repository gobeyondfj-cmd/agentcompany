// AgentCompany Dashboard - Frontend

let ws = null;
let currentChatAgent = null;
let chatMessages = {};

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    refreshAll();
    setInterval(refreshAll, 10000); // Refresh every 10s
});

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleEvent(msg.event, msg.data);
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 3000); // Reconnect
    };
}

function handleEvent(event, data) {
    // Add to activity feed
    addActivity(event, data);

    // Refresh relevant sections
    if (event.startsWith('agent.')) refreshAgents();
    if (event.startsWith('task.')) refreshTasks();
    if (event === 'chat.reply') handleChatReply(data);
    if (event.startsWith('goal.')) refreshStatus();
    if (event === 'cost.updated') updateCostDisplay(data);
}

// ------------------------------------------------------------------
// Tab switching
// ------------------------------------------------------------------

function switchTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

    document.querySelector(`.tab-content#tab-${name}`).classList.add('active');
    // Find the correct tab button by matching text
    document.querySelectorAll('.tab').forEach(t => {
        if (t.textContent.trim().toLowerCase().replace(' ', '') === name.toLowerCase()) {
            t.classList.add('active');
        }
    });

    // Load data for the tab
    if (name === 'orgchart') refreshOrgChart();
    if (name === 'tasks') refreshTasks();
    if (name === 'activity') refreshActivity();
}

// ------------------------------------------------------------------
// Data fetching
// ------------------------------------------------------------------

async function refreshAll() {
    await Promise.all([refreshStatus(), refreshAgents(), refreshTasks(), refreshCost()]);
}

async function refreshStatus() {
    const data = await fetch('/api/status').then(r => r.json());
    document.getElementById('company-name').textContent = data.name || 'AgentCompany';
    document.getElementById('stat-agents').textContent = data.agents || 0;
    document.getElementById('stat-running').textContent = data.running ? 'Yes' : 'No';
    const tasks = data.tasks || {};
    document.getElementById('stat-tasks-active').textContent =
        (tasks.in_progress || 0) + (tasks.assigned || 0) + (tasks.pending || 0);
    document.getElementById('stat-tasks-done').textContent = tasks.done || 0;
}

async function refreshCost() {
    const data = await fetch('/api/cost').then(r => r.json());
    updateCostDisplay(data);
}

function updateCostDisplay(data) {
    if (!data) return;
    const cost = data.total_cost_usd || 0;
    document.getElementById('cost-total').textContent = '$' + cost.toFixed(6);
    document.getElementById('cost-tokens').textContent = formatNumber(data.total_tokens || 0);
    document.getElementById('cost-calls').textContent = data.api_calls || 0;

    // Flash the cost bar briefly on update
    const bar = document.getElementById('cost-bar');
    bar.style.borderColor = 'var(--success)';
    setTimeout(() => { bar.style.borderColor = 'var(--border)'; }, 600);
}

function formatNumber(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
    return String(n);
}

async function refreshAgents() {
    const agents = await fetch('/api/agents').then(r => r.json());

    // Roster
    const roster = document.getElementById('agent-roster');
    roster.innerHTML = agents.map(a => `
        <div class="agent-card">
            <div class="agent-name">${esc(a.name)}</div>
            <div class="agent-role">${esc(a.role)}</div>
            <div class="agent-title">${esc(a.title)}</div>
        </div>
    `).join('') || '<p style="color:var(--text-dim)">No agents hired yet.</p>';

    // Chat sidebar
    const chatList = document.getElementById('chat-agent-list');
    chatList.innerHTML = agents.map(a => `
        <button class="chat-agent-btn ${currentChatAgent === a.name ? 'active' : ''}"
                onclick="selectChatAgent('${esc(a.name)}')">
            ${esc(a.name)} <small style="color:var(--text-dim)">${esc(a.role)}</small>
        </button>
    `).join('');
}

async function refreshTasks() {
    const tasks = await fetch('/api/tasks').then(r => r.json());

    const buckets = { pending: [], assigned: [], in_progress: [], review: [], done: [], failed: [] };
    tasks.forEach(t => {
        const bucket = buckets[t.status] || buckets.pending;
        bucket.push(t);
    });

    // Merge pending + assigned into pending column
    const pendingAll = [...buckets.pending, ...buckets.assigned];

    renderKanbanColumn('tasks-pending', pendingAll);
    renderKanbanColumn('tasks-in_progress', [...buckets.in_progress, ...buckets.review]);
    renderKanbanColumn('tasks-done', buckets.done);
    renderKanbanColumn('tasks-failed', buckets.failed);
}

function renderKanbanColumn(elementId, tasks) {
    const el = document.getElementById(elementId);
    el.innerHTML = tasks.map(t => `
        <div class="task-card">
            <div class="task-desc">${esc(t.description).substring(0, 80)}</div>
            <div class="task-meta">
                ${t.assignee ? `Assigned: ${esc(t.assignee)}` : 'Unassigned'}
                ${t.subtask_count ? ` | Subtasks: ${t.subtasks_done}/${t.subtask_count}` : ''}
            </div>
        </div>
    `).join('') || '<p style="color:var(--text-dim);font-size:12px;text-align:center">No tasks</p>';
}

async function refreshOrgChart() {
    const data = await fetch('/api/org-chart').then(r => r.json());
    const container = document.getElementById('org-chart');
    container.innerHTML = renderOrgNode(data, true);
}

function renderOrgNode(node, isRoot = false) {
    const cardClass = isRoot ? 'org-card owner' : 'org-card';
    let html = `<div class="org-node">
        <div class="${cardClass}">
            <div class="org-name">${esc(node.name)}</div>
            <div class="org-title">${esc(node.title || node.role || '')}</div>
        </div>`;

    if (node.children && node.children.length > 0) {
        html += '<div class="org-children">';
        node.children.forEach(child => {
            html += `<div class="org-connector">${renderOrgNode(child)}</div>`;
        });
        html += '</div>';
    }

    html += '</div>';
    return html;
}

async function refreshActivity() {
    const messages = await fetch('/api/messages').then(r => r.json());
    const feed = document.getElementById('activity-feed');
    feed.innerHTML = messages.reverse().map(m => `
        <div class="activity-item">
            <span class="activity-from">${esc(m.from || 'Owner')}</span>
            &rarr; ${esc(m.to || 'All')}:
            ${esc(m.content).substring(0, 200)}
            <div class="activity-time">${new Date(m.timestamp).toLocaleString()} | ${esc(m.topic)}</div>
        </div>
    `).join('') || '<p style="color:var(--text-dim);text-align:center">No activity yet.</p>';
}

// ------------------------------------------------------------------
// Chat
// ------------------------------------------------------------------

function selectChatAgent(name) {
    currentChatAgent = name;
    refreshAgents(); // Update active state

    const container = document.getElementById('chat-messages');
    const history = chatMessages[name] || [];

    if (history.length === 0) {
        container.innerHTML = `<p class="chat-placeholder">Start a conversation with ${esc(name)}.</p>`;
    } else {
        container.innerHTML = history.map(m => `
            <div class="chat-msg">
                <div class="msg-sender ${m.sender === 'You' ? 'user' : 'agent'}">${esc(m.sender)}</div>
                <div class="msg-text">${esc(m.text)}</div>
            </div>
        `).join('');
        container.scrollTop = container.scrollHeight;
    }
}

async function sendChat() {
    if (!currentChatAgent) return;
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    addChatMessage(currentChatAgent, 'You', message);

    const resp = await fetch(`/api/chat/${encodeURIComponent(currentChatAgent)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
    }).then(r => r.json());

    if (resp.reply) {
        addChatMessage(currentChatAgent, currentChatAgent, resp.reply);
    } else if (resp.error) {
        addChatMessage(currentChatAgent, 'System', `Error: ${resp.error}`);
    }
}

function addChatMessage(agent, sender, text) {
    if (!chatMessages[agent]) chatMessages[agent] = [];
    chatMessages[agent].push({ sender, text });

    if (currentChatAgent === agent) {
        const container = document.getElementById('chat-messages');
        container.innerHTML += `
            <div class="chat-msg">
                <div class="msg-sender ${sender === 'You' ? 'user' : 'agent'}">${esc(sender)}</div>
                <div class="msg-text">${esc(text)}</div>
            </div>
        `;
        container.scrollTop = container.scrollHeight;
    }
}

function handleChatReply(data) {
    addChatMessage(data.agent, data.agent, data.reply);
}

// ------------------------------------------------------------------
// Activity feed (real-time)
// ------------------------------------------------------------------

function addActivity(event, data) {
    const feed = document.getElementById('activity-feed');
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `
        <span class="activity-from">${esc(event)}</span>:
        ${esc(JSON.stringify(data)).substring(0, 200)}
        <div class="activity-time">${new Date().toLocaleString()}</div>
    `;
    feed.prepend(item);
}

// ------------------------------------------------------------------
// Modals
// ------------------------------------------------------------------

function showModal(html) {
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').classList.add('show');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('show');
}

function showGoalModal() {
    showModal(`
        <h2>Set Company Goal</h2>
        <label>Goal</label>
        <textarea id="goal-input" placeholder="e.g. Build and launch an MVP for a task management SaaS"></textarea>
        <div class="modal-actions">
            <button onclick="closeModal()" class="btn btn-secondary">Cancel</button>
            <button onclick="submitGoal()" class="btn btn-primary">Run</button>
        </div>
    `);
}

async function submitGoal() {
    const goal = document.getElementById('goal-input').value.trim();
    if (!goal) return;
    closeModal();
    await fetch('/api/goal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal }),
    });
    refreshAll();
}

function showHireModal() {
    showModal(`
        <h2>Hire Agent</h2>
        <label>Role</label>
        <select id="hire-role">
            <option value="ceo">CEO</option>
            <option value="cto">CTO</option>
            <option value="developer">Developer</option>
            <option value="marketer">Marketer</option>
            <option value="sales">Sales</option>
            <option value="support">Support</option>
            <option value="finance">Finance</option>
            <option value="hr">HR</option>
            <option value="project_manager">Project Manager</option>
        </select>
        <label>Name (optional)</label>
        <input id="hire-name" placeholder="Leave empty for default">
        <div class="modal-actions">
            <button onclick="closeModal()" class="btn btn-secondary">Cancel</button>
            <button onclick="submitHire()" class="btn btn-primary">Hire</button>
        </div>
    `);
}

async function submitHire() {
    const role = document.getElementById('hire-role').value;
    const name = document.getElementById('hire-name').value.trim() || undefined;
    closeModal();
    await fetch('/api/hire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, name }),
    });
    refreshAll();
}

function showTaskModal() {
    showModal(`
        <h2>New Task</h2>
        <label>Description</label>
        <textarea id="task-desc" placeholder="Describe the task..."></textarea>
        <label>Assign to (optional)</label>
        <input id="task-assignee" placeholder="Agent name">
        <div class="modal-actions">
            <button onclick="closeModal()" class="btn btn-secondary">Cancel</button>
            <button onclick="submitTask()" class="btn btn-primary">Create</button>
        </div>
    `);
}

async function submitTask() {
    const description = document.getElementById('task-desc').value.trim();
    const assignee = document.getElementById('task-assignee').value.trim() || undefined;
    if (!description) return;
    closeModal();
    await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description, assignee }),
    });
    refreshTasks();
}

// ------------------------------------------------------------------
// Util
// ------------------------------------------------------------------

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}
