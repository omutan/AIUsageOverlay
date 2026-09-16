# -*- coding: utf-8 -*-
"""各AIの使用量を「ローカルのファイル」から読むプロバイダ群.
どれも API/トークン不要。アプリ自身が書き出すファイルを読むだけ。

返り値: dict(ok, five, week, plan, reset_five, reset_week, note)
  five/week = 使用率%(0-100)。取れない枠は None。
"""
import os, glob, json, re, time, subprocess
from datetime import datetime

APPDATA = os.environ.get('APPDATA', '')
HOME = os.path.expanduser('~')
CLAUDE_USAGE_URL = 'https://claude.ai/settings/usage'
CLAUDE_APP_ID = r'shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude'
CLAUDE_STALE_SECONDS = 180
_LAST_GOOD = {}
_UIA_AUTOMATION = None


def _empty(note='未取得', url=None):
    result = {'ok': False, 'five': None, 'week': None, 'plan': None,
              'reset_five': None, 'reset_week': None, 'note': note, 't': 0}
    if url:
        result['url'] = url
    return result


# ---------- Claude (クロ) ----------
def _claude_window_handle():
    try:
        import win32gui
        found = []

        def collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).strip() == 'Claude':
                found.append(hwnd)

        win32gui.EnumWindows(collect, None)
        return found[0] if found else None
    except Exception:
        return None


def _parse_claude_usage_names(names):
    five = None
    week = None
    for name in names:
        text = ' '.join(str(name).split())
        match = re.search(r'使用量[：:]\s*5時間制限の\s*(\d+)%', text)
        if match:
            five = int(match.group(1))
        match = re.search(r'5時間制限.*?(\d+)%.*?週間.*?(\d+)%', text)
        if match:
            five, week = int(match.group(1)), int(match.group(2))
            break
    if five is None:
        # 使用量ポップアップでは、ラベルと百分率が別要素になっている。
        for i, name in enumerate(names):
            text = ' '.join(str(name).split())
            if text == '5時間制限':
                for candidate in names[i + 1:i + 7]:
                    match = re.fullmatch(r'(\d+)%', str(candidate).strip())
                    if match:
                        five = int(match.group(1)); break
    if week is None:
        for i, name in enumerate(names):
            if '週間' in str(name):
                for candidate in names[i + 1:i + 7]:
                    match = re.fullmatch(r'(\d+)%', str(candidate).strip())
                    if match:
                        week = int(match.group(1)); break
    return five, week


def _claude_uia_usage():
    """Claude画面に表示されている公式使用率を、読み取り専用で取得する。"""
    global _UIA_AUTOMATION
    hwnd = _claude_window_handle()
    if not hwnd:
        return None
    try:
        import comtypes
        from comtypes.client import CreateObject, GetModule
        if _UIA_AUTOMATION is None:
            comtypes.CoInitialize()
            GetModule('UIAutomationCore.dll')
            from comtypes.gen import UIAutomationClient as UIA
            _UIA_AUTOMATION = (CreateObject(UIA.CUIAutomation,
                                            interface=UIA.IUIAutomation), UIA)
        automation, UIA = _UIA_AUTOMATION
        root = automation.ElementFromHandle(hwnd)
        elements = root.FindAll(UIA.TreeScope_Subtree, automation.CreateTrueCondition())
        names = []
        for index in range(elements.Length):
            try:
                name = elements.GetElement(index).CurrentName
                if name:
                    names.append(name)
            except Exception:
                continue
        five, week = _parse_claude_usage_names(names)
        if five is None and week is None:
            return None
        return {'five': five, 'week': week, 't': int(time.time() * 1000)}
    except Exception:
        return None


def _merge_claude_ui(result, ui_usage):
    if not ui_usage:
        return result
    result = dict(result)
    if ui_usage.get('five') is not None:
        result['five'] = ui_usage['five']
    if ui_usage.get('week') is not None:
        result['week'] = ui_usage['week']
    result['ok'] = result.get('five') is not None or result.get('week') is not None
    result['t'] = ui_usage.get('t', result.get('t', 0))
    result['stale'] = False
    return result


def _claude_is_running():
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
                ('szExeFile', wintypes.WCHAR * 260),
            ]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return False
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
                return False
            while True:
                if entry.szExeFile.lower() == 'claude.exe':
                    return True
                if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                    return False
        finally:
            kernel.CloseHandle(snapshot)
    except Exception:
        return False


def _claude_freshness(result):
    result = dict(result)
    stamp = result.get('t') or 0
    old = (not stamp or
           (time.time() - stamp / 1000.0) > CLAUDE_STALE_SECONDS)
    result['stale'] = bool(old and not _claude_is_running())
    return result


def launch_claude_desktop():
    """手動更新時に公式Claudeを起動し、使用量ファイルの更新を促す。"""
    try:
        explorer = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'explorer.exe')
        subprocess.Popen([explorer, CLAUDE_APP_ID], close_fds=True)
        return True
    except Exception:
        return False


def claude_local(cfg=None):
    ui_usage = _claude_uia_usage()
    # 従来版とMicrosoft Store版では保存場所が異なる。
    candidates = [os.path.join(APPDATA, 'Claude', 'plan-usage-history.json')]
    local_appdata = os.environ.get('LOCALAPPDATA', '')
    candidates += glob.glob(os.path.join(
        local_appdata, 'Packages', 'Claude_*', 'LocalCache', 'Roaming',
        'Claude', 'plan-usage-history.json'))
    candidates = [p for p in candidates if os.path.isfile(p)]
    candidates.sort(key=os.path.getmtime, reverse=True)
    if not candidates:
        cached = _LAST_GOOD.get('claude')
        if cached:
            result = _merge_claude_ui(_claude_freshness(cached), ui_usage)
            _LAST_GOOD['claude'] = dict(result)
            return result
        if ui_usage:
            result = _merge_claude_ui(_empty(''), ui_usage)
            _LAST_GOOD['claude'] = dict(result)
            return result
        missing = _empty('Claudeを開いて更新', CLAUDE_USAGE_URL)
        missing['stale'] = True
        return missing

    for path in candidates:
        for attempt in range(3):
            try:
                with open(path, encoding='utf-8') as f:
                    d = json.load(f)
                samples = d.get('samples', [])
                if not samples:
                    break
                last = max(samples, key=lambda s: s.get('t', 0))
                u = last.get('u', {})
                result = {'ok': True, 'five': u.get('fh'), 'week': u.get('sd'),
                          'plan': None, 'reset_five': None, 'reset_week': None,
                          'note': ('⚠上限' if u.get('xu') == 100 else ''),
                          't': last.get('t', 0)}
                result = _merge_claude_ui(_claude_freshness(result), ui_usage)
                _LAST_GOOD['claude'] = dict(result)
                return result
            except Exception:
                if attempt < 2:
                    time.sleep(0.08)
        # 別の候補ファイルがあれば続けて試す。
    cached = _LAST_GOOD.get('claude')
    if cached:
        result = _merge_claude_ui(_claude_freshness(cached), ui_usage)
        _LAST_GOOD['claude'] = dict(result)
        return result
    if ui_usage:
        result = _merge_claude_ui(_empty(''), ui_usage)
        _LAST_GOOD['claude'] = dict(result)
        return result
    failed = _empty('Claudeを開いて更新', CLAUDE_USAGE_URL)
    failed['stale'] = True
    return failed


# ---------- ChatGPT / Codex (レイ) ----------
def _rate_limit_dicts(value):
    """JSONの文字列内ではなく、実データの使用率だけを再帰的に探す。"""
    if isinstance(value, dict):
        for key in ('rate_limits', 'rateLimits'):
            limits = value.get(key)
            if isinstance(limits, dict):
                yield limits
        for child in value.values():
            yield from _rate_limit_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _rate_limit_dicts(child)


def _event_epoch(event, fallback):
    stamp = event.get('timestamp') if isinstance(event, dict) else None
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
        except Exception:
            pass
    return fallback


def _limit_value(data, snake, camel):
    value = data.get(snake)
    return data.get(camel) if value is None else value


def codex_local(cfg=None):
    sess = os.path.join(HOME, '.codex', 'sessions')
    try:
        files = glob.glob(os.path.join(sess, '**', 'rollout-*.jsonl'), recursive=True)
        if not files:
            return _empty('セッション無し')
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        # 生テキスト検索では会話中に引用された古い値を誤認するため、各JSON行を
        # 構造として読み、複数セッションのうち時刻が最も新しい実データを選ぶ。
        rl = None
        newest = 0.0
        for p in files[:20]:
            fallback = os.path.getmtime(p)
            with open(p, encoding='utf-8', errors='ignore') as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    event_time = _event_epoch(event, fallback)
                    for candidate in _rate_limit_dicts(event):
                        primary = candidate.get('primary') or {}
                        secondary = candidate.get('secondary') or {}
                        five = _limit_value(primary, 'used_percent', 'usedPercent')
                        week = _limit_value(secondary, 'used_percent', 'usedPercent')
                        if (isinstance(five, (int, float)) or
                                isinstance(week, (int, float))):
                            if event_time >= newest:
                                rl, newest = candidate, event_time
        if not rl:
            return _empty('レート情報無し')
        pri = rl.get('primary') or {}
        sec = rl.get('secondary') or {}
        five = _limit_value(pri, 'used_percent', 'usedPercent')
        week = _limit_value(sec, 'used_percent', 'usedPercent')
        five = round(five) if isinstance(five, (int, float)) else None
        week = round(week) if isinstance(week, (int, float)) else None
        return {'ok': True, 'five': five, 'week': week,
                'plan': _limit_value(rl, 'plan_type', 'planType'),
                'reset_five': _limit_value(pri, 'resets_at', 'resetsAt'),
                'reset_week': _limit_value(sec, 'resets_at', 'resetsAt'),
                'note': '', 't': int(newest * 1000)}
    except Exception as e:
        return _empty('読取失敗')


# ---------- 未対応 (ジェミ 等) ----------
def none_provider(cfg=None):
    return _empty('未対応')


REGISTRY = {
    'claude_local': claude_local,
    'codex_local': codex_local,
    'none': none_provider,
}


def read_provider(ptype, cfg=None):
    fn = REGISTRY.get(ptype, none_provider)
    return fn(cfg)


if __name__ == '__main__':
    print('claude:', claude_local())
    print('codex :', codex_local())
