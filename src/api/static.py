"""简单 HTML 前端 — 直接通过 FastAPI 提供服务"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🧠 SecondBrain Chat</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; }
.header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }
.header h1 { font-size: 24px; margin-bottom: 5px; }
.header p { font-size: 14px; opacity: 0.8; }
.container { max-width: 900px; margin: 20px auto; display: flex; gap: 20px; }
.chat-area { flex: 1; background: white; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); display: flex; flex-direction: column; height: 600px; }
.messages { flex: 1; overflow-y: auto; padding: 20px; }
.message { margin-bottom: 16px; padding: 12px 16px; border-radius: 12px; line-height: 1.6; font-size: 14px; }
.message.user { background: #e8eaf6; margin-left: 40px; }
.message.assistant { background: #fff; border: 1px solid #e0e0e0; }
.message .sources { margin-top: 8px; font-size: 12px; color: #666; border-top: 1px dashed #ddd; padding-top: 8px; }
.input-area { padding: 16px; border-top: 1px solid #e0e0e0; display: flex; gap: 10px; }
.input-area input { flex: 1; padding: 10px 16px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; }
.input-area input:focus { border-color: #667eea; }
.input-area button { padding: 10px 24px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
.input-area button:hover { background: #5a6fd6; }
.input-area button:disabled { background: #aaa; cursor: not-allowed; }
.sidebar { width: 250px; }
.sidebar .card { background: white; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
.sidebar h3 { font-size: 14px; margin-bottom: 10px; color: #666; }
.sidebar select, .sidebar input[type="range"] { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
.sidebar .stat { font-size: 13px; color: #555; padding: 4px 0; }
.sidebar .stat span { color: #667eea; font-weight: 600; }
.typing { display: inline-block; width: 20px; height: 20px; border: 2px solid #667eea; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="header">
    <h1>🧠 SecondBrain Chat</h1>
    <p>基于 RAG 的个人知识库智能问答 — Obsidian 笔记驱动</p>
</div>
<div class="container">
    <div class="chat-area">
        <div class="messages" id="messages">
            <div class="message assistant">👋 你好！我是 SecondBrain Chat，基于你的 Obsidian 笔记库回答问题。试试问我点什么吧！</div>
        </div>
        <div class="input-area">
            <input type="text" id="query" placeholder="输入你的问题..." onkeydown="if(event.key==='Enter')send()">
            <button id="sendBtn" onclick="send()">发送</button>
        </div>
    </div>
    <div class="sidebar">
        <div class="card">
            <h3>⚙️ 检索设置</h3>
            <label style="font-size:13px;color:#666;">领域过滤</label>
            <select id="domain">
                <option value="">全部领域</option>
                <option value="通识">通识（得到笔记）</option>
                <option value="AI/ML">AI/ML</option>
                <option value="编程">编程</option>
                <option value="面试">面试</option>
            </select>
            <br><br>
            <label style="font-size:13px;color:#666;">返回结果数: <span id="topkVal">5</span></label>
            <input type="range" id="topk" min="1" max="10" value="5" oninput="document.getElementById('topkVal').textContent=this.value">
        </div>
        <div class="card" id="statsCard">
            <h3>📊 知识库统计</h3>
            <div id="stats">加载中...</div>
        </div>
        <div class="card">
            <h3>💡 提示</h3>
            <div style="font-size:12px;color:#888;line-height:1.8;">
                • 支持自然语言提问<br>
                • 可按领域过滤检索<br>
                • 基于混合检索（BM25+向量）<br>
                • 1727篇笔记 / 1808个chunks
            </div>
        </div>
    </div>
</div>
<script>
const messagesDiv = document.getElementById('messages');
const queryInput = document.getElementById('query');
const sendBtn = document.getElementById('sendBtn');

async function loadStats() {
    try {
        const resp = await fetch('/stats');
        const data = await resp.json();
        const statsHtml = `
            <div class="stat">总笔记: <span>${data.total_notes || 0}</span> 篇</div>
            <div class="stat">总Chunk: <span>${data.total_chunks || 0}</span> 个</div>
        `;
        const domains = data.domain_distribution || {};
        let domainHtml = '';
        for (const [k, v] of Object.entries(domains)) {
            domainHtml += `<div class="stat">${k}: <span>${v}</span></div>`;
        }
        document.getElementById('stats').innerHTML = statsHtml + domainHtml;
    } catch(e) { document.getElementById('stats').innerHTML = '加载失败'; }
}

function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = content;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return div;
}

function showTyping() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'typing';
    div.innerHTML = '<div class="typing"></div>';
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function hideTyping() {
    const el = document.getElementById('typing');
    if (el) el.remove();
}

async function send() {
    const query = queryInput.value.trim();
    if (!query) return;

    sendBtn.disabled = true;
    addMessage('user', escapeHtml(query));
    queryInput.value = '';
    showTyping();

    try {
        const resp = await fetch('/api/v1/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                domain: document.getElementById('domain').value || null,
                top_k: parseInt(document.getElementById('topk').value),
                stream: false,
            }),
        });
        const data = await resp.json();
        hideTyping();

        let sourcesHtml = '';
        if (data.sources && data.sources.length > 0) {
            sourcesHtml = '<div class="sources">📎 <b>参考来源：</b><br>';
            data.sources.forEach((s, i) => {
                sourcesHtml += `${i+1}. ${escapeHtml(s.title || '').substring(0, 50)} (${escapeHtml(s.folder || '')}) — 相关度 ${s.score || 0}<br>`;
            });
            sourcesHtml += '</div>';
        }
        addMessage('assistant', escapeHtml(data.answer || '未获取到回答') + sourcesHtml);
    } catch(e) {
        hideTyping();
        addMessage('assistant', '❌ 请求失败: ' + e.message + '<br><small>提示：请确保 LLM 服务已启动（端口 11434）</small>');
    }

    sendBtn.disabled = false;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

loadStats();
queryInput.focus();
</script>
</body>
</html>
"""
