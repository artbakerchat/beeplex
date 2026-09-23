"""Tier-2 Streamlit custom component: clickable conversation cards.

Two-way communication: the React frontend renders one card per
conversation; clicking a card sends that conversation back to Python
via Streamlit.setComponentValue, and this function returns it.

Build the frontend once with:
    cd frontend && npm install && npm run build
"""

import os

import streamlit.components.v1 as components

_BUILD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "build")

_conversation_cards = components.declare_component("conversation_cards", path=_BUILD_DIR)


def conversation_cards(conversations, key=None):
    """Render clickable conversation cards.

    Args:
        conversations: list of {"date": str, "title": str, "topic": str}
        key: Streamlit widget key

    Returns:
        The clicked conversation dict, or None if nothing clicked yet.
    """
    return _conversation_cards(conversations=conversations, key=key)
