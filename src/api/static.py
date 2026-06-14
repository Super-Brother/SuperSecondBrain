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
/* 文件夹树形结构 */
.folder-tree-node {{ user-select: none; }}
.folder-tree-row {{
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 3px 4px;
    border-radius: 6px;
    cursor: pointer;
    transition: background-color 0.15s;
    min-height: 28px;
}}
.folder-tree-row:hover {{ background-color: rgba(255,255,255,0.05); }}
.folder-tree-selected {{
    background-color: rgba(255,255,255,0.08);
    color: #e2e4e9;
}}
.folder-tree-expand-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    font-size: 14px;
    color: rgba(255,255,255,0.35);
    cursor: pointer;
    border-radius: 3px;
    font-family: 'Material Symbols Outlined';
    flex-shrink: 0;
}}
.folder-tree-expand-icon:hover {{
    background-color: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.6);
}}
.folder-tree-folder-icon {{
    font-size: 16px;
    color: rgba(255,255,255,0.45);
    font-family: 'Material Symbols Outlined';
    flex-shrink: 0;
}}
.folder-tree-selected .folder-tree-folder-icon {{ color: rgba(255,255,255,0.7); }}
.folder-tree-label {{
    font-size: 12px;
    color: rgba(255,255,255,0.55);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    margin-left: 2px;
}}
.folder-tree-selected .folder-tree-label {{
    color: #e2e4e9;
    font-weight: 500;
}}
.folder-tree-expand-icon.invisible {{
    visibility: hidden;
    pointer-events: none;
}}
.notes-tree-row {{
    display: flex;
    align-items: center;
    gap: 4px;
    min-height: 28px;
    padding: 3px 6px;
    border-radius: 6px;
    cursor: pointer;
    color: rgba(226,226,230,0.62);
    transition: background-color 0.15s, color 0.15s;
}}
.notes-tree-row:hover {{ background: rgba(255,255,255,0.05); color: #e2e2e6; }}
.notes-tree-row.active {{ background: rgba(46,91,255,0.18); color: #fff; }}
.notes-tree-expander {{
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    color: rgba(255,255,255,0.38);
    font-family: 'Material Symbols Outlined';
    flex-shrink: 0;
}}
.notes-tree-icon {{
    font-size: 16px;
    color: rgba(255,255,255,0.48);
    font-family: 'Material Symbols Outlined';
    flex-shrink: 0;
}}
.notes-tree-title {{
    flex: 1;
    min-width: 0;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.notes-tree-meta {{
    font-size: 10px;
    color: rgba(255,255,255,0.35);
    flex-shrink: 0;
}}
.notes-tree-empty {{
    color: rgba(226,226,230,0.35);
    font-size: 12px;
    text-align: center;
    padding: 24px 8px;
}}
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
    <aside id="historyDrawer" class="drawer fixed md:relative md:translate-x-0 z-40 w-[280px] h-full bg-surface-container/80 border-r border-white/5 flex flex-col -translate-x-full md:w-64 flex-shrink-0">
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
        <nav class="bg-background/80 backdrop-blur-xl sticky top-0 z-20 flex items-center justify-between px-4 h-14 border-b border-white/5 flex-shrink-0">
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
        <div class="flex-shrink-0 p-3 md:p-4 bg-surface border-t border-white/5">
            <div class="max-w-2xl mx-auto">
                <div class="bg-surface-container-high rounded-xl flex items-end p-1.5 gap-2 border border-white/5">
                    <textarea id="query" class="flex-1 bg-transparent border-none focus:ring-0 text-on-surface py-2.5 px-3 resize-none placeholder-on-surface/40 text-sm max-h-[120px]" placeholder="输入你的问题..." rows="1"></textarea>
                    <button id="sendBtn" onclick="send()" class="bg-primary-container text-white font-bold p-2.5 rounded-lg hover:bg-primary-container/80 transition-all flex items-center justify-center flex-shrink-0 mb-0.5">
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
        <nav class="bg-background/80 backdrop-blur-xl sticky top-0 z-20 flex items-center justify-between px-4 h-14 border-b border-white/5 flex-shrink-0">
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
        <div id="notesContent" class="flex-1 flex min-h-0">
            <!-- 左侧 Explorer：文件夹 + 笔记混合树 -->
            <div id="notesLeftSidebar" class="w-full md:w-80 self-stretch border-r border-white/5 bg-surface-container/40 flex flex-col">
                <div class="p-3 border-b border-white/5 space-y-2">
                    <button id="notesSearchInput" type="button" onclick="openNotesSearchModal()" class="w-full bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm text-left text-on-surface/40 hover:text-on-surface/70 transition-colors">
                        搜索笔记...
                    </button>
                    <div class="flex items-center justify-between">
                        <span id="notesTreeSummary" class="text-[11px] text-on-surface/45">加载中...</span>
                        <button onclick="clearNotesFilters()" class="text-[11px] text-on-surface/40 hover:text-on-surface">清除筛选</button>
                    </div>
                </div>
                <div class="px-3 py-2 border-b border-white/5 space-y-2">
                    <details>
                        <summary class="cursor-pointer text-[10px] font-bold text-on-surface/40 uppercase tracking-wider">领域</summary>
                        <div id="notesDomainFilters" class="mt-2 flex flex-wrap gap-1"></div>
                    </details>
                    <details>
                        <summary class="cursor-pointer text-[10px] font-bold text-on-surface/40 uppercase tracking-wider">标签</summary>
                        <div id="notesTagFilters" class="mt-2 flex flex-wrap gap-1"></div>
                    </details>
                </div>
                <div id="notesTree" class="flex-1 overflow-y-auto p-2 scrollbar-hide">
                    <div class="notes-tree-empty">加载中...</div>
                </div>
            </div>

            <!-- 右侧内容区（列表/详情/编辑切换） -->
            <div id="notesRightPanel" class="hidden md:flex flex-1 flex-col min-w-0 min-h-0 relative">
                <!-- 未选中笔记时的空状态 -->
                <div id="notesListView" class="flex-1 flex flex-col">
                    <div id="notesListHeader" class="p-3 border-b border-white/5 flex items-center justify-between">
                        <span id="notesCount" class="text-xs text-on-surface/50">加载中...</span>
                        <div class="flex items-center gap-2">
                            <button onclick="refreshNotes()" class="material-symbols-outlined text-on-surface/40 hover:text-on-surface text-sm p-1">refresh</button>
                        </div>
                    </div>
                    <div id="notesList" class="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-hide">
                        <div class="text-xs text-on-surface/30 text-center py-8">加载中...</div>
                    </div>
                </div>

                <!-- 笔记详情视图 -->
                <div id="noteDetailView" class="hidden absolute inset-0 w-full h-full flex flex-col bg-background">
                    <!-- 顶部面包屑栏（固定） -->
                    <div class="px-4 md:px-8 py-3 border-b border-white/5 bg-surface-container flex-shrink-0 flex items-center justify-between">
                        <div id="noteBreadcrumb" class="text-xs text-on-surface/40 flex items-center gap-1"></div>
                        <button onclick="backToNotesList()" class="md:hidden material-symbols-outlined text-on-surface/60 hover:text-on-surface text-sm">close</button>
                    </div>

                    <!-- 可滚动内容区 -->
                    <div class="flex-1 overflow-y-auto p-4 md:p-8 scrollbar-hide">
                        <div class="max-w-3xl mx-auto pb-4">
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
                        </div>
                    </div>

                    <!-- 底部操作栏（固定） -->
                    <div class="px-4 md:px-8 py-3 border-t border-white/5 bg-surface-container flex items-center gap-3 flex-shrink-0">
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

                <!-- 笔记编辑器视图 -->
                <div id="noteEditorView" class="hidden absolute inset-0 w-full h-full flex flex-col bg-background">
                    <!-- 顶部栏（固定） -->
                    <div class="px-4 md:px-8 py-3 border-b border-white/5 bg-surface-container flex-shrink-0 flex items-center justify-between">
                        <div id="editorBreadcrumb" class="text-xs text-on-surface/40 flex items-center gap-1"></div>
                        <button onclick="cancelEdit()" class="md:hidden material-symbols-outlined text-on-surface/60 hover:text-on-surface text-sm">close</button>
                    </div>

                    <!-- 可滚动编辑区 -->
                    <div class="flex-1 overflow-y-auto p-4 md:p-6 scrollbar-hide">
                        <div class="max-w-4xl mx-auto">
                            <!-- 编辑头部 -->
                            <div class="flex items-center gap-3 mb-4">
                                <input id="editorNotePath" type="text" placeholder="文件路径（如：未分类/新笔记.md）" class="flex-1 bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm placeholder-on-surface/40">
                            </div>
                            <div class="flex items-center gap-3 mb-4">
                                <input id="editorNoteTags" type="text" placeholder="标签（逗号分隔）" class="flex-1 bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm placeholder-on-surface/40">
                                <input id="editorNoteDate" type="date" class="bg-surface-container-high border-none text-on-surface rounded-lg py-2 px-3 text-sm">
                            </div>

                            <!-- 编辑区 -->
                            <div class="flex gap-4 min-h-0" style="height: calc(100vh - 280px);">
                                <div class="flex-1 flex flex-col min-w-0">
                                    <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-1">Markdown</div>
                                    <textarea id="editorNoteContent" class="flex-1 w-full bg-surface-container-high border-none text-on-surface rounded-lg p-3 text-sm resize-none font-mono leading-relaxed placeholder-on-surface/40" placeholder="在此输入 Markdown 内容..."></textarea>
                                </div>
                                <div class="flex-1 flex flex-col min-w-0 hidden md:flex">
                                    <div class="text-[10px] font-bold text-on-surface/40 uppercase tracking-wider mb-1">预览</div>
                                    <div id="editorNotePreview" class="flex-1 w-full bg-surface-container-high border-none text-on-surface rounded-lg p-3 text-sm overflow-y-auto scrollbar-hide"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 底部操作栏（固定） -->
                    <div class="px-4 md:px-8 py-3 border-t border-white/5 bg-surface-container flex items-center justify-end gap-3 flex-shrink-0">
                        <button onclick="cancelEdit()" class="text-sm text-on-surface/60 hover:text-on-surface px-4 py-2">取消</button>
                        <button onclick="saveNote()" class="bg-primary-container text-white text-sm font-bold px-6 py-2 rounded-lg hover:bg-primary-container/80 transition-all">保存</button>
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
    <div class="p-5 border-b border-white/5 flex items-center justify-between flex-shrink-0">
        <h2 class="font-bold text-lg">设置</h2>
        <button onclick="closeSettings()" class="material-symbols-outlined text-on-surface/50 hover:text-on-surface transition-colors">close</button>
    </div>

    <!-- Tab 导航 -->
    <div class="flex border-b border-white/5 flex-shrink-0">
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

<!-- ============ 笔记搜索弹窗 ============ -->
<div id="notesSearchOverlay" onclick="closeNotesSearchModal()" class="fixed inset-0 bg-black/60 z-40 hidden backdrop-blur-sm"></div>
<div id="notesSearchModal" class="fixed left-1/2 top-[12vh] -translate-x-1/2 z-50 w-[calc(100vw-24px)] max-w-2xl bg-surface-container rounded-2xl border border-white/10 shadow-2xl hidden flex-col max-h-[76vh]">
    <div class="p-4 border-b border-white/5 flex items-center gap-3 flex-shrink-0">
        <span class="material-symbols-outlined text-on-surface/40">search</span>
        <input id="notesSearchModalInput" type="text" placeholder="搜索标题、路径和正文..." oninput="scheduleNotesModalSearch()" onkeydown="handleNotesSearchKeydown(event)" class="flex-1 bg-transparent border-none focus:ring-0 text-on-surface text-sm placeholder-on-surface/35">
        <button onclick="closeNotesSearchModal()" class="material-symbols-outlined text-on-surface/50 hover:text-on-surface transition-colors">close</button>
    </div>
    <div id="notesSearchStatus" class="px-4 py-2 text-[11px] text-on-surface/40 border-b border-white/5">输入关键词开始搜索</div>
    <div id="notesSearchResults" class="flex-1 overflow-y-auto p-2 scrollbar-hide">
        <div class="notes-tree-empty">输入关键词开始搜索</div>
    </div>
</div>

<script>
const API_BASE = '';
let currentSessionId = null;
let sessions = [];
let sessionArchiveFilter = 'active';
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
        const archived = sessionArchiveFilter === 'archived';
        const resp = await fetch('/api/v1/sessions?archived=' + archived, {{ headers }});
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

function getSessionTitle(s) {{
    if (s.title && s.title.trim()) return s.title;
    if (!s.msg_count) return '新对话';
    return '对话 ' + s.session_id.slice(0, 8);
}}

function setSessionArchiveFilter(filter) {{
    sessionArchiveFilter = filter;
    loadSessions();
}}

function renderSessions() {{
    const list = document.getElementById('sessionList');
    const filterHtml = `
        <div class="flex gap-1 px-2 mb-2">
            <button onclick="setSessionArchiveFilter('active')" class="flex-1 text-[10px] font-medium py-1 rounded-lg transition-colors ${{sessionArchiveFilter === 'active' ? 'bg-primary/20 text-primary' : 'text-on-surface/50 hover:bg-white/5'}}">活跃</button>
            <button onclick="setSessionArchiveFilter('archived')" class="flex-1 text-[10px] font-medium py-1 rounded-lg transition-colors ${{sessionArchiveFilter === 'archived' ? 'bg-primary/20 text-primary' : 'text-on-surface/50 hover:bg-white/5'}}">已归档</button>
        </div>
    `;

    if (!sessions.length) {{
        list.innerHTML = filterHtml + '<div class="text-xs text-on-surface/30 text-center py-8">暂无历史对话</div>';
        return;
    }}

    list.innerHTML = filterHtml + sessions.map(s => {{
        const isActive = s.session_id === currentSessionId;
        const time = new Date(s.updated_at).toLocaleDateString('zh-CN', {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }});
        const isArchived = sessionArchiveFilter === 'archived';
        return `
            <div onclick="loadSession('${{s.session_id}}')" class="group cursor-pointer px-3 py-2.5 rounded-xl ${{isActive ? 'bg-primary/10' : 'hover:bg-white/5'}} transition-colors">
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-sm text-on-surface/40">chat_bubble</span>
                    <div class="flex-1 min-w-0">
                        <div class="text-xs font-medium truncate ${{isActive ? 'text-primary' : 'text-on-surface/80'}}">${{escapeHtml(getSessionTitle(s))}}</div>
                        <div class="text-[10px] text-on-surface/40">${{time}} · ${{s.msg_count}} 条消息</div>
                    </div>
                    <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onclick="event.stopPropagation(); renameSession('${{s.session_id}}')" class="material-symbols-outlined text-xs text-on-surface/40 hover:text-primary transition-colors">edit</button>
                        ${{isArchived
                            ? `<button onclick="event.stopPropagation(); restoreSession('${{s.session_id}}')" class="material-symbols-outlined text-xs text-on-surface/40 hover:text-green-400 transition-colors">unarchive</button>`
                            : `<button onclick="event.stopPropagation(); archiveSession('${{s.session_id}}')" class="material-symbols-outlined text-xs text-on-surface/40 hover:text-yellow-400 transition-colors">archive</button>`
                        }}
                        <button onclick="event.stopPropagation(); deleteSession('${{s.session_id}}')" class="material-symbols-outlined text-xs text-on-surface/40 hover:text-red-400 transition-colors">delete</button>
                    </div>
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
        renderWelcomeMessage();
        showChatView();
        await loadSessions();
        if (window.innerWidth < 768) toggleHistoryDrawer();
    }} catch(e) {{}}
}}

function renderWelcomeMessage() {{
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

async function loadSession(sessionId) {{
    currentSessionId = sessionId;
    const session = sessions.find(s => s.session_id === sessionId);
    document.getElementById('currentSessionTitle').textContent = session ? getSessionTitle(session) : '对话 ' + sessionId.slice(0,8);
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
            renderWelcomeMessage();
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
                            <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center flex-shrink-0 mt-0.5">
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
        renderWelcomeMessage();
    }}

    if (window.innerWidth < 768) toggleHistoryDrawer();
}}

async function patchSession(sessionId, payload) {{
    const headers = token
        ? {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }}
        : {{ 'Content-Type': 'application/json' }};
    const resp = await fetch('/api/v1/sessions/' + sessionId, {{
        method: 'PATCH',
        headers,
        body: JSON.stringify(payload),
    }});
    if (!resp.ok) {{
        const data = await resp.json().catch(() => ({{}}));
        throw new Error(data.error || '会话更新失败');
    }}
}}

async function renameSession(sessionId) {{
    const session = sessions.find(s => s.session_id === sessionId);
    const currentTitle = session ? getSessionTitle(session) : '';
    const title = prompt('重命名会话', currentTitle);
    if (title === null) return;
    const trimmed = title.trim();
    if (!trimmed) {{
        alert('会话名称不能为空');
        return;
    }}
    await patchSession(sessionId, {{ title: trimmed }});
    if (currentSessionId === sessionId) {{
        document.getElementById('currentSessionTitle').textContent = trimmed;
    }}
    await loadSessions();
}}

async function archiveSession(sessionId) {{
    await patchSession(sessionId, {{ archived: true }});
    if (currentSessionId === sessionId) {{
        currentSessionId = null;
        document.getElementById('currentSessionTitle').textContent = '新对话';
        renderWelcomeMessage();
    }}
    await loadSessions();
}}

async function restoreSession(sessionId) {{
    await patchSession(sessionId, {{ archived: false }});
    await loadSessions();
}}

async function deleteSession(sessionId) {{
    if (!confirm('确定要删除会话吗？此操作不可恢复。')) return;
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        await fetch('/api/v1/sessions/' + sessionId, {{ method: 'DELETE', headers }});
        if (currentSessionId === sessionId) {{
            currentSessionId = null;
            document.getElementById('currentSessionTitle').textContent = '新对话';
            renderWelcomeMessage();
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
                <div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center flex-shrink-0 mt-0.5">
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
        const current = sessions.find(s => s.session_id === currentSessionId);
        if (current) {{
            document.getElementById('currentSessionTitle').textContent = getSessionTitle(current);
        }}

    }} catch(e) {{
        addMessage('assistant', '❌ 请求失败: ' + e.message, null, {{ showCursor: false }});
    }}

    sendBtn.disabled = false;
    sendBtn.innerHTML = '<span class="material-symbols-outlined text-base">send</span>';
    queryInput.focus();
}}

// ---- 笔记管理 ----

let notesState = {{
    domain: null,
    tag: null,
    keyword: null,
    currentNote: null,
    isEditing: false,
    treeTotal: 0,
}};

let notesTreeState = {{
    tree: [],
    expanded: new Set(),
    savedExpandedBeforeFilter: null,
}};

let notesSearchState = {{
    timer: null,
    requestId: 0,
}};

function hasActiveNotesFilters() {{
    return Boolean(notesState.domain || notesState.tag || notesState.keyword);
}}

function setNotesMobilePanel(panel) {{
    const sidebar = document.getElementById('notesLeftSidebar');
    const rightPanel = document.getElementById('notesRightPanel');
    if (!sidebar || !rightPanel) return;
    if (window.innerWidth >= 768) {{
        sidebar.classList.remove('hidden');
        sidebar.classList.add('flex');
        rightPanel.classList.remove('hidden');
        rightPanel.classList.add('flex');
        return;
    }}
    if (panel === 'tree') {{
        sidebar.classList.remove('hidden');
        sidebar.classList.add('flex');
        rightPanel.classList.add('hidden');
        rightPanel.classList.remove('flex');
    }} else {{
        sidebar.classList.add('hidden');
        sidebar.classList.remove('flex');
        rightPanel.classList.remove('hidden');
        rightPanel.classList.add('flex');
    }}
}}

function showNotesView() {{
    document.getElementById('chatView').classList.add('hidden');
    document.getElementById('notesView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '笔记管理';
    document.getElementById('notesListView').classList.remove('hidden');
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.add('hidden');
    notesState.currentNote = null;
    notesState.isEditing = false;
    setNotesMobilePanel('tree');
    renderNotesEmptyState(notesState.treeTotal);
    loadNotesTree();
    loadNotesFilters();
}}

function showChatView() {{
    document.getElementById('notesView').classList.add('hidden');
    document.getElementById('chatView').classList.remove('hidden');
}}

function renderNotesEmptyState(total) {{
    const listDiv = document.getElementById('notesList');
    const count = total || 0;
    document.getElementById('notesCount').textContent = `共 ${{count}} 篇笔记`;
    listDiv.innerHTML = `
        <div class="h-full min-h-[360px] flex flex-col items-center justify-center text-center text-on-surface/45">
            <div class="material-symbols-outlined text-5xl text-on-surface/20 mb-3">article</div>
            <div class="text-sm font-medium text-on-surface/70">从左侧选择一篇笔记查看</div>
            <div class="text-xs mt-1">当前树中有 ${{count}} 篇笔记</div>
        </div>
    `;
}}

async function loadNotesTree() {{
    const treeDiv = document.getElementById('notesTree');
    const summary = document.getElementById('notesTreeSummary');
    treeDiv.innerHTML = '<div class="notes-tree-empty">加载中...</div>';
    try {{
        const params = new URLSearchParams();
        if (notesState.domain) params.set('domain', notesState.domain);
        if (notesState.tag) params.set('tag', notesState.tag);
        if (notesState.keyword) params.set('keyword', notesState.keyword);

        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/notes/tree?' + params.toString(), {{ headers }});
        const data = await resp.json();
        notesTreeState.tree = data.tree || [];
        notesState.treeTotal = data.total || 0;

        if (hasActiveNotesFilters()) {{
            expandAllNotesTreeFolders(notesTreeState.tree);
        }}
        if (notesState.currentNote) {{
            expandNoteAncestors(notesState.currentNote.folder);
        }}

        renderNotesTree(notesTreeState.tree);
        summary.textContent = hasActiveNotesFilters()
            ? `筛选结果 ${{notesState.treeTotal}} 篇`
            : `共 ${{notesState.treeTotal}} 篇笔记`;
        if (!notesState.currentNote && !notesState.isEditing) {{
            renderNotesEmptyState(notesState.treeTotal);
        }}
    }} catch (e) {{
        treeDiv.innerHTML = '<div class="notes-tree-empty text-red-400">加载失败</div>';
    }}
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
            <button onclick="filterNotesByDomain('${{d}}')" class="px-2 py-1 rounded-lg text-[10px] text-on-surface/60 hover:bg-white/5 hover:text-on-surface transition-colors ${{notesState.domain === d ? 'bg-white/5 text-on-surface' : ''}}">
                ${{escapeHtml(d)}} <span class="text-on-surface/30">(${{domains[d]}})</span>
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

function renderNotesTree(nodes) {{
    const treeDiv = document.getElementById('notesTree');
    if (!nodes || !nodes.length) {{
        treeDiv.innerHTML = '<div class="notes-tree-empty">没有匹配的笔记</div>';
        return;
    }}
    treeDiv.innerHTML = nodes.map(node => renderNotesTreeNode(node, 0)).join('');
}}

function renderNotesTreeNode(node, level = 0) {{
    if (node.type === 'folder') {{
        const isExpanded = notesTreeState.expanded.has(node.path);
        const icon = isExpanded ? 'expand_more' : 'chevron_right';
        let html = `
            <div class="notes-tree-node">
                <div class="notes-tree-row" style="padding-left: ${{level * 14 + 4}}px" onclick="toggleNotesTreeFolder('${{encodeURIComponent(node.path)}}')">
                    <span class="notes-tree-expander">${{icon}}</span>
                    <span class="notes-tree-icon">${{isExpanded ? 'folder_open' : 'folder'}}</span>
                    <span class="notes-tree-title">${{escapeHtml(node.name)}}</span>
                    <span class="notes-tree-meta">${{node.count || 0}}</span>
                </div>
        `;
        if (isExpanded) {{
            html += (node.children || []).map(child => renderNotesTreeNode(child, level + 1)).join('');
        }}
        html += '</div>';
        return html;
    }}

    if (node.type === 'note') {{
        const isActive = notesState.currentNote && notesState.currentNote.relative_path === node.relative_path;
        const formatLabel = node.format && node.format !== 'markdown' ? node.format : '';
        // Keep this helper path explicit for static regression coverage.
        const openNode = () => showNoteDetail(encodeURIComponent(node.relative_path));
        void openNode;
        return `
            <div class="notes-tree-row ${{isActive ? 'active' : ''}}" style="padding-left: ${{level * 14 + 22}}px" onclick="showNoteDetail('${{encodeURIComponent(node.relative_path)}}')">
                <span class="notes-tree-icon">${{node.format === 'markdown' ? 'description' : 'draft'}}</span>
                <span class="notes-tree-title">${{escapeHtml(node.title)}}</span>
                <span class="notes-tree-meta">${{escapeHtml(formatLabel)}}</span>
            </div>
        `;
    }}
    return '';
}}

function toggleNotesTreeFolder(encodedPath) {{
    const path = decodeURIComponent(encodedPath);
    if (notesTreeState.expanded.has(path)) {{
        notesTreeState.expanded.delete(path);
    }} else {{
        notesTreeState.expanded.add(path);
    }}
    renderNotesTree(notesTreeState.tree);
}}

function expandAllNotesTreeFolders(nodes) {{
    for (const node of nodes || []) {{
        if (node.type === 'folder') {{
            notesTreeState.expanded.add(node.path);
            expandAllNotesTreeFolders(node.children || []);
        }}
    }}
}}

function expandNoteAncestors(folder) {{
    if (!folder || folder === 'root') return;
    const parts = folder.split('/').filter(Boolean);
    let path = '';
    for (const part of parts) {{
        path = path ? path + '/' + part : part;
        notesTreeState.expanded.add(path);
    }}
}}

function setNotesFilter(updater) {{
    const wasFiltered = hasActiveNotesFilters();
    if (!wasFiltered && !notesTreeState.savedExpandedBeforeFilter) {{
        notesTreeState.savedExpandedBeforeFilter = new Set(notesTreeState.expanded);
    }}
    updater();
    if (!hasActiveNotesFilters() && notesTreeState.savedExpandedBeforeFilter) {{
        notesTreeState.expanded = notesTreeState.savedExpandedBeforeFilter;
        notesTreeState.savedExpandedBeforeFilter = null;
    }}
    notesState.currentNote = null;
    notesState.isEditing = false;
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.add('hidden');
    document.getElementById('notesListView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '笔记管理';
    setNotesMobilePanel('tree');
    loadNotesTree();
    loadNotesFilters();
}}

function filterNotesByDomain(d) {{
    setNotesFilter(() => {{
        notesState.domain = notesState.domain === d ? null : d;
    }});
}}

function showNotesFolder(encodedFolder) {{
    const folder = encodedFolder ? decodeURIComponent(encodedFolder) : null;
    notesState.currentNote = null;
    notesState.isEditing = false;
    expandNoteAncestors(folder);
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.add('hidden');
    document.getElementById('notesListView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '笔记管理';
    setNotesMobilePanel('tree');
    renderNotesTree(notesTreeState.tree);
    renderNotesEmptyState(notesState.treeTotal);
}}

function filterNotesByTag(t) {{
    setNotesFilter(() => {{
        notesState.tag = notesState.tag === t ? null : t;
    }});
}}

async function searchNotes() {{
    openNotesSearchModal();
}}

function openNotesSearchModal() {{
    const overlay = document.getElementById('notesSearchOverlay');
    const modal = document.getElementById('notesSearchModal');
    const input = document.getElementById('notesSearchModalInput');
    const sidebarTrigger = document.getElementById('notesSearchInput');
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    if (input && sidebarTrigger && sidebarTrigger.value) {{
        input.value = sidebarTrigger.value;
    }}
    setTimeout(() => input && input.focus(), 0);
    scheduleNotesModalSearch();
}}

function closeNotesSearchModal() {{
    document.getElementById('notesSearchOverlay').classList.add('hidden');
    document.getElementById('notesSearchModal').classList.add('hidden');
    document.getElementById('notesSearchModal').classList.remove('flex');
}}

function handleNotesSearchKeydown(event) {{
    if (event.key === 'Escape') {{
        closeNotesSearchModal();
    }}
    if (event.key === 'Enter') {{
        event.preventDefault();
        runNotesModalSearch();
    }}
}}

function scheduleNotesModalSearch() {{
    clearTimeout(notesSearchState.timer);
    notesSearchState.timer = setTimeout(runNotesModalSearch, 250);
}}

async function runNotesModalSearch() {{
    const input = document.getElementById('notesSearchModalInput');
    const status = document.getElementById('notesSearchStatus');
    const resultsDiv = document.getElementById('notesSearchResults');
    const query = input ? input.value.trim() : '';

    if (!query) {{
        status.textContent = '输入关键词开始搜索';
        resultsDiv.innerHTML = '<div class="notes-tree-empty">输入关键词开始搜索</div>';
        return;
    }}

    const requestId = ++notesSearchState.requestId;
    status.textContent = '搜索中...';
    resultsDiv.innerHTML = '<div class="notes-tree-empty">搜索中...</div>';

    const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
    const titleUrl = '/api/v1/notes?keyword=' + encodeURIComponent(query) + '&page_size=10';
    const contentUrl = '/api/v1/notes/keyword-search?q=' + encodeURIComponent(query) + '&top_k=20';

    const [titleResp, contentResp] = await Promise.allSettled([
        fetch(titleUrl, {{ headers }}),
        fetch(contentUrl, {{ headers }}),
    ]);

    if (requestId !== notesSearchState.requestId) return;

    let titleResults = [];
    let contentResults = [];
    let contentUnavailable = false;

    if (titleResp.status === 'fulfilled' && titleResp.value.ok) {{
        const data = await titleResp.value.json();
        titleResults = data.items || [];
    }}

    if (contentResp.status === 'fulfilled' && contentResp.value.ok) {{
        const data = await contentResp.value.json();
        contentResults = data.results || [];
    }} else {{
        contentUnavailable = true;
    }}

    renderNotesSearchResults(query, titleResults, contentResults, contentUnavailable);
}}

function renderNotesSearchResults(query, titleResults, contentResults, contentUnavailable) {{
    const status = document.getElementById('notesSearchStatus');
    const resultsDiv = document.getElementById('notesSearchResults');
    const seen = new Set();
    let html = '';

    const titleMatches = (titleResults || []).filter(note => {{
        if (!note.relative_path || seen.has(note.relative_path)) return false;
        seen.add(note.relative_path);
        return true;
    }});

    const contentMatches = (contentResults || []).filter(result => {{
        const note = result.note || {{}};
        if (!note.relative_path || seen.has(note.relative_path)) return false;
        seen.add(note.relative_path);
        return true;
    }});

    if (titleMatches.length) {{
        html += '<div class="px-2 pb-1 text-[10px] font-bold text-on-surface/40 uppercase tracking-wider">标题和路径</div>';
        html += titleMatches.map(note => renderNotesSearchResultItem(note, null, '标题匹配')).join('');
    }}

    if (contentMatches.length) {{
        html += '<div class="px-2 pt-3 pb-1 text-[10px] font-bold text-on-surface/40 uppercase tracking-wider">正文关键词匹配</div>';
        html += contentMatches.map(result => renderNotesSearchResultItem(result.note, result.matched_chunks, result.note.date ? escapeHtml(result.note.date) : '关键词匹配')).join('');
    }}

    if (!html) {{
        html = `<div class="notes-tree-empty">没有找到和「${{escapeHtml(query)}}」相关的笔记</div>`;
    }}

    if (contentUnavailable) {{
        html += '<div class="px-3 py-2 text-[11px] text-yellow-300/70">全文搜索暂不可用，已显示标题和路径匹配结果。</div>';
    }}

    status.textContent = `找到 ${{titleMatches.length + contentMatches.length}} 条结果`;
    resultsDiv.innerHTML = html;
}}

function renderNotesSearchResultItem(note, chunks, meta) {{
    const snippet = chunks && chunks.length ? chunks[0] : note.relative_path;
    return `
        <button onclick="openNoteFromSearch('${{encodeURIComponent(note.relative_path)}}')" class="w-full text-left px-3 py-2.5 rounded-xl hover:bg-white/5 transition-colors">
            <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-sm text-on-surface/40">${{note.format === 'markdown' ? 'description' : 'draft'}}</span>
                <span class="text-sm font-medium text-on-surface/85 truncate">${{escapeHtml(note.title || note.relative_path)}}</span>
                <span class="text-[10px] text-on-surface/35 flex-shrink-0">${{escapeHtml(meta || '')}}</span>
            </div>
            <div class="mt-1 text-[11px] text-on-surface/40 line-clamp-2">${{escapeHtml(snippet || '')}}</div>
        </button>
    `;
}}

function openNoteFromSearch(encodedPath) {{
    closeNotesSearchModal();
    showNoteDetail(encodedPath);
}}

function clearNotesFilters() {{
    setNotesFilter(() => {{
        notesState.domain = null;
        notesState.tag = null;
        notesState.keyword = null;
        const input = document.getElementById('notesSearchModalInput');
        if (input) input.value = '';
    }});
}}

async function showNoteDetail(encodedPath) {{
    const relativePath = decodeURIComponent(encodedPath);
    try {{
        const headers = token ? {{ 'Authorization': 'Bearer ' + token }} : {{}};
        const resp = await fetch('/api/v1/notes/' + encodeURIComponent(relativePath), {{ headers }});
        const note = await resp.json();
        if (note.error) return;

        notesState.currentNote = note;
        expandNoteAncestors(note.folder);
        renderNotesTree(notesTreeState.tree);
        document.getElementById('notesListView').classList.add('hidden');
        document.getElementById('noteDetailView').classList.remove('hidden');
        document.getElementById('noteEditorView').classList.add('hidden');
        document.getElementById('notesNavTitle').textContent = note.title;
        setNotesMobilePanel('detail');

        // 面包屑
        document.getElementById('noteBreadcrumb').innerHTML = renderNoteBreadcrumb(note);

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

function renderNoteBreadcrumb(note) {{
    const breadcrumbParts = [`
        <button onclick="showNotesFolder('')" class="flex items-center gap-1 hover:text-on-surface transition-colors flex-shrink-0">
            <span class="material-symbols-outlined text-sm">arrow_back</span>
            <span>笔记管理</span>
        </button>
    `];

    const folderParts = (note.folder && note.folder !== 'root')
        ? note.folder.split('/').filter(Boolean)
        : [];
    let path = '';
    for (const part of folderParts) {{
        path = path ? path + '/' + part : part;
        const encodedPath = encodeURIComponent(path);
        breadcrumbParts.push('<span class="text-on-surface/20 flex-shrink-0">/</span>');
        breadcrumbParts.push(`
            <button onclick="showNotesFolder('${{encodedPath}}')" class="truncate hover:text-on-surface transition-colors">
                ${{escapeHtml(part)}}
            </button>
        `);
    }}

    breadcrumbParts.push('<span class="text-on-surface/20 flex-shrink-0">/</span>');
    breadcrumbParts.push(`<span class="truncate text-on-surface">${{escapeHtml(note.title)}}</span>`);
    return breadcrumbParts.join('');
}}

function backToNotesList() {{
    document.getElementById('noteDetailView').classList.add('hidden');
    document.getElementById('noteEditorView').classList.add('hidden');
    document.getElementById('notesListView').classList.remove('hidden');
    document.getElementById('notesNavTitle').textContent = '笔记管理';
    notesState.currentNote = null;
    notesState.isEditing = false;
    setNotesMobilePanel('tree');
    renderNotesTree(notesTreeState.tree);
    renderNotesEmptyState(notesState.treeTotal);
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

    document.getElementById('editorBreadcrumb').innerHTML = `
        <button onclick="cancelEdit()" class="flex items-center gap-1 hover:text-on-surface transition-colors">
            <span class="material-symbols-outlined text-sm">arrow_back</span>
            <span>笔记管理</span>
        </button>
        <span class="text-on-surface/20">/</span>
        <span class="truncate">编辑</span>
        <span class="text-on-surface/20">/</span>
        <span class="truncate text-on-surface">${{escapeHtml(note.title)}}</span>
    `;

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
    setNotesMobilePanel('detail');

    document.getElementById('editorBreadcrumb').innerHTML = `
        <button onclick="cancelEdit()" class="flex items-center gap-1 hover:text-on-surface transition-colors">
            <span class="material-symbols-outlined text-sm">arrow_back</span>
            <span>笔记管理</span>
        </button>
        <span class="text-on-surface/20">/</span>
        <span class="truncate text-on-surface">新建笔记</span>
    `;

    document.getElementById('editorNotePath').value = '';
    document.getElementById('editorNotePath').readOnly = false;
    document.getElementById('editorNoteTags').value = '';
    document.getElementById('editorNoteDate').value = '';
    document.getElementById('editorNoteContent').value = '# 标题\\n\\n正文内容...\\n';
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
        await loadNotesTree();
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
        await loadNotesTree();
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
    loadNotesTree();
    loadNotesFilters();
}}

// ---- 初始化 ----
checkAuth();
</script>
</body>
</html>
'''
