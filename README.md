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

## Remote control API (personal use)
1. Set a strong token in `.env`:
```env
AGENT_WEB_TOKEN=your-long-random-token
```
2. Start server:
```bash
uvicorn webapp.app:app --host 0.0.0.0 --port 8000
```
3. Create a run:
```bash
curl -X POST http://127.0.0.1:8000/runs ^
  -H "Authorization: Bearer your-long-random-token" ^
  -H "Content-Type: application/json" ^
  -d "{\"goal\":\"List files and summarize\",\"cwd\":\".\",\"provider\":\"gemini\",\"max_steps\":5}"
```
4. Check pending approval:
```bash
curl -H "Authorization: Bearer your-long-random-token" http://127.0.0.1:8000/runs/{run_id}
```
5. Approve:
```bash
curl -X POST http://127.0.0.1:8000/runs/{run_id}/approve ^
  -H "Authorization: Bearer your-long-random-token" ^
  -H "Content-Type: application/json" ^
  -d "{\"request_id\":\"...\",\"decision\":\"y\"}"
```

## Cloudflare Tunnel (`stockgame.cc`)
Use this when you want remote access without opening router ports.

1. Install and login:
```bash
cloudflared login
```
2. Create tunnel:
```bash
cloudflared tunnel create ai-agent
```
3. Create DNS route:
```bash
cloudflared tunnel route dns ai-agent api.stockgame.cc
```
If you get `code: 1003`, remove the existing `api.stockgame.cc` A/CNAME record in Cloudflare DNS first, then run the command again.
4. Update `deploy/cloudflared/config.yml`:
- Replace `REPLACE_WITH_TUNNEL_UUID`
- Replace credentials-file path if your Windows username/path differs
- Keep origin service as `http://127.0.0.1:8000` unless changed

5. Start API server:
```bash
python -m uvicorn webapp.app:app --host 0.0.0.0 --port 8000
```
6. Start tunnel:
```bash
powershell -ExecutionPolicy Bypass -File scripts/run_cloudflared.ps1
```
7. Verify:
```bash
curl https://api.stockgame.cc/health
```
8. Open approval UI:
```text
https://api.stockgame.cc/
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

## API endpoints
- `GET /health`
- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `POST /runs/{run_id}/approve`

## Tests
```bash
python -m pytest -q
```
