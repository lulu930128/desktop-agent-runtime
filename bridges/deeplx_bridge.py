# C:\kuro\bridges\deeplx_bridge.py
from fastapi import FastAPI, Request
from fastapi.responses import Response
import httpx
import os
import time
import json
import logging
import re
import traceback
from typing import Dict, Any

app = FastAPI()

# =======================
# Config
# =======================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-5-mini").strip()
OPENAI_RESPONSES_URL = os.getenv("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses").strip()

# Optional DeepLX fallback (default off, because upstream often 503)
DEEPLX_ENDPOINT = os.getenv("DEEPLX_ENDPOINT", "http://127.0.0.1:1189/translate").strip()
ENABLE_DEEPLX_FALLBACK = os.getenv("ENABLE_DEEPLX_FALLBACK", "0").strip().lower() in ("1", "true", "yes", "y")

DEDUP_WINDOW_S = float(os.getenv("DEDUP_WINDOW_S", "1.2"))
TIMEOUT_S = float(os.getenv("TRANSLATE_TIMEOUT_S", "45"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kuro-translate-bridge")

# Simple dedup cache (last request)
last = {"text": "", "ts": 0.0, "data": ""}


# =======================
# UTF-8 JSON Response Helper
# =======================
def json_utf8(obj: Dict[str, Any]) -> Response:
    """
    Force UTF-8 JSON output with charset header to avoid mojibake / ???? in some clients.
    """
    return Response(
        content=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        media_type="application/json; charset=utf-8",
    )


# =======================
# Language / Skip Helpers
# =======================
def contains_kana(s: str) -> bool:
    """Heuristic: if text contains any Hiragana/Katakana, treat as Japanese and skip translation."""
    for ch in s:
        code = ord(ch)
        if 0x3040 <= code <= 0x309F:  # Hiragana
            return True
        if 0x30A0 <= code <= 0x30FF:  # Katakana
            return True
        if 0x31F0 <= code <= 0x31FF:  # Katakana Extensions
            return True
        if 0xFF66 <= code <= 0xFF9F:  # Halfwidth Katakana
            return True
    return False


def is_mostly_japanese(s: str) -> bool:
    """Safer skip-translation heuristic.
    We only skip when the text looks like a Japanese sentence (has kana + common particles/aux).
    This avoids skipping mixed zh/ja like 'ゆきゆき在這裡' which must still be translated.
    """
    if not s:
        return False
    if not contains_kana(s):
        return False
    # Strong Japanese sentence cues
    strong = ["です", "ます", "だよ", "だね", "かな", "でしょう", "ません", "だった", "だっ"]
    if any(x in s for x in strong):
        return True
    # Common particles (single kana) - require at least one AND some length
    particles = ["は", "が", "を", "に", "で", "と", "の", "も", "へ", "や"]
    if any(p in s for p in particles) and len(s) >= 10:
        return True
    return False

# =======================
# OpenAI (Responses API) Translator
# =======================
def _extract_output_text(resp_json: Dict[str, Any]) -> str:
    """
    Responses API can return output_text directly, or inside output[].content[].
    Try both.
    """
    out = (resp_json.get("output_text") or "").strip()
    if out:
        return out

    parts = []
    for item in resp_json.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    parts.append(c.get("text", ""))
    return "".join(parts).strip()


async def translate_openai_to_ja(text: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing in environment.")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Requirement:
    # - If already Japanese => return unchanged
    # - Else => translate to Japanese
    # - Output ONLY the final text
    instructions = (
        "You are a translation engine.\n"
        "Detect the input language automatically.\n"
        "If the input is already Japanese, return it unchanged.\n"
        "Otherwise translate the input into Japanese.\n"
        "Output ONLY the final text (no quotes, no explanations, no prefixes).\n"
        "Preserve line breaks, punctuation, lists, and code blocks.\n"
    )

    body = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": text,
        "reasoning": {"effort": "low"},
        "max_output_tokens": 2048,
        "store": False,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(OPENAI_RESPONSES_URL, headers=headers, json=body)

    if r.status_code != 200:
        raise RuntimeError(f"OpenAI HTTP {r.status_code}: {r.text[:800]}")

    data = r.json()
    out = _extract_output_text(data).replace("\ufeff", "").strip()
    if not out:
        raise RuntimeError(f"OpenAI empty output_text. Raw: {json.dumps(data)[:1000]}")
    return out


# =======================
# DeepLX (Optional Fallback)
# =======================
async def translate_deeplx_to_ja(text: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            DEEPLX_ENDPOINT,
            json={"text": text, "source_lang": "AUTO", "target_lang": "JA"},
        )

    if r.status_code == 503:
        raise RuntimeError("DeepLX upstream 503 (rate-limited / IP blocked).")
    if r.status_code >= 400:
        raise RuntimeError(f"DeepLX HTTP {r.status_code}: {r.text[:300]}")

    resp = r.json()
    out = (resp.get("data") or resp.get("text") or "").replace("\ufeff", "").strip()
    if not out:
        raise RuntimeError(f"DeepLX empty output. Raw: {json.dumps(resp)[:800]}")
    return out


# =======================
# Core Translate Implementation
# =======================
async def _translate_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = (payload.get("text") or "").replace("\ufeff", "").strip()

    if not text:
        return {"out": "", "provider": "noop", "skipped": False, "errors": {}}

    # 1) Fast skip: contains kana => Japanese => do not translate
    if is_mostly_japanese(text):
        now = time.time()
        last.update({"text": text, "ts": now, "data": text})
        return {"out": text, "provider": "skip-ja", "skipped": True, "errors": {}}

    # 2) Dedup window (only for non-kana texts)
    now = time.time()
    if text == last["text"] and (now - last["ts"]) < DEDUP_WINDOW_S:
        return {"out": last["data"], "provider": "dedup-cache", "skipped": False, "errors": {}}

    errors: Dict[str, str] = {}

    # 3) Primary: OpenAI
    try:
        out = await translate_openai_to_ja(text)

        # If OpenAI decides it's already Japanese, it should return unchanged.
        if out.strip() == text.strip():
            last.update({"text": text, "ts": now, "data": out})
            return {
                "out": out,
                "provider": f"openai:{OPENAI_MODEL}:already-ja",
                "skipped": True,
                "errors": {},
            }

        last.update({"text": text, "ts": now, "data": out})
        return {"out": out, "provider": f"openai:{OPENAI_MODEL}", "skipped": False, "errors": {}}

    except Exception as e:
        errors["openai"] = str(e)
        logger.error("OpenAI translate failed: %s", errors["openai"])
        logger.debug(traceback.format_exc())

    # 4) Optional fallback: DeepLX
    if ENABLE_DEEPLX_FALLBACK:
        try:
            out = await translate_deeplx_to_ja(text)
            last.update({"text": text, "ts": now, "data": out})
            return {"out": out, "provider": "deeplx", "skipped": False, "errors": errors}
        except Exception as e:
            errors["deeplx"] = str(e)
            logger.error("DeepLX translate failed: %s", errors["deeplx"])
            logger.debug(traceback.format_exc())

    # 5) Ultimate fallback: return original
    last.update({"text": text, "ts": now, "data": text})
    return {"out": text, "provider": "fallback-original", "skipped": False, "errors": errors}

# =======================
# Speech Renderer (spoken_short) + Emotion
# =======================
EMOTION_KEYS = ["neutral","joy","smirk","surprise","anger","sadness","fear","disgust"]
SPOKEN_MAX_CHARS = int(os.getenv("SPOKEN_MAX_CHARS", "120"))

def _safe_json_parse(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        # try slice from first { to last }
        a = s.find("{")
        b = s.rfind("}")
        if a != -1 and b != -1 and b > a:
            try:
                return json.loads(s[a:b+1])
            except Exception:
                return {}
        return {}

async def render_openai_spoken_short(text: str, style_prompt_ja: str = "") -> Dict[str, Any]:
    """
    Returns dict: {"ja": "...", "emotion": "..."}.
    Uses ONE OpenAI call to generate short spoken Japanese + emotion classification.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing in environment.")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    base_rules = (
        "You are a speech renderer for a VTuber desktop assistant.\n"
        "Input is Traditional Chinese (or mixed). Produce:\n"
        "1) ja: Natural spoken Japanese suitable for TTS.\n"
        f"   - Keep it short (<= {SPOKEN_MAX_CHARS} Japanese characters ideally).\n"
        "   - NO bullet lists, NO step numbers (1./2./-), NO headings.\n"
        "   - If the input is long or contains lists, summarize into 1-2 spoken sentences.\n"
        "   - Do not include Chinese characters that are not common in Japanese; avoid mixing languages.\n"
        "2) emotion: one of [neutral, joy, smirk, surprise, anger, sadness, fear, disgust].\n"
        "Return ONLY a valid JSON object: {\"ja\":\"...\",\"emotion\":\"...\"}.\n"
    )

    if style_prompt_ja:
        base_rules += "\nCharacter style:\n" + style_prompt_ja.strip() + "\n"

    body = {
        "model": OPENAI_MODEL,
        "instructions": base_rules,
        "input": text,
        "reasoning": {"effort": "low"},
        "max_output_tokens": 512,
        "store": False,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(OPENAI_RESPONSES_URL, headers=headers, json=body)

    if r.status_code != 200:
        raise RuntimeError(f"OpenAI HTTP {r.status_code}: {r.text[:800]}")

    data = r.json()
    out_raw = _extract_output_text(data).replace("\ufeff", "").strip()
    if not out_raw:
        raise RuntimeError("OpenAI empty output_text for render_spoken.")

    obj = _safe_json_parse(out_raw)
    ja = (obj.get("ja") or "").strip()
    emo = _canonical_emotion(obj.get("emotion"))

    if not ja:
        # fallback: use raw text as ja if looks japanese; else throw
        if is_mostly_japanese(out_raw):
            ja = out_raw
        else:
            raise RuntimeError(f"render_spoken returned no ja. Raw={out_raw[:200]!r}")

    if emo not in EMOTION_KEYS:
        emo = "neutral"

    # Ensure no bullet/step markers leak into spoken output
    ja = re.sub(r"^\s*[-•]\s*", "", ja)
    ja = re.sub(r"\b\d+\s*[.)．、:：]\s*", "", ja)

    # Hard truncate to prevent long TTS queues
    if len(ja) > SPOKEN_MAX_CHARS * 2:
        ja = ja[:SPOKEN_MAX_CHARS * 2].rstrip()

    return {"ja": ja, "emotion": emo}

def _canonical_emotion(e: Any) -> str:
    if not e:
        return "neutral"
    t = str(e).strip().lower()
    mapping = {
        "happy":"joy","joy":"joy","smile":"joy",
        "sad":"sadness","sadness":"sadness",
        "angry":"anger","anger":"anger",
        "surprised":"surprise","surprise":"surprise",
        "fear":"fear","disgust":"disgust",
        "neutral":"neutral","smirk":"smirk",
    }
    return mapping.get(t, t)



# =======================
# Routes
# =======================
@app.post("/translate")
async def translate(req: Request):
    payload = await req.json()
    result = await _translate_impl(payload)
    # Keep upstream-compatible response format
    return json_utf8({"code": 200, "data": result["out"]})


@app.post("/translate_debug")
async def translate_debug(req: Request):
    payload = await req.json()
    result = await _translate_impl(payload)
    return json_utf8(
        {
            "code": 200,
            "data": result["out"],
            "provider": result["provider"],
            "skipped": result["skipped"],
            "openai_key_loaded": bool(OPENAI_API_KEY),
            "errors": result["errors"],
        }
    )


@app.post("/render_spoken")
async def render_spoken(req: Request):
    payload = await req.json()
    text = (payload.get("text") or "").replace("\ufeff", "").strip()
    style_prompt_ja = (payload.get("style_prompt_ja") or "").strip()
    mode = (payload.get("mode") or "spoken_short").strip().lower()

    if not text:
        return json_utf8({"code": 200, "data": "", "emotion": "neutral", "provider": "noop"})

    # If already Japanese (true Japanese sentence), return as-is and neutral emotion (cheap path)
    if is_mostly_japanese(text):
        return json_utf8({"code": 200, "data": text, "emotion": "neutral", "provider": "skip-ja"})

    errors: Dict[str, str] = {}

    # Primary: OpenAI render spoken short
    try:
        obj = await render_openai_spoken_short(text, style_prompt_ja=style_prompt_ja)
        return json_utf8({"code": 200, "data": obj["ja"], "emotion": obj["emotion"], "provider": f"openai:{OPENAI_MODEL}:render_spoken"})
    except Exception as e:
        errors["openai"] = str(e)
        logger.error("OpenAI render_spoken failed: %s", errors["openai"])
        logger.debug(traceback.format_exc())

    # Fallback: translate only (no emotion)
    try:
        out = await translate_openai_to_ja(text)
        return json_utf8({"code": 200, "data": out, "emotion": "neutral", "provider": f"openai:{OPENAI_MODEL}:translate_only", "errors": errors})
    except Exception as e:
        errors["translate_only"] = str(e)
        logger.error("Fallback translate_only failed: %s", errors["translate_only"])
        logger.debug(traceback.format_exc())

    if ENABLE_DEEPLX_FALLBACK:
        try:
            out = await translate_deeplx_to_ja(text)
            return json_utf8({"code": 200, "data": out, "emotion": "neutral", "provider": "deeplx", "errors": errors})
        except Exception as e:
            errors["deeplx"] = str(e)

    return json_utf8({"code": 200, "data": text, "emotion": "neutral", "provider": "fallback-original", "errors": errors})
