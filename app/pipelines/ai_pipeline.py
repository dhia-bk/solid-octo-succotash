"""
AI pipeline — chatbot conversations, messages, tool calls.

FK chain: conversations before messages before tool_calls.
Requires identity_pipeline (User for TALKED_TO).
"""

from __future__ import annotations

from app.core.constants import AI_PIPELINE
from app.pipelines.base import BasePipeline


class AIPipeline(BasePipeline):
    """
    Loads chatbot interaction graph: ChatbotConversation, ChatbotMessage, ToolCall, Tool.
    """

    pipeline_name = AI_PIPELINE
    sources = (
        "dim_chatbot_conversations",  # ChatbotConversation nodes + TALKED_TO rels
    )
