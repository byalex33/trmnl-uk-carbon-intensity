"""Normalize carbonintensity.org.uk multi-URL poll into flat Liquid vars."""
import json
import urllib.request
import urllib.error

REGIONAL = "https://api.carbonintensity.org.uk/regional/postcode/{outcode}"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "trmnl-uk-carbon/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def run(input):
    # Multi-URL poll: IDX_0 intensity, IDX_1 generation, IDX_2 forecast
    # Also accept single-object merge after platform unwrap
    idx0 = input.get("IDX_0") or input
    idx1 = input.get("IDX_1") or {}
    idx2 = input.get("IDX_2") or {}

    intensity_block = None
    region_name = "National"
    mix = []

    # Current intensity (national)
    data0 = idx0.get("data") if isinstance(idx0, dict) else None
    if isinstance(data0, list) and data0:
        intensity_block = data0[0]
    elif isinstance(data0, dict):
        intensity_block = data0

    # Generation mix (national)
    gen = idx1.get("data") if isinstance(idx1, dict) else None
    if isinstance(gen, dict):
        mix = gen.get("generationmix") or []

    # Optional regional override via outcode carried in custom fields echo
    # Hosted TRMNL injects custom fields into polling URLs only; for local
    # preview .trmnlp.yml supplies outcode. Try regional fetch when present
    # in plugin_settings nested under input (some runtimes) or env-style.
    outcode = (
        (input.get("trmnl") or {}).get("plugin_settings", {}).get("custom_fields_values", {}).get("outcode")
        or input.get("outcode")
        or ""
    )
    outcode = (outcode or "").strip().upper()
    if outcode:
        try:
            reg = _get(REGIONAL.format(outcode=outcode))
            regions = reg.get("data") or []
            if regions:
                r0 = regions[0]
                region_name = r0.get("shortname") or r0.get("dnoregion") or outcode
                slots = r0.get("data") or []
                if slots:
                    intensity_block = slots[0]
                    mix = slots[0].get("generationmix") or mix
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            pass

    intensity = (intensity_block or {}).get("intensity") or {}
    actual = intensity.get("actual")
    forecast_now = intensity.get("forecast")
    index = (intensity.get("index") or "unknown").title()
    gco2 = actual if actual is not None else forecast_now

    # Forecast periods (next ~8 half-hours with future/null actual preferred)
    fdata = idx2.get("data") if isinstance(idx2, dict) else []
    if not isinstance(fdata, list):
        fdata = []
    forecast = []
    for slot in fdata:
        inten = slot.get("intensity") or {}
        # skip past slots that already have actual when we have enough future
        forecast.append({
            "from": (slot.get("from") or "")[11:16],
            "to": (slot.get("to") or "")[11:16],
            "gco2": inten.get("forecast"),
            "index": (inten.get("index") or "").title(),
            "has_actual": inten.get("actual") is not None,
        })
    # Prefer upcoming (no actual yet), else take next 8
    upcoming = [f for f in forecast if not f["has_actual"]]
    forecast = (upcoming or forecast)[:8]

    # Sort mix by perc desc, drop zeros for clutter
    mix_sorted = sorted(
        [{"fuel": m.get("fuel", "").title(), "perc": m.get("perc", 0)} for m in mix],
        key=lambda x: x["perc"],
        reverse=True,
    )
    mix_shown = [m for m in mix_sorted if m["perc"] and m["perc"] > 0][:8]

    return {
        "gco2": gco2,
        "index": index,
        "region": region_name,
        "from": (intensity_block or {}).get("from", ""),
        "to": (intensity_block or {}).get("to", ""),
        "forecast": forecast,
        "mix": mix_shown,
        "mix_top": mix_shown[0] if mix_shown else {"fuel": "—", "perc": 0},
    }
