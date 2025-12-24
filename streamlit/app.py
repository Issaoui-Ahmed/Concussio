"""
app.py
------
ChatGPT-like web UI using Streamlit.

Run:
  streamlit run app.py

Files expected alongside this:
- app.py
- chatbot.py
- generator.py
- prompts.py
- (optionally) all_rec_markdown.md (used by prompts.build_generator_prompt)
"""

from __future__ import annotations

import streamlit as st

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.chatbot import ChatSession


st.set_page_config(page_title="Chatbot", page_icon="💬", layout="centered")

st.title("💬 Chatbot")

# Session state init
if "bot" not in st.session_state:
    st.session_state.bot = ChatSession()

if "ui_messages" not in st.session_state:
    # This is just what we render in the UI. The bot maintains its own history too,
    # but keeping a UI list makes rendering simple and robust.
    st.session_state.ui_messages = []  # [{"role": "user"|"assistant", "content": "..."}]

# Render chat history
for msg in st.session_state.ui_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_text = st.chat_input("Message…")

if user_text:
    # Show user message
    st.session_state.ui_messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # Generate assistant reply
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                answer = st.session_state.bot.reply(user_text)
            except Exception as e:
                answer = f"⚠️ Error:\n\n`{type(e).__name__}: {e}`"
        st.markdown(answer)

    st.session_state.ui_messages.append({"role": "assistant", "content": answer})
