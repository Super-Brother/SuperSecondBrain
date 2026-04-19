"""SecondBrain Chat UI — Google Stitch 设计"""

import os

VAULT_NAME = os.getenv("VAULT_PATH", "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本").split("/")[-1]

HTML_TEMPLATE = f'''<!DOCTYPE html>
<html class="dark" lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>SecondBrain Chat</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script>
tailwind.config = {{
    darkMode: "class",
    theme: {{
        extend: {{
            "colors": {{
                "primary-container": "#2e5bff",
                "surface-variant": "#333538",
                "on-surface": "#e2e2e6",
                "background": "#111317",
                "surface": "#111317",
                "surface-container-low": "#1a1c1f",
                "surface-container": "#1e2023",
                "surface-container-high": "#282a2d",
                "surface-container-highest": "#333538",
                "primary": "#b8c3ff",
                "on-primary": "#002388",
            }},
        }},
    }},
}}
</script>
<style>
.material-symbols-outlined {{ font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; }}
body {{ font-family: 'Inter', sans-serif; }}
.cursor-blink {{ animation: blink 0.8s infinite; }}
@keyframes blink {{ 0%, 50% {{ opacity: 1; }} 51%, 100% {{ opacity: 0; }} }}
.source-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 25px rgba(46,91,255,0.2); }}
</style>
</head>
<body class="bg-surface text-on-surface overflow-hidden">
<!-- TopNavBar -->
<nav class="bg-background/80 backdrop-blur-xl sticky top-0 z-50 flex justify-between items-center w-full px-8 h-16 border-b border-white/5">
    <div class="text-xl font-black tracking-tighter text-white uppercase">🧠 SecondBrain Chat</div>
    <div class="flex items-center gap-4">
        <span class="text-xs text-primary font-bold bg-primary/10 px-3 py-1 rounded-full">RAG Knowledge Base</span>
    </div>
</nav>

<div class="flex h-[calc(100vh-64px)] overflow-hidden">
    <!-- Main Chat Canvas -->
    <main class="flex-1 flex flex-col relative bg-surface">
        <!-- Chat Scroll Area -->
        <div id="messages" class="flex-1 overflow-y-auto p-8 space-y-8 pb-32">
            <!-- Welcome Message -->
            <div class="max-w-3xl mx-auto flex flex-col gap-3">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center">
                        <span class="material-symbols-outlined text-xs text-white" style="font-variation-settings: 'FILL' 1;">psychology</span>
                    </div>
                    <span class="text-xs font-bold tracking-widest uppercase text-on-surface/60">AI Assistant</span>
                </div>
                <div class="bg-surface-container-low p-5 rounded-xl text-on-surface leading-relaxed border-l-2 border-primary/30">
                    你好！我是 SecondBrain Chat，基于你的 Obsidian 笔记库回答问题。试试问我点什么吧！
                </div>
            </div>
        </div>

        <!-- Fixed Input Bar -->
        <div class="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-surface via-surface/95 to-transparent">
            <div class="max-w-3xl mx-auto">
                <div class="bg-surface-container-high rounded-xl flex items-center p-1.5 gap-2 border border-white/5">
                    <textarea id="query" class="flex-1 bg-transparent border-none focus:ring-0 text-on-surface py-2 px-3 resize-none placeholder-on-surface/40 text-sm" placeholder="输入你的问题..." rows="1"></textarea>
                    <button id="sendBtn" onclick="send()" class="bg-primary text-on-primary font-bold px-4 py-2 rounded-lg hover:bg-primary/80 transition-all flex items-center gap-1.5 text-sm">
                        <span>发送</span>
                        <span class="material-symbols-outlined text-base">send</span>
                    </button>
                </div>
            </div>
        </div>
    </main>

    <!-- Right SideBar -->
    <aside class="bg-surface-container/50 border-l border-white/5 w-72 flex flex-col p-6 overflow-y-auto">
        <div class="mb-8">
            <div class="text-primary font-bold text-lg mb-1">控制面板</div>
            <div class="text-xs text-on-surface/50 uppercase tracking-widest">检索设置</div>
        </div>

        <!-- Domain Selector -->
        <div class="mb-6">
            <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50 mb-3 block">知识领域</label>
            <div class="relative">
                <select id="domain" class="w-full bg-surface-container-low border-none text-on-surface rounded-lg py-3 pl-4 pr-10 appearance-none focus:ring-1 focus:ring-primary/30 text-sm cursor-pointer">
                    <option value="">全部领域</option>
                    <option value="通识">通识（得到笔记）</option>
                    <option value="AI/ML">AI/ML</option>
                    <option value="编程">编程</option>
                    <option value="面试">面试</option>
                </select>
                <span class="material-symbols-outlined absolute right-3 top-2.5 text-on-surface/50 pointer-events-none text-lg">expand_more</span>
            </div>
        </div>

        <!-- Top-K Slider -->
        <div class="mb-6">
            <div class="flex justify-between items-center mb-3">
                <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50">返回结果数</label>
                <span id="topkVal" class="text-xs font-mono text-primary bg-primary/10 px-2 py-0.5 rounded">5</span>
            </div>
            <input type="range" id="topk" min="1" max="10" value="5" class="w-full accent-primary" oninput="document.getElementById('topkVal').textContent=this.value">
        </div>

        <!-- Stats -->
        <div class="bg-surface-container-low rounded-xl p-4 mb-6">
            <div class="text-xs font-bold text-on-surface/50 mb-3">📊 知识库统计</div>
            <div id="stats" class="text-xs text-on-surface/70 space-y-1">加载中...</div>
        </div>
    </aside>
</div>

<script>
const VAULT_NAME = '{VAULT_NAME}';
const messagesDiv = document.getElementById('messages');
const queryInput = document.getElementById('query');
const sendBtn = document.getElementById('sendBtn');

// Auto-resize textarea
queryInput.addEventListener('input', function() {{
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
}});
queryInput.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter' && !e.shiftKey) {{
        e.preventDefault();
        send();
    }}
}});

async function loadStats() {{
    try {{
        const resp = await fetch('/stats');
        const data = await resp.json();
        document.getElementById('stats').innerHTML = `
            <div>总笔记: <span class="text-primary font-bold">${{data.total_notes || 0}}</span> 篇</div>
            <div>总Chunk: <span class="text-primary font-bold">${{data.total_chunks || 0}}</span> 个</div>
        `;
    }} catch(e) {{}}
}}
loadStats();

function addMessage(role, content, sources = null) {{
    const wrapper = document.createElement('div');
    wrapper.className = 'max-w-3xl mx-auto flex flex-col gap-3';

    if (role === 'user') {{
        wrapper.innerHTML = `
            <div class="flex justify-end items-start gap-2">
                <div class="bg-gradient-to-br from-primary-container to-blue-600 text-white px-3 py-1.5 rounded-xl text-sm max-w-[70%]">
                    ${{content}}
                </div>
                <div class="w-6 h-6 rounded-full bg-primary-container flex items-center justify-center shrink-0 mt-0.5">
                    <span class="material-symbols-outlined text-white" style="font-size: 14px;">person</span>
                </div>
            </div>
        `;
    }} else {{
        let sourcesHtml = '';
        if (sources && sources.length > 0) {{
            const filteredSources = sources.filter(s => (s.score || 0) >= 0.2);
            if (filteredSources.length > 0) {{
                sourcesHtml = '<div class="flex flex-wrap gap-2 mt-2">';
                filteredSources.forEach((s, i) => {{
                    const title = (s.title || '未知').substring(0, 30);
                    const score = ((s.score || 0) * 100).toFixed(0);
                    const source = s.source || '';

                    if (source && source.includes(VAULT_NAME + '/')) {{
                        const relPath = source.split(VAULT_NAME + '/')[1];
                        const obsUrl = `obsidian://open?vault=${{encodeURIComponent(VAULT_NAME)}}&file=${{encodeURIComponent(relPath)}}`;
                        sourcesHtml += `<a href="${{obsUrl}}" target="_blank" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs hover:bg-primary/20 transition-colors"><span class="material-symbols-outlined text-sm">link</span>${{title}} <span class="opacity-60">${{score}}%</span></a>`;
                    }} else {{
                        sourcesHtml += `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 text-on-surface/70 text-xs">${{title}} <span class="opacity-60">${{score}}%</span></span>`;
                    }}
                }});
                sourcesHtml += '</div>';
            }}
        }}

        wrapper.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center">
                    <span class="material-symbols-outlined text-xs text-white" style="font-variation-settings: 'FILL' 1;">psychology</span>
                </div>
                <span class="text-xs font-bold tracking-widest uppercase text-on-surface/60">AI Assistant</span>
            </div>
            <div class="bg-surface-container-low px-4 py-2.5 rounded-xl text-on-surface leading-relaxed border-l-2 border-primary/30 whitespace-pre-wrap text-sm">
                ${{content}}<span id="cursor" class="cursor-blink text-primary">▌</span>
            </div>
            ${{sourcesHtml}}
        `;
    }}

    messagesDiv.appendChild(wrapper);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return wrapper;
}}

function escapeHtml(text) {{
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}}

async function send() {{
    const query = queryInput.value.trim();
    if (!query) return;

    sendBtn.disabled = true;
    sendBtn.innerHTML = '<span class="material-symbols-outlined animate-spin">progress_activity</span>';

    addMessage('user', escapeHtml(query));
    queryInput.value = '';
    queryInput.style.height = 'auto';

    // 添加 AI 思考状态
    const thinkingDiv = document.createElement('div');
    thinkingDiv.id = 'ai-thinking';
    thinkingDiv.className = 'max-w-3xl mx-auto flex items-center gap-2 text-primary text-sm';
    thinkingDiv.innerHTML = '<span class="material-symbols-outlined animate-spin">psychology</span> AI 正在思考...';
    messagesDiv.appendChild(thinkingDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    let fullAnswer = '';
    let sources = [];

    try {{
        const resp = await fetch('/api/v1/chat/stream', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
                query: query,
                domain: document.getElementById('domain').value || null,
                top_k: parseInt(document.getElementById('topk').value),
            }}),
        }});

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();

        // Add placeholder message
        const wrapper = addMessage('assistant', '');

        while (true) {{
            const {{ done, value }} = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\\n');

            for (const line of lines) {{
                if (line.startsWith('data: ')) {{
                    try {{
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'answer') {{
                            fullAnswer += data.content;
                            // Update content
                            const contentDiv = wrapper.querySelector('.bg-surface-container-low');
                            if (contentDiv) {{
                                contentDiv.innerHTML = escapeHtml(fullAnswer) + '<span id="cursor" class="cursor-blink text-primary">▌</span>';
                            }}
                            messagesDiv.scrollTop = messagesDiv.scrollHeight;
                        }} else if (data.type === 'sources') {{
                            sources = data.data;
                        }} else if (data.type === 'done') {{
                            // Remove cursor
                            const cursor = document.getElementById('cursor');
                            if (cursor) cursor.remove();
                        }}
                    }} catch(e) {{}}
                }}
            }}
        }}

        // Add sources if any (filter out low relevance < 20%)
        const filteredSourcesFinal = sources.filter(s => (s.score || 0) >= 0.2);
        if (filteredSourcesFinal.length > 0) {{
            let sourcesHtml = '<div class="flex flex-wrap gap-2 mt-2">';
            filteredSourcesFinal.forEach((s, i) => {{
                const title = (s.title || '未知').substring(0, 30);
                const score = ((s.score || 0) * 100).toFixed(0);
                const source = s.source || '';

                if (source && source.includes(VAULT_NAME + '/')) {{
                    const relPath = source.split(VAULT_NAME + '/')[1];
                    const obsUrl = `obsidian://open?vault=${{encodeURIComponent(VAULT_NAME)}}&file=${{encodeURIComponent(relPath)}}`;
                    sourcesHtml += `<a href="${{obsUrl}}" target="_blank" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs hover:bg-primary/20 transition-colors"><span class="material-symbols-outlined text-sm">link</span>${{title}} <span class="opacity-60">${{score}}%</span></a>`;
                }} else {{
                    sourcesHtml += `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 text-on-surface/70 text-xs">${{title}} <span class="opacity-60">${{score}}%</span></span>`;
                }}
            }});
            sourcesHtml += '</div>';
            wrapper.insertAdjacentHTML('beforeend', sourcesHtml);
        }}

    }} catch(e) {{
        addMessage('assistant', '❌ 请求失败: ' + e.message + '<br><small class="text-on-surface/50">请确保 LLM 服务已启动（端口 11434）</small>');
    }}

    // 移除思考状态
    const thinkingEl = document.getElementById('ai-thinking');
    if (thinkingEl) thinkingEl.remove();

    sendBtn.disabled = false;
    sendBtn.innerHTML = '<span>发送</span><span class="material-symbols-outlined text-base">send</span>';
    queryInput.focus();
}}
</script>
</body>
</html>
'''
