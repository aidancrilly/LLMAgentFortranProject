# LLMAgentFortranProject

An Ollama-powered tool-calling agent designed to inspect Fortran projects, answer code questions, and draft git command sequences that implement requested changes. The assistant talks directly to Ollama's Python client and advertises a small suite of local tools (file reader, code search, git helpers, etc.) that the model can invoke as needed.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally with a lightweight model pulled (defaults to `gemma3:1b`)
- Access to the Fortran codebase you want the agent to explore

See the [Ollama PoC guide](https://github.com/RamiKrispin/ollama-poc?tab=readme-ov-file) for a quick start on configuring Ollama.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate  # or source .venv/bin/activate on Unix
pip install -r requirements.txt
```

## Running the Agent

```bash
python query.py \
  --project-root "F:/Visual Studio 2015/Projects/MinotaurLITE/MinotaurLITE/src" \
  --repo-root "F:/Visual Studio 2015/Projects/MinotaurLITE/MinotaurLITE" \
  --namelist-path "F:/Visual Studio 2015/Projects/MinotaurLITE/MinotaurLITE/input/config_ionkin.ini" \
  --model "gemma3-tools:1b"
```

Important flags:

- `--project-root`: directory containing the Fortran sources (used by read/search tools)
- `--repo-root`: git repository root (used by git status/diff/plan tools)
- `--namelist-path`: optional NAMELIST file for `ReadNamelistVar`
- `--base-branch`: default branch that git plans should branch from
- `--context-file`: priming instructions injected when the session starts

Inside the REPL, ask natural-language questions like:

- "Show me the main solver loop."
- "Where is `update_turbulence` defined?"
- "Please add comments at the beginning of every subroutine briefly describing its purpose."

For change requests, the agent will inspect the relevant files and then return a git command recipe (branch creation, patch stub, staging, commit message) so you can apply the edits manually.
