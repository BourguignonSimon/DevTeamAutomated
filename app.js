/**
 * Project Tracking Web Interface
 * Manages interaction with the AI orchestrator through unique project IDs
 */
(() => {
  // Application state
  const state = {
    projectId: null,
    questionPoll: null,
    statusPoll: null,
    messagePoll: null,
    projects: [],
  };

  // DOM Elements
  const elements = {
    // Project ID display
    projectIdSection: document.getElementById('project-id-section'),
    activeProjectId: document.getElementById('active-project-id'),

    // Init form
    initForm: document.getElementById('init-form'),
    initFeedback: document.getElementById('init-feedback'),

    // Prompt section
    promptSection: document.getElementById('prompt-section'),
    promptForm: document.getElementById('prompt-form'),
    promptFeedback: document.getElementById('prompt-feedback'),

    // Messages section
    messagesSection: document.getElementById('messages-section'),
    messagesContainer: document.getElementById('messages-container'),
    messagesError: document.getElementById('messages-error'),
    messagesRefreshBtn: document.getElementById('messages-refresh'),
    unreadOnlyCheckbox: document.getElementById('unread-only'),

    // Questions section
    questionsContainer: document.getElementById('questions-container'),
    questionsError: document.getElementById('questions-error'),

    // Status section
    projectStatusBlock: document.getElementById('project-status'),
    statusError: document.getElementById('status-error'),
    statusRefreshBtn: document.getElementById('status-refresh'),

    // History section
    historySection: document.getElementById('history-section'),
    interactionHistory: document.getElementById('interaction-history'),

    // Logs section
    logsRefreshBtn: document.getElementById('logs-refresh'),
    logsClearBtn: document.getElementById('logs-clear'),
    logsStatus: document.getElementById('logs-status'),
    logsError: document.getElementById('logs-error'),
    logFilter: document.getElementById('log-filter'),
    logBlock: document.getElementById('log'),
  };

  // Log state
  // Project selection elements
  const projectSelect = document.getElementById('project-select');
  const refreshProjectsBtn = document.getElementById('refresh-projects');
  const selectedProjectInfo = document.getElementById('selected-project-info');
  const projectSelectError = document.getElementById('project-select-error');
  const projectActions = document.getElementById('project-actions');
  const stopProjectBtn = document.getElementById('stop-project-btn');
  const orchestratorMessage = document.getElementById('orchestrator-message');
  const sendMessageBtn = document.getElementById('send-message-btn');
  const messageFeedback = document.getElementById('message-feedback');

  const logState = {
    entries: [],
    filterText: '',
  };

  // -------------------------
  // Utility Functions
  // -------------------------
  function normalizeLogEntry(entry, source = 'remote') {
    const normalized = { level: 'other', text: '', timestamp: '', source };
    if (entry && typeof entry === 'object') {
      normalized.text = entry.message || entry.msg || entry.text || entry.log || JSON.stringify(entry);
      const level = `${entry.level || entry.severity || entry.status || ''}`.toLowerCase();
      if (['error', 'err'].includes(level)) normalized.level = 'error';
      else if (['warn', 'warning'].includes(level)) normalized.level = 'warn';
      else if (['info', 'information'].includes(level)) normalized.level = 'info';
      normalized.timestamp = entry.timestamp || entry.time || entry.ts || entry.date || '';
    } else {
      normalized.text = `${entry ?? ''}`;
      const lowered = normalized.text.toLowerCase();
      if (lowered.includes('error')) normalized.level = 'error';
      else if (lowered.includes('warn')) normalized.level = 'warn';
      else if (lowered.includes('info')) normalized.level = 'info';
    }
    return normalized;
  }

  function log(message, level = 'info') {
    const entry = normalizeLogEntry({
      message,
      level,
      timestamp: new Date().toISOString(),
    }, 'ui');
    logState.entries = [entry, ...logState.entries];
    renderLogs();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${text}`);
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function showSection(element) {
    element.classList.remove('hidden');
  }

  function hideSection(element) {
    element.classList.add('hidden');
  }

  // -------------------------
  // Project Management
  // -------------------------
  function setActiveProject(projectId) {
    state.projectId = projectId;
    elements.activeProjectId.textContent = projectId;
    showSection(elements.projectIdSection);
    showSection(elements.promptSection);
    showSection(elements.messagesSection);
    showSection(elements.historySection);

    // Store in localStorage for persistence
    localStorage.setItem('activeProjectId', projectId);

    // Start polling
    startPollingQuestions();
    startStatusPolling();
    startMessagePolling();

    log(`Project activated: ${projectId}`);
  }

  function restoreActiveProject() {
    const savedProjectId = localStorage.getItem('activeProjectId');
    if (savedProjectId) {
      setActiveProject(savedProjectId);
      refreshProjectStatus();
      loadCustomerMessages();
      loadInteractionHistory();
    }
  }

  // -------------------------
  // Polling Functions
  // -------------------------
  function startPollingQuestions() {
    if (state.questionPoll) return;
    state.questionPoll = setInterval(loadOpenQuestions, 5000);
    loadOpenQuestions();
  }

  function startStatusPolling() {
    if (state.statusPoll) return;
    state.statusPoll = setInterval(() => {
      if (state.projectId) {
        refreshProjectStatus();
      }
    }, 5000);
  }

  function startMessagePolling() {
    if (state.messagePoll) return;
    state.messagePoll = setInterval(() => {
      if (state.projectId) {
        loadCustomerMessages();
      }
    }, 5000);
  }

  // -------------------------
  // Init Form Handler
  // -------------------------
  elements.initForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    elements.initFeedback.textContent = 'Creating project...';
    elements.statusError.textContent = '';

    const formData = new FormData(elements.initForm);

    try {
      const data = await fetchJson('/api/project/init', {
        method: 'POST',
        body: formData,
      });

      const projectId = data?.project_id || data?.projectId;
      if (projectId) {
        setActiveProject(projectId);
        elements.initFeedback.innerHTML = `<span class="success">Project created successfully!</span>`;
        elements.initForm.reset();
        refreshProjectStatus();
      } else {
        elements.initFeedback.textContent = `Project created but no ID returned.`;
      }
    } catch (error) {
      console.error(error);
      elements.initFeedback.innerHTML = `<span class="error">Failed to create project: ${error.message}</span>`;
    }
  });

  // -------------------------
  // Prompt Form Handler
  // -------------------------
  elements.promptForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.projectId) {
      elements.promptFeedback.innerHTML = '<span class="error">No active project. Create a project first.</span>';
      return;
    }

    const promptText = document.getElementById('prompt_text').value.trim();
    if (!promptText) {
      elements.promptFeedback.innerHTML = '<span class="error">Please enter a message.</span>';
      return;
    }

    elements.promptFeedback.textContent = 'Sending to orchestrator...';

    try {
      const data = await fetchJson(`/api/project/${state.projectId}/prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: state.projectId,
          prompt: promptText,
        }),
      });

      elements.promptFeedback.innerHTML = '<span class="success">Message sent to orchestrator!</span>';
      document.getElementById('prompt_text').value = '';
      log(`Prompt sent: ${promptText.substring(0, 50)}...`);

      // Refresh interaction history
      loadInteractionHistory();

      // Clear feedback after delay
      setTimeout(() => {
        elements.promptFeedback.textContent = '';
      }, 3000);
    } catch (error) {
      console.error(error);
      elements.promptFeedback.innerHTML = `<span class="error">Failed to send: ${error.message}</span>`;
    }
  });

  // -------------------------
  // Customer Messages
  // -------------------------
  async function loadCustomerMessages() {
    if (!state.projectId) return;

    elements.messagesError.textContent = '';
    const unreadOnly = elements.unreadOnlyCheckbox?.checked || false;

    try {
      const data = await fetchJson(`/api/project/${state.projectId}/messages?unread_only=${unreadOnly}`);
      const messages = data?.messages || [];
      renderMessages(messages);
    } catch (error) {
      console.error(error);
      elements.messagesError.textContent = 'Failed to load messages.';
    }
  }

  function renderMessages(messages) {
    elements.messagesContainer.innerHTML = '';

    if (!messages.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = 'No messages from the orchestrator yet.';
      elements.messagesContainer.appendChild(empty);
      return;
    }

    messages.forEach((msg) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'message';
      if (msg.status === 'UNREAD') wrapper.classList.add('unread');
      if (msg.requires_response) wrapper.classList.add('requires-response');

      // Message type badge
      const typeBadge = document.createElement('span');
      typeBadge.className = `message-type ${msg.message_type}`;
      typeBadge.textContent = msg.message_type?.replace('_', ' ') || 'message';
      wrapper.appendChild(typeBadge);

      // Timestamp
      if (msg.timestamp) {
        const time = document.createElement('span');
        time.className = 'muted';
        time.style.fontSize = '0.8rem';
        time.textContent = new Date(msg.timestamp).toLocaleString();
        wrapper.appendChild(time);
      }

      // Content
      const content = document.createElement('p');
      content.textContent = msg.content;
      content.style.marginTop = '8px';
      wrapper.appendChild(content);

      // Response form if required
      if (msg.requires_response && msg.status !== 'RESPONDED') {
        const responseForm = document.createElement('div');
        responseForm.style.marginTop = '10px';

        const input = document.createElement('textarea');
        input.placeholder = 'Type your response...';
        input.style.width = '100%';
        input.style.marginBottom = '8px';
        input.rows = 2;

        const btn = document.createElement('button');
        btn.textContent = 'Send Response';
        btn.addEventListener('click', () => respondToMessage(msg.id, input.value, btn, wrapper));

        responseForm.appendChild(input);
        responseForm.appendChild(btn);
        wrapper.appendChild(responseForm);
      }

      // Mark as read button
      if (msg.status === 'UNREAD') {
        const readBtn = document.createElement('button');
        readBtn.className = 'secondary';
        readBtn.textContent = 'Mark as Read';
        readBtn.style.marginTop = '8px';
        readBtn.style.marginLeft = '8px';
        readBtn.addEventListener('click', () => markMessageRead(msg.id, wrapper));
        wrapper.appendChild(readBtn);
      }

      elements.messagesContainer.appendChild(wrapper);
    });
  }

  async function respondToMessage(messageId, response, button, wrapper) {
    if (!response.trim()) {
      alert('Please enter a response.');
      return;
    }

    button.disabled = true;
    button.textContent = 'Sending...';

    try {
      await fetchJson(`/api/project/${state.projectId}/messages/${messageId}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId, response: response.trim() }),
      });

      wrapper.classList.remove('requires-response');
      const status = document.createElement('div');
      status.className = 'success';
      status.textContent = 'Response sent!';
      wrapper.appendChild(status);
      log(`Responded to message ${messageId}`);
      loadCustomerMessages();
    } catch (error) {
      console.error(error);
      button.disabled = false;
      button.textContent = 'Send Response';
      alert('Failed to send response: ' + error.message);
    }
  }

  async function markMessageRead(messageId, wrapper) {
    try {
      await fetchJson(`/api/project/${state.projectId}/messages/${messageId}/read`, {
        method: 'POST',
      });
      wrapper.classList.remove('unread');
      loadCustomerMessages();
    } catch (error) {
      console.error(error);
    }
  }

  // -------------------------
  // Questions
  // -------------------------
  async function loadOpenQuestions() {
    elements.questionsError.textContent = '';

    try {
      const params = state.projectId ? `?status=open&project_id=${state.projectId}` : '?status=open';
      const data = await fetchJson(`/api/questions${params}`);
      const questions = Array.isArray(data) ? data : data?.questions || [];
      renderQuestions(questions);
    } catch (error) {
      console.error(error);
      elements.questionsError.textContent = 'Failed to load questions.';
    }
  }

  function renderQuestions(questions) {
    elements.questionsContainer.innerHTML = '';

    if (!questions.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = 'No open questions right now.';
      elements.questionsContainer.appendChild(empty);
      return;
    }

    questions.forEach((q) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'question';
      wrapper.dataset.questionId = q.question_id || q.id;

      const title = document.createElement('div');
      title.innerHTML = `<strong>Question ID:</strong> <code>${q.question_id || q.id}</code>`;
      wrapper.appendChild(title);

      if (q.backlog_item_id) {
        const backlog = document.createElement('div');
        backlog.innerHTML = `<strong>Related task:</strong> <code>${q.backlog_item_id}</code>`;
        wrapper.appendChild(backlog);
      }

      const text = document.createElement('p');
      text.textContent = q.question_text || q.text || 'No question text provided.';
      text.style.fontWeight = 'bold';
      wrapper.appendChild(text);

      const expected = (q.expected_answer_type || q.answer_type || 'text').toLowerCase();
      const label = document.createElement('label');
      label.textContent = `Expected answer type: ${expected}`;
      label.className = 'muted';
      wrapper.appendChild(label);

      const input = buildAnswerInput(expected, q);
      wrapper.appendChild(input);

      const submitBtn = document.createElement('button');
      submitBtn.textContent = 'Submit Answer';
      submitBtn.addEventListener('click', () => submitAnswer(q, input, wrapper, submitBtn));
      wrapper.appendChild(submitBtn);

      elements.questionsContainer.appendChild(wrapper);
    });
  }

  function buildAnswerInput(expected, question) {
    const input = document.createElement(expected === 'number' ? 'input' : 'textarea');
    if (expected === 'number') {
      input.type = 'number';
    } else {
      input.rows = 2;
    }
    input.placeholder = 'Enter your answer';
    input.required = true;
    input.dataset.expectedType = expected;
    input.name = `answer-${question.question_id || question.id}`;
    input.style.width = '100%';
    input.style.marginBottom = '8px';
    return input;
  }

  async function submitAnswer(question, input, wrapper, button) {
    elements.questionsError.textContent = '';
    const answerValue = input.value.trim();

    if (!answerValue) {
      alert('Answer cannot be empty.');
      return;
    }

    button.disabled = true;
    input.disabled = true;

    try {
      await fetchJson('/api/questions/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question_id: question.question_id || question.id,
          answer: answerValue,
          project_id: state.projectId,
        }),
      });

      const status = document.createElement('div');
      status.className = 'success';
      status.textContent = 'Answer submitted successfully!';
      wrapper.appendChild(status);
      log(`Answered question ${question.question_id || question.id}`);

      // Refresh questions after a short delay
      setTimeout(loadOpenQuestions, 1000);
    } catch (error) {
      console.error(error);
      elements.questionsError.textContent = 'Failed to submit answer.';
      button.disabled = false;
      input.disabled = false;
    }
  }

  // -------------------------
  // Project Status
  // -------------------------
  async function refreshProjectStatus() {
    elements.statusError.textContent = '';

    if (!state.projectId) {
      elements.projectStatusBlock.textContent = 'No project tracked yet. Create a project to start.';
      return;
    }

    try {
      const data = await fetchJson(`/api/project/${state.projectId}/status`);

      elements.projectStatusBlock.innerHTML = `
        <div><strong>Project ID:</strong> <code>${state.projectId}</code></div>
        <div><strong>Name:</strong> ${data?.name || 'N/A'}</div>
        <div><strong>State:</strong> <span class="pill">${data?.state || 'unknown'}</span></div>
        <div><strong>Completion:</strong> ${data?.completion_percentage ?? 'N/A'}%</div>
        <div><strong>Total Tasks:</strong> ${data?.total_items ?? 'N/A'}</div>
        <div><strong>Completed:</strong> ${data?.completed_items ?? 'N/A'}</div>
        <div><strong>In Progress:</strong> ${data?.in_progress_items ?? 'N/A'}</div>
        <div><strong>Blocked:</strong> ${data?.blocked_items ?? 'N/A'}</div>
      `;
    } catch (error) {
      console.error(error);
      elements.statusError.textContent = 'Failed to load project status.';
    }
  }

  // -------------------------
  // Interaction History
  // -------------------------
  async function loadInteractionHistory() {
    if (!state.projectId) return;

    try {
      const data = await fetchJson(`/api/project/${state.projectId}/interactions?limit=20`);
      const interactions = data?.interactions || [];
      renderInteractionHistory(interactions);
    } catch (error) {
      console.error(error);
    }
  }

  function renderInteractionHistory(interactions) {
    elements.interactionHistory.innerHTML = '';

    if (!interactions.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = 'No interactions yet.';
      elements.interactionHistory.appendChild(empty);
      return;
    }

    // Show most recent first
    interactions.reverse().forEach((interaction) => {
      const item = document.createElement('div');
      item.className = 'interaction-item';

      const type = document.createElement('span');
      type.className = 'interaction-type';
      type.textContent = interaction.type?.replace('_', ' ') || 'interaction';
      item.appendChild(type);

      const time = document.createElement('span');
      time.className = 'muted';
      time.style.marginLeft = '8px';
      time.style.fontSize = '0.75rem';
      time.textContent = new Date(interaction.timestamp).toLocaleTimeString();
      item.appendChild(time);

      const content = document.createElement('div');
      content.textContent = interaction.content?.substring(0, 100) + (interaction.content?.length > 100 ? '...' : '');
      item.appendChild(content);

      elements.interactionHistory.appendChild(item);
    });
  }

  // -------------------------
  // Logs
  // -------------------------
  async function fetchLogs() {
    elements.logsError.textContent = '';
    elements.logsStatus.textContent = 'Loading logs...';

    try {
      const data = await fetchJson('/api/logs');
      const logs = Array.isArray(data) ? data : data?.logs || [];
      logState.entries = logs.map(e => normalizeLogEntry(e, 'remote'));
      renderLogs();
      elements.logsStatus.textContent = `Loaded ${logs.length} logs.`;
    } catch (error) {
      console.error(error);
      elements.logsError.textContent = 'Failed to load logs.';
      elements.logsStatus.textContent = 'No logs loaded.';
    }
  }

  function renderLogs() {
    elements.logBlock.innerHTML = '';

    const filtered = logState.filterText
      ? logState.entries.filter((entry) =>
          entry.text.toLowerCase().includes(logState.filterText) ||
          entry.level.toLowerCase().includes(logState.filterText)
        )
      : logState.entries;

    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = logState.entries.length ? 'No logs match filter.' : 'No logs available.';
      elements.logBlock.appendChild(empty);
      return;
    }

    filtered.slice(0, 100).forEach((entry) => {
      const row = document.createElement('div');
      row.className = 'log-row';

      const badge = document.createElement('span');
      badge.className = `badge ${entry.level}`;
      badge.textContent = entry.level.toUpperCase();
      row.appendChild(badge);

      if (entry.timestamp) {
        const meta = document.createElement('span');
        meta.className = 'log-meta';
        meta.textContent = entry.timestamp.substring(11, 19);
        row.appendChild(meta);
      }

      const text = document.createElement('span');
      text.textContent = entry.text;
      row.appendChild(text);

      elements.logBlock.appendChild(row);
    });
  }

  // -------------------------
  // Event Listeners
  // -------------------------
  elements.statusRefreshBtn.addEventListener('click', refreshProjectStatus);
  elements.messagesRefreshBtn?.addEventListener('click', loadCustomerMessages);
  elements.unreadOnlyCheckbox?.addEventListener('change', loadCustomerMessages);
  elements.logsRefreshBtn.addEventListener('click', fetchLogs);
  elements.logsClearBtn.addEventListener('click', () => {
    logState.entries = [];
    elements.logsStatus.textContent = 'Cleared log view.';
    renderLogs();
  });
  elements.logFilter.addEventListener('input', (event) => {
    logState.filterText = (event.target.value || '').toLowerCase();
    renderLogs();
  });

  // -------------------------
  // Initialize
  // -------------------------
  restoreActiveProject();
  // Initialize
  startPollingQuestions();
  loadProjects(); // Load projects on startup
})();
