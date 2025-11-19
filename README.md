# LLMAgentFortranProject

Note: WORK IN PROGRESS

An Ollama-powered tool-calling agent designed to inspect Fortran projects, answer code questions, and draft git command sequences that implement requested changes. The assistant talks directly to Ollama's Python client and advertises a small suite of local tools (file reader, code search, git helpers, etc.) that the model can invoke as needed.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally with a lightweight model pulled (defaults to `gemma3:1b`)
- Access to the Fortran codebase you want the agent to explore

See the [Ollama PoC guide](https://github.com/RamiKrispin/ollama-poc?tab=readme-ov-file) for a quick start on configuring Ollama.


## Running the Agent

```bash
python query.py \
  --project-root "<path to source>" \
  --repo-root "<path to base>" \
  --model "gemma3-tools:1b"
```

Important flags:

- `--project-root`: directory containing the Fortran sources (used by read/search tools)
- `--repo-root`: git repository root (used by git status/diff/plan tools)
- `--base-branch`: default branch that git plans should branch from
- `--context-file`: priming instructions injected when the session starts

Inside the REPL, ask natural-language questions, agent will invoke tools.

For change requests, the agent will inspect the relevant files and then return a git command recipe (branch creation, patch stub, staging, commit message) so you can apply the edits manually - automation is WIP.
