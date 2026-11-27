"""Bounded editor for the existing Conversation policy; never execute tools.

Only the optional enabled bit is editable. Existing policy owns every mode
and argument restriction; this adapter cannot grant a new privilege.
"""
import json
import os
from pathlib import Path
import tempfile
import re

from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy, _valid_tool_config


CONTRACT = 'kuro.tool-policy-settings.v1'
GROUPS = {'kuro-web': '網路搜尋', 'kuro-filesystem': '過往對話', 'project-workspace': '專案工作區',
          'kuro-mail': '郵件', 'omi-search': 'OMI 市場資料', 'japanese-study': '日文學習',
          'english-study': '英文學習', 'listening-audio': '聽力練習',
          'memory-core': 'Memory Core 正式記憶', 'personal-asset-os': '個人資產 PAOS'}
# Presentation metadata only; all execution authority remains in ToolPolicy.
CATALOG = {
    'kuro-web::get_current_time': ('目前時間', '讀取目前時間與時區。'),
    'kuro-web::search_web': ('網路搜尋', '搜尋公開網頁資訊。'),
    'kuro-web::smart_search_web': ('智慧搜尋', '依問題選擇公開搜尋方式。'),
    'kuro-web::advanced_search_web': ('進階搜尋', '使用條件縮小公開搜尋結果。'),
    'kuro-web::fetch_content': ('讀取網頁', '讀取公開網頁；保留內網網址限制。'),
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
    'memory-core::search': ('搜尋正式記憶', '依使用者需求搜尋 Memory Core；與 Kuro 過往對話及角色記憶分開。'),
    'memory-core::fetch': ('讀取正式記憶', '依穩定識別碼讀取外部正式記憶，不保存或修改記憶。'),
    'memory-core::memory_fetch_record_revision': ('正式記憶版本', '唯讀指定紀錄的歷史版本。'),
    'memory-core::memory_list_record_links': ('正式記憶關聯', '唯讀指定紀錄的關聯，不建立或移除關聯。'),
    'memory-core::memory_overview': ('正式記憶概覽', '按需讀取 Memory Core 概覽；不是 Kuro History 或 Core Today。'),
    'memory-core::memory_detect_duplicates': ('記憶重複查詢', '唯讀可能重複的紀錄；不合併、刪除或封存。'),
    'memory-core::memory_list_collections': ('正式記憶集合', '唯讀列出可見集合，不建立或修改集合。'),
    'memory-core::memory_get_collection': ('正式記憶集合內容', '有界讀取指定集合的成員，不自動寫入長期記憶。'),
    'personal-asset-os::get_asset_overview': ('個人資產總覽', '按需讀取 PAOS 資產總覽；來源可能讀 Broker／FX，保留時間與品質警告。'),
    'personal-asset-os::list_asset_accounts': ('資產帳戶清單', '唯讀帳戶與餘額，不調整帳務。'),
    'personal-asset-os::list_asset_positions': ('投資部位', '按需讀取部位；來源可能讀 Broker／FX，不下單或刷新交易。'),
    'personal-asset-os::list_recent_asset_transactions': ('近期資產交易', '唯讀近期交易摘要，不新增、沖銷或修改交易。'),
    'personal-asset-os::get_pending_financial_events': ('待處理財務事件', '唯讀待處理記錄，不核准或寫入帳本。'),
    'personal-asset-os::get_reconciliation_status': ('資產對帳狀態', '唯讀既有對帳證據，不執行對帳。'),
    'personal-asset-os::get_asset_system_status': ('資產系統狀態', '按需讀取來源狀態，不啟停、備份或還原服務。'),
}


def validate_change(payload):
    if not isinstance(payload, dict) or set(payload) != {'name', 'enabled', 'expectedDigest'}:
        raise ValueError('tool_policy_fields')
    name, enabled, digest = (payload[k] for k in ('name', 'enabled', 'expectedDigest'))
    if not isinstance(name, str) or name.partition("::")[0] not in GROUPS or not re.fullmatch(r"[a-zA-Z0-9_.%-]+::[a-zA-Z0-9_.%-]+", name):
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
        if not isinstance(data, dict) or not isinstance(data.get('tools'), dict):
            raise ValueError('tool_policy_registry_mismatch')
        if data.get('default_mode') != 'blocked' or any(not isinstance(row, dict) or not _valid_tool_config(row) for row in data['tools'].values()):
            raise ValueError('tool_policy_invalid')
        policy = ToolPolicy(data)
        if not policy.valid:
            raise ValueError('tool_policy_invalid')
        return raw, data, policy

    def read(self, inventory=None):
        _, data, policy = self._load()
        inventory = inventory or {}
        live = {r['name']: r for r in inventory.get('tools', [])}
        services = inventory.get('services', {})
        records = []
        for name in sorted(set(data['tools']) | set(live)):
            service, _, wire = name.partition('::')
            source = live.get(name, {})
            config = data['tools'].get(name, {})
            label, description = CATALOG.get(name, (wire, ''))
            decision = policy.check(name, {})
            records.append({
                'name': name, 'label': source.get('label', label), 'description': source.get('description', description),
                'service': service, 'serviceLabel': GROUPS.get(service, service),
                'enabled': config.get('enabled', True), 'category': config.get('category', service),
                'mode': config.get('mode', 'owner'), 'operation': source.get('operation', 'unknown'),
                'allowed': source.get('allowed', False), 'reason': decision.reason,
                'reason_code': source.get('reason_code', services.get(service, {}).get('reason') or 'not_discovered'),
            })
        return {'contract': CONTRACT, 'default_mode': policy.default_mode, 'tools': records,
                'services': services, 'inventory_error': inventory.get('error', ''),
                'catalog': {'toolNames': [r['name'] for r in records], 'groups': dict(GROUPS)},
                'confirmation_available': False, 'settings_confirmation_required': True,
                'runtime_adoption': ('MATCHED' if inventory.get('policy_digest') == policy.digest else 'UNVERIFIED'),
                'restart_required': inventory.get('policy_digest') != policy.digest, 'digest': policy.digest}

    def update(self, payload, *, confirmed=False, inventory=None):
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
            name = payload['name']
            if name not in data['tools']:
                observed = {r['name'] for r in (inventory or {}).get('tools', [])}
                if name not in observed or name.partition('::')[0] not in policy.owner_services:
                    raise ValueError('tool_policy_unknown_tool')
                data['tools'][name] = {'mode': 'owner'}
            data['tools'][name]['enabled'] = payload['enabled']
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
            readback = self.read(inventory)
            if readback['digest'] != ToolPolicy(data).digest:
                raise RuntimeError('tool_policy_readback_unverified')
            return {**readback, 'persisted': True}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            lock.unlink()
