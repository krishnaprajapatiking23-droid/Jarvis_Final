"""
Ollama Service — LLM service layer for JARVIS Core.

Canonical implementation: ``brains_v2.llm.ollama_provider``

This module provides the jarvis_core.ollama_service import path used by roadmap
category 36 (Developer Maintenance). The actual Ollama integration lives in
brains_v2.llm.ollama_provider.
"""

from __future__ import annotations

from brains_v2.llm.ollama_provider import OllamaProvider

__all__ = ['OllamaProvider']
