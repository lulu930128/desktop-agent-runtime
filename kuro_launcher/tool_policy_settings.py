"""Bounded editor for the existing Conversation policy; never execute tools.

Only the optional enabled bit is editable. Existing policy owns every mode
and argument restriction; this adapter cannot grant a new privilege.
"""
import json
import os
from pathlib import Path
import tempfile

from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy, _valid_tool_config


CONTRACT = 'kuro.tool-policy-settings.v1'
GROUPS = {'kuro-web': '網路搜尋', 'kuro-filesystem': '檔案與對話查找',
          'kuro-mail': '郵件', 'omi-market': '市場情報'}
# Presentation metadata only; all execution authority remains in ToolPolicy.
CATALOG = {
    'kuro-web::get_current_time': ('目前時間', '讀取目前時間與時區。'),
    'kuro-web::search_web': ('網路搜尋', '搜尋公開網頁資訊。'),
    'kuro-web::smart_search_web': ('智慧搜尋', '依問題選擇公開搜尋方式。'),
    'kuro-web::advanced_search_web': ('進階搜尋', '使用條件縮小公開搜尋結果。'),
    'kuro-web::fetch_content': ('讀取網頁', '讀取公開網頁；保留內網網址限制。'),
    'kuro-filesystem::list_allowed_roots': ('可讀取的資料夾', '查看服務允許存取的根目錄。'),
    'kuro-filesystem::list_directory': ('列出資料夾', '列出允許路徑；不包含隱藏或受保護檔案。'),
    'kuro-filesystem::search_files': ('搜尋檔案', '在允許範圍尋找檔案，保留私人路徑限制。'),
    'kuro-filesystem::read_text_file': ('讀取文字檔', '讀取允許的文字檔，不寫入檔案。'),
    'kuro-filesystem::search_past_conversations': ('查找過往對話', '由既有服務依其範圍查找對話；不擴大存取權。'),
    'kuro-mail::mail.auth_status': ('郵件授權狀態', '查看既有郵件授權狀態。'),
    'kuro-mail::mail.auth_start': ('開始郵件授權', '需逐次確認；執行佇列尚未提供，保持封鎖。'),
    'kuro-mail::mail.auth_finish': ('完成郵件授權', '需逐次確認；執行佇列尚未提供，保持封鎖。'),
    'kuro-mail::mail.list_unread': ('未讀郵件', '唯讀列出未讀郵件，不包含垃圾桶或垃圾郵件。'),
    'kuro-mail::mail.search_recent': ('搜尋近期郵件', '唯讀搜尋近期郵件，保留查詢限制。'),
    'kuro-mail::mail.get_message_summary': ('郵件摘要', '由原郵件服務讀取指定郵件摘要。'),
    'kuro-mail::mail.get_message_detail': ('郵件內容', '由原郵件服務唯讀取得內容；不寄出或修改郵件。'),
    'kuro-mail::mail.daily_brief': ('每日郵件概覽', '由原服務整理郵件；可能讀取信箱，不是 Core 快照。'),
    'kuro-mail::mail.refresh': ('更新郵件觀測', '原服務唯讀查詢信箱並更新本機 handoff；不寄信。'),
    'omi-market::omi.ask': ('市場問題分析', '由 OMI 分析；保留預算、禁止寫入及報告模式限制，可能使用外部資料或 LLM。'),
    'omi-market::omi.ask_stream': ('串流市場分析', '由 OMI 串流回覆；同樣受預算與禁止寫入限制，不是背景自動觀測。'),
}


def validate_change(payload):
    if not isinstance(payload, dict) or set(payload) != {'name', 'enabled', 'expectedDigest'}:
        raise ValueError('tool_policy_fields')
    name, enabled, digest = (payload[k] for k in ('name', 'enabled', 'expectedDigest'))
    if not isinstance(name, str) or name not in CATALOG:
        raise ValueError('tool_policy_unknown_tool')
    if type(enabled) is not bool:
        raise ValueError('tool_policy_enabled_boolean_required')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('tool_policy_revision_required')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('tool_policy_duplicate_key')
        result[key] = value
    return result


class ToolPolicySettings:
    def __init__(self, path):
        self.path = Path(path).absolute()

    def _load(self):
        if self.path.resolve(strict=True) != self.path or self.path.is_symlink():
            raise ValueError('tool_policy_redirected_path')
        with self.path.open('rb') as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('tool_policy_too_large')
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object)
        if not isinstance(data, dict) or not isinstance(data.get('tools'), dict) or set(data['tools']) != set(CATALOG):
            raise ValueError('tool_policy_registry_mismatch')
        if data.get('default_mode') != 'blocked' or any(not isinstance(row, dict) or not _valid_tool_config(row) for row in data['tools'].values()):
            raise ValueError('tool_policy_invalid')
        policy = ToolPolicy(data)
        if not policy.valid:
            raise ValueError('tool_policy_invalid')
        return raw, data, policy

    def read(self):
        _, data, policy = self._load()
        records = []
        for name, (label, description) in CATALOG.items():
            decision = policy.check(name, {})
            service = name.split('::', 1)[0]
            records.append({'name': name, 'label': label, 'description': description,
                'service': service, 'serviceLabel': GROUPS[service],
                'enabled': data['tools'][name].get('enabled', True),
                'category': data['tools'][name]['category'], 'mode': data['tools'][name]['mode'],
                'allowed': decision.allowed, 'reason': decision.reason, 'reason_code': decision.reason_code})
        return {'contract': CONTRACT, 'default_mode': policy.default_mode, 'tools': records,
                'confirmation_available': False, 'settings_confirmation_required': True,
                'runtime_adoption': 'UNVERIFIED', 'restart_required': True, 'digest': policy.digest}

    def update(self, payload, *, confirmed=False):
        validate_change(payload)
        if confirmed is not True:
            raise PermissionError('tool_policy_confirmation_required')
        self._load()  # Refuse invalid/redirected input before creating the writer lock.
        # One writer across Launcher instances. No retry or stale-lock removal.
        lock = self.path.with_name(self.path.name + '.settings.lock')
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        temporary = None
        try:
            os.close(fd)
            raw, data, policy = self._load()
            if policy.digest != payload['expectedDigest']:
                raise ValueError('tool_policy_stale_digest')
            data['tools'][payload['name']]['enabled'] = payload['enabled']
            encoded = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.tool-policy-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if self._load()[0] != raw:
                raise ValueError('tool_policy_stale_digest')
            os.replace(temporary, self.path)
            temporary = None
            readback = self.read()
            if readback['digest'] != ToolPolicy(data).digest:
                raise RuntimeError('tool_policy_readback_unverified')
            return {**readback, 'persisted': True}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            lock.unlink()
