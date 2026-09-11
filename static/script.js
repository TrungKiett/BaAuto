/* ============================================================
   Web Automator Studio – JavaScript
   Script Builder (existing) + AI Agent (new)
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

    // ── Desktop app update ────────────────────────────────────────────
    // Chỉ hiện trên file .exe. Khi có bản mới, người dùng có thể tải và
    // thay thế app ngay từ cửa sổ hiện tại.
    const updateBanner       = document.getElementById('update-banner');
    const updateVersionText  = document.getElementById('update-version-text');
    const updateNotesPreview = document.getElementById('update-notes-preview');
    const updateNowBtn       = document.getElementById('update-now-btn');
    const updateLaterBtn     = document.getElementById('update-later-btn');
    const updateProgressWrap = document.getElementById('update-progress-bar-wrap');
    const updateProgressFill = document.getElementById('update-progress-fill');
    const updateProgressLabel = document.getElementById('update-progress-label');
    let updateDownloadUrl = '';

    function hideUpdateBanner() {
        updateBanner.classList.add('hidden');
    }

    function showUpdateProgress(item) {
        updateProgressWrap.classList.remove('hidden');
        if (typeof item.progress === 'number') {
            updateProgressFill.style.width = `${Math.max(0, Math.min(100, item.progress))}%`;
        }
        if (item.message) updateProgressLabel.textContent = item.message;
    }

    async function applyDesktopUpdate() {
        if (!updateDownloadUrl) return;

        updateNowBtn.disabled = true;
        updateLaterBtn.disabled = true;
        showUpdateProgress({ progress: 0, message: 'Đang chuẩn bị cập nhật...' });

        try {
            const response = await fetch('/api/apply-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_url: updateDownloadUrl })
            });
            if (!response.ok || !response.body) {
                throw new Error('Không thể bắt đầu cập nhật.');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split('\n\n');
                buffer = events.pop();
                for (const event of events) {
                    const payload = event.split('\n').find(line => line.startsWith('data: '));
                    if (!payload) continue;
                    const item = JSON.parse(payload.slice(6));
                    if (item.status !== 'waiting') showUpdateProgress(item);
                    if (item.status === 'error') {
                        updateNowBtn.disabled = false;
                        updateLaterBtn.disabled = false;
                    }
                }
            }
        } catch (error) {
            showUpdateProgress({ message: `Cập nhật chưa thành công: ${error.message}` });
            updateNowBtn.disabled = false;
            updateLaterBtn.disabled = false;
        }
    }

    async function checkDesktopUpdate() {
        try {
            const response = await fetch('/api/check-update');
            const update = await response.json();
            if (!update.has_update || !update.download_url) return;

            updateDownloadUrl = update.download_url;
            updateVersionText.textContent = `Có bản cập nhật v${update.latest_version}`;
            const notes = (update.release_notes || '')
                .replace(/[#*_`]/g, '')
                .replace(/\s+/g, ' ')
                .trim();
            updateNotesPreview.textContent = notes.slice(0, 150) || 'Cập nhật mới đã sẵn sàng.';
            updateBanner.classList.remove('hidden');
        } catch (_) {
            // Không làm gián đoạn công việc khi không có Internet hoặc GitHub tạm lỗi.
        }
    }

    updateNowBtn.addEventListener('click', applyDesktopUpdate);
    updateLaterBtn.addEventListener('click', hideUpdateBanner);
    checkDesktopUpdate();

    // ── Google account ────────────────────────────────────────────────
    const accountStatus = document.getElementById('account-status');
    const googleLoginBtn = document.getElementById('google-login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    let loginPoll = null;

    function showAccount(auth) {
        const signedIn = Boolean(auth.authenticated);
        const name = auth.user?.name || auth.user?.email || 'Tài khoản Google';
        accountStatus.textContent = signedIn ? `☁ ${name}` : (auth.login_in_progress ? 'Đang chờ đăng nhập Google…' : 'Chưa đăng nhập');
        googleLoginBtn.classList.toggle('hidden', signedIn);
        logoutBtn.classList.toggle('hidden', !signedIn);
        googleLoginBtn.disabled = Boolean(auth.login_in_progress);
        if (auth.error) accountStatus.textContent = `⚠ ${auth.error}`;
    }

    async function refreshAuth() {
        try {
            const response = await fetch('/api/auth/status');
            const auth = await response.json();
            showAccount(auth);
            if (auth.authenticated || auth.error || !auth.login_in_progress) {
                clearInterval(loginPoll);
                loginPoll = null;
                if (auth.authenticated) loadSavedScripts();
            }
        } catch (_) {
            accountStatus.textContent = 'Không kiểm tra được tài khoản';
        }
    }

    googleLoginBtn.addEventListener('click', async () => {
        googleLoginBtn.disabled = true;
        accountStatus.textContent = 'Đang mở Google để đăng nhập…';
        try {
            const response = await fetch('/api/auth/google/start', { method: 'POST' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Không thể bắt đầu đăng nhập.');
            clearInterval(loginPoll);
            loginPoll = setInterval(refreshAuth, 1000);
            refreshAuth();
        } catch (error) {
            accountStatus.textContent = `⚠ ${error.message}`;
            googleLoginBtn.disabled = false;
        }
    });

    logoutBtn.addEventListener('click', async () => {
        await fetch('/api/auth/logout', { method: 'POST' });
        refreshAuth();
        loadSavedScripts();
    });
    refreshAuth();

    // ── Tab Switching ──────────────────────────────────────────────────
    const tabScript  = document.getElementById('tab-script');
    const tabAi      = document.getElementById('tab-ai');
    const panelScript = document.getElementById('panel-script');
    const panelAi    = document.getElementById('panel-ai');
    const scriptTabActions = document.getElementById('script-tab-actions');
    const aiTabActions     = document.getElementById('ai-tab-actions');

    function switchTab(tab) {
        const isAi = tab === 'ai';
        tabScript.classList.toggle('active', !isAi);
        tabAi.classList.toggle('active', isAi);
        tabScript.setAttribute('aria-selected', String(!isAi));
        tabAi.setAttribute('aria-selected', String(isAi));
        panelScript.classList.toggle('hidden', isAi);
        panelAi.classList.toggle('hidden', !isAi);
        scriptTabActions.classList.toggle('hidden', isAi);
        aiTabActions.classList.toggle('hidden', !isAi);
    }

    tabScript.addEventListener('click', () => switchTab('script'));
    tabAi.addEventListener('click', () => switchTab('ai'));

    // ================================================================
    //  SECTION 1: Script Builder (original logic, preserved)
    // ================================================================

    const stepsContainer   = document.getElementById('steps-container');
    const addStepBtns      = document.querySelectorAll('.add-step-btn');
    const runBtn           = document.getElementById('run-btn');
    const saveBtn          = document.getElementById('save-btn');
    const newBtn           = document.getElementById('new-btn');
    const scriptNameInput  = document.getElementById('script-name');
    const savedScriptsList = document.getElementById('saved-scripts-list');
    const stepCountSpan    = document.querySelector('.step-count');
    const resultsPanel     = document.getElementById('results-panel');
    const closeResultsBtn  = document.getElementById('close-results');
    const resultsContent   = document.getElementById('results-content');

    let stepCount = 0;

    const actionMap = {
        'navigate':       { icon: 'bx-globe',        title: 'Truy cập Trang',                  inputs: [{ name: 'value',    label: 'URL',                             type: 'url',    placeholder: 'vd: https://example.com' }] },
        'click_element':  { icon: 'bx-pointer',       title: 'Click Element',                   inputs: [{ name: 'selector', label: 'CSS Selector',                     type: 'text',   placeholder: 'Dán CSS Selector vào đây (vd: #btn)' }] },
        'fill_input':     { icon: 'bx-edit-alt',      title: 'Nhập Văn Bản',                    inputs: [{ name: 'selector', label: 'CSS Selector',                     type: 'text',   placeholder: 'Dán Selector ô nhập liệu' }, { name: 'value', label: 'Nội dung nhập', type: 'text', placeholder: 'Chữ bạn muốn nhập' }] },
        'fill_with_retry':{ icon: 'bx-check-shield',  title: 'Nhập Có Kiểm Tra (Tránh trùng)', inputs: [
            { name: 'selector',        label: 'CSS Selector (Ô nhập chữ)',       type: 'text',   placeholder: 'vd: #username' },
            { name: 'value',           label: 'Nội dung nhập ban đầu',           type: 'text',   placeholder: 'vd: admin' },
            { name: 'error_selector',  label: 'Selector Dòng chữ báo lỗi',       type: 'text',   placeholder: 'vd: .error-message' },
            { name: 'append_char',     label: 'Ký tự thêm vào nếu bị trùng',    type: 'text',   placeholder: 'vd: 1' },
            { name: 'submit_selector', label: 'Selector Nút xác nhận (Tùy chọn)', type: 'text', placeholder: 'Để trống nếu tự kiểm tra', required: false }
        ]},
        'get_text':       { icon: 'bx-text',           title: 'Đọc Văn Bản',                    inputs: [{ name: 'selector', label: 'CSS Selector', type: 'text', placeholder: 'Dán Selector của đoạn text cần đọc' }] },
        'drag_and_drop':  { icon: 'bx-move',           title: 'Kéo Thả',                        inputs: [
            { name: 'selector',     label: 'CSS Selector nguồn (phần tử kéo)', type: 'text',   placeholder: 'Selector của các field trên thanh thêm' },
            { name: 'source_text',  label: 'Tên field nguồn (ưu tiên)',          type: 'text',   placeholder: 'vd: Single hoặc Number', required: false },
            { name: 'target',       label: 'CSS Selector đích (chỗ thả)',       type: 'text',   placeholder: 'Selector của khu vực thả' },
            { name: 'target_text',  label: 'Nội dung field đích (nếu cần)',      type: 'text',   placeholder: 'Để trống nếu chỉ có một khu vực thả', required: false },
            { name: 'source_index', label: 'Số thứ tự nguồn (chỉ khi trùng tên)', type: 'number', placeholder: 'Tùy chọn', min: 1, step: 1, required: false },
            { name: 'target_index', label: 'Số thứ tự đích (chỉ khi trùng tên)',  type: 'number', placeholder: 'Tùy chọn', min: 1, step: 1, required: false }
        ], help: 'Ưu tiên nhập tên field hiển thị như Single, Number hoặc Lookup — ứng dụng sẽ tự tìm đúng field. Chỉ dùng số thứ tự khi nhiều field có cả selector lẫn tên giống hệt nhau.' },
        'create_field':   { icon: 'bx-layer-plus',     title: 'Thêm Field (Kéo + Nhập + Lưu)',  inputs: [
            { name: 'source_selector',     label: 'CSS Selector field trên thanh thêm', type: 'text', placeholder: 'Selector của các ô Single, Number…' },
            { name: 'source_text',          label: 'Tên/loại field cần thêm',             type: 'text', placeholder: 'vd: Single' },
            { name: 'target',               label: 'CSS Selector khu vực thả',            type: 'text', placeholder: 'Selector của vùng thiết kế form' },
            { name: 'field_input_selector', label: 'CSS ô nhập tên field vừa tạo',         type: 'text', placeholder: 'Selector chung của các ô tên field' },
            { name: 'value',                label: 'Tên field muốn nhập',                 type: 'text', placeholder: 'vd: ThanhToan' },
            { name: 'save_selector',        label: 'CSS nút Lưu',                          type: 'text', placeholder: 'Selector nút Lưu' }
        ], help: 'Một bước hoàn chỉnh cho từng field: kéo đúng loại theo tên, chờ ô tên mới xuất hiện, nhập nội dung rồi bấm Lưu. Không cần biết số thứ tự của field.' },
        'wait':           { icon: 'bx-time',           title: 'Dừng Chờ',                       inputs: [{ name: 'value',    label: 'Thời gian chờ (giây)', type: 'number', placeholder: 'vd: 3' }] }
    };

    function updateStepCount() {
        const steps = document.querySelectorAll('.step-card').length;
        stepCount = steps;
        stepCountSpan.textContent = `${steps} bước`;
        const emptyState = document.querySelector('.empty-state');
        if (emptyState) emptyState.style.display = steps > 0 ? 'none' : 'flex';
    }

    function createStepCard(actionType) {
        const actionDef = actionMap[actionType];
        const card = document.createElement('div');
        card.className = 'step-card';
        card.dataset.action = actionType;

        let inputsHtml = '';
        const inputClass = actionDef.inputs.length === 1 ? 'single-input' : '';
        actionDef.inputs.forEach(input => {
            const value = input.value !== undefined ? ` value="${input.value}"` : '';
            const min   = input.min !== undefined ? ` min="${input.min}"` : '';
            const step  = input.step !== undefined ? ` step="${input.step}"` : '';
            inputsHtml += `
                <div class="form-group">
                    <label>${input.label}</label>
                    <input type="${input.type}" name="${input.name}" placeholder="${input.placeholder || ''}"${value}${min}${step} ${input.required === false ? '' : 'required'}>
                </div>`;
        });

        card.innerHTML = `
            <div class="step-header">
                <div class="step-title"><i class='bx ${actionDef.icon}'></i> ${actionDef.title}</div>
                <div class="step-actions">
                    <button type="button" class="btn-icon move-up" title="Di chuyển lên"><i class='bx bx-up-arrow-alt'></i></button>
                    <button type="button" class="btn-icon move-down" title="Di chuyển xuống"><i class='bx bx-down-arrow-alt'></i></button>
                    <button type="button" class="btn-icon delete-step" title="Xóa bước"><i class='bx bx-trash'></i></button>
                </div>
            </div>
            <div class="step-inputs ${inputClass}">${inputsHtml}</div>
            ${actionDef.help ? `<p class="step-help"><i class='bx bx-info-circle'></i> ${actionDef.help}</p>` : ''}`;

        card.querySelector('.move-up').addEventListener('click', () => {
            const prev = card.previousElementSibling;
            if (prev && prev.classList.contains('step-card')) card.parentNode.insertBefore(card, prev);
        });
        card.querySelector('.move-down').addEventListener('click', () => {
            const next = card.nextElementSibling;
            if (next && next.classList.contains('step-card')) card.parentNode.insertBefore(next, card);
        });
        card.querySelector('.delete-step').addEventListener('click', () => { card.remove(); updateStepCount(); });
        return card;
    }

    addStepBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const card = createStepCard(btn.dataset.action);
            stepsContainer.appendChild(card);
            updateStepCount();
        });
    });

    closeResultsBtn.addEventListener('click', () => resultsPanel.classList.add('hidden'));

    runBtn.addEventListener('click', async () => {
        if (stepCount === 0) { alert('Vui lòng thêm ít nhất một bước!'); return; }
        let isValid = true;
        document.querySelectorAll('.step-card input[required]').forEach(input => {
            if (!input.value.trim()) isValid = false;
        });
        if (!isValid) { alert('Vui lòng điền đầy đủ thông tin cho tất cả các bước!'); return; }

        const steps  = getStepsData();
        const config = getConfigData();
        const orig   = runBtn.innerHTML;
        runBtn.innerHTML = "<i class='bx bx-loader-alt bx-spin'></i> Đang chạy...";
        runBtn.disabled  = true;
        resultsContent.innerHTML = 'Đang khởi chạy trình duyệt...<br>';
        resultsPanel.classList.remove('hidden');

        try {
            const res  = await fetch('/run-script', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({config, steps}) });
            const data = await res.json();
            resultsContent.innerHTML = '';
            if (data.status === 'error') {
                resultsContent.innerHTML = `<div class="log-item log-error">Lỗi Hệ thống: ${data.message}</div>`;
            } else {
                data.results.forEach((r, i) => {
                    const cls = r.status === 'success' ? 'log-success' : 'log-error';
                    resultsContent.innerHTML += `<div class="log-item ${cls}"><strong>Bước ${i+1}:</strong> ${r.message}</div>`;
                });
            }
        } catch(e) {
            resultsContent.innerHTML = `<div class="log-item log-error">Lỗi kết nối: ${e.message}</div>`;
        } finally {
            runBtn.innerHTML = orig;
            runBtn.disabled  = false;
        }
    });

    async function loadSavedScripts() {
        try {
            const res = await fetch('/api/scripts');
            const scripts = await res.json();
            if (!res.ok || !Array.isArray(scripts)) {
                const message = scripts.error || 'Không thể tải kịch bản.';
                savedScriptsList.innerHTML = `<div style="font-size:0.78rem;color:#ff8096;padding:0.4rem;">${escHtml(message)}</div>`;
                return;
            }
            savedScriptsList.innerHTML = '';
            if (scripts.length === 0) {
                savedScriptsList.innerHTML = '<div style="font-size:0.78rem;color:#6b84a8;padding:0.4rem;">Chưa có kịch bản nào.</div>';
                return;
            }
            scripts.forEach(name => {
                const div = document.createElement('div');
                div.className = 'saved-script-item';
                div.innerHTML = `
                    <div class="saved-script-name"><i class='bx bx-file'></i><span>${name}</span></div>
                    <button class="btn-icon delete-saved" data-name="${name}" title="Xóa"><i class='bx bx-x'></i></button>`;
                div.querySelector('.saved-script-name').addEventListener('click', () => loadScript(name));
                div.querySelector('.delete-saved').addEventListener('click', e => { e.stopPropagation(); deleteScript(name); });
                savedScriptsList.appendChild(div);
            });
        } catch(e) { console.error('Failed to load scripts', e); }
    }

    async function saveScript() {
        const name = scriptNameInput.value.trim();
        if (!name) { alert('Vui lòng nhập tên kịch bản (ví dụ: DangNhap)'); return; }
        const steps = getStepsData();
        if (steps.length === 0) { alert('Kịch bản trống!'); return; }
        try {
            const res = await fetch(`/api/scripts/${encodeURIComponent(name)}`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({steps, config: getConfigData()}) });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Không thể lưu kịch bản.');
            loadSavedScripts();
        } catch(e) { alert(`Lỗi khi lưu kịch bản: ${e.message}`); }
    }

    async function loadScript(name) {
        try {
            const res  = await fetch(`/api/scripts/${encodeURIComponent(name)}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Không thể nạp kịch bản.');
            stepsContainer.innerHTML = '';
            data.steps.forEach(step => {
                const card = createStepCard(step.action);
                Object.keys(step).forEach(key => {
                    if (key !== 'action') {
                        const inp = card.querySelector(`input[name="${key}"]`);
                        if (inp) inp.value = step[key];
                    }
                });
                stepsContainer.appendChild(card);
            });
            updateStepCount();
            if (data.config) {
                document.getElementById('config-browser').value  = data.config.browser_type || 'chrome';
                document.getElementById('config-headless').value = data.config.headless ? 'true' : 'false';
                document.getElementById('config-keep-open').value= data.config.keep_open ? 'true' : 'false';
                document.getElementById('config-slowmo').value   = data.config.slow_mo || 500;
            }
            scriptNameInput.value = name;
        } catch(e) { alert(`Lỗi khi nạp kịch bản: ${e.message}`); }
    }

    async function deleteScript(name) {
        if (!confirm(`Bạn có chắc muốn xóa kịch bản "${name}"?`)) return;
        try {
            const res = await fetch(`/api/scripts/${encodeURIComponent(name)}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Không thể xóa kịch bản.');
            loadSavedScripts();
        } catch(e) { alert(`Lỗi khi xóa: ${e.message}`); }
    }

    function getStepsData() {
        const stepCards = document.querySelectorAll('.step-card');
        const steps = [];
        stepCards.forEach(card => {
            const stepObj = { action: card.dataset.action };
            card.querySelectorAll('input').forEach(inp => stepObj[inp.name] = inp.value);
            steps.push(stepObj);
        });
        return steps;
    }

    function getConfigData() {
        return {
            browser_type: document.getElementById('config-browser').value,
            headless:     document.getElementById('config-headless').value === 'true',
            keep_open:    document.getElementById('config-keep-open').value === 'true',
            slow_mo:      parseInt(document.getElementById('config-slowmo').value)
        };
    }

    newBtn.addEventListener('click', () => {
        if (stepCount > 0 && !confirm('Bạn có chắc muốn tạo kịch bản mới? Các thay đổi chưa lưu sẽ bị mất.')) return;
        stepsContainer.innerHTML = '';
        scriptNameInput.value = '';
        updateStepCount();
    });

    saveBtn.addEventListener('click', saveScript);
    loadSavedScripts();


    // ================================================================
    //  SECTION 2: AI Agent
    // ================================================================

    const aiProviderSel  = document.getElementById('ai-provider');
    const aiModelInput   = document.getElementById('ai-model');
    const aiApiKeyInput  = document.getElementById('ai-apikey');
    const aiMaxStepsInput= document.getElementById('ai-max-steps');
    const aiBrowserSel   = document.getElementById('ai-browser');
    const aiHeadlessSel  = document.getElementById('ai-headless');
    const aiGoalTextarea = document.getElementById('ai-goal');
    const aiStartUrlInput= document.getElementById('ai-start-url');
    const aiStartBtn     = document.getElementById('ai-start-btn');
    const aiStopBtn      = document.getElementById('ai-stop-btn');
    const aiLog          = document.getElementById('ai-log');
    const clearLogBtn    = document.getElementById('clear-log-btn');
    const progressSection= document.getElementById('progress-section');
    const progressLabel  = document.getElementById('progress-label');
    const progressFill   = document.getElementById('progress-fill');
    const progressStatusText = document.getElementById('progress-status-text');
    const statusDot      = document.getElementById('status-dot');
    const statusLabel    = document.getElementById('status-label');
    const saveAiConfigBtn= document.getElementById('save-ai-config-btn');
    const toggleApiKeyBtn= document.getElementById('toggle-apikey');
    const hintList       = document.getElementById('hint-list');
    const screenshotModal= document.getElementById('screenshot-modal');
    const modalImg       = document.getElementById('modal-img');
    const modalBackdrop  = document.getElementById('modal-backdrop');
    const closeModal     = document.getElementById('close-modal');

    let currentSessionId = null;
    let currentEventSource = null;
    let currentMaxSteps = 20;

    // Model hints per provider
    const MODEL_HINTS = {
        gemini: ['gemini-3.6-flash', 'gemini-3.6-flash-lite', 'gemini-2.5-pro', 'gemini-2.0-flash'],
        openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
        claude: ['claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-3-5'],
    };

    function updateModelHints() {
        const provider = aiProviderSel.value;
        const hints    = MODEL_HINTS[provider] || [];
        hintList.innerHTML = hints.map(m =>
            `<div class="hint-item" title="Click để chọn model này">${m}</div>`
        ).join('');
        hintList.querySelectorAll('.hint-item').forEach(el => {
            el.addEventListener('click', () => {
                aiModelInput.value = el.textContent;
                aiModelInput.focus();
            });
        });
        aiModelInput.placeholder = hints[0] ? `vd: ${hints[0]}` : 'model name...';
    }

    aiProviderSel.addEventListener('change', updateModelHints);
    updateModelHints();

    // Toggle API key visibility
    toggleApiKeyBtn.addEventListener('click', () => {
        const isPassword = aiApiKeyInput.type === 'password';
        aiApiKeyInput.type = isPassword ? 'text' : 'password';
        toggleApiKeyBtn.querySelector('i').className = `bx bx-${isPassword ? 'hide' : 'show'}`;
    });

    // Save AI config
    saveAiConfigBtn.addEventListener('click', async () => {
        const body = {
            provider:         aiProviderSel.value,
            api_key:          aiApiKeyInput.value.trim(),
            model:            aiModelInput.value.trim(),
            max_steps:        parseInt(aiMaxStepsInput.value),
            default_provider: aiProviderSel.value
        };
        try {
            const res = await fetch('/api/config/ai', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
            if (res.ok) {
                saveAiConfigBtn.innerHTML = "<i class='bx bx-check'></i> Đã lưu!";
                setTimeout(() => saveAiConfigBtn.innerHTML = "<i class='bx bx-save'></i> Lưu cấu hình", 2000);
            }
        } catch(e) { console.error(e); }
    });

    // Clear log
    clearLogBtn.addEventListener('click', () => {
        aiLog.innerHTML = `
            <div class="log-empty-state">
                <i class='bx bx-brain'></i>
                <p>Nhập mục tiêu và bấm <strong>Bắt đầu</strong> để AI Agent hoạt động</p>
            </div>`;
    });

    // Screenshot modal
    function openScreenshot(src) {
        modalImg.src = src;
        screenshotModal.classList.remove('hidden');
    }
    modalBackdrop.addEventListener('click', () => screenshotModal.classList.add('hidden'));
    closeModal.addEventListener('click',    () => screenshotModal.classList.add('hidden'));
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') screenshotModal.classList.add('hidden');
    });

    // ── Agent Start ────────────────────────────────────────────────────
    aiStartBtn.addEventListener('click', async () => {
        const goal     = aiGoalTextarea.value.trim();
        const startUrl = aiStartUrlInput.value.trim();
        const apiKey   = aiApiKeyInput.value.trim();
        const provider = aiProviderSel.value;
        const model    = aiModelInput.value.trim() || null;
        const maxSteps = parseInt(aiMaxStepsInput.value) || 20;
        const browser  = aiBrowserSel.value;
        const headless = aiHeadlessSel.value === 'true';

        if (!goal)     { highlightField(aiGoalTextarea,  'Vui lòng nhập mục tiêu!'); return; }
        if (!startUrl) { highlightField(aiStartUrlInput, 'Vui lòng nhập URL bắt đầu!'); return; }
        if (!apiKey)   { highlightField(aiApiKeyInput,   'Vui lòng nhập API Key!'); return; }

        currentMaxSteps = maxSteps;

        // Clear log & show progress
        aiLog.innerHTML = '';
        progressSection.classList.remove('hidden');
        updateProgress(0, maxSteps, 'Đang khởi động...');
        setAgentStatus('running', 'Đang chạy...');
        aiStartBtn.disabled = true;
        aiStartBtn.classList.add('hidden');
        aiStopBtn.classList.remove('hidden');

        try {
            const res = await fetch('/ai/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ goal, start_url: startUrl, provider, api_key: apiKey, model, max_steps: maxSteps, browser_type: browser, headless })
            });
            const data = await res.json();

            if (data.error) {
                appendLogEvent({ type: 'error', data: { message: data.error }, timestamp: now() });
                resetAgentUI();
                return;
            }

            currentSessionId = data.session_id;
            startSSEStream(data.session_id);

        } catch(e) {
            appendLogEvent({ type: 'error', data: { message: `Lỗi kết nối: ${e.message}` }, timestamp: now() });
            resetAgentUI();
        }
    });

    // ── Agent Stop ─────────────────────────────────────────────────────
    aiStopBtn.addEventListener('click', async () => {
        if (!currentSessionId) return;
        try {
            await fetch(`/ai/stop/${currentSessionId}`, { method: 'POST' });
        } catch(e) { console.error(e); }
        aiStopBtn.disabled = true;
    });

    // ── SSE Stream ─────────────────────────────────────────────────────
    function startSSEStream(sessionId) {
        if (currentEventSource) currentEventSource.close();

        currentEventSource = new EventSource(`/ai/stream/${sessionId}`);

        currentEventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.type === 'stream_end') {
                    currentEventSource.close();
                    currentEventSource = null;
                    return;
                }
                handleAgentEvent(event);
            } catch(err) {
                console.error('SSE parse error', err);
            }
        };

        currentEventSource.onerror = () => {
            currentEventSource.close();
            currentEventSource = null;
        };
    }

    // ── Event Handler ──────────────────────────────────────────────────
    function handleAgentEvent(event) {
        const { type, data, timestamp } = event;

        switch(type) {
            case 'start':
                appendLogEvent({
                    type, timestamp,
                    data: { message: `🚀 Bắt đầu! Goal: "${data.goal}" | Provider: ${data.provider} | Max: ${data.max_steps} bước` }
                });
                break;

            case 'info':
                appendLogEvent({ type, timestamp, data: { message: data.message } });
                break;

            case 'thinking':
                updateProgress(data.step, data.max, 'Đang suy nghĩ...');
                appendLogEvent({
                    type, timestamp,
                    data: { message: `Bước ${data.step}/${data.max} — AI đang phân tích trang web...` }
                });
                break;

            case 'decision': {
                updateProgress(data.step, currentMaxSteps, `Thực hiện: ${data.action}`);
                const confidence = data.confidence || 0;
                const confClass  = confidence >= 0.8 ? 'confidence-high' : confidence >= 0.5 ? 'confidence-mid' : 'confidence-low';
                const confPct    = Math.round(confidence * 100);

                const extraHtml = `
                    <div class="log-event-reasoning">${escHtml(data.reasoning)}</div>
                    <div class="log-event-action">
                        <i class='bx bx-right-arrow-alt'></i>
                        ${escHtml(data.action)}(${escHtml(JSON.stringify(data.params))})
                        <span class="confidence-badge ${confClass}">${confPct}%</span>
                    </div>
                    ${data.screenshot ? `<img class="log-screenshot-thumb" src="data:image/png;base64,${data.screenshot}" alt="Screenshot bước ${data.step}" loading="lazy">` : ''}
                `;
                appendLogEvent({ type, timestamp, data: { message: `Bước ${data.step} — Quyết định:` }, extra: extraHtml });

                // Attach click on newly added screenshot
                setTimeout(() => {
                    const thumbs = aiLog.querySelectorAll('.log-screenshot-thumb');
                    if (thumbs.length) {
                        const lastThumb = thumbs[thumbs.length - 1];
                        lastThumb.addEventListener('click', () => openScreenshot(lastThumb.src));
                    }
                }, 50);
                break;
            }

            case 'action_result': {
                const ok = data.success;
                appendLogEvent({
                    type,
                    timestamp,
                    data: { message: `${ok ? '✓' : '✗'} ${escHtml(data.result)}` },
                    success: ok
                });
                break;
            }

            case 'done':
                updateProgress(currentMaxSteps, currentMaxSteps, 'Hoàn thành!');
                progressStatusText.classList.remove('thinking-pulse');
                appendLogEvent({ type, timestamp, data: { message: `✅ Hoàn thành sau ${data.steps} bước!\n${data.summary}` } });
                setAgentStatus('done', `Hoàn thành (${data.steps} bước)`);
                resetAgentUI(false);
                break;

            case 'failed':
                appendLogEvent({ type, timestamp, data: { message: `❌ Thất bại: ${data.reason}` } });
                setAgentStatus('failed', 'Thất bại');
                resetAgentUI(false);
                break;

            case 'stopped':
                appendLogEvent({ type, timestamp, data: { message: `⏹ Đã dừng sau ${data.steps} bước` } });
                setAgentStatus('stopped', 'Đã dừng');
                resetAgentUI(false);
                break;

            case 'error':
                appendLogEvent({ type, timestamp, data: { message: `🔴 Lỗi: ${data.message}` } });
                setAgentStatus('failed', 'Lỗi');
                resetAgentUI(false);
                break;

            case 'end':
                break;
        }
    }

    // ── Log Rendering ──────────────────────────────────────────────────
    const EVENT_META = {
        start:         { icon: 'bx-rocket',       iconClass: 'icon-start',    label: 'Bắt đầu'   },
        thinking:      { icon: 'bx-loader-alt',   iconClass: 'icon-thinking', label: 'Đang nghĩ' },
        decision:      { icon: 'bx-brain',        iconClass: 'icon-decision', label: 'Quyết định' },
        action_result: { icon: 'bx-check-circle', iconClass: 'icon-success',  label: 'Kết quả'   },
        done:          { icon: 'bx-check-shield', iconClass: 'icon-done',     label: 'Xong'       },
        failed:        { icon: 'bx-error',        iconClass: 'icon-failed',   label: 'Thất bại'  },
        stopped:       { icon: 'bx-stop-circle',  iconClass: 'icon-warning',  label: 'Dừng'       },
        info:          { icon: 'bx-info-circle',  iconClass: 'icon-info',     label: 'Thông tin' },
        error:         { icon: 'bx-x-circle',     iconClass: 'icon-error',    label: 'Lỗi'        },
    };

    function appendLogEvent({ type, timestamp, data, extra = '', success = true }) {
        // Remove empty state
        const emptyEl = aiLog.querySelector('.log-empty-state');
        if (emptyEl) emptyEl.remove();

        const meta = EVENT_META[type] || { icon: 'bx-circle', iconClass: 'icon-info', label: type };
        let iconClass = meta.iconClass;
        if (type === 'action_result') iconClass = success ? 'icon-success' : 'icon-error';

        const el = document.createElement('div');
        el.className = `log-event type-${type} ${type === 'action_result' ? (success ? 'success' : 'error') : ''}`;
        el.innerHTML = `
            <div class="log-event-icon ${iconClass}"><i class='bx ${meta.icon}'></i></div>
            <div class="log-event-body">
                <div class="log-event-header">
                    <span class="log-event-type">${meta.label}</span>
                    <span class="log-event-time">${timestamp || now()}</span>
                </div>
                <div class="log-event-text">${escHtml(data.message || '').replace(/\n/g, '<br>')}</div>
                ${extra}
            </div>`;

        aiLog.appendChild(el);
        aiLog.scrollTop = aiLog.scrollHeight;
    }

    // ── UI Helpers ─────────────────────────────────────────────────────
    function updateProgress(step, max, statusText) {
        const pct = max > 0 ? Math.min(100, Math.round((step / max) * 100)) : 0;
        progressLabel.textContent = `Bước ${step} / ${max}`;
        progressFill.style.width  = pct + '%';
        progressStatusText.textContent = statusText;
    }

    function setAgentStatus(status, label) {
        statusDot.className   = `status-dot ${status}`;
        statusLabel.textContent = label;
    }

    function resetAgentUI(stillRunning = true) {
        if (!stillRunning) {
            aiStartBtn.disabled = false;
            aiStartBtn.classList.remove('hidden');
            aiStopBtn.classList.add('hidden');
            aiStopBtn.disabled = false;
            progressStatusText.classList.remove('thinking-pulse');
        }
    }

    function highlightField(field, msg) {
        field.focus();
        field.style.borderColor = 'var(--danger)';
        field.style.boxShadow   = '0 0 0 3px rgba(255,77,109,0.2)';
        const orig = field.placeholder;
        field.placeholder = msg;
        setTimeout(() => {
            field.style.borderColor = '';
            field.style.boxShadow   = '';
            field.placeholder = orig;
        }, 2500);
    }

    function escHtml(str) {
        if (typeof str !== 'string') str = JSON.stringify(str);
        return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function now() {
        return new Date().toLocaleTimeString('vi-VN', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
    }

});
