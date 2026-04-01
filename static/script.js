document.addEventListener("DOMContentLoaded", () => {
    let allPapers = [];
    let activeFilter = '全部';

    // ---- 1. Load Papers ----
    const loadPapers = () => {
        fetch('/api/papers')
            .then(res => res.json())
            .then(data => {
                allPapers = data;
                if (data.length > 0) {
                    document.getElementById('update-time').innerText = `全量就绪 · 共 ${data.length} 篇论文`;
                    buildFilterBar(data);
                    renderCards(data);
                } else {
                    document.getElementById('papers-grid').innerHTML = `
                        <div class="empty-state">
                            <p>后台翻译引擎正在全力翻译所有论文，约需 1-2 分钟...<br>请稍后点击"重新抓取"按钮刷新。</p>
                            <div class="loader"></div>
                        </div>`;
                }
            })
            .catch(err => console.error('Load error:', err));
    };

    // ---- 2. Build Filter Bar ----
    const buildFilterBar = (data) => {
        const tagSet = new Set();
        data.forEach(p => p.matched_keywords.forEach(t => tagSet.add(t)));
        const bar = document.getElementById('filter-bar');
        bar.innerHTML = '';

        // "全部" button
        const allBtn = document.createElement('button');
        allBtn.className = 'filter-tag active';
        allBtn.textContent = `全部 (${data.length})`;
        allBtn.onclick = () => { activeFilter = '全部'; updateFilters(); renderCards(allPapers); };
        bar.appendChild(allBtn);

        // Count per tag
        const tagCounts = {};
        data.forEach(p => p.matched_keywords.forEach(t => { tagCounts[t] = (tagCounts[t] || 0) + 1; }));

        // Sort tags by count descending
        const sortedTags = [...tagSet].sort((a, b) => (tagCounts[b] || 0) - (tagCounts[a] || 0));

        sortedTags.forEach(tag => {
            const btn = document.createElement('button');
            btn.className = 'filter-tag';
            btn.textContent = `${tag} (${tagCounts[tag]})`;
            btn.onclick = () => {
                activeFilter = tag;
                updateFilters();
                const filtered = allPapers.filter(p => p.matched_keywords.includes(tag));
                renderCards(filtered);
            };
            bar.appendChild(btn);
        });
    };

    const updateFilters = () => {
        document.querySelectorAll('.filter-tag').forEach(btn => {
            btn.classList.toggle('active', btn.textContent.startsWith(activeFilter));
        });
    };

    // ---- 3. Render Cards ----
    const renderCards = (data) => {
        const grid = document.getElementById('papers-grid');
        grid.innerHTML = '';

        data.forEach((item, idx) => {
            const tagsHtml = item.matched_keywords.map(kw => `<span class="tag">${kw}</span>`).join('');
            const card = document.createElement('div');
            card.className = 'card';
            card.style.animationDelay = `${Math.min(idx * 0.06, 2)}s`;
            card.innerHTML = `
                <div>
                    <h2 class="card-title"><a href="${item.url}" target="_blank">${item.title}</a></h2>
                    <div class="card-eng">${item.eng_title || ''}</div>
                    <div class="tags">${tagsHtml}</div>
                    <p class="summary">${item.summary}</p>
                </div>
                <div class="card-footer">
                    <span class="date">获取于: ${item.date_scraped}</span>
                    <a href="${item.url}" class="btn" target="_blank">查看原文 →</a>
                </div>
            `;
            grid.appendChild(card);
        });
    };

    // ---- 4. Refresh Button ----
    document.getElementById('refresh-btn').addEventListener('click', function() {
        this.classList.add('spinning');
        document.getElementById('update-time').innerText = '后台重新抓取中...';
        fetch('/api/refresh', { method: 'POST' })
            .then(res => res.json())
            .then(() => {
                setTimeout(() => {
                    loadPapers();
                    this.classList.remove('spinning');
                }, 3000);
            })
            .catch(() => this.classList.remove('spinning'));
    });

    // ---- 5. AI Chatbot ----
    const fabButton = document.getElementById('chat-fab');
    const panel = document.getElementById('chat-panel');
    const closeBtn = document.getElementById('close-chat');
    fabButton.addEventListener('click', () => panel.classList.toggle('active'));
    closeBtn.addEventListener('click', () => panel.classList.remove('active'));

    const sendBtn = document.getElementById('chat-send');
    const inputField = document.getElementById('chat-input');
    const chatBody = document.getElementById('chat-body');

    const appendMessage = (text, sender, isHTML = false) => {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}`;
        if (isHTML) msgDiv.innerHTML = text;
        else msgDiv.innerText = text;
        chatBody.appendChild(msgDiv);
        chatBody.scrollTop = chatBody.scrollHeight;
    };

    const sendMessage = async () => {
        const msg = inputField.value.trim();
        if (!msg) return;
        appendMessage(msg, 'user');
        inputField.value = '';

        const typingId = 'typing-' + Date.now();
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message ai';
        typingDiv.id = typingId;
        typingDiv.innerHTML = `<i>🔍 正在全库检索...</i>`;
        chatBody.appendChild(typingDiv);
        chatBody.scrollTop = chatBody.scrollHeight;

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            const data = await res.json();
            document.getElementById(typingId).remove();
            appendMessage(data.response, 'ai', true);
        } catch (e) {
            document.getElementById(typingId).remove();
            appendMessage("网络异常，请确认服务器正在运行。", 'ai');
        }
    };

    sendBtn.addEventListener('click', sendMessage);
    inputField.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });

    // ---- Initial Load ----
    loadPapers();
});
