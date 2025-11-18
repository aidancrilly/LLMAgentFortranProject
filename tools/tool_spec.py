from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class ToolSpec:
    """Represents a callable tool that can be advertised to Ollama."""

    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable[[Dict[str, Any]], str]

    def as_ollama_tool(self) -> Dict[str, Any]:
        """Return the JSON schema Ollama expects (function tools)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
