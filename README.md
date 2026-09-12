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
GEOAPIFY_API_KEY=your_geoapify_key
SIDEQUEST_LOCATION=Dubai
```

`OPENROUTER_API_KEY` enables the real SideQuest Agent for both plan generation and compromise. `EXA_API_KEY` optionally adds live web context to agent requests. Both keys stay server-side. If either provider is unavailable, the app returns request-aware local plans and a validated compromise so the demo continues working. The current venue catalog is still curated demo data; Exa context is advisory and cannot introduce unapproved venue IDs into the final plan.

The plan screen sends the current request, selected budget, selected vibe, group profiles, and venue catalog to `POST /api/agent/plans`. The compromise screen sends votes and plans to `POST /api/agent/compromise`.

On the plan screen, tapping `Use my current location` requests browser permission. If granted, the server queries Geoapify Places within 5 km and ranks them by proximity before the SideQuest Agent builds the three plans. If permission is denied or Geoapify fails, the curated Dubai demo catalog remains available.

After the collection screen, `Make our edit` opens the Memory Lab. Multiple uploaded photos and videos are arranged into a branded 9:16 SideQuest template with title, collage, sticker, progress, and end cards. Media stays in the browser; `canvas.captureStream()` and `MediaRecorder` create a downloadable WebM edit. No media is uploaded to the server in this version.
