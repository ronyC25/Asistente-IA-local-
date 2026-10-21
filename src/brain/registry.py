"""Registro de herramientas y definicion de Tool."""
from __future__ import annotations

from typing import Any, Callable

READ = "read"
WRITE = "write"


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable[..., Any],
        kind: str = READ,
        describe: Callable[[dict], str] | None = None,
    ) -> None:
        self.name = name
        self.func = func
        self.kind = kind
        self.describe = describe
        self.schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }

    def run(self, args: dict) -> Any:
        return self.func(**(args or {}))


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, spec: dict) -> None:
        tool = Tool(
            name=spec["name"],
            description=spec["description"],
            parameters=spec["parameters"],
            func=spec["func"],
            kind=spec.get("kind", READ),
            describe=spec.get("describe"),
        )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self, nombres: set[str] | None = None) -> list[dict]:
        if nombres is None:
            return [t.schema for t in self._tools.values()]
        return [t.schema for name, t in self._tools.items() if name in nombres]

    def names(self) -> list[str]:
        return list(self._tools)
