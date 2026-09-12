# SideQuest

SideQuest prototype with a server-side SideQuest Agent. The browser never receives provider API keys.

## Run

```bash
cp .env.example .env
# Add your keys to .env, then:
uv run server.py
```

Then open http://localhost:4173.

Open http://localhost:4173.

Add keys in `.env`:

```env
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=google/gemini-2.0-flash-001
EXA_API_KEY=your_exa_key
SIDEQUEST_LOCATION=Dubai
```

`OPENROUTER_API_KEY` enables the real SideQuest Agent compromise. `EXA_API_KEY` optionally adds live web context to the agent request. Both keys stay server-side. If either provider is unavailable, the app returns a validated local compromise so the demo continues working. The current venue catalog is still curated demo data; Exa context is advisory and cannot introduce unapproved venue IDs into the final plan.
