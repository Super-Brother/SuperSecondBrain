"""Gradio Web 前端

用法: cd ~/projects/secondbrain-chat && source .venv/bin/activate && python scripts/gradio_app.py
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gradio as gr

from src.retrievers.pipeline import SecondBrainPipeline, PipelineConfig

INDEX_DIR = os.getenv("INDEX_DIR", str(ROOT / "data" / "index"))
VAULT_PATH = os.getenv(
    "VAULT_PATH",
    "/Users/zhangwenchao/Library/Mobile Documents/iCloud~md~obsidian/Documents/文超的笔记本"
)
VAULT_NAME = VAULT_PATH.split("/")[-1]  # 提取 vault 名称用于 URL scheme

pipeline: SecondBrainPipeline = None


def init_pipeline():
    global pipeline
    config = PipelineConfig(
        vault_path=VAULT_PATH,
        index_dir=INDEX_DIR,
        llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", "not-needed"),
        llm_model=os.getenv("LLM_MODEL", "qwen2.5:3b"),
    )
    pipeline = SecondBrainPipeline(config)
    index_path = Path(INDEX_DIR)
    if (index_path / "faiss.index").exists():
        pipeline.load_index(INDEX_DIR)
        return True
    else:
        print("[WARN] 索引不存在，请先运行: python scripts/build_index.py")
        return False


def format_sources(sources: list[dict]) -> str:
    """格式化来源为可点击的 Obsidian 链接"""
    if not sources:
        return ""

    lines = ["\n\n📎 **参考来源：**"]
    for i, src in enumerate(sources):
        title = src.get("title", "")[:50]
        score = src.get("score", 0)
        source_file = src.get("source", "")

        if source_file and VAULT_NAME + "/" in source_file:
            # 提取相对路径
            rel_path = source_file.split(VAULT_NAME + "/")[-1]
            obs_url = f"obsidian://open?vault={VAULT_NAME}&file={rel_path}"
            lines.append(f"\n{i+1}. [{title}]({obs_url}) — 相关度 {score:.2f}")
        else:
            lines.append(f"\n{i+1}. **{title}** — 相关度 {score:.2f}")

    return "".join(lines)


async def respond(message, chat_history, domain, top_k):
    """对话回调（流式输出）"""
    if pipeline is None or pipeline.rag_retriever is None:
        chat_history.append((message, "⚠️ 知识库索引未加载，请先运行 `python scripts/build_index.py`。"))
        yield "", chat_history
        return

    domain_filter = None if domain == "全部" else domain

    full_answer = ""
    sources = []

    try:
        async for chunk in pipeline.chat_stream(query=message, domain=domain_filter, top_k=int(top_k)):
            if chunk.startswith("__SOURCES__:"):
                sources_json = chunk.replace("__SOURCES__:", "").strip()
                sources = json.loads(sources_json)
            else:
                full_answer += chunk
                # 增量更新 Chatbot
                if chat_history and chat_history[-1][0] == message:
                    chat_history[-1] = (message, full_answer + "▌")
                else:
                    chat_history.append((message, full_answer + "▌"))
                yield "", chat_history
    except Exception as e:
        error_msg = f"⚠️ 生成失败: {str(e)}"
        if chat_history and chat_history[-1][0] == message:
            chat_history[-1] = (message, error_msg)
        else:
            chat_history.append((message, error_msg))
        yield "", chat_history
        return

    # 最终答案 + 可点击来源
    final_answer = full_answer + format_sources(sources)
    if chat_history and chat_history[-1][0] == message:
        chat_history[-1] = (message, final_answer)
    else:
        chat_history.append((message, final_answer))
    yield "", chat_history


def get_stats_fn():
    if pipeline is None:
        return "Pipeline 未初始化"
    stats = pipeline.get_stats()
    if not stats:
        return "暂无统计数据"
    output = f"📚 **知识库统计**\n\n"
    output += f"- 总笔记数：{stats.get('total_notes', 0)} 篇\n"
    output += f"- 总 Chunk 数：{stats.get('total_chunks', 0)} 个\n\n"
    output += "**领域分布：**\n"
    for domain, count in stats.get("domain_distribution", {}).items():
        output += f"- {domain}：{count} chunks\n"
    return output


def create_ui():
    with gr.Blocks(title="🧠 SecondBrain Chat", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🧠 SecondBrain Chat")
        gr.Markdown("基于 RAG 的个人知识库智能问答 | Obsidian 笔记驱动")

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(height=500, label="对话")
                with gr.Row():
                    msg_input = gr.Textbox(
                        placeholder="输入你的问题...",
                        show_label=False,
                        scale=4,
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1)
                with gr.Row():
                    domain_dropdown = gr.Dropdown(
                        choices=["全部", "通识", "AI/ML", "编程", "面试", "其他"],
                        value="全部",
                        label="检索领域",
                    )
                    top_k_slider = gr.Slider(
                        minimum=1, maximum=20, value=5, step=1,
                        label="返回结果数",
                    )
                    clear_btn = gr.Button("清空对话")
            with gr.Column(scale=1):
                stats_btn = gr.Button("📊 知识库统计", variant="secondary")
                stats_output = gr.Markdown("点击查看统计信息")
                gr.Markdown("---")
                gr.Markdown("### 💡 使用提示")
                gr.Markdown("- 支持自然语言提问\n- 可按领域过滤检索\n- 每个回答附带参考来源\n- 基于混合检索（BM25+向量）")

        msg_input.submit(respond, [msg_input, chatbot, domain_dropdown, top_k_slider], [msg_input, chatbot])
        submit_btn.click(respond, [msg_input, chatbot, domain_dropdown, top_k_slider], [msg_input, chatbot])
        clear_btn.click(lambda: (None, []), outputs=[msg_input, chatbot])
        stats_btn.click(get_stats_fn, outputs=[stats_output])

    return demo


if __name__ == "__main__":
    print("🧠 SecondBrain Chat 启动中...")
    loaded = init_pipeline()
    if loaded:
        print("✅ 索引加载成功！")
    else:
        print("⚠️ 索引未加载，请先运行 python scripts/build_index.py")

    demo = create_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)
