(() => {
  const state = {
    projectId: null,
    questionPoll: null,
    statusPoll: null,
  };

  const initForm = document.getElementById('init-form');
  const initFeedback = document.getElementById('init-feedback');
  const questionsContainer = document.getElementById('questions-container');
  const questionsError = document.getElementById('questions-error');
  const projectStatusBlock = document.getElementById('project-status');
  const statusError = document.getElementById('status-error');
  const statusRefreshBtn = document.getElementById('status-refresh');
  const logsRefreshBtn = document.getElementById('logs-refresh');
  const logsClearBtn = document.getElementById('logs-clear');
  const logsStatus = document.getElementById('logs-status');
  const logsError = document.getElementById('logs-error');
  const logFilter = document.getElementById('log-filter');
  const logLevelSelect = document.getElementById('log-level');
  const logBlock = document.getElementById('log');

  const logState = {
    entries: [],
    filterText: '',
    filterLevel: 'all',
  };

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
  };

  const logBlock = document.getElementById('log');

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${text}`);
    }
    if (response.status === 204) return null;
    return response.json();
  }

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

  async function fetchLogs() {
    logsError.textContent = '';
    logsStatus.textContent = 'Loading logs...';
    try {
      const data = await fetchJson('/api/logs');
      const logs = Array.isArray(data) ? data : data?.logs || [];
      logState.entries = logs;
      renderLogs();
      logsStatus.textContent = `Loaded ${logs.length} logs.`;
      log('Fetched logs.');
    } catch (error) {
      console.error(error);
      logsError.textContent = `Failed to load logs (${error.message}). Ensure the backend exposes /api/logs on this origin.`;
      logsError.textContent = 'Failed to load logs. Backend owns log storage and filtering.';
      logsStatus.textContent = 'No logs loaded.';
    }
  }

  function renderLogs() {
    logBlock.innerHTML = '';
    const filtered = logState.filterText
      ? logState.entries.filter((line) => `${line}`.toLowerCase().includes(logState.filterText))
      : logState.entries;

    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = logState.entries.length
        ? 'No logs match filter.'
        : 'No logs available yet.';
      logBlock.appendChild(empty);
      return;
    }

    filtered.forEach((entry) => {
      const row = document.createElement('div');
      row.className = 'log-row';

      const badge = document.createElement('span');
      badge.className = `badge ${entry.level}`;
      badge.textContent = entry.level.toUpperCase();
      row.appendChild(badge);

      if (entry.timestamp) {
        const meta = document.createElement('span');
        meta.className = 'log-meta';
        meta.textContent = entry.timestamp;
        row.appendChild(meta);
      }

      const text = document.createElement('span');
      text.textContent = entry.text;
      row.appendChild(text);

      if (entry.source) {
        const source = document.createElement('span');
        source.className = 'muted';
        source.style.marginLeft = '8px';
        source.textContent = `(${entry.source})`;
        row.appendChild(source);
      }

      logBlock.appendChild(row);
    });
  }

  initForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    initFeedback.textContent = '';
    statusError.textContent = '';
    const formData = new FormData(initForm);
    try {
      const data = await fetchJson('/api/project/init', {
        method: 'POST',
        body: formData,
      });
      const projectId = data?.project_id || data?.projectId;
      state.projectId = projectId;
      initFeedback.textContent = `project_id: ${projectId || 'unknown'} | status: ${data?.status || 'CREATED'}`;
      log('Initial audit request submitted.');
      if (projectId) {
        refreshProjectStatus();
        startStatusPolling();
      }
    } catch (error) {
      initFeedback.textContent = '';
      statusError.textContent = '';
      questionsError.textContent = '';
      console.error(error);
      alert('Initial request failed. Check console for details.');
    }
  });

  async function loadOpenQuestions() {
    questionsError.textContent = '';
    try {
      const data = await fetchJson('/api/questions?status=open');
      const questions = Array.isArray(data) ? data : data?.questions || [];
      renderQuestions(questions);
      log('Fetched open questions.');
    } catch (error) {
      console.error(error);
      questionsError.textContent = 'Failed to load open questions. Backend is authoritative.';
    }
  }

  function renderQuestions(questions) {
    questionsContainer.innerHTML = '';
    if (!questions.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = 'No open questions right now.';
      questionsContainer.appendChild(empty);
      return;
    }

    questions.forEach((q) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'question';
      wrapper.dataset.questionId = q.question_id || q.id;

      const title = document.createElement('div');
      title.innerHTML = `<strong>question_id:</strong> ${q.question_id || q.id}`;
      wrapper.appendChild(title);

      const backlog = document.createElement('div');
      backlog.innerHTML = `<strong>related backlog_item_id:</strong> ${q.backlog_item_id || 'unknown'}`;
      wrapper.appendChild(backlog);

      const text = document.createElement('p');
      text.textContent = q.question_text || q.text || 'No question text provided.';
      wrapper.appendChild(text);

      const expected = (q.expected_answer_type || q.answer_type || 'text').toLowerCase();
      const label = document.createElement('label');
      label.textContent = `Expected answer type: ${expected}`;
      wrapper.appendChild(label);

      const input = buildAnswerInput(expected, q);
      wrapper.appendChild(input);

      const submitBtn = document.createElement('button');
      submitBtn.textContent = 'Submit answer';
      submitBtn.addEventListener('click', () => submitAnswer(q, input, wrapper, submitBtn));
      wrapper.appendChild(submitBtn);

      questionsContainer.appendChild(wrapper);
    });
  }

  function buildAnswerInput(expected, question) {
    const input = document.createElement(expected === 'number' ? 'input' : 'textarea');
    if (expected === 'number') {
      input.type = 'number';
    } else {
      input.rows = 2;
    }
    input.placeholder = expected === 'choice' ? 'Provide the chosen value from backend options' : 'Enter answer';
    input.required = true;
    input.dataset.expectedType = expected;
    input.name = `answer-${question.question_id || question.id}`;
    input.style.width = '100%';
    return input;
  }

  async function submitAnswer(question, input, wrapper, button) {
    questionsError.textContent = '';
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
        }),
      });
      const status = document.createElement('div');
      status.className = 'status-block';
      status.textContent = 'Status: ANSWERED (awaiting backend confirmation)';
      wrapper.appendChild(status);
      log(`Answered question ${question.question_id || question.id}.`);
      loadOpenQuestions();
    } catch (error) {
      console.error(error);
      questionsError.textContent = 'Failed to submit answer. Backend controls question lifecycle.';
      button.disabled = false;
      input.disabled = false;
    }
  }

  async function refreshProjectStatus() {
    statusError.textContent = '';
    if (!state.projectId) {
      statusError.textContent = 'No project_id available. Submit an audit request first.';
      return;
    }
    try {
      const data = await fetchJson(`/api/project/${state.projectId}/status`);
      projectStatusBlock.innerHTML = `
        <div><strong>project_id:</strong> ${state.projectId}</div>
        <div><strong>Current state:</strong> ${data?.state || 'unknown'}</div>
        <div><strong>% completion:</strong> ${data?.completion_percentage ?? 'n/a'}</div>
        <div><strong>Blocked items:</strong> ${data?.blocked_items ?? 'n/a'}</div>
      `;
      log('Project status refreshed.');
    } catch (error) {
      console.error(error);
      statusError.textContent = 'Failed to load project status. Backend is the authority.';
    }
  }

  statusRefreshBtn.addEventListener('click', refreshProjectStatus);
  logsRefreshBtn.addEventListener('click', fetchLogs);
  logFilter.addEventListener('input', (event) => {
    logState.filterText = (event.target.value || '').toLowerCase();
    renderLogs();
  });
  logLevelSelect.addEventListener('change', (event) => {
    logState.filterLevel = event.target.value;
    renderLogs();
  });
  logsClearBtn.addEventListener('click', () => {
    logState.entries = [];
    logsStatus.textContent = 'Cleared log view.';
    renderLogs();
  });

  startPollingQuestions();
})();
