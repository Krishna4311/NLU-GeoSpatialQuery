from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import re
import os
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import logging
import traceback

logger = logging.getLogger("uvicorn.error")
load_dotenv()

app = FastAPI(title="Simple NLU Metric Extractor + Metric API Caller")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=".", html=True), name="static")

METRIC_KEYWORDS = {
    "temperature": [r"temp(?:erature)?", r"hotter", r"colder", r"degrees", r"°c", r"°f", r"\bweather\b"],
    "rainfall": [r"rain(?:fall)?", r"precipitation", r"mm of rain", r"rainy"],
    "humidity": [r"humidity", r"humid"],
    "wind_speed": [r"wind(?: speed)?", r"windspeed", r"wind gust"],
    "pressure": [r"pressure", r"hpa", r"atm"],
}

LOCATION_PATTERN = r"in ([A-Z0-9a-z \-_,]+)"

class ExtractRequest(BaseModel):
    text: str

class ExtractResponse(BaseModel):
    metrics: List[str]
    raw_text: str
    location: Optional[str] = None
    time: Optional[str] = None

def extract_metrics(text: str) -> Dict[str, Any]:
    text_low = text.lower()
    found = []
    for metric, patterns in METRIC_KEYWORDS.items():
        for pat in patterns:
            if re.search(pat, text_low):
                found.append(metric)
                break
    location = None
    m = re.search(LOCATION_PATTERN, text, flags=re.IGNORECASE)
    if m:
        location = m.group(1).strip()
    months = r"(january|february|march|april|may|june|july|august|september|october|november|december|today|now|yesterday|last week|this week)"
    t = None
    tm = re.search(months, text_low)
    if tm:
        t = tm.group(1)
    return {"metrics": list(dict.fromkeys(found)), "location": location, "time": t}

_TIME_TOKENS = [
    r"\bnow\b", r"\btoday\b", r"\byesterday\b", r"\blast\b", r"\bthis\b", r"\bnext\b",
    r"\bweek\b", r"\bmonth\b",
    r"\bjan(?:uary)?\b", r"\bfeb(?:ruary)?\b", r"\bmar(?:ch)?\b", r"\bapr(?:il)?\b",
    r"\bmay\b", r"\bjun(?:e)?\b", r"\bjul(?:y)?\b", r"\baug(?:ust)?\b", r"\bsep(?:tember)?\b",
    r"\boct(?:ober)?\b", r"\bnov(?:ember)?\b", r"\bdec(?:ember)?\b"
]
_TIME_RE = re.compile("|".join(_TIME_TOKENS), flags=re.IGNORECASE)

def sanitize_location(raw_location: Optional[str]) -> Optional[str]:
    if not raw_location:
        return None
    loc = raw_location
    loc = re.sub(r"[()]", " ", loc).strip()
    loc = re.sub(r"[.,;:]+$", "", loc).strip()
    loc = _TIME_RE.sub("", loc).strip()
    loc = re.sub(r"\s{2,}", " ", loc).strip().strip(",")
    return loc or None

def call_openweathermap_current(location: str, api_key: str) -> Dict[str, Any]:
    if not api_key:
        raise RuntimeError("OpenWeather API key is missing. Set OWM_API_KEY (or OWA) in environment.")
    if not location:
        raise RuntimeError("Location is empty.")
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": location, "appid": api_key, "units": "metric"}
    logger.info("Calling OpenWeather API: %s params=%s", url, params)
    resp = requests.get(url, params=params, timeout=10)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(f"{resp.status_code} {resp.reason}: {resp.text}") from e
    return resp.json()

def extract_metric_from_owm(metric: str, owm_json: Dict[str, Any]) -> Any:
    if metric == "temperature":
        return owm_json.get("main", {}).get("temp")
    if metric == "humidity":
        return owm_json.get("main", {}).get("humidity")
    if metric == "pressure":
        return owm_json.get("main", {}).get("pressure")
    if metric == "wind_speed":
        return owm_json.get("wind", {}).get("speed")
    if metric == "rainfall":
        rain = owm_json.get("rain")
        if isinstance(rain, dict):
            return rain.get("1h") or rain.get("3h") or 0.0
        return 0.0
    return None

def split_locations(raw_location: Optional[str]) -> List[str]:
    if not raw_location:
        return []
    parts = re.split(r"\s+and\s+|,|;|/|\|", raw_location, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p and p.strip()]

@app.post("/extract_metric")
def api_extract(req: ExtractRequest):
    try:
        res = extract_metrics(req.text)
        return ExtractResponse(
            metrics=res.get("metrics", []),
            raw_text=req.text,
            location=res.get("location"),
            time=res.get("time"),
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("extract_metric error: %s\n%s", e, tb)
        raise HTTPException(status_code=500, detail={"error": str(e), "trace": tb})

@app.get("/")
def serve_frontend():
    return FileResponse("nlu_frontend.html")

@app.get("/get_metric")
def api_get_metric(metric: str, location: str = None, request: Request = None):
    metric = (metric or "").lower()
    if metric not in METRIC_KEYWORDS:
        raise HTTPException(status_code=400, detail=f"Metric '{metric}' not supported.")
    if not location:
        raise HTTPException(status_code=400, detail="`location` query param is required")
    api_key = os.getenv("OWM_API_KEY") or os.getenv("OWA") or None
    logger.info("api_get_metric called: metric=%s, raw_location=%s, api_key_present=%s", metric, location, bool(api_key))
    raw_locations = split_locations(location)
    clean_locations = []
    for rl in raw_locations:
        cl = sanitize_location(rl)
        if cl:
            clean_locations.append(cl)
    if not clean_locations:
        raise HTTPException(status_code=400, detail="No valid location found after parsing/sanitization")
    results = []
    errors = []
    for loc in clean_locations:
        try:
            owm = call_openweathermap_current(loc, api_key)
            value = extract_metric_from_owm(metric, owm)
            results.append({"metric": metric, "location": loc, "value": value, "units": "metric (see provider)", "provider": "openweathermap"})
        except requests.HTTPError as e:
            errors.append({"location": loc, "error": str(e)})
        except Exception as e:
            errors.append({"location": loc, "error": str(e)})
    if not results and errors:
        raise HTTPException(status_code=502, detail={"errors": errors})
    return {"results": results, "errors": errors}

# uvicorn nlu_main:app --reload --host 0.0.0.0 --port 8000
# localhost:8000
