from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Union, List
import requests

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "qwen2.5:7b"

LANG_MAP = {
    "JA": "Japanese",
    "EN": "English",
    "ZH": "Chinese",
    "ZH-CN": "Chinese",
    "ZH-TW": "Chinese (Traditional)",
}

app = FastAPI()

class Req(BaseModel):
    # VTuber 端有時會傳 ["句1","句2",...]；所以接受字串或字串列表
    text: Union[str, List[str]]
    target_lang: str = "JA"

def translate_with_ollama(text: str, target_lang: str) -> str:
    target = LANG_MAP.get(target_lang.upper(), "Japanese")
    sys = (
        f"You are a professional translator. "
        f"Translate the user's input into {target}. "
        f"Return ONLY the translated sentence, no explanations, no labels, no quotes."
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

@app.post("/translate")
def translate(req: Req):
    try:
        if isinstance(req.text, list):
            out_list = []
            for t in req.text:
                if not isinstance(t, str):
                    t = str(t)
                out = translate_with_ollama(t, req.target_lang)
                out_list.append({"text": out})
            # ✅ 關鍵：頂層就是 translations
            return {"translations": out_list}
        else:
            out = translate_with_ollama(req.text, req.target_lang)
            return {"translations": [{"text": out}]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
