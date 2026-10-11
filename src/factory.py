"""Fabrica del agente: construye el registro y el Agent desde la configuracion."""
from __future__ import annotations

from .brain.agent import Agent
from .brain.prompts import system_prompt
from .brain.registry import Registry
from .brain.schema import build_tools
from .config import settings
from .db import init_db


def build_registry() -> Registry:
    registry = Registry()
    for spec in build_tools():
        registry.add(spec)
    return registry


def build_agent() -> Agent:
    init_db(settings.database)
    registry = build_registry()
    return Agent(
        registry=registry,
        model=settings.model,
        system_prompt=system_prompt(settings.assistant_name),
        temperature=settings.temperature,
        max_iters=settings.max_tool_iters,
        num_ctx=settings.num_ctx,
        host=settings.ollama_host,
    )
