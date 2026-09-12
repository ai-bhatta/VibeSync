"""Small dependency-free SideQuest API and static server.

Run with: uv run server.py
The agent uses OpenRouter when configured, Exa for optional live context, and
always falls back to a validated local compromise when a provider is absent or fails.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

FALLBACK = {
    "title": "A little bit of everyone's night",
    "stops": [
        {"venueId": "venue_01", "name": "Pixel Arcade", "icon": "🎮", "challenge": "Beat one friend at an arcade game."},
        {"venueId": "venue_03", "name": "Seoul Table", "icon": "🍜", "challenge": "Someone orders something they have never tried before."},
        {"venueId": "venue_05", "name": "Cloud 9 Mochi", "icon": "🍦", "challenge": "Group votes for MVP of the night."},
    ],
    "pricePerPerson": 68,
    "match": 96,
    "reasons": [
        "Competitive activity for Adeeb",
        "Gaming experience for Saif",
        "Asian food and vegetarian options for Kaveri",
        "Within Ahmed's AED 70 budget",
    ],
    "summary": "A competitive first stop, familiar Asian comfort, and a playful finish keep the whole party in the game.",
}


def fallback_plans(payload: dict) -> list[dict]:
    """A request-aware offline planner, used only when OpenRouter is unavailable."""
    venues = payload.get("venues", [])
    by_tag = {tag: next((v for v in venues if tag in v.get("tags", [])), None) for tag in
              ["competitive", "gaming", "asian", "burgers", "cafe", "chill", "creative", "dessert"]}
    request = str(payload.get("request", "")).lower()
    vibe = str(payload.get("vibe", "surprise")).lower()
    def pick(*keys):
        return next((by_tag[k] for k in keys if by_tag.get(k)), venues[0] if venues else {"id":"unknown","name":"A local adventure","icon":"✦","estimatedPrice":0})
    activity = pick("gaming", "competitive") if any(x in request + vibe for x in ["game", "competitive", "arcade"]) else pick("creative", "chill", "competitive")
    food = pick("burgers") if "burger" in request else pick("asian", "cafe")
    sweet = pick("dessert", "cafe")
    alt_activity = pick("creative", "chill", "competitive")
    alt_food = pick("cafe", "asian", "burgers")
    routes = [[activity, food, sweet], [pick("competitive", "gaming"), pick("burgers", "asian"), sweet], [alt_activity, alt_food, pick("asian", "dessert")]]
    labels = ["Best fit for the party", "High-energy wildcard", "Easygoing social run"]
    plans = []
    for i, route in enumerate(routes):
        plans.append({"id": f"agent_plan_{i+1}", "title": labels[i], "places": route,
                      "price": sum(int(v.get("estimatedPrice", 0)) for v in route),
                      "match": max(72, 94 - i * 4),
                      "reason": f"Built from your request: {payload.get('request', 'something fun for everyone')}."})
    return plans


def call_planner(payload: dict) -> tuple[list[dict], str, bool]:
    venues = discovered_venues(payload)
    live_context = exa_context(location_label(payload.get("location", os.getenv("SIDEQUEST_LOCATION", "Dubai"))), payload.get("request", ""))
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return fallback_plans(payload), "fallback_no_openrouter_key", bool(live_context)
    schema = {"type":"object","additionalProperties":False,"properties":{"plans":{"type":"array","minItems":3,"maxItems":3,"items":{"type":"object","additionalProperties":False,"properties":{"title":{"type":"string"},"venueIds":{"type":"array","minItems":3,"maxItems":3,"items":{"type":"string"}},"price":{"type":"integer"},"match":{"type":"integer"},"reason":{"type":"string"}},"required":["title","venueIds","price","match","reason"]}}},"required":["plans"]}
    prompt = {"group":payload.get("group"),"budget":payload.get("budget"),"vibe":payload.get("vibe"),"request":payload.get("request"),"location":payload.get("location"),"venues":venues,"liveContext":live_context}
    try:
        data = json_request("https://openrouter.ai/api/v1/chat/completions", {"model":os.getenv("OPENROUTER_MODEL","google/gemini-2.0-flash-001"),"messages":[{"role":"system","content":"You are SideQuest Agent. Create exactly 3 complete group experiences from the supplied venues. Use only supplied venue IDs. Respect the requested budget and vibe. Return only JSON matching the schema."},{"role":"user","content":json.dumps(prompt)}],"temperature":0.7,"response_format":{"type":"json_schema","json_schema":{"name":"sidequest_plans","strict":True,"schema":schema}}},{"Authorization":f"Bearer {api_key}","HTTP-Referer":"http://localhost:4173","X-Title":"SideQuest"})
        raw = data["choices"][0]["message"]["content"]
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        allowed = {str(v.get("id")):v for v in venues}
        clean=[]
        for i, plan in enumerate(parsed.get("plans", [])):
            ids=plan.get("venueIds", [])
            if len(ids)!=3 or any(str(x) not in allowed for x in ids): raise ValueError("invalid venue ids")
            places=[allowed[str(x)] for x in ids]
            clean.append({"id":f"agent_plan_{i+1}","title":str(plan.get("title","SideQuest plan"))[:80],"places":places,"price":int(plan.get("price",sum(int(v.get("estimatedPrice",0)) for v in places))),"match":max(0,min(100,int(plan.get("match",80)))),"reason":str(plan.get("reason","A plan built for the whole party."))[:180]})
        if len(clean)==3: return clean, "openrouter", bool(live_context)
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError, json.JSONDecodeError):
        pass
    return fallback_plans(payload), "fallback_provider_error", bool(live_context)


def json_request(url: str, payload: dict, headers: dict, timeout: int = 20) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def location_label(location: object) -> str:
    if isinstance(location, dict):
        return str(location.get("city") or f"{location.get('lat', '')},{location.get('lng', '')}")
    return str(location or os.getenv("SIDEQUEST_LOCATION", "Dubai"))


def google_places(location: object) -> list[dict]:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key or not isinstance(location, dict) or location.get("lat") is None or location.get("lng") is None:
        return []
    try:
        data = json_request("https://places.googleapis.com/v1/places:searchNearby", {
            "includedTypes": ["restaurant", "cafe", "bowling_alley", "amusement_center", "movie_theater", "park", "museum", "tourist_attraction"],
            "maxResultCount": 20, "rankPreference": "DISTANCE",
            "locationRestriction": {"circle": {"center": {"latitude": float(location["lat"]), "longitude": float(location["lng"])}, "radius": 8000.0}},
        }, {"X-Goog-Api-Key": key, "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.priceLevel,places.currentOpeningHours,places.googleMapsUri,places.types"})
        result = []
        for place in data.get("places", []):
            name, point = place.get("displayName", {}).get("text"), place.get("location", {})
            if not name or "latitude" not in point:
                continue
            result.append({"id": place.get("id", name), "name": name, "icon": "📍", "address": place.get("formattedAddress", ""),
                           "lat": point.get("latitude"), "lng": point.get("longitude"), "rating": place.get("rating"),
                           "priceLevel": place.get("priceLevel", ""), "openNow": place.get("currentOpeningHours", {}).get("openNow"),
                           "mapsUrl": place.get("googleMapsUri", ""), "estimatedPrice": 35, "tags": place.get("types", [])})
        return result
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return []


def discovered_venues(payload: dict) -> list[dict]:
    location = payload.get("location", os.getenv("SIDEQUEST_LOCATION", "Dubai"))
    real = google_places(location)
    if real:
        return real
    live = exa_context(location_label(location), str(payload.get("request", "")))
    result = []
    for i, item in enumerate(live):
        result.append({"id": f"exa_{i+1}", "name": str(item.get("title") or "Local experience")[:100], "icon": "✦",
                       "sourceUrl": item.get("url", ""), "details": " ".join(item.get("highlights", []))[:800],
                       "estimatedPrice": 35, "tags": ["social", "local"]})
    return result or payload.get("venues", [])


def exa_context(location: str, request_text: str) -> list[dict]:
    key = os.getenv("EXA_API_KEY")
    if not key:
        return []
    query = f"real restaurants activities things to do near {location} open today prices {request_text}".strip()
    try:
        data = json_request(
            "https://api.exa.ai/search",
            {"query": query, "type": "auto", "numResults": 5, "contents": {"highlights": {"maxCharacters": 500}}},
            {"x-api-key": key},
        )
        return [{"title": x.get("title"), "url": x.get("url"), "highlights": x.get("highlights", [])} for x in data.get("results", [])]
    except (OSError, ValueError, KeyError):
        return []


def valid_compromise(candidate: object, venues: list[dict]) -> dict | None:
    if not isinstance(candidate, dict):
        return None
    allowed = {str(v.get("id")): v for v in venues if v.get("id")}
    stops = candidate.get("stops")
    if not isinstance(stops, list) or len(stops) != 3:
        return None
    clean_stops = []
    for stop in stops:
        if not isinstance(stop, dict) or str(stop.get("venueId")) not in allowed:
            return None
        venue = allowed[str(stop["venueId"])]
        clean_stops.append({
            "venueId": venue["id"], "name": venue["name"], "icon": venue.get("icon", "✦"),
            "challenge": str(stop.get("challenge", "Make a memory together."))[:160],
        })
    try:
        price = int(candidate.get("pricePerPerson"))
        match = max(0, min(100, int(candidate.get("match"))))
    except (TypeError, ValueError):
        return None
    reasons = candidate.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        return None
    return {"title": str(candidate.get("title", "A little bit of everyone's night"))[:80], "stops": clean_stops,
            "pricePerPerson": price, "match": match, "reasons": [str(x)[:120] for x in reasons[:5]],
            "summary": str(candidate.get("summary", "A plan designed around the whole party."))[:240]}


def call_agent(payload: dict) -> tuple[dict, str, bool]:
    venues = discovered_venues(payload)
    live_context = exa_context(location_label(payload.get("location", os.getenv("SIDEQUEST_LOCATION", "Dubai"))), payload.get("request", ""))
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return FALLBACK, "fallback_no_openrouter_key", bool(live_context)

    schema = {"type": "object", "additionalProperties": False, "properties": {
        "title": {"type": "string"}, "pricePerPerson": {"type": "integer"}, "match": {"type": "integer"},
        "summary": {"type": "string"}, "reasons": {"type": "array", "items": {"type": "string"}},
        "stops": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "additionalProperties": False,
            "properties": {"venueId": {"type": "string"}, "challenge": {"type": "string"}}, "required": ["venueId", "challenge"]}},
    }, "required": ["title", "pricePerPerson", "match", "summary", "reasons", "stops"]}
    system = """You are SideQuest Agent, one multiplayer planning agent. Resolve the group's disagreement. Use only supplied venue IDs. Never invent venues. Return JSON matching the schema. Keep it fun, practical, and within the lowest member budget when possible. Match is your qualitative recommendation, but the app will cap it and display it as a demo score."""
    user = {"group": payload.get("group"), "request": payload.get("request"), "location": payload.get("location"),
            "plans": payload.get("plans"), "votes": payload.get("votes"), "venues": venues, "exaContext": live_context}
    try:
        response = json_request("https://openrouter.ai/api/v1/chat/completions", {
            "model": os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user)}],
            "temperature": 0.4,
            "response_format": {"type": "json_schema", "json_schema": {"name": "sidequest_compromise", "strict": True, "schema": schema}},
        }, {"Authorization": f"Bearer {api_key}", "HTTP-Referer": "http://localhost:4173", "X-Title": "SideQuest"})
        content = response["choices"][0]["message"]["content"]
        parsed = json.loads(content) if isinstance(content, str) else content
        clean = valid_compromise(parsed, venues)
        if clean:
            return clean, "openrouter", bool(live_context)
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        pass
    return FALLBACK, "fallback_provider_error", bool(live_context)


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path == "/api/agent/plans":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                plans, source, exa_used = call_planner(payload)
                self.send_json(200, {"ok": True, "source": source, "exaUsed": exa_used, "plans": plans})
            except (ValueError, TypeError, json.JSONDecodeError):
                self.send_json(400, {"ok": False, "error": "Invalid request"})
            return
        if self.path != "/api/agent/compromise":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result, source, exa_used = call_agent(payload)
            self.send_json(200, {"ok": True, "source": source, "exaUsed": exa_used, "compromise": result})
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json(400, {"ok": False, "error": "Invalid request"})

    def send_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    os.chdir(ROOT)
    port = int(os.getenv("PORT", "4173"))
    print(f"SideQuest running at http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
