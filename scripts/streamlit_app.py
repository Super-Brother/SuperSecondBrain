"""Streamlit 前端 — SecondBrain Chat"""

import requests
import streamlit as st

API_BASE = st.secrets.get("API_BASE", "http://localhost:8001")


def init_session():
    if "session_id" not in st.session_state:
        r = requests.post(f"{API_BASE}/api/v1/sessions")
        st.session_state.session_id = r.json()["session_id"]
    if "messages" not in st.session_state:
        st.session_state.messages = []


def send_query(query: str, domain: str | None = None):
    r = requests.post(f"{API_BASE}/api/v1/chat", json={
        "query": query,
        "session_id": st.session_state.session_id,
        "domain": domain if domain != "全部" else None,
    })
    return r.json()


def main():
    st.set_page_config(page_title="SecondBrain Chat", page_icon="🧠", layout="wide")
    st.title("🧠 SecondBrain Chat")
    st.caption("基于 RAG 的个人知识库智能问答")

    init_session()

    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 设置")
        domain = st.selectbox("检索领域", ["全部", "通识", "AI/ML", "编程", "面试", "其他"])
        top_k = st.slider("返回结果数", 1, 10, 5)

        st.divider()
        if st.button("🆕 新对话"):
            st.session_state.messages = []
            r = requests.post(f"{API_BASE}/api/v1/sessions")
            st.session_state.session_id = r.json()["session_id"]
            st.rerun()

        st.divider()
        st.markdown("### 📊 知识库统计")
        try:
            stats = requests.get(f"{API_BASE}/stats").json()
            st.metric("笔记数", stats.get("total_notes", 0))
            st.metric("Chunk数", stats.get("total_chunks", 0))
            if "token_usage" in stats:
                st.metric("Token用量", stats["token_usage"].get("total_tokens", 0))
        except Exception:
            st.warning("无法获取统计")

    # 对话历史
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📎 来源"):
                    for i, src in enumerate(msg["sources"], 1):
                        st.markdown(f"**{i}. {src['title'][:50]}** ({src.get('folder', '')}) — 相关度 {src.get('score', 0):.2f}")

    # 输入框
    if prompt := st.chat_input("输入你的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                result = send_query(prompt, domain)

            st.markdown(result["answer"])

            if result.get("sources"):
                with st.expander("📎 来源"):
                    for i, src in enumerate(result["sources"], 1):
                        st.markdown(f"**{i}. {src['title'][:50]}** ({src.get('folder', '')}) — 相关度 {src.get('score', 0):.2f}")

        st.session_state.messages.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result.get("sources", []),
        })


if __name__ == "__main__":
    main()
