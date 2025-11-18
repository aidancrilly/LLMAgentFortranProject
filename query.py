import argparse
import json
from pathlib import Path
from typing import Dict, List

import ollama

from tools.code_search import (
    build_code_search_tool,
    build_fortran_summary_tool,
    build_fortran_symbol_extractor_tool,
)
from tools.file_tools import build_file_reader_tool
from tools.git_tools import build_git_tools
from tools.namelist_tools import build_namelist_tool
from tools.project_state import build_project_overview_tools
from tools.tool_spec import ToolSpec


def load_context(context_path: Path) -> str:
    if not context_path.exists():
        return ""
    return context_path.read_text(encoding="utf-8", errors="ignore")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive Fortran project assistant backed by Ollama."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to the Fortran project root that the agent should explore.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
        help="Path to the git repository.",
    )
    parser.add_argument(
        "--namelist-path",
        type=Path,
        default=None,
        help="Optional path to the NAMELIST input deck for ReadNamelistVar tool.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen3:1.7b",
        help="Ollama model identifier to load.",
    )
    parser.add_argument(
        "--base-branch",
        type=str,
        default="main",
        help="Default base branch name used by the GitPlan tool.",
    )
    parser.add_argument(
        "--context-file",
        type=Path,
        default=Path("AGEND.md"),
        help="Priming document injected before the conversation.",
    )
    return parser.parse_args()


def build_system_prompt(context: str) -> str:
    """Compose the system message that guides the agent."""
    prompt = (
        "You are an Ollama-hosted assistant that helps inspect Fortran projects. "
    )
    cleaned_context = context.strip()
    if cleaned_context:
        prompt += f"\n\n{cleaned_context}"
    return prompt


def build_tools(args: argparse.Namespace) -> List[ToolSpec]:
    tools = []
    project_root = args.project_root.expanduser().resolve()
    repo_root = args.repo_root.expanduser().resolve()

    print(f"Binding tools to project root: {project_root}")
    print(f"Binding git tools to repo root: {repo_root}")

    tools.append(build_file_reader_tool(project_root))
    tools.append(build_code_search_tool(project_root))
    tools.append(build_fortran_summary_tool(project_root))
    tools.append(build_fortran_symbol_extractor_tool(project_root))
    tools.extend(build_project_overview_tools(project_root))
    if args.namelist_path:
        tools.append(build_namelist_tool(args.namelist_path.expanduser().resolve()))
    tools.extend(build_git_tools(repo_root, args.base_branch))
    return tools


def _parse_arguments(raw_args) -> Dict:
    if isinstance(raw_args, str):
        try:
            data = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
    elif isinstance(raw_args, dict):
        data = raw_args
    else:
        data = {}
    return data if isinstance(data, dict) else {}


def call_model_with_tools(
    model: str, messages: List[Dict[str, str]], tools: List[ToolSpec]
) -> Dict[str, str]:
    """Send the conversation to Ollama, honoring tool-calling responses."""
    name_to_tool = {tool.name: tool for tool in tools}
    ollama_tools = [tool.as_ollama_tool() for tool in tools]

    while True:
        response = ollama.chat(model=model, messages=messages, tools=ollama_tools)

        message = response.get("message", {})
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return message

        messages.append(message)
        for call in tool_calls:
            function_payload = call.get("function", {})
            name = function_payload.get("name")
            tool = name_to_tool.get(name)
            if not tool:
                tool_output = f"Tool '{name}' is not available."
            else:
                args = _parse_arguments(function_payload.get("arguments"))
                try:
                    tool_output = tool.func(args)
                except Exception as exc:
                    tool_output = f"Tool '{name}' raised an error: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "name": name or "unknown",
                    "content": tool_output,
                    "tool_call_id": call.get("id"),
                }
            )


def main():
    args = parse_args()
    tools = build_tools(args)
    context = load_context(args.context_file)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(context)}
    ]

    print("Ollama Fortran Agent ready. Type 'exit' to quit.\n")
    while True:
        try:
            query = input("User> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break
        messages.append({"role": "user", "content": query})
        reply = call_model_with_tools(args.model, messages, tools)
        messages.append(reply)
        output_text = reply.get("content", "").strip() or "(no response from model)"
        print(f"\nAgent> {output_text}\n")


if __name__ == "__main__":
    main()
