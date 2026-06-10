"""SecondBrain Chat UI — 响应式重构版

支持：
- 移动端适配
- 历史聊天记录
- 设置页
- 登录/注册
"""

import os

VAULT_NAME = os.getenv("VAULT_PATH", "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本").split("/")[-1]

HTML_TEMPLATE = f'''<!DOCTYPE html>
<html class="dark" lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" name="viewport"/>
<meta name="theme-color" content="#111317"/>
<title>SecondBrain Chat</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
tailwind.config = {{
    darkMode: "class",
    theme: {{
        extend: {{
            colors: {{
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
body {{ font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }}
.cursor-blink {{ animation: blink 0.8s infinite; }}
@keyframes blink {{ 0%, 50% {{ opacity: 1; }} 51%, 100% {{ opacity: 0; }} }}
.scrollbar-hide {{ -ms-overflow-style: none; scrollbar-width: none; }}
.scrollbar-hide::-webkit-scrollbar {{ display: none; }}
.drawer {{ transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
.drawer-open {{ transform: translateX(0) !important; }}
.msg-bubble {{ animation: msgIn 0.3s ease-out; }}
@keyframes msgIn {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
.source-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 25px rgba(46,91,255,0.2); }}
@media (max-width: 768px) {{
    .mobile-full {{ width: 100vw !important; }}
}}
/* 笔记管理样式 */
.prose {{ color: #e2e2e6; }}
.prose h1, .prose h2, .prose h3, .prose h4 {{ color: #b8c3ff; margin-top: 1.5em; margin-bottom: 0.5em; font-weight: 600; }}
.prose h1 {{ font-size: 1.5em; }}
.prose h2 {{ font-size: 1.25em; }}
.prose h3 {{ font-size: 1.1em; }}
.prose p {{ margin-bottom: 0.75em; }}
.prose ul, .prose ol {{ padding-left: 1.5em; margin-bottom: 0.75em; }}
.prose li {{ margin-bottom: 0.25em; }}
.prose code {{ background: rgba(255,255,255,0.08); padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.9em; }}
.prose pre {{ background: #1a1c1f; padding: 1em; border-radius: 8px; overflow-x: auto; margin-bottom: 0.75em; }}
.prose pre code {{ background: none; padding: 0; }}
.prose blockquote {{ border-left: 3px solid #2e5bff; padding-left: 1em; color: #e2e2e6aa; margin-bottom: 0.75em; }}
.prose a {{ color: #b8c3ff; text-decoration: underline; }}
.prose hr {{ border-color: rgba(255,255,255,0.1); margin: 1em 0; }}
.prose table {{ width: 100%; border-collapse: collapse; margin-bottom: 0.75em; }}
.prose th, .prose td {{ border: 1px solid rgba(255,255,255,0.1); padding: 0.5em; text-align: left; }}
.prose th {{ background: rgba(255,255,255,0.05); }}
.note-card {{ transition: all 0.2s ease; }}
.note-card:hover {{ background: rgba(255,255,255,0.04); }}
</style>
</head>
<body class="bg-surface text-on-surface h-screen overflow-hidden">

<!-- ============ 登录页 ============ -->
<div id="loginPage" class="fixed inset-0 z-50 flex items-center justify-center bg-surface">
    <div class="w-full max-w-sm px-6">
        <div class="text-center mb-6">
            <div class="w-16 h-16 rounded-2xl bg-primary-container flex items-center justify-center mx-auto mb-4">
                <span class="material-symbols-outlined text-3xl text-white">psychology</span>
            </div>
            <h1 class="text-2xl font-black text-white tracking-tight">SecondBrain</h1>
            <p class="text-sm text-on-surface/50 mt-1">你的智能知识库助手</p>
        </div>

        <!-- 标签切换 -->
        <div class="flex mb-4 bg-surface-container-high rounded-xl p-1">
            <button id="tabLogin" onclick="switchTab('login')" class="flex-1 py-2 text-xs font-bold rounded-lg bg-primary-container text-white transition-all">登录</button>
            <button id="tabRegister" onclick="switchTab('register')" class="flex-1 py-2 text-xs font-bold rounded-lg text-on-surface/60 hover:text-on-surface transition-all">注册</button>
        </div>

        <!-- 登录表单 -->
        <div id="loginForm" class="space-y-3">
            <input id="loginInput" type="text" placeholder="用户名或邮箱" class="w-full bg-surface-container-high border border-white/5 rounded-xl py-3 px-4 text-on-surface text-sm focus:outline-none focus:border-primary/30"/>
            <input id="loginPassword" type="password" placeholder="密码" class="w-full bg-surface-container-high border border-white/5 rounded-xl py-3 px-4 text-on-surface text-sm focus:outline-none focus:border-primary/30"/>
            <button onclick="handleLogin()" class="w-full bg-primary-container text-white font-bold py-3 rounded-xl hover:bg-primary-container/80 transition-all text-sm">登录</button>
        </div>

        <!-- 注册表单 -->
        <div id="registerForm" class="space-y-3 hidden">
            <input id="regUsername" type="text" placeholder="用户名（至少3个字符）" class="w-full bg-surface-container-high border border-white/5 rounded-xl py-3 px-4 text-on-surface text-sm focus:outline-none focus:border-primary/30"/>
            <input id="regEmail" type="email" placeholder="邮箱" class="w-full bg-surface-container-high border border-white/5 rounded-xl py-3 px-4 text-on-surface text-sm focus:outline-none focus:border-primary/30"/>
            <div class="flex gap-2">
                <input id="regCode" type="text" placeholder="验证码" class="flex-1 bg-surface-container-high border border-white/5 rounded-xl py-3 px-4 text-on-surface text-sm focus:outline-none focus:border-primary/30"/>
                <button id="sendCodeBtn" onclick="sendVerifyCode()" class="bg-surface-container text-on-surface font-medium px-4 rounded-xl text-xs border border-white/5 hover:bg-surface-container-high transition-all whitespace-nowrap">获取验证码</button>
            </div>
            <input id="regPassword" type="password" placeholder="密码（至少6个字符）" class="w-full bg-surface-container-high border border-white/5 rounded-xl py-3 px-4 text-on-surface text-sm focus:outline-none focus:border-primary/30"/>
            <button onclick="handleRegister()" class="w-full bg-primary-container text-white font-bold py-3 rounded-xl hover:bg-primary-container/80 transition-all text-sm">注册</button>
        </div>

        <div id="loginError" class="text-red-400 text-xs text-center mt-3 hidden"></div>
        <div id="loginSuccess" class="text-green-400 text-xs text-center mt-3 hidden"></div>
    </div>
</div>

<!-- ============ 主应用 ============ -->
<div id="mainApp" class="hidden h-full flex">

    <!-- 左侧历史会话栏（桌面端常驻，移动端抽屉） -->
    <aside id="historyDrawer" class="drawer fixed md:relative md:translate-x-0 z-40 w-[280px] h-full bg-surface-container/80 border-r border-white/5 flex flex-col -translate-x-full md:w-64 shrink-0">
        <div class="p-4 border-b border-white/5 flex items-center justify-between">
            <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-primary">psychology</span>
                <span class="font-bold text-sm">SecondBrain</span>
            </div>
            <button onclick="toggleHistoryDrawer()" class="md:hidden material-symbols-outlined text-on-surface/50">close</button>
        </div>
        <button onclick="newChat()" class="mx-4 mt-4 mb-2 bg-primary-container text-white font-medium py-2.5 px-4 rounded-xl flex items-center gap-2 text-sm hover:bg-primary-container/80 transition-all">
            <span class="material-symbols-outlined text-base">add</span>
            新建对话
        </button>
        <div id="sessionList" class="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-hide">
            <div class="text-xs text-on-surface/30 text-center py-8">加载中...</div>
        </div>
        <div class="p-4 border-t border-white/5">
            <button onclick="showNotesView()" class="w-full flex items-center gap-2 text-sm text-on-surface/60 hover:text-on-surface transition-colors py-2 px-3 rounded-lg hover:bg-white/5">
                <span class="material-symbols-outlined text-base">folder_open</span>
                笔记管理
            </button>
            <button onclick="openSettings()" class="w-full flex items-center gap-2 text-sm text-on-surface/60 hover:text-on-surface transition-colors py-2 px-3 rounded-lg hover:bg-white/5">
                <span class="material-symbols-outlined text-base">settings</span>
                设置
            </button>
            <button onclick="logout()" class="w-full flex items-center gap-2 text-sm text-on-surface/60 hover:text-red-400 transition-colors py-2 px-3 rounded-lg hover:bg-white/5">
                <span class="material-symbols-outlined text-base">logout</span>
                退出登录
            </button>
        </div>
    </aside>

    <!-- 遮罩层（移动端） -->
    <div id="historyOverlay" onclick="toggleHistoryDrawer()" class="fixed inset-0 bg-black/50 z-30 hidden md:hidden"></div>

    <!-- 中间聊天区域 -->
    <main id="chatView" class="flex-1 flex flex-col h-full min-w-0 relative">
        <!-- 顶部导航 -->
        <nav class="bg-background/80 backdrop-blur-xl sticky top-0 z-20 flex items-center justify-between px-4 h-14 border-b border-white/5 shrink-0">
            <div class="flex items-center gap-3">
                <button onclick="toggleHistoryDrawer()" class="md:hidden material-symbols-outlined text-on-surface/60">menu</button>
                <span id="currentSessionTitle" class="text-sm font-semibold truncate max-w-[200px]">新对话</span>
            </div>
            <div class="flex items-center gap-2">
            </div>
        </nav>

        <!-- 消息区域 -->
        <div id="messages" class="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 scrollbar-hide pb-4">
            <!-- 欢迎消息 -->
            <div class="max-w-2xl mx-auto flex flex-col gap-3">
                <div class="flex items-center gap-2">
                    <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center">
                        <span class="material-symbols-outlined text-xs text-white">psychology</span>
                    </div>
                    <span class="text-xs font-medium text-on-surface/50">AI Assistant</span>
                </div>
                <div class="bg-surface-container-low p-4 rounded-xl text-on-surface text-sm leading-relaxed border-l-2 border-primary/30">
                    你好！我是 SecondBrain Chat，基于你的知识库回答问题。试试问我点什么吧！
                </div>
            </div>
        </div>

        <!-- 底部输入栏 -->
        <div class="shrink-0 p-3 md:p-4 bg-surface border-t border-white/5">
            <div class="max-w-2xl mx-auto">
                <div class="bg-surface-container-high rounded-xl flex items-end p-1.5 gap-2 border border-white/5">
                    <textarea id="query" class="flex-1 bg-transparent border-none focus:ring-0 text-on-surface py-2.5 px-3 resize-none placeholder-on-surface/40 text-sm max-h-[120px]" placeholder="输入你的问题..." rows="1"></textarea>
                    <button id="sendBtn" onclick="send()" class="bg-primary-container text-white font-bold p-2.5 rounded-lg hover:bg-primary-container/80 transition-all flex items-center justify-center shrink-0 mb-0.5">
                        <span class="material-symbols-outlined text-base">send</span>
                    </button>
                </div>
                <div class="text-[10px] text-on-surface/30 text-center mt-1.5">AI 生成内容仅供参考</div>
            </div>
        </div>
    </main>

    <!-- ============ 笔记管理视图 ============ -->
    <div id="notesView" class="hidden flex-1 flex flex-col h-full min-w-0 relative">
        <!-- 顶部导航 -->
        <nav class="bg-background/80 backdrop-blur-xl sticky top-0 z-20 flex items-center justify-between px-4 h-14 border-b border-white/5 shrink-0">
            <div class="flex items-center gap-3">
                <button onclick="showChatView()" class="material-symbols-outlined text-on-surface/60 hover:text-on-surface">arrow_back</button>
                <span id="notesNavTitle" class="text-sm font-semibold truncate">笔记管理</span>
            </div>
            <div class="flex items-center gap-2">
                <button id="newNoteBtn" onclick="showNoteEditor()" class="bg-primary-container text-white text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-primary-container/80 transition-all flex items-center gap-1">
                    <span class="material-symbols-outlined text-sm">add</span>新建
                </button>
            </div>
        </nav>

        <!-- 笔记管理内容区 -->
        <div id="notesContent" class="flex-1 overflow-y-auto scrollbar-hide">
            <!-- 笔记列表视图 -->
            <div id="notesListView" class="h-full flex">
                <!-- 左侧过滤栏 -->
                <div class="w-60 h-full border-r border-white/5 bg-surface-container/40 flex flex-col hidden md:flex">
                    <div class="p-3 border-b border-white/5">
                        <input id="notesSearchInput" type="text" placeholder="搜索笔记..." onkeydown="if(event.key==='Enter')searchNotes()" class="w-full bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm placeholder-on-surface/40">
                    </div>
                    <div class="flex-1 overflow-y-auto p-3 space-y-4 scrollbar-hide">
                        <div>
                            <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-2">领域</div>
                            <div id="notesDomainFilters" class="space-y-1"></div>
                        </div>
                        <div>
                            <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-2">文件夹</div>
                            <div id="notesFolderFilters" class="space-y-1 max-h-48 overflow-y-auto scrollbar-hide"></div>
                        </div>
                        <div>
                            <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-2">标签</div>
                            <div id="notesTagFilters" class="flex flex-wrap gap-1"></div>
                        </div>
                    </div>
                </div>

                <!-- 右侧笔记列表 -->
                <div class="flex-1 flex flex-col min-w-0">
                    <div id="notesListHeader" class="p-3 border-b border-white/5 flex items-center justify-between">
                        <span id="notesCount" class="text-xs text-on-surface/50">加载中...</span>
                        <div class="flex items-center gap-2">
                            <button onclick="refreshNotes()" class="material-symbols-outlined text-on-surface/40 hover:text-on-surface text-sm p-1">refresh</button>
                        </div>
                    </div>
                    <div id="notesList" class="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-hide">
                        <div class="text-xs text-on-surface/30 text-center py-8">加载中...</div>
                    </div>
                    <!-- 分页 -->
                    <div id="notesPagination" class="p-3 border-t border-white/5 flex items-center justify-center gap-2"></div>
                </div>
            </div>

            <!-- 笔记详情视图 -->
            <div id="noteDetailView" class="hidden h-full flex flex-col">
                <div class="flex-1 overflow-y-auto p-4 md:p-8 scrollbar-hide">
                    <div class="max-w-3xl mx-auto">
                        <!-- 面包屑 -->
                        <div id="noteBreadcrumb" class="text-xs text-on-surface/40 mb-4 flex items-center gap-1"></div>

                        <!-- 元数据 -->
                        <div class="flex flex-wrap items-center gap-2 mb-4">
                            <span id="noteDomainBadge" class="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-medium"></span>
                            <span id="noteDate" class="text-xs text-on-surface/40"></span>
                            <span id="noteWordCount" class="text-xs text-on-surface/40"></span>
                        </div>

                        <!-- 标签 -->
                        <div id="noteTags" class="flex flex-wrap gap-1.5 mb-6"></div>

                        <!-- 内容 -->
                        <div id="noteContent" class="prose prose-invert max-w-none text-sm leading-relaxed"></div>

                        <!-- 双向链接 -->
                        <div id="noteOutboundLinks" class="mt-8 hidden">
                            <div class="text-xs font-bold text-on-surface/50 mb-2">双向链接</div>
                            <div id="noteOutboundLinksList" class="flex flex-wrap gap-2"></div>
                        </div>

                        <!-- 操作栏 -->
                        <div class="mt-8 flex items-center gap-3">
                            <button onclick="editCurrentNote()" class="bg-primary-container text-white text-xs font-bold px-4 py-2 rounded-lg hover:bg-primary-container/80 transition-all flex items-center gap-1">
                                <span class="material-symbols-outlined text-sm">edit</span>编辑
                            </button>
                            <button onclick="downloadCurrentNote()" id="noteDownloadBtn" class="hidden bg-surface-container-high text-on-surface text-xs font-bold px-4 py-2 rounded-lg hover:bg-surface-container-highest transition-all flex items-center gap-1">
                                <span class="material-symbols-outlined text-sm">download</span>下载
                            </button>
                            <button onclick="deleteCurrentNote()" class="bg-red-500/10 text-red-400 text-xs font-bold px-4 py-2 rounded-lg hover:bg-red-500/20 transition-all flex items-center gap-1">
                                <span class="material-symbols-outlined text-sm">delete</span>删除
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 笔记编辑器视图 -->
            <div id="noteEditorView" class="hidden h-full flex flex-col">
                <div class="flex-1 overflow-y-auto p-4 md:p-6 scrollbar-hide">
                    <div class="max-w-4xl mx-auto h-full flex flex-col">
                        <!-- 编辑头部 -->
                        <div class="flex items-center gap-3 mb-4">
                            <input id="editorNotePath" type="text" placeholder="文件路径（如：未分类/新笔记.md）" class="flex-1 bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm placeholder-on-surface/40">
                        </div>
                        <div class="flex items-center gap-3 mb-4">
                            <input id="editorNoteTags" type="text" placeholder="标签（逗号分隔）" class="flex-1 bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm placeholder-on-surface/40">
                            <input id="editorNoteDate" type="date" class="bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm">
                        </div>

                        <!-- 编辑区 -->
                        <div class="flex-1 flex gap-4 min-h-0">
                            <div class="flex-1 flex flex-col min-w-0">
                                <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-1">Markdown</div>
                                <textarea id="editorNoteContent" class="flex-1 w-full bg-surface-container-high border-none text-on-surface rounded-lg p-3 text-sm resize-none font-mono leading-relaxed placeholder-on-surface/40" placeholder="在此输入 Markdown 内容..."></textarea>
                            </div>
                            <div class="flex-1 flex flex-col min-w-0 hidden md:flex">
                                <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-1">预览</div>
                                <div id="editorNotePreview" class="flex-1 w-full bg-surface-container-high border-none text-on-surface rounded-lg p-3 text-sm overflow-y-auto scrollbar-hide"></div>
                            </div>
                        </div>

                        <!-- 操作栏 -->
                        <div class="mt-4 flex items-center justify-end gap-3">
                            <button onclick="cancelEdit()" class="text-sm text-on-surface/60 hover:text-on-surface px-4 py-2">取消</button>
                            <button onclick="saveNote()" class="bg-primary-container text-white text-sm font-bold px-6 py-2 rounded-lg hover:bg-primary-container/80 transition-all">保存</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- ============ 设置弹窗 ============ -->
<div id="settingsOverlay" onclick="closeSettings()" class="fixed inset-0 bg-black/60 z-40 hidden backdrop-blur-sm"></div>
<div id="settingsModal" class="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-lg bg-surface-container rounded-2xl border border-white/10 shadow-2xl hidden flex-col max-h-[85vh]">
    <!-- 头部 -->
    <div class="p-5 border-b border-white/5 flex items-center justify-between shrink-0">
        <h2 class="font-bold text-lg">设置</h2>
        <button onclick="closeSettings()" class="material-symbols-outlined text-on-surface/50 hover:text-on-surface transition-colors">close</button>
    </div>

    <!-- Tab 导航 -->
    <div class="flex border-b border-white/5 shrink-0">
        <button id="tabModelBtn" onclick="switchSettingsTab('model')" class="flex-1 py-3 text-sm font-medium text-primary border-b-2 border-primary transition-colors">模型配置</button>
        <button id="tabGeneralBtn" onclick="switchSettingsTab('general')" class="flex-1 py-3 text-sm font-medium text-on-surface/50 hover:text-on-surface transition-colors">通用设置</button>
    </div>

    <div class="flex-1 overflow-y-auto p-5 scrollbar-hide">
        <!-- 模型配置 Tab -->
        <div id="tabModel" class="space-y-5">
            <div>
                <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50 mb-2 block">预设模型</label>
                <select id="settingsModel" onchange="onSettingsModelChange()" class="w-full bg-surface-container-high border-none text-on-surface rounded-lg py-3 px-4 text-sm">
                    <option value="ollama-local">Ollama 本地 (Qwen2.5-3B)</option>
                    <option value="deepseek">DeepSeek-V3</option>
                    <option value="deepseek-reasoner">DeepSeek-R1</option>
                    <option value="custom">自定义...</option>
                </select>
            </div>

            <div id="settingsCustomModel" class="hidden space-y-3">
                <div>
                    <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50 mb-1.5 block">Base URL</label>
                    <input id="settingsBaseUrl" type="text" placeholder="例如: https://api.openai.com/v1" class="w-full bg-surface-container-high border-none rounded-lg py-2.5 px-3 text-sm text-on-surface placeholder-on-surface/30"/>
                </div>
                <div>
                    <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50 mb-1.5 block">API Key</label>
                    <input id="settingsApiKey" type="password" placeholder="sk-..." class="w-full bg-surface-container-high border-none rounded-lg py-2.5 px-3 text-sm text-on-surface placeholder-on-surface/30"/>
                </div>
                <div>
                    <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50 mb-1.5 block">模型 ID</label>
                    <input id="settingsModelId" type="text" placeholder="例如: gpt-4o" class="w-full bg-surface-container-high border-none rounded-lg py-2.5 px-3 text-sm text-on-surface placeholder-on-surface/30"/>
                </div>
            </div>

            <button onclick="saveSettingsModel()" class="w-full bg-primary-container text-white text-sm font-bold py-3 rounded-lg hover:opacity-90 transition-opacity">保存模型配置</button>
            <div id="settingsModelStatus" class="text-[11px] text-center"></div>
        </div>

        <!-- 通用设置 Tab -->
        <div id="tabGeneral" class="hidden space-y-5">
            <!-- 知识领域 -->
            <div>
                <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50 mb-2 block">知识领域</label>
                <select id="settingsDomain" class="w-full bg-surface-container-high border-none text-on-surface rounded-lg py-3 px-4 text-sm">
                    <option value="">全部领域</option>
                    <option value="通识">通识</option>
                    <option value="AI/ML">AI/ML</option>
                    <option value="编程">编程</option>
                    <option value="面试">面试</option>
                </select>
            </div>

            <!-- 返回结果数 -->
            <div>
                <div class="flex justify-between items-center mb-2">
                    <label class="text-[10px] font-black uppercase tracking-widest text-on-surface/50">返回结果数</label>
                    <span id="settingsTopkVal" class="text-xs font-mono text-primary bg-primary/10 px-2 py-0.5 rounded">5</span>
                </div>
                <input type="range" id="settingsTopk" min="1" max="10" value="5" class="w-full accent-primary" oninput="document.getElementById('settingsTopkVal').textContent=this.value">
            </div>

            <!-- 统计 -->
            <div class="bg-surface-container-low rounded-xl p-4">
                <div class="text-xs font-bold text-on-surface/50 mb-3">知识库统计</div>
                <div id="settingsStats" class="text-xs text-on-surface/70 space-y-1.5">
                    <div class="flex justify-between"><span>总笔记</span><span class="text-primary font-bold" id="statNotes">-</span></div>
                    <div class="flex justify-between"><span>总片段</span><span class="text-primary font-bold" id="statChunks">-</span></div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
const API_BASE = '';
let currentSessionId = null;
let sessions = [];
let token = localStorage.getItem('sb_token');
let isLoggedIn = false;

// ---- 认证 ----

function checkAuth() {{
    if (token) {{
        showMainApp();
    }} else {{
        document.getElementById('loginPage').classList.remove('hidden');
        document.getElementById('mainApp').classList.add('hidden');
    }}
}}

function switchTab(tab) {{
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const tabLogin = document.getElementById('tabLogin');
    const tabRegister = document.getElementById('tabRegister');
    const errorEl = document.getElementById('loginError');
    const successEl = document.getElementById('loginSuccess');
    if (errorEl) errorEl.classList.add('hidden');
    if (successEl) successEl.classList.add('hidden');

    if (tab === 'login') {{
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
        tabLogin.classList.add('bg-primary-container', 'text-white');
        tabLogin.classList.remove('text-on-surface/60');
        tabRegister.classList.remove('bg-primary-container', 'text-white');
        tabRegister.classList.add('text-on-surface/60');
    }} else {{
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
        tabRegister.classList.add('bg-primary-container', 'text-white');
        tabRegister.classList.remove('text-on-surface/60');
        tabLogin.classList.remove('bg-primary-container', 'text-white');
        tabLogin.classList.add('text-on-surface/60');
    }}
}}

function showMainApp() {{
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('mainApp').classList.remove('hidden');
    loadSessions();
    loadStats();
    loadUserInfo();
}}

async function handleLogin() {{
    const login = document.getElementById('loginInput').value.trim();
    const password = document.getElementById('loginPassword').value.trim();
    const errorEl = document.getElementById('loginError');

    if (!login || !password) {{
        errorEl.textContent = '请填写用户名/邮箱和密码';
        errorEl.classList.remove('hidden');
        return;
    }}

    try {{
        const resp = await fetch('/api/v1/auth/login', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ login, password }}),
        }});
        const data = await resp.json();
        if (data.token) {{
            token = data.token;
            localStorage.setItem('sb_token', token);
            isLoggedIn = true;
            showMainApp();
        }} else {{
            errorEl.textContent = data.error || '登录失败';
            errorEl.classList.remove('hidden');
        }}
    }} catch(e) {{
        errorEl.textContent = '网络错误';
        errorEl.classList.remove('hidden');
    }}
}}

async function handleRegister() {{
    const username = document.getElementById('regUsername').value.trim();
    const email = document.getElementById('regEmail').value.trim();
    const verifyCode = document.getElementById('regCode').value.trim();
    const password = document.getElementById('regPassword').value.trim();
    const errorEl = document.getElementById('loginError');
    const successEl = document.getElementById('loginSuccess');

    if (!username || !email || !verifyCode || !password) {{
        errorEl.textContent = '请填写所有字段';
        errorEl.classList.remove('hidden');
        return;
    }}
    if (username.length < 3) {{
        errorEl.textContent = '用户名至少3个字符';
        errorEl.classList.remove('hidden');
        return;
    }}
    if (password.length < 6) {{
        errorEl.textContent = '密码至少6个字符';
        errorEl.classList.remove('hidden');
        return;
    }}

    try {{
        const resp = await fetch('/api/v1/auth/register', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ username, email, password, verify_code: verifyCode }}),
        }});
        const data = await resp.json();
        if (data.token) {{
            token = data.token;
            localStorage.setItem('sb_token', token);
            isLoggedIn = true;
            successEl.textContent = '注册成功！';
            successEl.classList.remove('hidden');
            errorEl.classList.add('hidden');
            showMainApp();
        }} else {{
            errorEl.textContent = data.error || '注册失败';
            errorEl.classList.remove('hidden');
        }}
    }} catch(e) {{
        errorEl.textContent = '网络错误';
        errorEl.classList.remove('hidden');
    }}
}}

let codeCooldown = 0;
async function sendVerifyCode() {{
    const email = document.getElementById('regEmail').value.trim();
    const btn = document.getElementById('sendCodeBtn');
    const errorEl = document.getElementById('loginError');

    if (!email) {{
        errorEl.textContent = '请先填写邮箱';
        errorEl.classList.remove('hidden');
        return;
    }}

    if (codeCooldown > 0) return;

    try {{
        const resp = await fetch('/api/v1/auth/send-code', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ email }}),
        }});
        const data = await resp.json();
        if (data.status === 'ok') {{
            codeCooldown = 60;
            btn.textContent = `${{codeCooldown}}s`;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            const timer = setInterval(() => {{
                codeCooldown--;
                if (codeCooldown <= 0) {{
                    clearInterval(timer);
                    btn.textContent = '获取验证码';
                    btn.classList.remove('opacity-50', 'cursor-not-allowed');
                }} else {{
                    btn.textContent = `${{codeCooldown}}s`;
                }}
            }}, 1000);
        }} else {{
            errorEl.textContent = data.error || '发送失败';
            errorEl.classList.remove('hidden');
        }}
    }} catch(e) {{
        errorEl.textContent = '网络错误';
        errorEl.classList.remove('hidden');
    }}
}}

async function loadUserInfo() {{
    if (!token) return;
    try {{
        const resp = await fetch('/api/v1/auth/me', {{
            headers: {{ 'Authorization': 'Bearer ' + token }},
        }});
        if (resp.ok) {{
            const data = await resp.json();
            isLoggedIn = true;
            // 可以在界面上显示用户信息
        }}
    }} catch(e) {{}}
}}

function logout() {{
    token = null;
    localStorage.removeItem('sb_token');
    location.reload();
}}

// ---- 会话管理 ----

async function loadSessions() {{
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/sessions', {{ headers }});
        if (!resp.ok) {{
            console.error('加载会话列表失败:', resp.status, resp.statusText);
            return;
        }}
        const data = await resp.json();
        sessions = data.sessions || [];
        renderSessions();
    }} catch(e) {{
        console.error('加载会话列表异常:', e);
    }}
}}

function renderSessions() {{
    const list = document.getElementById('sessionList');
    if (!sessions.length) {{
        list.innerHTML = '<div class="text-xs text-on-surface/30 text-center py-8">暂无历史对话</div>';
        return;
    }}

    list.innerHTML = sessions.map(s => {{
        const isActive = s.session_id === currentSessionId;
        const time = new Date(s.updated_at).toLocaleDateString('zh-CN', {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }});
        return `
            <div onclick="loadSession('${{s.session_id}}')" class="group cursor-pointer px-3 py-2.5 rounded-xl ${{isActive ? 'bg-primary/10' : 'hover:bg-white/5'}} transition-colors">
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-sm text-on-surface/40">chat_bubble</span>
                    <div class="flex-1 min-w-0">
                        <div class="text-xs font-medium truncate ${{isActive ? 'text-primary' : 'text-on-surface/80'}}">对话 ${{s.session_id.slice(0,8)}}</div>
                        <div class="text-[10px] text-on-surface/40">${{time}} · ${{s.msg_count}} 条消息</div>
                    </div>
                    <button onclick="event.stopPropagation(); deleteSession('${{s.session_id}}')" class="opacity-0 group-hover:opacity-100 material-symbols-outlined text-xs text-on-surface/40 hover:text-red-400 transition-opacity">delete</button>
                </div>
            </div>
        `;
    }}).join('');
}}

async function newChat() {{
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }} : {{ 'Content-Type': 'application/json' }};
        const resp = await fetch('/api/v1/sessions', {{ method: 'POST', headers }});
        const data = await resp.json();
        currentSessionId = data.session_id;
        document.getElementById('currentSessionTitle').textContent = '新对话';
        // 重置为欢迎消息
        document.getElementById('messages').innerHTML = `
            <div class="max-w-2xl mx-auto flex flex-col gap-3">
                <div class="flex items-center gap-2">
                    <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center">
                        <span class="material-symbols-outlined text-xs text-white">psychology</span>
                    </div>
                    <span class="text-xs font-medium text-on-surface/50">AI Assistant</span>
                </div>
                <div class="bg-surface-container-low p-4 rounded-xl text-on-surface text-sm leading-relaxed border-l-2 border-primary/30">
                    你好！我是 SecondBrain Chat，基于你的知识库回答问题。试试问我点什么吧！
                </div>
            </div>
        `;
        await loadSessions();
        if (window.innerWidth < 768) toggleHistoryDrawer();
    }} catch(e) {{}}
}}

async function loadSession(sessionId) {{
    currentSessionId = sessionId;
    document.getElementById('currentSessionTitle').textContent = '对话 ' + sessionId.slice(0,8);
    renderSessions();

    // 加载历史消息
    const messagesDiv = document.getElementById('messages');
    messagesDiv.innerHTML = '';

    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/sessions/' + sessionId + '/messages', {{ headers }});
        const data = await resp.json();
        const messages = data.messages || [];

        if (messages.length === 0) {{
            // 显示欢迎消息
            messagesDiv.innerHTML = `
                <div class="max-w-2xl mx-auto flex flex-col gap-3">
                    <div class="flex items-center gap-2">
                        <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center">
                            <span class="material-symbols-outlined text-xs text-white">psychology</span>
                        </div>
                        <span class="text-xs font-medium text-on-surface/50">AI Assistant</span>
                    </div>
                    <div class="bg-surface-container-low p-4 rounded-xl text-on-surface text-sm leading-relaxed border-l-2 border-primary/30">
                        你好！我是 SecondBrain Chat，基于你的知识库回答问题。试试问我点什么吧！
                    </div>
                </div>
            `;
        }} else {{
            // 渲染历史消息（无动画、无光标）
            for (const msg of messages) {{
                if (msg.role === 'user') {{
                    const wrapper = document.createElement('div');
                    wrapper.className = 'max-w-2xl mx-auto flex flex-col gap-2';
                    wrapper.innerHTML = `
                        <div class="flex justify-end items-start gap-2">
                            <div class="bg-gradient-to-br from-primary-container to-blue-600 text-white px-4 py-2.5 rounded-2xl text-sm max-w-[85%] md:max-w-[70%] leading-relaxed">
                                ${{escapeHtml(msg.content)}}
                            </div>
                            <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center shrink-0 mt-0.5">
                                <span class="material-symbols-outlined text-white" style="font-size: 14px;">person</span>
                            </div>
                        </div>
                    `;
                    messagesDiv.appendChild(wrapper);
                }} else if (msg.role === 'assistant') {{
                    addMessage('assistant', msg.content, msg.sources || [], {{ showCursor: false, animated: false }});
                }}
            }}
            scrollMessagesToBottom();
        }}
    }} catch(e) {{
        // 加载失败时显示欢迎消息
        messagesDiv.innerHTML = `
            <div class="max-w-2xl mx-auto flex flex-col gap-3">
                <div class="flex items-center gap-2">
                    <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center">
                        <span class="material-symbols-outlined text-xs text-white">psychology</span>
                    </div>
                    <span class="text-xs font-medium text-on-surface/50">AI Assistant</span>
                </div>
                <div class="bg-surface-container-low p-4 rounded-xl text-on-surface text-sm leading-relaxed border-l-2 border-primary/30">
                    你好！我是 SecondBrain Chat，基于你的知识库回答问题。试试问我点什么吧！
                </div>
            </div>
        `;
    }}

    if (window.innerWidth < 768) toggleHistoryDrawer();
}}

async function deleteSession(sessionId) {{
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        await fetch('/api/v1/sessions/' + sessionId, {{ method: 'DELETE', headers }});
        if (currentSessionId === sessionId) {{
            currentSessionId = null;
            document.getElementById('currentSessionTitle').textContent = '新对话';
            document.getElementById('messages').innerHTML = `
                <div class="max-w-2xl mx-auto flex flex-col gap-3">
                    <div class="flex items-center gap-2">
                        <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center">
                            <span class="material-symbols-outlined text-xs text-white">psychology</span>
                        </div>
                        <span class="text-xs font-medium text-on-surface/50">AI Assistant</span>
                    </div>
                    <div class="bg-surface-container-low p-4 rounded-xl text-on-surface text-sm leading-relaxed border-l-2 border-primary/30">
                        你好！我是 SecondBrain Chat，基于你的知识库回答问题。试试问我点什么吧！
                    </div>
                </div>
            `;
        }}
        await loadSessions();
    }} catch(e) {{}}
}}

// ---- 抽屉控制 ----

function toggleHistoryDrawer() {{
    const drawer = document.getElementById('historyDrawer');
    const overlay = document.getElementById('historyOverlay');
    drawer.classList.toggle('drawer-open');
    overlay.classList.toggle('hidden');
}}

function openSettings() {{
    document.getElementById('settingsOverlay').classList.remove('hidden');
    document.getElementById('settingsModal').classList.remove('hidden');
    document.getElementById('settingsModal').classList.add('flex');
    switchSettingsTab('model');
    loadSettingsStats();
    loadCurrentModelConfig();
}}

async function loadCurrentModelConfig() {{
    // 从后端拉取当前生效的模型配置并回填 UI（修复刷新后配置丢失问题）
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/models', {{ headers }});
        if (!resp.ok) return;
        const data = await resp.json();
        const cur = data.current || {{}};
        const select = document.getElementById('settingsModel');
        if (select && cur.preset) {{
            select.value = cur.preset;
            onSettingsModelChange();
        }}
        if (cur.preset === 'custom') {{
            const baseUrlEl = document.getElementById('settingsBaseUrl');
            const apiKeyEl = document.getElementById('settingsApiKey');
            const modelIdEl = document.getElementById('settingsModelId');
            if (baseUrlEl) baseUrlEl.value = cur.base_url || '';
            if (modelIdEl) modelIdEl.value = cur.model || '';
            // api_key 后端返回 *** 占位，留空让用户重新输入
            if (apiKeyEl) apiKeyEl.placeholder = cur.api_key === '***' ? '已配置（如需修改请重新输入）' : 'sk-...';
        }}
    }} catch(e) {{}}
}}

function closeSettings() {{
    document.getElementById('settingsOverlay').classList.add('hidden');
    document.getElementById('settingsModal').classList.add('hidden');
    document.getElementById('settingsModal').classList.remove('flex');
}}

function switchSettingsTab(tab) {{
    const tabModel = document.getElementById('tabModel');
    const tabGeneral = document.getElementById('tabGeneral');
    const tabModelBtn = document.getElementById('tabModelBtn');
    const tabGeneralBtn = document.getElementById('tabGeneralBtn');

    if (tab === 'model') {{
        tabModel.classList.remove('hidden');
        tabGeneral.classList.add('hidden');
        tabModelBtn.classList.add('text-primary', 'border-b-2', 'border-primary');
        tabModelBtn.classList.remove('text-on-surface/50');
        tabGeneralBtn.classList.remove('text-primary', 'border-b-2', 'border-primary');
        tabGeneralBtn.classList.add('text-on-surface/50');
    }} else {{
        tabModel.classList.add('hidden');
        tabGeneral.classList.remove('hidden');
        tabGeneralBtn.classList.add('text-primary', 'border-b-2', 'border-primary');
        tabGeneralBtn.classList.remove('text-on-surface/50');
        tabModelBtn.classList.remove('text-primary', 'border-b-2', 'border-primary');
        tabModelBtn.classList.add('text-on-surface/50');
    }}
}}

// ---- 设置 ----

async function loadStats() {{
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/stats', {{ headers }});
        const data = await resp.json();
        const statNotes = document.getElementById('statNotes');
        const statChunks = document.getElementById('statChunks');
        if (statNotes) statNotes.textContent = data.total_notes || 0;
        if (statChunks) statChunks.textContent = data.total_chunks || 0;
    }} catch(e) {{}}
}}

async function loadSettingsStats() {{
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/stats', {{ headers }});
        const data = await resp.json();
        document.getElementById('statNotes').textContent = data.total_notes || 0;
        document.getElementById('statChunks').textContent = data.total_chunks || 0;
    }} catch(e) {{}}
}}

function onSettingsModelChange() {{
    const preset = document.getElementById('settingsModel').value;
    document.getElementById('settingsCustomModel').classList.toggle('hidden', preset !== 'custom');
}}

async function saveSettingsModel() {{
    const preset = document.getElementById('settingsModel').value;
    const statusEl = document.getElementById('settingsModelStatus');
    statusEl.textContent = '保存中...';
    statusEl.className = 'text-[10px] text-primary mt-1';

    let body;
    if (preset === 'custom') {{
        body = JSON.stringify({{
            base_url: document.getElementById('settingsBaseUrl').value,
            api_key: document.getElementById('settingsApiKey').value,
            model: document.getElementById('settingsModelId').value,
            temperature: 0.3,
        }});
    }} else {{
        body = JSON.stringify({{ preset: preset }});
    }}

    const headers = token ? {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }} : {{ 'Content-Type': 'application/json' }};
    try {{
        const resp = await fetch('/api/v1/models/switch', {{
            method: 'POST',
            headers: headers,
            body: body,
        }});
        const data = await resp.json();
        if (data.status === 'ok') {{
            statusEl.textContent = '已保存: ' + data.model;
            statusEl.className = 'text-[10px] text-green-400 mt-1';
        }} else {{
            statusEl.textContent = '失败: ' + (data.error || '未知错误');
            statusEl.className = 'text-[10px] text-red-400 mt-1';
        }}
    }} catch(e) {{
        statusEl.textContent = '保存失败';
        statusEl.className = 'text-[10px] text-red-400 mt-1';
    }}
}}

// ---- 聊天 ----

const messagesDiv = document.getElementById('messages');
const queryInput = document.getElementById('query');
const sendBtn = document.getElementById('sendBtn');

function scrollMessagesToBottom() {{
    requestAnimationFrame(() => {{
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        requestAnimationFrame(() => {{
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }});
    }});
}}

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

function escapeHtml(text) {{
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}}

function renderSources(sources) {{
    if (!sources || sources.length === 0) return '';
    const filtered = sources.filter(s => (s.score || 0) >= 0.2);
    if (filtered.length === 0) return '';

    let sourcesHtml = '<div class="flex flex-wrap gap-2 mt-2">';
    filtered.forEach(s => {{
        const title = escapeHtml((s.title || '未知').substring(0, 30));
        const score = ((s.score || 0) * 100).toFixed(0);
        const source = s.source || '';
        if (source && source.includes('{VAULT_NAME}')) {{
            const relPath = source.split('{VAULT_NAME}/')[1];
            const obsUrl = `obsidian://open?vault=${{encodeURIComponent('{VAULT_NAME}')}}&file=${{encodeURIComponent(relPath)}}`;
            sourcesHtml += `<a href="${{obsUrl}}" target="_blank" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs hover:bg-primary/20 transition-colors"><span class="material-symbols-outlined text-sm">link</span>${{title}} <span class="opacity-60">${{score}}%</span></a>`;
        }} else {{
            sourcesHtml += `<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white/5 text-on-surface/70 text-xs">${{title}} <span class="opacity-60">${{score}}%</span></span>`;
        }}
    }});
    sourcesHtml += '</div>';
    return sourcesHtml;
}}

function addMessage(role, content, sources = null, options = {{}}) {{
    const wrapper = document.createElement('div');
    wrapper.className = 'max-w-2xl mx-auto flex flex-col gap-2' + (options.animated === false ? '' : ' msg-bubble');

    if (role === 'user') {{
        wrapper.innerHTML = `
            <div class="flex justify-end items-start gap-2">
                <div class="bg-gradient-to-br from-primary-container to-blue-600 text-white px-4 py-2.5 rounded-2xl text-sm max-w-[85%] md:max-w-[70%] leading-relaxed">
                    ${{escapeHtml(content)}}
                </div>
                <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center shrink-0 mt-0.5">
                    <span class="material-symbols-outlined text-white" style="font-size: 14px;">person</span>
                </div>
            </div>
        `;
    }} else {{
        const cursorHtml = options.showCursor === false ? '' : '<span id="cursor" class="cursor-blink text-primary">▌</span>';

        wrapper.innerHTML = `
            <div class="flex items-center gap-2">
                <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center">
                    <span class="material-symbols-outlined text-xs text-white">psychology</span>
                </div>
                <span class="text-xs font-medium text-on-surface/50">AI Assistant</span>
            </div>
            <div class="bg-surface-container-low px-4 py-3 rounded-xl text-on-surface leading-relaxed border-l-2 border-primary/30 whitespace-pre-wrap text-sm">
                ${{escapeHtml(content)}}${{cursorHtml}}
            </div>
            ${{renderSources(sources)}}
        `;
    }}

    messagesDiv.appendChild(wrapper);
    scrollMessagesToBottom();
    return wrapper;
}}

async function send() {{
    const query = queryInput.value.trim();
    if (!query) return;

    sendBtn.disabled = true;
    sendBtn.innerHTML = '<span class="material-symbols-outlined animate-spin text-base">progress_activity</span>';

    addMessage('user', query);
    queryInput.value = '';
    queryInput.style.height = 'auto';

    if (!currentSessionId) {{
        try {{
            const headers = token ? {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }} : {{ 'Content-Type': 'application/json' }};
            const resp = await fetch('/api/v1/sessions', {{ method: 'POST', headers }});
            const data = await resp.json();
            currentSessionId = data.session_id;
            document.getElementById('currentSessionTitle').textContent = '对话 ' + currentSessionId.slice(0,8);
        }} catch(e) {{}}
    }}

    let fullAnswer = '';
    let sources = [];

    try {{
        const domain = document.getElementById('settingsDomain').value || null;
        const topk = parseInt(document.getElementById('settingsTopk').value) || 5;

        const headers = token ? {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }} : {{ 'Content-Type': 'application/json' }};
        const resp = await fetch('/api/v1/chat/stream', {{
            method: 'POST',
            headers: headers,
            body: JSON.stringify({{
                query: query,
                domain: domain,
                top_k: topk,
                session_id: currentSessionId,
            }}),
        }});

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
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
                            const contentDiv = wrapper.querySelector('.bg-surface-container-low');
                            if (contentDiv) {{
                                contentDiv.innerHTML = escapeHtml(fullAnswer) + '<span id="cursor" class="cursor-blink text-primary">▌</span>';
                            }}
                            scrollMessagesToBottom();
                        }} else if (data.type === 'sources') {{
                            sources = data.data;
                        }} else if (data.type === 'done') {{
                            const cursor = document.getElementById('cursor');
                            if (cursor) cursor.remove();
                        }}
                    }} catch(e) {{}}
                }}
            }}
        }}

        const sourcesHtml = renderSources(sources);
        if (sourcesHtml) {{
            wrapper.insertAdjacentHTML('beforeend', sourcesHtml);
        }}

        await loadSessions();

    }} catch(e) {{
        addMessage('assistant', '❌ 请求失败: ' + e.message, null, {{ showCursor: false }});
    }}

    sendBtn.disabled = false;
    sendBtn.innerHTML = '<span class="material-symbols-outlined text-base">send</span>';
    queryInput.focus();
}}

// ---- 笔记管理 ----

let notesState = {{
    page: 1,
    pageSize: 20,
    folder: null,
    domain: null,
    tag: null,
    keyword: null,
    currentNote: null,
    isEditing: false,
}};

function showNotesView() {{
    document.getElementById('chatView').classList.add('hidden');
    document.getElementById('notesView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '笔记管理';
    loadNotes();
    loadNotesFilters();
}}

function showChatView() {{
    document.getElementById('notesView').classList.add('hidden');
    document.getElementById('chatView').classList.remove('hidden');
}}

async function loadNotes() {{
    const listDiv = document.getElementById('notesList');
    listDiv.innerHTML = '<div class="text-xs text-on-surface/30 text-center py-8">加载中...</div>';

    try {{
        const params = new URLSearchParams();
        params.set('page', notesState.page);
        params.set('page_size', notesState.pageSize);
        if (notesState.folder) params.set('folder', notesState.folder);
        if (notesState.domain) params.set('domain', notesState.domain);
        if (notesState.tag) params.set('tag', notesState.tag);
        if (notesState.keyword) params.set('keyword', notesState.keyword);

        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/notes?' + params.toString(), {{ headers }});
        const data = await resp.json();

        document.getElementById('notesCount').textContent = `共 ${{data.total || 0}} 篇笔记`;
        renderNotesList(data.items || []);
        renderNotesPagination(data.total || 0, data.page || 1, data.page_size || 20);
    }} catch (e) {{
        listDiv.innerHTML = '<div class="text-xs text-red-400 text-center py-8">加载失败</div>';
    }}
}}

function renderNotesList(items) {{
    const listDiv = document.getElementById('notesList');
    if (!items.length) {{
        listDiv.innerHTML = '<div class="text-xs text-on-surface/30 text-center py-8">暂无笔记</div>';
        return;
    }}

    listDiv.innerHTML = items.map(note => {{
        const domainColor = {{
            '通识': 'bg-blue-500/10 text-blue-400',
            'AI/ML': 'bg-purple-500/10 text-purple-400',
            '编程': 'bg-green-500/10 text-green-400',
            '面试': 'bg-orange-500/10 text-orange-400',
        }}[note.domain] || 'bg-white/5 text-on-surface/50';

        const tagsHtml = (note.tags || []).map(t => `<span class="px-1.5 py-0.5 rounded bg-white/5 text-[10px] text-on-surface/50">${{escapeHtml(t)}}</span>`).join('');

        return `
            <div onclick="showNoteDetail('${{encodeURIComponent(note.relative_path)}}')" class="note-card cursor-pointer p-3 rounded-xl border border-white/5 hover:border-white/10">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <div class="text-sm font-medium text-on-surface truncate">${{escapeHtml(note.title)}}</div>
                        <div class="text-[10px] text-on-surface/40 mt-0.5 truncate">${{escapeHtml(note.folder)}} · ${{note.format}}</div>
                    </div>
                    <span class="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium ${{domainColor}}">${{escapeHtml(note.domain)}}</span>
                </div>
                <div class="flex items-center gap-2 mt-2">${{tagsHtml}}</div>
            </div>
        `;
    }}).join('');
}}

function renderNotesPagination(total, page, pageSize) {{
    const div = document.getElementById('notesPagination');
    const totalPages = Math.ceil(total / pageSize) || 1;
    if (totalPages <= 1) {{
        div.innerHTML = '';
        return;
    }}

    let html = '';
    if (page > 1) {{
        html += `<button onclick="goNotesPage(${{page - 1}})" class="px-2 py-1 rounded text-xs text-on-surface/60 hover:bg-white/5">上一页</button>`;
    }}
    html += `<span class="text-xs text-on-surface/40">${{page}} / ${{totalPages}}</span>`;
    if (page < totalPages) {{
        html += `<button onclick="goNotesPage(${{page + 1}})" class="px-2 py-1 rounded text-xs text-on-surface/60 hover:bg-white/5">下一页</button>`;
    }}
    div.innerHTML = html;
}}

function goNotesPage(p) {{
    notesState.page = p;
    loadNotes();
}}

async function loadNotesFilters() {{
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};

        // 领域
        const domainResp = await fetch('/api/v1/domains', {{ headers }});
        const domainData = await domainResp.json();
        const domains = domainData.domains || {{}};
        const domainDiv = document.getElementById('notesDomainFilters');
        domainDiv.innerHTML = Object.keys(domains).map(d => `
            <button onclick="filterNotesByDomain('${{d}}')" class="w-full text-left px-2 py-1.5 rounded-lg text-xs text-on-surface/60 hover:bg-white/5 hover:text-on-surface transition-colors ${{notesState.domain === d ? 'bg-white/5 text-on-surface' : ''}}">
                ${{escapeHtml(d)}} <span class="text-on-surface/30">(${{domains[d]}})</span>
            </button>
        `).join('');

        // 文件夹
        const folderResp = await fetch('/api/v1/folders', {{ headers }});
        const folderData = await folderResp.json();
        const folderDiv = document.getElementById('notesFolderFilters');
        folderDiv.innerHTML = (folderData.folders || []).map(f => `
            <button onclick="filterNotesByFolder('${{f}}')" class="w-full text-left px-2 py-1 rounded-lg text-xs text-on-surface/60 hover:bg-white/5 hover:text-on-surface transition-colors truncate ${{notesState.folder === f ? 'bg-white/5 text-on-surface' : ''}}">
                ${{escapeHtml(f)}}
            </button>
        `).join('');

        // 标签
        const tagResp = await fetch('/api/v1/tags?with_count=true', {{ headers }});
        const tagData = await tagResp.json();
        const tagDiv = document.getElementById('notesTagFilters');
        tagDiv.innerHTML = (tagData.tags || []).slice(0, 20).map(t => `
            <button onclick="filterNotesByTag('${{t.name}}')" class="px-2 py-1 rounded-lg text-[10px] text-on-surface/60 hover:bg-white/5 hover:text-on-surface transition-colors ${{notesState.tag === t.name ? 'bg-white/5 text-on-surface' : ''}}">
                ${{escapeHtml(t.name)}}${{t.count ? ` · ${{t.count}}` : ''}}
            </button>
        `).join('');
    }} catch (e) {{}}
}}

function filterNotesByDomain(d) {{
    notesState.domain = notesState.domain === d ? null : d;
    notesState.page = 1;
    loadNotes();
    loadNotesFilters();
}}

function filterNotesByFolder(f) {{
    notesState.folder = notesState.folder === f ? null : f;
    notesState.page = 1;
    loadNotes();
    loadNotesFilters();
}}

function filterNotesByTag(t) {{
    notesState.tag = notesState.tag === t ? null : t;
    notesState.page = 1;
    loadNotes();
    loadNotesFilters();
}}

async function searchNotes() {{
    const q = document.getElementById('notesSearchInput').value.trim();
    if (!q) {{
        notesState.keyword = null;
        notesState.page = 1;
        loadNotes();
        return;
    }}
    // 使用全文搜索 API
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/notes/search?q=' + encodeURIComponent(q), {{ headers }});
        const data = await resp.json();
        document.getElementById('notesCount').textContent = `搜索 "${{escapeHtml(q)}}" 找到 ${{(data.results || []).length}} 个结果`;
        renderNotesSearchResults(data.results || []);
        document.getElementById('notesPagination').innerHTML = '';
    }} catch (e) {{}}
}}

function renderNotesSearchResults(results) {{
    const listDiv = document.getElementById('notesList');
    if (!results.length) {{
        listDiv.innerHTML = '<div class="text-xs text-on-surface/30 text-center py-8">无搜索结果</div>';
        return;
    }}
    listDiv.innerHTML = results.map(r => {{
        const note = r.note;
        const chunks = (r.matched_chunks || []).map(c => `<div class="text-[10px] text-on-surface/40 truncate">${{escapeHtml(c)}}</div>`).join('');
        return `
            <div onclick="showNoteDetail('${{encodeURIComponent(note.relative_path)}}')" class="note-card cursor-pointer p-3 rounded-xl border border-white/5 hover:border-white/10">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-medium text-primary">${{(r.score * 100).toFixed(0)}}%</span>
                    <span class="text-sm font-medium text-on-surface truncate">${{escapeHtml(note.title)}}</span>
                </div>
                <div class="text-[10px] text-on-surface/40 mt-0.5">${{escapeHtml(note.folder)}}</div>
                <div class="mt-1 space-y-0.5">${{chunks}}</div>
            </div>
        `;
    }}).join('');
}}

async function showNoteDetail(encodedPath) {{
    const relativePath = decodeURIComponent(encodedPath);
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/notes/' + encodeURIComponent(relativePath), {{ headers }});
        const note = await resp.json();
        if (note.error) return;

        notesState.currentNote = note;
        document.getElementById('notesListView').classList.add('hidden');
        document.getElementById('noteDetailView').classList.remove('hidden');
        document.getElementById('noteEditorView').classList.add('hidden');
        document.getElementById('notesNavTitle').textContent = note.title;

        // 面包屑
        document.getElementById('noteBreadcrumb').innerHTML = `
            <button onclick="backToNotesList()" class="hover:text-on-surface transition-colors">笔记管理</button>
            <span class="text-on-surface/20">/</span>
            <span class="truncate">${{escapeHtml(note.folder)}}</span>
            <span class="text-on-surface/20">/</span>
            <span class="truncate">${{escapeHtml(note.title)}}</span>
        `;

        // 元数据
        document.getElementById('noteDomainBadge').textContent = note.domain;
        document.getElementById('noteDate').textContent = note.date || '';
        document.getElementById('noteWordCount').textContent = note.word_count ? `${{note.word_count}} 字` : '';

        // 标签
        const tagsDiv = document.getElementById('noteTags');
        tagsDiv.innerHTML = (note.tags || []).map(t => `<span class="px-2 py-0.5 rounded-full bg-white/5 text-xs text-on-surface/60">${{escapeHtml(t)}}</span>`).join('');

        // 内容（Markdown 渲染）
        if (note.format === 'markdown') {{
            document.getElementById('noteContent').innerHTML = marked.parse(note.content || '');
            document.getElementById('noteDownloadBtn').classList.add('hidden');
        }} else {{
            document.getElementById('noteContent').innerHTML = `
                <div class="text-sm text-on-surface/50 text-center py-12">
                    <div class="material-symbols-outlined text-4xl text-on-surface/20 mb-2">description</div>
                    <div>此格式不支持在线预览</div>
                    <div class="text-xs text-on-surface/30 mt-1">${{escapeHtml(note.format || '')}}</div>
                </div>
            `;
            document.getElementById('noteDownloadBtn').classList.remove('hidden');
        }}

        // 双向链接
        const linksDiv = document.getElementById('noteOutboundLinks');
        if (note.outbound_links && note.outbound_links.length) {{
            linksDiv.classList.remove('hidden');
            document.getElementById('noteOutboundLinksList').innerHTML = note.outbound_links.map(l => `
                <span class="px-2 py-0.5 rounded-lg bg-primary/10 text-primary text-xs cursor-pointer hover:bg-primary/20 transition-colors">[[${{escapeHtml(l)}}]]</span>
            `).join('');
        }} else {{
            linksDiv.classList.add('hidden');
        }}
    }} catch (e) {{}}
}}

function backToNotesList() {{
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.add('hidden');
    document.getElementById('notesListView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '笔记管理';
    notesState.currentNote = null;
    notesState.isEditing = false;
}}

function editCurrentNote() {{
    const note = notesState.currentNote;
    if (!note) return;
    if (note.format !== 'markdown') {{
        alert('仅支持编辑 Markdown 笔记');
        return;
    }}
    notesState.isEditing = true;
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '编辑笔记';

    document.getElementById('editorNotePath').value = note.relative_path;
    document.getElementById('editorNotePath').readOnly = true;
    document.getElementById('editorNoteTags').value = (note.tags || []).join(', ');
    document.getElementById('editorNoteDate').value = note.date || '';
    document.getElementById('editorNoteContent').value = note.raw_content || note.content || '';
    updateEditorPreview();
}}

function showNoteEditor() {{
    if (!isLoggedIn) {{
        alert('需要登录后才能新建笔记');
        return;
    }}
    notesState.isEditing = false;
    notesState.currentNote = null;
    document.getElementById('notesListView').classList.add('hidden');
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '新建笔记';

    document.getElementById('editorNotePath').value = '';
    document.getElementById('editorNotePath').readOnly = false;
    document.getElementById('editorNoteTags').value = '';
    document.getElementById('editorNoteDate').value = '';
    document.getElementById('editorNoteContent').value = '# 标题\n\n正文内容...\n';
    updateEditorPreview();
}}

function cancelEdit() {{
    if (notesState.currentNote) {{
        document.getElementById('noteEditorView').classList.add('hidden');
        document.getElementById('noteDetailView').classList.remove('hidden');
        document.getElementById('notesNavTitle').textContent = notesState.currentNote.title;
    }} else {{
        backToNotesList();
    }}
}}

function updateEditorPreview() {{
    const content = document.getElementById('editorNoteContent').value;
    const previewDiv = document.getElementById('editorNotePreview');
    if (previewDiv) {{
        previewDiv.innerHTML = marked.parse(content || '');
    }}
}}

document.getElementById('editorNoteContent').addEventListener('input', updateEditorPreview);

async function saveNote() {{
    const path = document.getElementById('editorNotePath').value.trim();
    const tagsStr = document.getElementById('editorNoteTags').value.trim();
    const date = document.getElementById('editorNoteDate').value || null;
    const content = document.getElementById('editorNoteContent').value;

    if (!path) {{
        alert('请填写文件路径');
        return;
    }}
    if (!path.endsWith('.md')) {{
        alert('文件路径必须以 .md 结尾');
        return;
    }}

    const tags = tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(Boolean) : [];

    try {{
        const headers = {{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token,
        }};

        let resp;
        if (notesState.isEditing && notesState.currentNote) {{
            // 更新
            resp = await fetch('/api/v1/notes/' + encodeURIComponent(notesState.currentNote.relative_path), {{
                method: 'PUT',
                headers,
                body: JSON.stringify({{ content, tags, date }}),
            }});
        }} else {{
            // 新建：需要提取标题
            const titleMatch = content.match(/^#\s+(.+)$/m);
            const title = titleMatch ? titleMatch[1].trim() : path.replace('.md', '').split('/').pop();
            resp = await fetch('/api/v1/notes', {{
                method: 'POST',
                headers,
                body: JSON.stringify({{ relative_path: path, title, content, tags, date }}),
            }});
        }}

        const data = await resp.json();
        if (data.error) {{
            alert(data.error);
            return;
        }}

        // 保存成功，刷新列表并返回
        notesState.currentNote = data;
        notesState.isEditing = false;
        await loadNotes();
        showNoteDetail(encodeURIComponent(data.relative_path));
    }} catch (e) {{
        alert('保存失败: ' + e.message);
    }}
}}

async function deleteCurrentNote() {{
    const note = notesState.currentNote;
    if (!note) return;
    if (!confirm(`确定要删除笔记 "${{note.title}}" 吗？此操作不可恢复。`)) return;

    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        await fetch('/api/v1/notes/' + encodeURIComponent(note.relative_path), {{ method: 'DELETE', headers }});
        backToNotesList();
        await loadNotes();
    }} catch (e) {{
        alert('删除失败');
    }}
}}

function downloadCurrentNote() {{
    const note = notesState.currentNote;
    if (!note) return;
    window.open('/api/v1/documents/download/' + encodeURIComponent(note.relative_path), '_blank');
}}

function refreshNotes() {{
    loadNotes();
    loadNotesFilters();
}}

// ---- 初始化 ----
checkAuth();
</script>
</body>
</html>
'''
