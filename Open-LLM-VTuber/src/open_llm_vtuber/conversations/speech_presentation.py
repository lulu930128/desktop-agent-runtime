from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import unicodedata
from decimal import Decimal
from typing import Any


SPEECH_ROUTE_SILENT_DISPLAY = "silent_display"
SPEECH_ROUTE_RENDER_THEN_TTS = "render_then_tts"
SPEECH_PLAN_SOURCE = "source"
SPEECH_PLAN_FIXED_JA = "fixed_ja"
SPEECH_PLAN_SKIP = "skip"
SPEECH_POLICY_CODE_JA = "コードは画面に表示しました。"
SPEECH_POLICY_TABLE_JA = "表にまとめて画面に表示しました。"
SPEECH_POLICY_URL_JA = "参考リンクは画面に表示しています。"
SPEECH_POLICY_ERROR_JA = "システムでエラーが出ました。詳細は画面に表示しています。"
SPEECH_POLICY_STOCK_NUMBERS_JA = "詳しい数字は画面に出しています。"
SPEECH_POLICY_OPTIONS_JA = "選択肢は画面に表示しています。"
SPEECH_POLICY_DETAIL_ITEMS_JA = "詳しい項目は画面に表示しています。"

# A footer keeps arbitrary Markdown/code in display lossless. Only this reserved
# line enters the private lane; tool arguments never pass through this parser.
SPEECH_LANE_CONTRACT = "kuro.speech-lanes.v1"
SPEECH_LANE_MARKER = "\n<<<KURO_SPEECH_V1>>>"
SPEECH_LANE_V2_CONTRACT = "kuro.speech-lanes.v2"
SPEECH_LANE_V2_MARKER = "\n<<<KURO_SPEECH_V2>>>"
_LANE_MARKERS = (SPEECH_LANE_MARKER, SPEECH_LANE_V2_MARKER)
_EMOTIONS = {"neutral", "joy", "sadness", "anger", "surprise", "fear", "disgust", "smirk"}


def _inside_markdown_literal(text: str) -> bool:
    """Context immediately before a reserved line, including split fence runs."""
    fence = None
    inline_ticks = 0
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            continue
        if match and not inline_ticks and (match[1][0] != "`" or "`" not in match[2]):
            fence = match[1]
            continue
        for run in re.finditer(r"(?<!\\)(`+)", line):
            size = len(run[1])
            if not inline_ticks:
                inline_ticks = size
            elif inline_ticks == size:
                inline_ticks = 0
    return bool(fence or inline_ticks)


class SpeechLaneResult(dict):
    """Only public diagnostics serialize; repair drafts stay inside Conversation."""
    candidate = None


class SpeechLaneParser:
    """Incremental footer parser for a single model response. Invalid speech never consumes display."""

    def __init__(self, *, strip_control_prefix: bool = True) -> None:
        self.pending = ""
        self.display = ""
        self.footer = ""
        self.in_speech = False
        self.contract = SPEECH_LANE_CONTRACT
        self.leading_checked = not strip_control_prefix

    def feed(self, chunk: str) -> str:
        if self.in_speech:
            self.footer += chunk
            return ""
        self.pending += chunk
        if not self.display and self.pending:
            # A footer-only/malformed answer can start at absolute BOL. Its
            # private JSON must not escape merely because Display was omitted.
            bare_markers = tuple(marker[1:] for marker in _LANE_MARKERS)
            if any(marker.startswith(self.pending) for marker in bare_markers):
                return ""
            if any(self.pending.startswith(marker) for marker in bare_markers):
                self.pending = "\n" + self.pending
        if not self.leading_checked:
            # A leading tag is ambiguous with a Markdown reference label. Only
            # this noncompliant prefix is held (<=4096 chars) until the real
            # footer proves the complete Display; ordinary streaming is unchanged.
            tokens = tuple(f"[{emotion}]" for emotion in _EMOTIONS)
            if any(token.startswith(self.pending) or self.pending == token + "\r" for token in tokens):
                return ""
            match = re.match(r"^\[(" + "|".join(sorted(_EMOTIONS)) + r")\](\r?\n|[ \t])", self.pending)
            if match:
                boundaries = []
                for candidate in _LANE_MARKERS:
                    start = self.pending.find(candidate)
                    while start >= 0:
                        if not _inside_markdown_literal(self.pending[:start] + "\n"):
                            boundaries.append(start)
                            break
                        start = self.pending.find(candidate, start + len(candidate))
                boundary = min(boundaries, default=-1)
                if boundary < 0 and len(self.pending) <= 4096:
                    return ""
                if 0 <= boundary <= 4096:
                    prefix_display = self.pending[:boundary]
                    reference = re.search(r"(?im)^ {0,3}\[" + re.escape(match[1]) + r"\]:", prefix_display)
                    if not reference and prefix_display.strip() != f"[{match[1]}]":
                        self.pending = self.pending[match.end():]
            self.leading_checked = True
        def next_marker():
            matches = [(self.pending.find(marker), marker) for marker in _LANE_MARKERS]
            return min((item for item in matches if item[0] >= 0), default=(-1, ""))
        index, marker = next_marker()
        literal = ""
        while index >= 0 and _inside_markdown_literal(self.display + literal + self.pending[:index] + "\n"):
            # A marker inside Markdown literal content is ordinary display.
            end = index + len(marker)
            literal += self.pending[:end]
            self.pending = self.pending[end:]
            index, marker = next_marker()
        if index >= 0:
            visible = literal + self.pending[:index]
            self.contract = SPEECH_LANE_V2_CONTRACT if marker == SPEECH_LANE_V2_MARKER else SPEECH_LANE_CONTRACT
            self.footer = self.pending[index + len(marker):]
            self.pending = ""
            self.in_speech = True
        else:
            # Hold only a possible marker prefix, never a complete sentence.
            keep = 0
            for candidate in _LANE_MARKERS:
                for size in range(1, min(len(self.pending), len(candidate) - 1) + 1):
                    if self.pending.endswith(candidate[:size]):
                        keep = max(keep, size)
            visible = literal + (self.pending[:-keep] if keep else self.pending)
            self.pending = self.pending[-keep:] if keep else ""
        self.display += visible
        return visible

    def finish_display(self) -> str:
        flushed = ""
        if not self.leading_checked:
            # Missing footer/overlong ambiguity is not authority to delete text.
            self.leading_checked = True
            flushed = self.feed("")
        tail, self.pending = self.pending, ""
        # A truncated reserved control line is private too.
        if tail.startswith(("\n<<<KURO_", "<<<KURO_")) and not _inside_markdown_literal(self.display + "\n"):
            tail = ""
        self.display += tail
        return flushed + tail

    def result(self, settings: dict) -> dict:
        result = SpeechLaneResult(type="speech_lane", contract=self.contract, state="missing",
                                  text="", emotion="neutral")
        if not self.in_speech:
            return result
        result["state"] = "malformed"
        try:
            def unique_pairs(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise ValueError("duplicate speech field")
                    obj[key] = value
                return obj
            value = json.loads(self.footer, object_pairs_hook=unique_pairs)
            if self.contract == SPEECH_LANE_V2_CONTRACT:
                diagnostics = {}
                spoken, reason = SpeechPolicyEngine().validate_semantic_lane(value, self.display, settings, diagnostics=diagnostics)
                result["diagnostics"] = dict(diagnostics, rule_id=reason)
                result["state"] = reason
                if reason in {"ready", "semantic_unverified"}:
                    result.update(value, text=spoken)
                elif diagnostics.get("stage") in {"segment", "required_anchor", "display"}:
                    # Internal recovery input only. Never forward rejected drafts to presentation.
                    result.candidate = value
                return result
            if (not isinstance(value, dict)
                    or set(value) != {"contract", "locale", "policy", "text", "emotion"}
                    or value["contract"] != SPEECH_LANE_CONTRACT
                    or value["locale"] != settings["locale"]
                    or value["policy"] != settings["policy"]
                    or not isinstance(value["text"], str)
                    or value["emotion"] not in _EMOTIONS):
                return result
            result.update(value)
            result["state"] = "ready" if value["text"].strip() else "silent"
        except (ValueError, TypeError, KeyError):
            pass
        return result


def display_lane_text(raw: str, *, strip_control_prefix: bool = True) -> str:
    parser = SpeechLaneParser(strip_control_prefix=strip_control_prefix)
    parser.feed(raw)
    parser.finish_display()
    return parser.display


async def route_speech_lanes(stream, settings: dict):
    """Route text before sentence/action transforms; preserve status ordering."""
    parser = SpeechLaneParser(strip_control_prefix=settings.get("route") != "legacy_bridge")
    try:
        async for item in stream:
            if isinstance(item, str):
                visible = parser.feed(item)
                if visible:
                    yield visible
            elif isinstance(item, dict) and item.get("type") == "completion_boundary":
                tail = parser.finish_display()
                if tail:
                    yield tail
                if item.get("final"):
                    yield parser.result(settings)
                parser = SpeechLaneParser(strip_control_prefix=settings.get("route") != "legacy_bridge")
            else:
                yield item
    except Exception:
        tail = parser.finish_display()
        if tail:
            yield tail
        raise
    tail = parser.finish_display()
    if tail:
        yield tail


def filter_speech_lane(text: str, locale: str) -> tuple[str, str]:
    """Reject unsafe technical payloads as a whole, preserving negation/limits.

    Do not salvage fragments around code/URLs: deleting them can invert a
    condition. The complete display remains available on rejection.
    """
    if locale not in {"ja-JP", "zh-Hant", "en-US"}:
        return "", "unsupported_locale"
    value = str(text or "").strip()
    if not value:
        return "", "empty"
    technical = (
        r"```|~~~|`|https?://|www\.|<<<KURO_|[{}\[\]]|[<>]",
        r"(?:[A-Za-z]:[\\/]|\\\\|(?:^|\s)(?:/|\./|\.\./))[\w./\\-]+",
        r"/(?:[A-Za-z_.-][\w.-]*/)+[\w.-]+|(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:py|js|ts|json|yaml|log|exe|md)(?![A-Za-z0-9_])",
        r"(?m)^\s*(?:Traceback|File \"|at \S+\s*\(|\w*(?:Error|Exception):|\d{4}-\d\d-\d\d[T ])",
        # Bare filenames alone are payload; names in natural prose (Node.js,
        # Next.js, etc.) are not paths. Actual paths/code remain rejected above.
        r"(?m)^.*\|.*\|.*$|^\s*[A-Za-z0-9_.-]+\.(?:py|js|ts|json|yaml|log|exe|md)\s*$",
        r"(?m)^\s*(?:def |class |import |from \S+ import |const |let |function |return |SELECT |INSERT |DELETE |UPDATE |(?:INFO|DEBUG|WARN|ERROR)\s*[:\[])|\w+\s*(?:==|:=|=>)\s*\S+",
        r"(?:^|\s)[A-Za-z_]\w*\s*=\s*(?:\d|[\"']|\w+\()",
    )
    if any(re.search(pattern, value) for pattern in technical):
        return "", "technical_payload"
    if re.search(r"[\x00-\x08\x0b-\x1f]", value):
        return "", "invalid_text"
    # Script validation is a guard, not an input-language classifier.
    if locale == "ja-JP" and not re.search(r"[ぁ-ゖァ-ヺ]", value) and not re.fullmatch(r"[\u3400-\u9fff々〇〆ヶ、。！？\s]+", value):
        return "", "locale_mismatch"
    if locale == "ja-JP" and re.search(r"(?:^|[\s、。])(?:はぁ|ふぅ|はあ|ふう)(?:$|[\s、。…])|[（(](?:笑|ため息|微笑|囁き)[）)]", value):
        return "", "non_speech_cue"
    if locale == "en-US" and re.search(r"[\u3040-\u30ff\u3400-\u9fff]", value):
        return "", "locale_mismatch"
    return value, "ready"


def _display_prose_lines(text: str, *, critical_tables_only: bool):
    """Skip fenced code and carry Markdown column names into each data row."""
    fence = None
    header = None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence, header = marker[1], None
            continue
        if line.count("|") >= 2:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            if header is None:
                header = cells
                continue
            row = "、".join(f"{header[i]} {c}" if i < len(header) else c for i, c in enumerate(cells))
            if not critical_tables_only or _critical_values(row) or _semantic_flags(row):
                yield row
        else:
            header = None
            yield line


def _semantic_prose(text: str) -> str:
    lines = []
    for line in _display_prose_lines(text, critical_tables_only=True):
        if re.search(r"\|.*\||^\s*(?:Traceback|File \"|at \S+\s*\(|[{}]|\"[^\"]+\"\s*:|(?:INFO|DEBUG|WARN|ERROR)\b|\d{4}-\d\d-\d\d[T ])", line):
            continue
        if line.lstrip().startswith("["):
            try:
                if isinstance(json.loads(line), list):
                    continue
            except ValueError:
                pass  # Markdown links/admonitions are ordinary prose.
        lines.append(line)
    value = "\n".join(lines)
    value = re.sub(r"(`+).*?\1", " ", value, flags=re.DOTALL)
    value = re.sub(r"https?://[^\s，。；;]+|www\.[^\s，。；;]+|[A-Za-z]:[\\/][^\s，。；;]+|(?<!\w)/(?:[\w.-]+/)+[\w.-]+", " ", value)
    return value


_SEMANTIC_FLAGS = {
    "failure": r"失敗|失败|エラー|\b(?:failed|failure|error)\b|未執行|未実行|not executed",
    "blocked": r"阻擋|受阻|拒絕|拒否|ブロック|\b(?:blocked|denied)\b",
    "unverified": r"未驗證|尚未驗證|未検証|未確認|(?:検証|確認)(?:していません|されてい(?:ない|ません)|できてい(?:ない|ません))|確認.{0,4}(?:未完了|していません)|\b(?:unverified|not verified|not tested)\b",
    "stale": r"(?:資料|數據|來源|データ).{0,8}(?:過期|陳舊|古い|古く)|\bstale\b|out.of.date",
    "partial": r"部分(?:成功|失敗|缺失)|(?:資料|結果|工具|データ).{0,8}(?:不全|不完整|一部のみ)|一部.{0,8}(?:失敗|欠落)|\bpartial(?:ly)?\s+(?:success|failure|data|results?)\b",
    "missing": r"(?:資料|數據|來源|結果|狀態|データ|結果|状態).{0,8}(?:缺失|缺少|不明|欠落|不足)|(?:missing|unknown|unavailable)\s+(?:data|source|results?|status)\b|(?:data|source|results?|status).{0,8}\b(?:missing|unknown|unavailable)\b|無法取得|取得でき(?:ません|ない)",
    "negative": r"(?:不能|不可|不會|不建議|不要|不得|無法).{0,10}(?:執行|操作|下單|交易|重試|修改|使用|判定|視為|當成)|できません|できない|禁止|\b(?:cannot|can't|mustn't|never|do not|don't)\s+(?:execute|run|trade|retry|modify|use|place|order|confirm)\b",
}


def _semantic_flags(text: str) -> set[str]:
    # Negated failure/verification words do not prove those actual states.
    value = re.sub(r"(?:沒有|並未|未曾)失敗|失敗(?:していません|ではありません|ではない)|(?:did not|didn't|not) fail(?:ed)?", "", text, flags=re.I)
    value = re.sub(r"(?:不是|並非|沒有)(?:權限)?(?:拒絕|阻擋)|(?:エラー|失敗|拒否)(?:は|が)?(?:ありません|ない)|\bno (?:error|failure)s?\b", "", value, flags=re.I)
    flags = {name for name, pattern in _SEMANTIC_FLAGS.items() if name != "negative" and re.search(pattern, value, re.I)}
    for name in flags:
        value = re.sub(_SEMANTIC_FLAGS[name], "", value, flags=re.I)
    if re.search(_SEMANTIC_FLAGS["negative"], value, re.I):
        flags.add("negative")
    return flags


def _status_conflict(source: str, spoken: str) -> bool:
    """Detect explicit reversals, never infer a contradiction from missing words.

    This is a bounded lexical guard, not a translation quality verdict. Unknown
    paraphrases remain audible with diagnostics and are covered by semantic QA.
    """
    opposite = {
        "failure": r"成功しました|処理は成功|操作は成功|失敗していません|\bsucceeded\b",
        "blocked": r"成功しました|処理は成功|許可されました|\bsucceeded\b",
        "unverified": r"(?<!未)確認しました|検証済み|確認済み|\bverified\b",
        "partial": r"(?:データ|資料|結果).{0,8}(?:完全|全部揃)|\bcomplete data\b",
        "missing": r"(?:データ|資料|結果).{0,8}(?:完全|全部揃)|\bcomplete data\b",
        "stale": r"(?:データ|資料).{0,8}(?:最新です|即時)|\bup.to.date\b",
        "negative": r"(?:注文|取引|実行|使用|再試行)(?:が)?できます|\bcan (?:trade|execute|retry)\b",
    }
    flags = _semantic_flags(source)
    spoken_flags = _semantic_flags(spoken)
    return any(flag not in spoken_flags and re.search(opposite[flag], spoken, re.I)
               for flag in flags)


def _semantic_numbers(text: str) -> set[str]:
    value = unicodedata.normalize("NFKC", text).replace("−", "-")
    numbers = set()
    for match in re.finditer(r"(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*%?|(?<=[\u3040-\u9fff])[-+]?\d+(?:\.\d+)?\s*%?", value):
        token = match[0].strip()
        percent = token.endswith("%")
        numbers.add(str(Decimal(token.rstrip("% ").replace(",", "")).normalize()) + ("%" if percent else ""))
    return numbers


def _critical_values(text: str) -> set[str]:
    values = set()
    for clause in re.split(r"[\n。！？!?；;]", text):
        if re.search(r"價格|價位|停損|止損|止盈|支撐|壓力|比率|百分|価格|損切|利確|\b(?:price|stop loss|target|ratio|percent)\b|%", clause, re.I):
            values.update(_semantic_numbers(clause))
    values.update(re.findall(r"(?<![A-Za-z0-9_])(?:HTTP\s*[45]\d\d|[A-Z]+_?(?:ERROR|FAILURE|DENIED)[A-Z_0-9]*|invalid_arguments|VAN\d+)(?![A-Za-z0-9_])", text))
    for role, pattern in (
        ("price", r"價格|價位|価格|\bprice"),
        ("stop", r"停損|止損|損切り?|\bstop loss"),
        ("target", r"止盈|利確|\btarget"),
    ):
        for match in re.finditer(r"(?:" + pattern + r")[^\d\n。；;]{0,12}([-+−]?\d+(?:,\d{3})*(?:\.\d+)?)", text, re.I):
            values.update(role + ":" + number for number in _semantic_numbers(match[1]))
    return values


def _asserted_success(text: str) -> bool:
    value = re.sub(r"(?:成功|success(?:ful)?)(?:した)?(?:ではありません|ではない|とは言えません|していません|しておらず|しなかった|しませんでした)|(?:不能|無法|not)\s*(?:判定)?\s*(?:成功|success(?:ful)?)", "", text, flags=re.I)
    return bool(re.search(r"成功|\b(?:success(?:ful)?|succeeded)\b", value, re.I))


_OPTION_ACTIONS = (
    (r"網路|網頁|web|ウェブ|ネット|公開.{0,4}(?:検索|查詢)", r"検索(?:が)?(?:する|します|できる|できます)|検索(?=か|と|を選べます|が可能です)|調べ(?:る|ます|られる|られます)|\bsearch\b|查詢|搜尋"),
    (r"清單|チェックリスト|診断|診斷|checklist|diagnos", r"(?:確認|チェック)(?:が)?(?:する|します|できる|できます)|確認(?=か|と|を選べます|が可能です)|調べ(?:る|ます)|\b(?:check|review)(?:ing)?\b|查看|檢查|檢視|先看"),
    (r"重試|再試|retry|再実行", r"再実行(?:する|します|できます)|再試行(?:する|します|できます)|\bretry\b|重試|再試"),
    (r"等待|稍後|待つ|待ち|wait", r"待つ|待ちます|\bwait\b|等待"),
    (r"重建|再構築|rebuild", r"再構築(?:する|します|できます)|\brebuild\b|重建"),
)


def _option_parts(text: str) -> list[str]:
    labelled = re.findall(r"(?:^|[\n；;。])\s*(?:[-*]\s*)?(?:[A-D][.:：、)]|(?:方案|選項)\s*[A-D一二三四][:：]?)\s*([^\n；;。]+)", text)
    if len(labelled) >= 2:
        return labelled
    if re.search(r"可以|可選|選擇|方案|選項|options?|choose|either|選択肢", text, re.I):
        for clause in re.split(r"[\n。！？!?；;]", text):
            parts = re.split(r"或者?|還是|または|あるいは|\bor\b", clause, flags=re.I)
            if len(parts) >= 2 and all(part.strip() for part in parts):
                return [part.strip() for part in parts]
    return []


def _option_supported(source: str, spoken: str) -> bool | None:
    """True: bounded support; False: known-action guard failed; None: unknown.

    Keep recognised omission/negation fail-closed. Absence of lexical evidence
    for an unrecognised translation is not evidence that the option is absent.
    """
    actions = [(topic, verb) for topic, verb in _OPTION_ACTIONS if re.search(topic, source, re.I)]
    if actions:
        # Keep a Japanese noun-option list with its shared affirmative ending.
        clauses = re.split(r"[。！？!?；;]|または|あるいは|\bor\b", spoken, flags=re.I)
        def positive_action(clause: str, verb: str) -> bool:
            for match in re.finditer(verb, clause, re.I):
                before, after = clause[:match.start()], clause[match.end():]
                if match[0] in {"検索", "確認"}:
                    shared = re.fullmatch(r"(?:か、?|と).{1,120}(?:ができます|を選べます|が可能です)[よね]?", after)
                    direct = re.fullmatch(r"(?:を選べます|が可能です)[よね]?", after)
                    if not (shared or direct) or "negative" in _semantic_flags(after):
                        continue
                if re.search(r"(?:cannot|can't|mustn't|do not|don't|not|不能|不可|不要|無法)\s*$", before, re.I):
                    continue
                if re.match(r"(?:(?:とは|と)?(?:言えません|言えない|限りません|限らない)|(?:わけ|の)では(?:ありません|ない)|(?:こと|の)(?:は|が)?でき(?:ません|ない))", after):
                    continue
                return True
            return False
        if all(any(re.search(topic, clause, re.I) and positive_action(clause, verb) for clause in clauses)
               for topic, verb in actions):
            return True
        if re.search(r"画面に(?:あります|表示しています)", spoken):
            return False
        if any(re.search(topic, clause, re.I) and ("negative" in _semantic_flags(clause)
               or re.search(r"(?:できるとは言えません|できるのではありません|調べられ(?:ません|ない))", clause))
               for topic, _ in actions for clause in clauses):
            return False
        return None
    # Same-language fallback only. Do not turn missing cross-language evidence
    # into either an affirmative equivalence claim or an omission claim.
    words = re.findall(r"[A-Za-z]{4,}|[\u3040-\u9fff]{4}", source)
    if any(word.lower() in spoken.lower() for word in words):
        if "negative" in _semantic_flags(spoken):
            return False
        if re.search(r"選ぶ|選択できます|実施します|\bcan\b|可以", spoken, re.I):
            return True
    return None

_SUBSTANTIVE_SOURCE_HINTS = (
    "結論",
    "答案",
    "重點",
    "核心",
    "建議",
    "看法",
    "提醒",
    "注意",
    "風險",
    "限制",
    "不確定",
    "資料",
    "趨勢",
    "比較",
    "差異",
    "主要",
    "適合",
    "取決",
    "可以",
    "不能",
    "沒有絕對",
)
_FOLLOWUP_QUESTION_RE = re.compile(
    r"^(?:要我|你想|是否|要不要|需不需要|請告訴我|如果要)"
)
_HEADING_ONLY_LABEL_RE = re.compile(
    r"^(?:簡短)?(?:重點|要點|結論|原因|建議|提醒|風險|補充|說明|比較|整理|如下|"
    r"核心結論(?:（[^）]{1,12}）)?)$"
)


def _clip_text(text: str, max_len: int | None) -> str:
    value = str(text or "")
    if max_len is None or len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "..."


@dataclass(frozen=True)
class SpeechPolicyConfig:
    """Runtime knobs for speech routing.

    The hard safety decisions stay in code. A future YAML layer should only
    populate this config and pronunciation/profile dictionaries.
    """

    response_type: str = "chat"
    allow_tts: bool = True
    max_spoken_segments: int = 3


@dataclass(frozen=True)
class SpeechPlanItem:
    kind: str
    text: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": str(self.kind or ""),
            "text": str(self.text or "").strip(),
            "reason": str(self.reason or ""),
        }


def speech_plan_item(kind: str, text: str = "", reason: str = "") -> dict[str, str]:
    return SpeechPlanItem(kind=kind, text=text, reason=reason).to_dict()


def _is_question(text: str) -> bool:
    value = str(text or "").strip()
    return value.endswith(("?", "？"))


def _is_list_intro(text: str) -> bool:
    value = str(text or "").strip()
    return value.endswith((":", "："))


def _is_heading_only(text: str) -> bool:
    value = str(text or "").strip()
    if not value.endswith((":", "：")):
        return False
    label = value.rstrip(":：").strip(" -•*+")
    if not label:
        return True
    if len(label) > 16:
        return False
    return bool(_HEADING_ONLY_LABEL_RE.match(label))


def _is_followup_question(text: str) -> bool:
    value = str(text or "").strip()
    return _is_question(value) and bool(_FOLLOWUP_QUESTION_RE.search(value))


def _source_content_score(text: str) -> int:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return -100
    if _is_heading_only(value):
        return -80

    score = 0
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", value))
    score += min(cjk_count, 40)

    if _is_question(value):
        score -= 18
        if _is_followup_question(value):
            score -= 8
    if _is_list_intro(value):
        score -= 8
    if cjk_count < 6:
        score -= 18
    if any(hint in value for hint in _SUBSTANTIVE_SOURCE_HINTS):
        score += 18
    if re.search(r"(?:但|不過|然而|所以|因此|因為|取決|建議|注意|風險)", value):
        score += 10
    return score


def _looks_like_inline_detail_items(text: str) -> bool:
    value = str(text or "")
    if "：" in value:
        _, detail = value.split("：", 1)
    elif ":" in value:
        _, detail = value.split(":", 1)
    else:
        return False
    separators = sum(detail.count(mark) for mark in ("、", "，", ",", "/", "／"))
    detail_keywords = (
        "營收",
        "毛利",
        "EPS",
        "資本支出",
        "股價",
        "市值",
        "財報",
        "製程",
        "產能",
        "技術節點",
        "指標",
    )
    return separators >= 3 and any(keyword in detail for keyword in detail_keywords)


def _trim_inline_detail_items(text: str) -> str:
    value = str(text or "").strip()
    if "：" in value:
        head, _detail = value.split("：", 1)
    elif ":" in value:
        head, _detail = value.split(":", 1)
    else:
        return value
    head = head.strip()
    if not head:
        return ""
    if "並列出每年" in head:
        head = head.split("並列出每年", 1)[0].rstrip("，,、；; ")
    return f"{head}。" if not head.endswith(("。", "？", "！", "?", "!")) else head


def _extract_inline_detail_followup(text: str) -> str:
    value = str(text or "")
    if "：" in value:
        _head, detail = value.split("：", 1)
    elif ":" in value:
        _head, detail = value.split(":", 1)
    else:
        return ""

    matches = list(
        re.finditer(
            r"(?:^|[；;。])\s*((?:或|還是|要|是否|需不需要|要不要|你要)[^？?]{1,80}[？?])",
            detail,
        )
    )
    if not matches:
        return ""
    return str(matches[-1].group(1) or "").strip()


def normalize_speech_plan_for_presentation(
    plan: list[dict[str, str]],
    *,
    max_spoken_segments: int = 3,
) -> list[dict[str, str]]:
    """Prune display-oriented detail into a compact, speakable presentation plan.

    This is not summarization of the visible answer. It only decides which blocks
    should reach the voice lane: normal conversational lines stay speakable,
    while option lists and dense detail lists stay on screen.
    """
    if not plan:
        return []

    items = [dict(item) for item in plan if dict(item).get("kind") != SPEECH_PLAN_SKIP]
    choice_count = sum(1 for item in items if item.get("reason") == "choice_item")
    has_choices = choice_count >= 2
    result: list[dict[str, str]] = []
    inserted_options_line = False
    inserted_detail_line = False

    for item in items:
        kind = item.get("kind", "")
        text = str(item.get("text") or "").strip()
        reason = item.get("reason", "")
        if not text:
            continue

        if has_choices and reason == "choice_item":
            if _is_question(text):
                result.append(speech_plan_item(SPEECH_PLAN_SOURCE, text, "source"))
                continue
            if not inserted_options_line:
                result.append(
                    speech_plan_item(
                        SPEECH_PLAN_FIXED_JA,
                        SPEECH_POLICY_OPTIONS_JA,
                        "choice_options_displayed",
                    )
                )
                inserted_options_line = True
            continue

        if kind == SPEECH_PLAN_SOURCE and _looks_like_inline_detail_items(text):
            trimmed = _trim_inline_detail_items(text)
            followup = _extract_inline_detail_followup(text)
            if trimmed:
                result.append(speech_plan_item(SPEECH_PLAN_SOURCE, trimmed, reason))
            if not inserted_detail_line:
                result.append(
                    speech_plan_item(
                        SPEECH_PLAN_FIXED_JA,
                        SPEECH_POLICY_DETAIL_ITEMS_JA,
                        "detail_items_displayed",
                    )
                )
                inserted_detail_line = True
            if followup:
                result.append(speech_plan_item(SPEECH_PLAN_SOURCE, followup, reason))
            continue

        result.append(speech_plan_item(kind, text, reason))

    has_non_heading_source = any(
        item.get("kind") == SPEECH_PLAN_SOURCE
        and not _is_heading_only(item.get("text", ""))
        for item in result
    )
    if has_non_heading_source:
        result = [
            item
            for item in result
            if not (
                item.get("kind") == SPEECH_PLAN_SOURCE
                and _is_heading_only(item.get("text", ""))
            )
        ]

    if len(result) <= max_spoken_segments:
        return result

    # Keep natural dialogue shape for long answers: substantive content first,
    # one display notice if details were skipped, then the final follow-up.
    indexed = list(enumerate(result))
    chosen: list[int] = []

    def add(index: int | None) -> None:
        if index is None:
            return
        if index in chosen:
            return
        if len(chosen) >= max_spoken_segments:
            return
        chosen.append(index)

    def source_indices(*, include_questions: bool = False) -> list[int]:
        candidates: list[int] = []
        for idx, item in indexed:
            if item.get("kind") != SPEECH_PLAN_SOURCE:
                continue
            text = item.get("text", "")
            if _is_heading_only(text):
                continue
            if not include_questions and _is_question(text):
                continue
            candidates.append(idx)
        return candidates

    has_choice_notice = any(
        item.get("kind") == SPEECH_PLAN_FIXED_JA
        and item.get("reason") == "choice_options_displayed"
        for item in result
    )
    primary_pool = [
        idx
        for idx in source_indices()
        if not _is_list_intro(result[idx].get("text", ""))
    ] or source_indices()
    if has_choice_notice:
        add(
            next(
                (
                    idx
                    for idx, item in indexed
                    if item.get("kind") == SPEECH_PLAN_SOURCE
                    and _is_question(item.get("text", ""))
                ),
                None,
            )
        )
    elif primary_pool:
        add(
            max(
                primary_pool,
                key=lambda idx: (
                    _source_content_score(result[idx].get("text", "")),
                    -idx,
                ),
            )
        )

    fixed_idx = next(
        (idx for idx, item in indexed if item.get("kind") == SPEECH_PLAN_FIXED_JA),
        None,
    )
    add(fixed_idx)

    final_question_idx = next(
        (
            idx
            for idx, item in reversed(indexed)
            if item.get("kind") == SPEECH_PLAN_SOURCE
            and _is_question(item.get("text", ""))
            and not _is_heading_only(item.get("text", ""))
        ),
        None,
    )
    add(final_question_idx)

    if len(chosen) < max_spoken_segments:
        remaining_sources = sorted(
            [idx for idx in source_indices() if idx not in chosen],
            key=lambda idx: (
                _source_content_score(result[idx].get("text", "")),
                -idx,
            ),
            reverse=True,
        )
        for idx in remaining_sources:
            add(idx)
            if len(chosen) >= max_spoken_segments:
                break

    if not chosen:
        add(indexed[0][0] if indexed else None)

    return [result[idx] for idx in sorted(chosen)][:max_spoken_segments]


@dataclass
class SpeechSegment:
    source_text: str = ""
    rendered_text: str = ""
    spoken_text: str = ""
    guard_reason: str = "not_rendered"
    provider: str = ""
    pronunciation_hits: list[str] = field(default_factory=list)
    speech_repaired: bool = False
    route: str = SPEECH_ROUTE_SILENT_DISPLAY

    def to_dict(self, *, max_text_len: int | None = None) -> dict[str, Any]:
        return {
            "route": self.route,
            "source_text": _clip_text(self.source_text, max_text_len),
            "rendered_text": _clip_text(self.rendered_text, max_text_len),
            "spoken_text": _clip_text(self.spoken_text, max_text_len),
            "guard_reason": self.guard_reason,
            "provider": self.provider,
            "pronunciation_hits": list(self.pronunciation_hits),
            "speech_repaired": self.speech_repaired,
        }


@dataclass
class PresentationEnvelope:
    """Separated presentation lanes for one assistant response.

    raw_content: original model/tool text before display cleanup.
    display_text: text shown in the chat/subtitle UI.
    speech_source: sanitized source sent to the spoken renderer.
    spoken_text: final text allowed to reach the TTS engine.

    expression_hint is intentionally only a route placeholder for now; the
    existing emotion behavior remains unchanged until an expression mapper is
    introduced.
    """

    raw_content: str = ""
    display_text: str = ""
    response_type: str = "chat"
    speech_route: str = SPEECH_ROUTE_SILENT_DISPLAY
    speech_source: str = ""
    spoken_text: str = ""
    speech_guard_reason: str = "not_rendered"
    speech_segments: list[SpeechSegment] = field(default_factory=list)
    expression_hint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def append_display(self, *, raw_text: str, display_text: str) -> None:
        self.raw_content += str(raw_text or "")
        self.display_text += str(display_text or "")

    def set_speech_source(
        self,
        source_text: str,
        *,
        route: str,
        guard_reason: str,
    ) -> None:
        self.speech_source = str(source_text or "").strip()
        self.speech_route = route
        self.speech_guard_reason = guard_reason

    def attach_speech_result(
        self,
        *,
        rendered_text: str,
        spoken_text: str,
        guard_reason: str,
        provider: str = "",
        pronunciation_hits: list[str] | None = None,
        speech_repaired: bool = False,
    ) -> SpeechSegment:
        self.spoken_text = str(spoken_text or "").strip()
        self.speech_guard_reason = guard_reason or "unknown"
        if self.speech_source:
            self.speech_route = SPEECH_ROUTE_RENDER_THEN_TTS
        else:
            self.speech_route = SPEECH_ROUTE_SILENT_DISPLAY

        segment = SpeechSegment(
            source_text=self.speech_source,
            rendered_text=str(rendered_text or "").strip(),
            spoken_text=self.spoken_text,
            guard_reason=self.speech_guard_reason,
            provider=str(provider or ""),
            pronunciation_hits=list(pronunciation_hits or []),
            speech_repaired=bool(speech_repaired),
            route=self.speech_route,
        )
        self.speech_segments = [segment]
        return segment

    def to_log_dict(self, *, max_text_len: int | None = None) -> dict[str, Any]:
        return {
            "response_type": self.response_type,
            "speech_route": self.speech_route,
            "speech_guard_reason": self.speech_guard_reason,
            "raw_content": _clip_text(self.raw_content, max_text_len),
            "display_text": _clip_text(self.display_text, max_text_len),
            "speech_source": _clip_text(self.speech_source, max_text_len),
            "spoken_text": _clip_text(self.spoken_text, max_text_len),
            "expression_hint": self.expression_hint,
            "metadata": dict(self.metadata),
            "speech_segments": [
                segment.to_dict(max_text_len=max_text_len)
                for segment in self.speech_segments
            ],
        }


class SpeechPolicyEngine:
    """Small routing facade between display text, speech renderer, and TTS."""

    def __init__(self, config: SpeechPolicyConfig | None = None) -> None:
        self.config = config or SpeechPolicyConfig()

    def validate_lane(self, text: str, locale: str) -> tuple[str, str]:
        if not self.config.allow_tts:
            return "", "tts_disabled"
        return filter_speech_lane(text, locale)

    def validate_semantic_lane(self, lane: Any, display: str, settings: dict, *, diagnostics: dict | None = None) -> tuple[str, str]:
        """Validate the whole v2 lane before any speech is queued.

        Only recognised lexical states, numeric forms and option actions can be
        checked deterministically. Unknown option translations remain audible
        with semantic_unverified diagnostics, after all hard checks pass.
        A ready result still needs human semantic QA.
        """
        # Only bounded counts/locations leave the parser on rejection, never
        # rejected text or anchors. Received != successfully validated counts.
        diag = diagnostics if diagnostics is not None else {}
        diag.update(received_anchors=(len(lane["anchors"]) if isinstance(lane, dict) and isinstance(lane.get("anchors"), list) else None),
                    received_semantic_segments=(len(lane["speech"]) if isinstance(lane, dict) and isinstance(lane.get("speech"), list) else None),
                    validated_anchors=0, validated_semantic_segments=0, stage="schema")
        if (not isinstance(lane, dict)
                or set(lane) != {"contract", "locale", "policy", "anchors", "speech", "emotion"}
                or lane["contract"] != SPEECH_LANE_V2_CONTRACT
                or lane["locale"] != settings.get("locale")
                or lane["policy"] != settings.get("policy")
                or not isinstance(lane["emotion"], str) or lane["emotion"] not in _EMOTIONS
                or not isinstance(lane["anchors"], list)
                or not isinstance(lane["speech"], list)):
            return "", "invalid_schema"
        if not display.strip():
            return "", "empty_display"
        anchors = {}
        diag["stage"] = "anchor"
        for index, anchor in enumerate(lane["anchors"]):
            diag["anchor_index"] = index
            if (not isinstance(anchor, dict) or set(anchor) != {"id", "source", "importance", "kind"}
                    or not isinstance(anchor["id"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", anchor["id"])
                    or not isinstance(anchor["source"], str) or not anchor["source"].strip()
                    or not isinstance(anchor["importance"], str) or anchor["importance"] not in {"required", "display_only"}
                    or not isinstance(anchor["kind"], str) or anchor["kind"] not in {"fact", "status", "option", "options", "code", "url", "path", "json", "log", "table", "detail"}):
                return "", "invalid_anchor"
            if anchor["id"] in anchors:
                return "", "duplicate_anchor"
            if anchor["source"] not in display:
                return "", "anchor_source_missing"
            anchors[anchor["id"]] = anchor
            diag["validated_anchors"] += 1
        diag.pop("anchor_index", None)
        texts, linked = [], {key: [] for key in anchors}
        diag["stage"] = "segment"
        for index, segment in enumerate(lane["speech"]):
            diag["segment_index"] = index
            if (not isinstance(segment, dict) or set(segment) != {"source_ids", "text"}
                    or not isinstance(segment["source_ids"], list)
                    or not all(isinstance(key, str) for key in segment["source_ids"])
                    or len(set(segment["source_ids"])) != len(segment["source_ids"])
                    or not isinstance(segment["text"], str)):
                return "", "invalid_segment"
            if any(key not in anchors for key in segment["source_ids"]):
                return "", "unknown_source_id"
            text, reason = self.validate_lane(segment["text"], settings["locale"])
            if not text:
                return "", reason
            texts.append(text)
            for key in segment["source_ids"]:
                linked[key].append(text)
            diag["validated_semantic_segments"] += 1
        diag.pop("segment_index", None)
        spoken = " ".join(texts)
        required = [anchor for anchor in anchors.values() if anchor["importance"] == "required"]
        diag["stage"] = "required_anchor"
        for index, anchor in enumerate(lane["anchors"]):
            if anchor["importance"] != "required":
                continue
            diag["anchor_index"] = index
            text = " ".join(linked[anchor["id"]])
            if not text:
                return "", "required_anchor_missing"
            source = _semantic_prose(anchor["source"])
            if _status_conflict(source, text):
                return "", "anchor_status_mismatch"
            if _semantic_flags(source) - _semantic_flags(text):
                diag.setdefault("soft_failures", []).append(dict(
                    rule_id="anchor_status_unverified", stage="required_anchor", anchor_index=index))
            if (_semantic_flags(source) & {"failure", "blocked"} and not _asserted_success(source)
                    and _asserted_success(text) and not _asserted_success(_semantic_prose(display))):
                return "", "anchor_status_conflict"
            if _critical_values(source) - (_critical_values(text) | _semantic_numbers(text)):
                return "", "anchor_value_mismatch"
            if anchor["kind"] in {"option", "options"}:
                for part in (_option_parts(source) or [source]):
                    supported = _option_supported(part, text)
                    if supported is False:
                        return "", "option_unverified"
                    if supported is None:
                        diag.setdefault("soft_failures", []).append(dict(
                            rule_id="option_unverified", stage="required_anchor", anchor_index=index))
        diag.pop("anchor_index", None)
        diag["stage"] = "display"
        # Independent Display scan prevents the model omitting/downgrading all
        # critical anchors, or referencing a true but irrelevant source fragment.
        prose = _semantic_prose(display)
        sources = "\n".join(_semantic_prose(anchor["source"]) for anchor in required)
        if _status_conflict(prose, spoken):
            return "", "anchor_status_mismatch"
        if (_semantic_flags(prose) & {"failure", "blocked"} and _asserted_success(spoken)
                and not _asserted_success(prose)):
            return "", "anchor_status_conflict"
        if _semantic_flags(prose) - _semantic_flags(sources):
            diag.setdefault("soft_failures", []).append(dict(rule_id="unanchored_status", stage="display"))
        if _critical_values(spoken) - (_critical_values(prose) | _semantic_numbers(prose)):
            return "", "unbacked_value"
        # Check every segment, including display-only anchors. A summary may
        # omit an incidental number but cannot introduce one absent from Display.
        if _semantic_numbers(spoken) - _semantic_numbers(prose):
            return "", "unbacked_value"
        if _critical_values(spoken) - (_critical_values(sources) | _semantic_numbers(sources)):
            return "", "unanchored_value"
        for part in _option_parts(prose):
            candidates = [anchor for anchor in required if part in anchor["source"] or anchor["source"] in part]
            if not candidates:
                # A short summary may select one next step from a detailed
                # Display. Only explicitly required references must be complete.
                diag.setdefault("soft_failures", []).append(dict(rule_id="unanchored_option", stage="display"))
                continue
            supported = _option_supported(part, " ".join(text for anchor in candidates for text in linked[anchor["id"]]))
            if supported is False:
                return "", "option_unverified"
            if supported is None:
                diag.setdefault("soft_failures", []).append(dict(rule_id="option_unverified", stage="display"))
        if not spoken:
            return "", "silent"
        diag["stage"] = "final"
        spoken, reason = self.validate_lane(spoken, settings["locale"])
        if spoken and reason == "ready" and diag.get("soft_failures"):
            reason = "semantic_unverified"
        return spoken, reason

    def create_envelope(
        self, *, response_type: str | None = None
    ) -> PresentationEnvelope:
        return PresentationEnvelope(
            response_type=response_type or self.config.response_type
        )

    def set_source(self, envelope: PresentationEnvelope, source_text: str) -> None:
        source = str(source_text or "").strip()
        if not self.config.allow_tts:
            envelope.set_speech_source(
                "",
                route=SPEECH_ROUTE_SILENT_DISPLAY,
                guard_reason="tts_disabled",
            )
            return
        if not source:
            envelope.set_speech_source(
                "",
                route=SPEECH_ROUTE_SILENT_DISPLAY,
                guard_reason="empty_source",
            )
            return
        envelope.set_speech_source(
            source,
            route=SPEECH_ROUTE_RENDER_THEN_TTS,
            guard_reason="ready",
        )
