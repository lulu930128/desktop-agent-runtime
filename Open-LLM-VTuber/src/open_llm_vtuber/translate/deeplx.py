import json
import logging
import os
from typing import List, Optional
import requests

logger = logging.getLogger(__name__)

# 可用環境變數覆寫端點，方便測試或外部注入
DEEPLX_ENDPOINT = os.getenv("DEEPLX_ENDPOINT")

def _parse_response_text(j: dict, default: str) -> str:
    """
    相容多種 DeepLX / 代理回包格式：
      1) {"data":"..."} (常見 DeepLX)
      2) {"translations":[{"text":"..."}]} (DeepL 官方風格)
      3) {"alternatives": {..., "data":"..."}}
      4) {"result":"..."}（某些分支）
    解析不到就回 default（原文），不中斷管線。
    """
    if not isinstance(j, dict):
        return default
    data = j.get("data")
    if isinstance(data, str) and data.strip():
        return data
    ts = j.get("translations")
    if isinstance(ts, list) and ts:
        t0 = ts[0]
        if isinstance(t0, dict):
            txt = t0.get("text")
            if isinstance(txt, str) and txt.strip():
                return txt
    alt = j.get("alternatives")
    if isinstance(alt, dict):
        d = alt.get("data")
        if isinstance(d, str) and d.strip():
            return d
    res = j.get("result")
    if isinstance(res, str) and res.strip():
        return res
    return default

def _post(ep: str, payload: dict, timeout: float = 8.0) -> Optional[str]:
    """
    發一次請求；HTTP 200 則嘗試解析文字，否則回 None。
    """
    r = requests.post(ep, json=payload, timeout=timeout)
    if r.status_code != 200:
        logger.warning("DeepLX HTTP %s: %s", r.status_code, r.text[:200])
        return None
    try:
        j = r.json()
    except Exception:
        logger.exception("DeepLX response is not JSON: %r", r.text[:200])
        return None
    text = _parse_response_text(j, default="")
    return text if isinstance(text, str) else ""

def translate(text: str,
              source_lang: Optional[str] = None,
              target_lang: Optional[str] = None,
              endpoint: Optional[str] = None) -> str:
    """
    翻譯主函式。若外層沒傳 endpoint，允許用環境變數 DEEPLX_ENDPOINT。
    自動嘗試三種 payload 風格（A/B/C），回包做容錯解析。
    任一成功即回翻譯文本；若全失敗，回原文，避免中斷對話/TTS。
    """
    try:
        if not isinstance(text, str) or not text.strip():
            return text

        ep = endpoint or DEEPLX_ENDPOINT
        if not ep:
            logger.error("DeepLX endpoint is not set.")
            return text

        tgt = target_lang or "JA"
        src = source_lang or "auto"

        # A：字串 + 指定 src/tgt（多數 DeepLX 支援）
        payloadA = {"text": text, "source_lang": src, "target_lang": tgt}
        out = _post(ep, payloadA)
        if out:
            return out

        # B：text 陣列 + 只指定 tgt（有些分支偏好）
        payloadB = {"text": [text], "target_lang": tgt}
        out = _post(ep, payloadB)
        if out:
            return out

        # C：字串 + 只指定 tgt（最精簡）
        payloadC = {"text": text, "target_lang": tgt}
        out = _post(ep, payloadC)
        if out:
            return out

        return text
    except Exception as e:
        logger.exception("DeepLX translate fatal: %s", e)
        return text

class DeepLXTranslate:
    """
    與 translate_factory 預期相容的薄包裝類別。
    允許使用 api_endpoint 或 endpoint 作為引數名稱；吃下多餘 **kwargs 以提升相容性。
    """
    def __init__(self,
                 api_endpoint: Optional[str] = None,
                 endpoint: Optional[str] = None,
                 target_lang: str = "JA",
                 source_lang: str = "auto",
                 timeout: float = 8.0,
                 **kwargs):
        # 兼容兩個參數名
        self.endpoint = endpoint or api_endpoint or DEEPLX_ENDPOINT
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.timeout = timeout
        if not self.endpoint:
            logger.error("DeepLXTranslate: endpoint/api_endpoint is not set.")

    def translate(self, text: str) -> str:
        return translate(text,
                         source_lang=self.source_lang,
                         target_lang=self.target_lang,
                         endpoint=self.endpoint)

    # 常見別名
    def translate_text(self, text: str) -> str:
        return self.translate(text)

    def __call__(self, text: str) -> str:
        return self.translate(text)

    def translate_batch(self, texts: List[str]) -> List[str]:
        return [self.translate(t) for t in texts]

    def translate_list(self, texts: List[str]) -> List[str]:
        return self.translate_batch(texts)

__all__ = ["DeepLXTranslate", "translate"]