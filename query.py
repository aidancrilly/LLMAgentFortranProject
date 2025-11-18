import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

import ollama
from rich.console import Console

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

FORTRAN_SUFFIXES: Set[str] = {".f", ".for", ".f90", ".f95", ".f03", ".f08"}
console = Console()


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

    console.print(f"Binding tools to project root: {project_root}", style="cyan")
    console.print(f"Binding git tools to repo root: {repo_root}", style="cyan")

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


def _format_tool_call(name: str, args: Dict) -> str:
    """Return a concise log entry for a tool invocation."""
    tool_name = name or "unknown"
    try:
        arg_text = json.dumps(args or {}, ensure_ascii=True)
    except TypeError:
        arg_text = str(args)
    return f"[tool] {tool_name}({arg_text})"


def describe_fortran_files(project_root: Path) -> str:
    """Return a readable list of Fortran source files under project_root."""
    try:
        root = project_root.expanduser().resolve()
    except OSError:
        return ""
    if not root.exists():
        return ""

    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in FORTRAN_SUFFIXES:
            files.append(str(path.relative_to(root)))

    if not files:
        return "No Fortran source files were found in the project directory."

    files.sort()
    listing = "\n".join(f"- {relative}" for relative in files)
    return f"Fortran source files detected in project root:\n{listing}"


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
                console.print(_format_tool_call(name, args), style="bold red")
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
    base_context = load_context(args.context_file).strip()
    fortran_listing = describe_fortran_files(args.project_root).strip()
    context_sections = [
        section for section in (base_context, fortran_listing) if section
    ]
    combined_context = "\n\n".join(context_sections)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(combined_context)}
    ]

    console.print("Ollama Fortran Agent ready. Type 'exit' to quit.\n", style="cyan")
    while True:
        try:
            query = console.input("[bold blue]User> [/bold blue]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting.", style="cyan")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break
        messages.append({"role": "user", "content": query})
        reply = call_model_with_tools(args.model, messages, tools)
        messages.append(reply)
        output_text = reply.get("content", "").strip() or "(no response from model)"
        console.print(f"\nAgent> {output_text}\n", style="bold green")


if __name__ == "__main__":
    main()
