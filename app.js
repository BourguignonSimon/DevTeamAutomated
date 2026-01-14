(() => {
  // ============================================================================
  // State Management
  // ============================================================================
  const state = {
    projectId: null,
    projects: [],
    questionPoll: null,
    statusPoll: null,
  };

  // ============================================================================
  // DOM Elements
  // ============================================================================
  const projectSelect = document.getElementById('project-select');
  const refreshProjectsBtn = document.getElementById('refresh-projects');
  const stopProjectBtn = document.getElementById('stop-project');
  const projectInfo = document.getElementById('project-info');
  const initForm = document.getElementById('init-form');
  const initFeedback = document.getElementById('init-feedback');
  const questionsContainer = document.getElementById('questions-container');
  const questionsError = document.getElementById('questions-error');
  const statusLoading = document.getElementById('status-loading');
  const statusContent = document.getElementById('status-content');
  const statusState = document.getElementById('status-state');
  const statusCompletion = document.getElementById('status-completion');
  const statusProgress = document.getElementById('status-progress');
  const statusTotal = document.getElementById('status-total');
  const statusBlocked = document.getElementById('status-blocked');
  const statusError = document.getElementById('status-error');
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

  // ============================================================================
  // Utility Functions
  // ============================================================================
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

  // ============================================================================
  // Project Management
  // ============================================================================
  async function loadProjects() {
    try {
      const projects = await fetchJson('/api/projects');
      state.projects = projects || [];
      renderProjectSelect();
    } catch (error) {
      console.error('Failed to load projects:', error);
      log('Failed to load projects: ' + error.message, 'error');
    }
  }

  function renderProjectSelect() {
    // Clear existing options except the first one
    while (projectSelect.options.length > 1) {
      projectSelect.remove(1);
    }

    // Add project options
    state.projects.forEach((project) => {
      const option = document.createElement('option');
      option.value = project.project_id;
      option.textContent = `${project.title || 'Untitled'} (${project.status || 'UNKNOWN'})`;
      if (project.project_id === state.projectId) {
        option.selected = true;
      }
      projectSelect.appendChild(option);
    });
  }

  function selectProject(projectId) {
    state.projectId = projectId;

    if (projectId) {
      const project = state.projects.find((p) => p.project_id === projectId);
      if (project) {
        projectInfo.innerHTML = `<strong>Project:</strong> ${project.title || 'Untitled'} | <strong>ID:</strong> <code>${projectId}</code>`;
      }
      stopProjectBtn.disabled = false;
      statusLoading.classList.add('hidden');
      statusContent.classList.remove('hidden');
      refreshProjectStatus();
      startStatusPolling();
    } else {
      projectInfo.textContent = 'No project selected. Create a new project or select an existing one.';
      stopProjectBtn.disabled = true;
      statusLoading.classList.remove('hidden');
      statusContent.classList.add('hidden');
      stopStatusPolling();
    }
  }

  async function stopProject() {
    if (!state.projectId) {
      alert('No project selected.');
      return;
    }

    if (!confirm('Are you sure you want to stop this project? This will cancel all pending work items.')) {
      return;
    }

    try {
      await fetchJson(`/api/project/${state.projectId}/stop`, {
        method: 'POST',
      });
      log(`Project ${state.projectId} stopped.`, 'warn');
      await loadProjects();
      refreshProjectStatus();
    } catch (error) {
      console.error('Failed to stop project:', error);
      alert('Failed to stop project: ' + error.message);
    }
  }

  // ============================================================================
  // Status Polling
  // ============================================================================
  function startStatusPolling() {
    if (state.statusPoll) return;
    state.statusPoll = setInterval(() => {
      if (state.projectId) {
        refreshProjectStatus();
      }
    }, 5000);
  }

  function stopStatusPolling() {
    if (state.statusPoll) {
      clearInterval(state.statusPoll);
      state.statusPoll = null;
    }
  }

  async function refreshProjectStatus() {
    if (!state.projectId) return;

    statusError.textContent = '';
    try {
      const data = await fetchJson(`/api/project/${state.projectId}/status`);

      statusState.textContent = data?.state || 'UNKNOWN';
      const completion = data?.completion_percentage ?? 0;
      statusCompletion.textContent = `${completion}%`;
      statusProgress.style.width = `${completion}%`;
      statusTotal.textContent = data?.total_items ?? 0;
      statusBlocked.textContent = data?.blocked_items ?? 0;

      // Update state color
      const stateColors = {
        'CREATED': '#3b82f6',
        'IN_PROGRESS': '#f59e0b',
        'BLOCKED': '#ef4444',
        'COMPLETED': '#22c55e',
        'STOPPED': '#6b7280',
      };
      statusState.style.color = stateColors[data?.state] || '#111';

    } catch (error) {
      console.error('Failed to load project status:', error);
      statusError.textContent = 'Failed to load status.';
    }
  }

  // ============================================================================
  // Questions
  // ============================================================================
  function startPollingQuestions() {
    if (state.questionPoll) return;
    state.questionPoll = setInterval(loadOpenQuestions, 5000);
    loadOpenQuestions();
  }

  async function loadOpenQuestions() {
    questionsError.textContent = '';
    try {
      let url = '/api/questions?status=open';
      if (state.projectId) {
        url += `&project_id=${state.projectId}`;
      }
      const data = await fetchJson(url);
      const questions = Array.isArray(data) ? data : data?.questions || [];
      renderQuestions(questions);
    } catch (error) {
      console.error('Failed to load questions:', error);
      questionsError.textContent = 'Failed to load questions.';
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
      title.innerHTML = `<strong>Question ID:</strong> <code>${q.question_id || q.id}</code>`;
      wrapper.appendChild(title);

      const backlog = document.createElement('div');
      backlog.innerHTML = `<strong>Related Item:</strong> ${q.backlog_item_id || 'N/A'}`;
      wrapper.appendChild(backlog);

      const text = document.createElement('p');
      text.style.margin = '12px 0';
      text.style.fontWeight = 'bold';
      text.textContent = q.question_text || q.text || 'No question text provided.';
      wrapper.appendChild(text);

      const expected = (q.expected_answer_type || q.answer_type || 'text').toLowerCase();
      const label = document.createElement('label');
      label.textContent = `Your answer (${expected}):`;
      label.style.marginTop = '8px';
      wrapper.appendChild(label);

      const input = buildAnswerInput(expected, q);
      wrapper.appendChild(input);

      const submitBtn = document.createElement('button');
      submitBtn.textContent = 'Submit Answer';
      submitBtn.style.marginTop = '8px';
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
    input.placeholder = 'Enter your answer...';
    input.required = true;
    input.dataset.expectedType = expected;
    input.name = `answer-${question.question_id || question.id}`;
    input.style.width = '100%';
    input.style.marginTop = '4px';
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
      status.className = 'success';
      status.style.marginTop = '8px';
      status.textContent = 'Answer submitted successfully!';
      wrapper.appendChild(status);
      log(`Answered question ${question.question_id || question.id}.`);
      setTimeout(loadOpenQuestions, 1000);
    } catch (error) {
      console.error('Failed to submit answer:', error);
      questionsError.textContent = 'Failed to submit answer.';
      button.disabled = false;
      input.disabled = false;
    }
  }

  // ============================================================================
  // Logs
  // ============================================================================
  async function fetchLogs() {
    logsError.textContent = '';
    logsStatus.textContent = 'Loading logs...';
    try {
      const data = await fetchJson('/api/logs');
      const logs = Array.isArray(data) ? data : data?.logs || [];
      logState.entries = logs.map((entry) => normalizeLogEntry(entry, entry.source || 'server'));
      renderLogs();
      logsStatus.textContent = `Loaded ${logs.length} logs.`;
    } catch (error) {
      console.error('Failed to fetch logs:', error);
      logsError.textContent = `Failed to load logs: ${error.message}`;
      logsStatus.textContent = 'No logs loaded.';
    }
  }

  function renderLogs() {
    logBlock.innerHTML = '';
    let filtered = logState.entries;

    // Apply text filter
    if (logState.filterText) {
      filtered = filtered.filter((entry) =>
        (entry.text || '').toLowerCase().includes(logState.filterText)
      );
    }

    // Apply level filter
    if (logState.filterLevel && logState.filterLevel !== 'all') {
      filtered = filtered.filter((entry) => entry.level === logState.filterLevel);
    }

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
        // Format timestamp to be shorter
        const ts = entry.timestamp.replace('T', ' ').replace('Z', '').substring(11, 19);
        meta.textContent = ts;
        row.appendChild(meta);
      }

      const text = document.createElement('span');
      text.textContent = entry.text;
      row.appendChild(text);

      logBlock.appendChild(row);
    });
  }

  // ============================================================================
  // Form Handlers
  // ============================================================================
  initForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    initFeedback.textContent = 'Creating project...';
    statusError.textContent = '';

    const formData = new FormData(initForm);

    try {
      const data = await fetchJson('/api/project/init', {
        method: 'POST',
        body: formData,
      });

      const projectId = data?.project_id || data?.projectId;
      state.projectId = projectId;

      initFeedback.innerHTML = `<span class="success">Project created!</span> ID: <code>${projectId || 'unknown'}</code>`;
      log(`Project "${formData.get('project_name')}" created and sent to orchestrator.`);

      // Reload projects and select the new one
      await loadProjects();
      projectSelect.value = projectId;
      selectProject(projectId);

      // Clear form
      initForm.reset();

    } catch (error) {
      console.error('Failed to create project:', error);
      initFeedback.innerHTML = `<span class="error">Failed to create project: ${error.message}</span>`;
    }
  });

  // ============================================================================
  // Event Listeners
  // ============================================================================
  projectSelect.addEventListener('change', (event) => {
    selectProject(event.target.value);
  });

  refreshProjectsBtn.addEventListener('click', loadProjects);
  stopProjectBtn.addEventListener('click', stopProject);
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

  // ============================================================================
  // Initialization
  // ============================================================================
  loadProjects();
  startPollingQuestions();
  fetchLogs();
})();
