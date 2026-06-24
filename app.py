"""
app.py
------
Streamlit front-end for the RAG Conversational Engine.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from document_processor import SUPPORTED_EXTENSIONS, process_document
from rag_engine import RAGEngine
from vector_store import VectorStore


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

st.set_page_config(
    page_title="RAG Conversational Engine",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Session-state initialisation (runs once per session)
# ---------------------------------------------------------------------------

def init_state() -> None:
    if "vector_store" not in st.session_state:
        st.session_state.vector_store = VectorStore()
    if "rag_engine" not in st.session_state:
        st.session_state.rag_engine   = RAGEngine(st.session_state.vector_store)
    if "messages" not in st.session_state:
        st.session_state.messages = []          # {"role": "user"|"assistant", "content": "..."}
    if "processed_files" not in st.session_state:
        st.session_state.processed_files: set   = set()


init_state()

vs: VectorStore = st.session_state.vector_store
engine: RAGEngine = st.session_state.rag_engine


# ---------------------------------------------------------------------------
# Sidebar — document management
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📁 Document Library")

    # ---- API key check ----
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.error("⚠️  ANTHROPIC_API_KEY not found.  Add it to **.env** or Streamlit secrets.")
        st.stop()

    # ---- Upload widget ----
    st.subheader("Upload Documents")
    ext_list = ", ".join(f"*{e}" for e in SUPPORTED_EXTENSIONS)
    uploaded = st.file_uploader(
        "Choose files",
        accept_multiple_files=True,
        type=[e.lstrip(".") for e in SUPPORTED_EXTENSIONS],
        help=f"Supported: {ext_list}",
    )

    if uploaded:
        new_files = [f for f in uploaded if f.name not in st.session_state.processed_files]
        if new_files:
            with st.spinner(f"Processing {len(new_files)} file(s)…"):
                for uf in new_files:
                    try:
                        chunks = process_document(uf.name, uf.read())
                        added  = vs.add_chunks(chunks)
                        st.session_state.processed_files.add(uf.name)
                        st.success(f"✅ **{uf.name}** — {added} chunk(s) indexed")
                    except ValueError as exc:
                        st.error(f"❌ {uf.name}: {exc}")
                    except Exception as exc:
                        st.error(f"❌ {uf.name}: unexpected error — {exc}")

    # ---- Indexed documents ----
    st.subheader("Indexed Documents")
    sources = vs.list_sources()
    if sources:
        st.caption(f"{vs.count:,} chunks across {len(sources)} document(s)")
        for src in sources:
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"📄 `{src}`")
            if col2.button("🗑️", key=f"del_{src}", help=f"Remove {src}"):
                removed = vs.delete_source(src)
                st.session_state.processed_files.discard(src)
                st.success(f"Removed {removed} chunk(s) from **{src}**")
                st.rerun()
    else:
        st.info("No documents indexed yet. Upload files above.")

    # ---- Clear all ----
    st.divider()
    if st.button("🧹 Clear All Documents", use_container_width=True):
        vs.clear()
        st.session_state.processed_files.clear()
        st.success("All documents cleared.")
        st.rerun()

    # ---- Settings ----
    st.divider()
    st.subheader("⚙️  Settings")
    top_k = st.slider(
        "Top-K chunks retrieved",
        min_value=1, max_value=15, value=5,
        help="More chunks = richer context but higher token cost.",
    )
    show_sources = st.toggle("Show retrieved sources", value=True)


# ---------------------------------------------------------------------------
# Main — chat interface
# ---------------------------------------------------------------------------

st.title("📚 RAG Conversational Engine")
st.caption(
    "Upload documents in the sidebar, then ask questions.  "
    "Powered by **Claude claude-opus-4-8** + **ChromaDB**."
)

# ---- Render chat history ----
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---- User input ----
placeholder = (
    "Ask a question about your documents…"
    if vs.count > 0
    else "Upload documents first, then ask questions here."
)

if prompt := st.chat_input(placeholder, disabled=(vs.count == 0)):

    # Show user bubble
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Show source chunks (optional)
    if show_sources:
        with st.expander("🔍 Retrieved context chunks", expanded=False):
            chunks = engine.get_sources(prompt, n_results=top_k)
            if chunks:
                for i, c in enumerate(chunks, 1):
                    src  = c["metadata"].get("source", "unknown")
                    sim  = 1 - c["distance"]
                    cidx = c["metadata"].get("chunk_index", "?")
                    st.markdown(
                        f"**Chunk {i}** — `{src}` (chunk #{cidx}, similarity {sim:.2f})"
                    )
                    st.text(c["text"][:400] + ("…" if len(c["text"]) > 400 else ""))
                    st.divider()
            else:
                st.warning("No relevant chunks found.")

    # Stream Claude's answer
    with st.chat_message("assistant"):
        # Build history excluding the current user turn (already appended)
        history = st.session_state.messages[:-1]
        response_placeholder = st.empty()
        full_response = ""

        try:
            for token in engine.stream_answer(prompt, history, n_results=top_k):
                full_response += token
                response_placeholder.markdown(full_response + "▌")
            response_placeholder.markdown(full_response)
        except Exception as exc:
            full_response = f"⚠️ Error generating response: {exc}"
            response_placeholder.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

# ---- Empty state hint ----
if vs.count == 0 and not st.session_state.messages:
    st.info(
        "👈  **Get started**: upload one or more documents in the sidebar, "
        "then ask a question below."
    )
