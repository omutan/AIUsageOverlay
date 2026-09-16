# -*- coding: utf-8 -*-
"""各AIの使用量を「ローカルのファイル」から読むプロバイダ群.
どれも API/トークン不要。アプリ自身が書き出すファイルを読むだけ。

返り値の契約（常に全キーを揃える）:
  ok, five, week, plan, reset_five, reset_week, note, t, stale, url
  five/week = 使用率%(0-100)。取れない枠は None。残り%への変換は表示側で行う。
"""
import os, glob, json, re, time, subprocess
from datetime import datetime

APPDATA = os.environ.get('APPDATA', '')
HOME = os.path.expanduser('~')
CLAUDE_USAGE_URL = 'https://claude.ai/settings/usage'
CLAUDE_APP_ID = r'shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude'
CLAUDE_STALE_SECONDS = 180
CODEX_TAIL_BYTES = 512 * 1024
CODEX_MAX_FILES = 20
CONTRACT_KEYS = ('ok', 'five', 'week', 'plan', 'reset_five', 'reset_week',
                 'note', 't', 'stale', 'url')


def _result(**kw):
    """契約キーを必ず揃えた結果 dict を作る。"""
    base = {'ok': False, 'five': None, 'week': None, 'plan': None,
            'reset_five': None, 'reset_week': None, 'note': '',
            't': 0, 'stale': False, 'url': None}
    base.update(kw)
    return base


def _empty(note='未取得', url=None):
    """旧APIとの互換のために残す薄いラッパ。"""
    return _result(note=note, url=url)


def _file_key(path):
    """ファイルの変化を見分ける鍵。読めなければ None。"""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return None


class Provider:
    """読み取り関数とキャッシュ状態をまとめた基底クラス。"""

    ptype = ''

    def __init__(self, cfg=None):
        self.cfg = cfg
        self.last_good = None
        self._keys = {}      # path -> _file_key
        self._parsed = {}    # path -> 解析結果（None も保持する）

    def read(self, force=False):
        raise NotImplementedError

    def _cached(self, path, key):
        if key is not None and self._keys.get(path) == key:
            return True, self._parsed.get(path)
        return False, None

    def _store(self, path, key, value):
        if key is None:
            self._keys.pop(path, None)
            self._parsed.pop(path, None)
            return
        self._keys[path] = key
        self._parsed[path] = value

    def _prune(self, keep_paths):
        keep = set(keep_paths)
        for path in [p for p in self._keys if p not in keep]:
            self._keys.pop(path, None)
            self._parsed.pop(path, None)


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
    """Claude画面に表示されている公式使用率を、読み取り専用で取得する。
    手動更新時にワーカースレッドから呼ばれるので、COMは毎回この場で初期化する。
    """
    hwnd = _claude_window_handle()
    if not hwnd:
        return None
    try:
        import comtypes
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except Exception:
        return None
    automation = None
    try:
        from comtypes.client import CreateObject, GetModule
        GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as UIA
        automation = CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
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
    finally:
        automation = None
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


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


class ClaudeProvider(Provider):
    ptype = 'claude_local'

    def _candidates(self):
        # 従来版とMicrosoft Store版では保存場所が異なる。
        paths = [os.path.join(APPDATA, 'Claude', 'plan-usage-history.json')]
        local_appdata = os.environ.get('LOCALAPPDATA', '')
        paths += glob.glob(os.path.join(
            local_appdata, 'Packages', 'Claude_*', 'LocalCache', 'Roaming',
            'Claude', 'plan-usage-history.json'))
        return [p for p in paths if os.path.isfile(p)]

    def _read_file(self, path):
        """使用量ファイルを読んで結果に変換する。読めなければ None。"""
        for attempt in range(3):
            try:
                with open(path, encoding='utf-8') as f:
                    d = json.load(f)
                samples = d.get('samples', [])
                if not samples:
                    return None
                last = max(samples, key=lambda s: s.get('t', 0))
                u = last.get('u', {})
                return _result(ok=True, five=u.get('fh'), week=u.get('sd'),
                               note=('⚠上限' if u.get('xu') == 100 else ''),
                               t=last.get('t', 0))
            except Exception:
                if attempt < 2:
                    time.sleep(0.08)
        return None

    def read(self, force=False):
        paths = self._candidates()
        base = None
        for path in paths:
            key = _file_key(path)
            hit, value = self._cached(path, key)
            if not hit:
                value = self._read_file(path)
                self._store(path, key, value)
            if value and (base is None or value.get('t', 0) > base.get('t', 0)):
                base = value
        self._prune(paths)

        if base is None:
            if self.last_good:
                base = dict(self.last_good)
            else:
                base = _result(note='Claudeを開いて更新', url=CLAUDE_USAGE_URL,
                               stale=True)
        base = _claude_freshness(base)
        if force:
            # UIA走査は重いので、手動更新（↻）のときだけ行う。
            base = _merge_claude_ui(base, _claude_uia_usage())
        # 仕様変更: 名前クリックで使用量ページを開けるよう、ok のときも url を入れる。
        base['url'] = CLAUDE_USAGE_URL
        if base.get('ok'):
            self.last_good = dict(base)
        return base


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


class CodexProvider(Provider):
    ptype = 'codex_local'

    def _list_files(self):
        sess = os.path.join(HOME, '.codex', 'sessions')
        files = glob.glob(os.path.join(sess, '**', 'rollout-*.jsonl'), recursive=True)
        stamped = []
        for path in files:
            try:
                stamped.append((path, os.path.getmtime(path)))
            except Exception:
                continue
        stamped.sort(key=lambda it: it[1], reverse=True)
        return stamped[:CODEX_MAX_FILES]

    def _scan_tail(self, path, fallback_mtime):
        """末尾だけを後ろから走査し、最後の rate_limits を (dict, epoch) で返す。
        生テキスト検索では会話中に引用された古い値を誤認するため、行ごとに
        JSONとして読む。"""
        with open(path, 'rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            start = max(0, size - CODEX_TAIL_BYTES)
            stream.seek(start)
            buf = stream.read()
        if start > 0:
            cut = buf.find(b'\n')
            buf = buf[cut + 1:] if cut >= 0 else b''
        for line in reversed(buf.split(b'\n')):
            if b'"rate_limits"' not in line and b'"rateLimits"' not in line:
                continue
            try:
                event = json.loads(line.decode('utf-8', 'ignore'))
            except Exception:
                continue
            epoch = _event_epoch(event, fallback_mtime)
            for candidate in _rate_limit_dicts(event):
                primary = candidate.get('primary') or {}
                secondary = candidate.get('secondary') or {}
                five = _limit_value(primary, 'used_percent', 'usedPercent')
                week = _limit_value(secondary, 'used_percent', 'usedPercent')
                if isinstance(five, (int, float)) or isinstance(week, (int, float)):
                    return candidate, epoch
        return None

    def read(self, force=False):
        try:
            files = self._list_files()
            if not files:
                return _result(note='セッション無し')
            best = None
            best_epoch = 0.0
            for path, mtime in files:
                # 更新時刻が採用中の値より古いファイルには、新しい値は無い。
                if best is not None and mtime < best_epoch:
                    break
                key = _file_key(path)
                hit, value = self._cached(path, key)
                if not hit:
                    try:
                        value = self._scan_tail(path, mtime)
                    except Exception:
                        value = None
                    self._store(path, key, value)
                if value and value[1] > best_epoch:
                    best, best_epoch = value
            self._prune([p for p, _ in files])
            if not best:
                return _result(note='レート情報無し')
            pri = best.get('primary') or {}
            sec = best.get('secondary') or {}
            five = _limit_value(pri, 'used_percent', 'usedPercent')
            week = _limit_value(sec, 'used_percent', 'usedPercent')
            five = round(five) if isinstance(five, (int, float)) else None
            week = round(week) if isinstance(week, (int, float)) else None
            result = _result(ok=True, five=five, week=week,
                             plan=_limit_value(best, 'plan_type', 'planType'),
                             reset_five=_limit_value(pri, 'resets_at', 'resetsAt'),
                             reset_week=_limit_value(sec, 'resets_at', 'resetsAt'),
                             t=int(best_epoch * 1000))
            self.last_good = dict(result)
            return result
        except Exception:
            if self.last_good:
                return dict(self.last_good)
            return _result(note='読取失敗')


# ---------- 未対応 (ジェミ 等) ----------
class NoneProvider(Provider):
    ptype = 'none'

    def read(self, force=False):
        return _result(note='未対応')


REGISTRY = {
    'claude_local': ClaudeProvider,
    'codex_local': CodexProvider,
    'none': NoneProvider,
}

_INSTANCES = {}


def get_provider(ptype, cfg=None):
    """種類ごとに1つだけ実体を持ち、キャッシュを引き継ぐ。"""
    inst = _INSTANCES.get(ptype)
    if inst is None:
        inst = REGISTRY.get(ptype, NoneProvider)(cfg)
        _INSTANCES[ptype] = inst
    else:
        inst.cfg = cfg if cfg is not None else inst.cfg
    return inst


def read_provider(ptype, cfg=None, force=False):
    return get_provider(ptype, cfg).read(force=force)


if __name__ == '__main__':
    import sys
    force = '--force' in sys.argv
    for name in ('claude_local', 'codex_local'):
        for i in range(3):
            t0 = time.perf_counter()
            r = read_provider(name, force=force and i == 0)
            print('%-12s #%d %.1fms %s' % (name, i, (time.perf_counter() - t0) * 1000, r))
