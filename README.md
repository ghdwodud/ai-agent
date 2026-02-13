# Approval-First Local CLI Agent (Python)

Local CLI AI agent MVP for safe task automation.

## Features
- Semi-autonomous loop: observe -> plan -> propose -> approve -> execute -> reflect.
- Approval gate before every tool execution.
- Tools: file, shell, web search.
- Policy checks: command allowlist + dangerous pattern/path blocking.
- Session memory is in-process only (non-persistent).
- Structured run log: `agent_run.jsonl`.

## Providers
- `openai`
- `anthropic`
- `gemini`

## Setup
```bash
pip install -r requirements.txt
copy .env.example .env
```

Set keys in `.env`:
- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Gemini: `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
- Optional web search: `TAVILY_API_KEY`

## Run
```bash
python cli.py --goal "List files and summarize" --cwd . --provider openai --model gpt-4.1-mini
python cli.py --goal "List files and summarize" --cwd . --provider anthropic --model claude-3-5-sonnet-latest
python cli.py --goal "List files and summarize" --cwd . --provider gemini --model gemini-2.5-flash
```

## CLI
- `--goal` required
- `--cwd` working scope root
- `--max-steps` max loop steps
- `--max-retries` retries for retryable tool errors
- `--provider` `openai|anthropic|gemini`
- `--model` model id
- `--approval` `strict|normal`
- `--team-mode` planner/executor/reviewer reasoning prompt mode

## Tests
```bash
python -m pytest -q
```

