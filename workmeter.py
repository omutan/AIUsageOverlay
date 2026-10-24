# -*- coding: utf-8 -*-
"""
作業メーター（見せる側の計算）。

進捗フック（C:\\AI\\ProgressHooks\\work_meter.py）が書く current.json / history.jsonl を読み、
小窓に出す「段階 3/7・12分経過・あと8〜13分」と、知らせ（終了・目安の1.5倍超え）の判断を作る。
tkinter には触らない（机上テストできる）。

残り時間の出し方
  - 目安があるとき: 目安 × 残りの段階の割合。段階が1つも終わっていなければ「目安 − 経過」。
  - 段階が1つ以上終わっていれば、ここまでの速さ（経過 ÷ 終わった数 × 残りの数）も出し、
    目安からの値と合わせて幅にする（小さい方〜大きい方）。
  - 目安が無ければ速さだけ（±25%）。段階が1つも終わっていなければ「—」。

実績による補正（2026-10-24）
  - history.jsonl の終わった作業から「実際 ÷ 目安の真ん中」の比を取り、目安に掛ける。
  - 同じプロジェクトの直近5件が3件以上あればその中央値、無ければ全体の直近10件（3件以上）の中央値。
    3件に届かないうちは補正しない。1分未満で終わった作業と目安の無い作業は数えない。
  - 同じ task_id が複数行あれば（開き直して終わり直した）最後の行だけ使う。

知らせ
  - 終わったとき1回、目安の上限 × 1.5 を超えたとき1回。どちらも作業（task_id）ごとに1回だけ。
  - 小窓を起こす前に終わっていた作業は知らせない（起こした直後に古い知らせが並ばないように）。
  - 音は鳴らさない（Windows の通知を audio silent で出す）。
"""
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta

# 置き場は %USERPROFILE%\.claude\ProgressHooks（2026-10-24 に %LOCALAPPDATA% から移した）。
# Claude アプリはパッケージ化アプリで、アプリが起こした子プロセス（進捗フックも）は %LOCALAPPDATA% への
# 読み書きが Packages\Claude_*\LocalCache\Local の写しに振り替えられ、外で動く小窓から見えなかったため。
DEFAULT_FILE = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')),
                            '.claude', 'ProgressHooks', 'work', 'current.json')
SHOW_DONE_MIN = 10        # 終わった作業を「完了」として出し続ける分数
OVERRUN_RATIO = 1.5       # 目安の上限 × これ を超えたら「遅れ」
CORR_PROJECT_N = 5        # 補正: 同じプロジェクトの直近何件を見るか
CORR_ALL_N = 10           # 補正: 全体の直近何件を見るか
CORR_MIN_N = 3            # 補正: この件数に届かないうちは補正しない
CORR_CLAMP = (0.5, 3.0)   # 補正の比はこの範囲に収める（外れ値で目安が壊れないように）


def _parse(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def current_path(path=None):
    return path or os.environ.get('WORK_METER_FILE') or DEFAULT_FILE


def history_path(path=None):
    return os.path.join(os.path.dirname(current_path(path)), 'history.jsonl')


def load(path=None):
    try:
        with open(current_path(path), encoding='utf-8') as f:
            d = json.load(f)
        tasks = d.get('tasks', {}) if isinstance(d, dict) else {}
        return [t for t in tasks.values() if isinstance(t, dict)]
    except Exception:
        return []


def load_history(path=None):
    """history.jsonl を読む。同じ task_id は最後の行だけ残し、終わった順に返す"""
    recs = {}
    try:
        with open(history_path(path), encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if isinstance(r, dict) and r.get('task_id'):
                    recs[r['task_id']] = r
    except Exception:
        return []
    out = list(recs.values())
    out.sort(key=lambda r: r.get('finished_at') or '')
    return out


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _ratios(recs):
    out = []
    for r in recs:
        lo, hi, act = r.get('estimate_min'), r.get('estimate_max'), r.get('actual_min')
        if lo is None or hi is None or act is None:
            continue
        mid = (float(lo) + float(hi)) / 2.0
        if mid <= 0 or act < 1 or float(hi) < 3:
            continue   # 1分未満で終わった作業、目安3分未満の小さな作業は比がぶれるので数えない
        out.append(float(act) / mid)
    return out


def correction(project, history):
    """目安に掛ける比と、根拠にした件数と範囲（'project' / 'all' / ''）を返す"""
    if project:
        same = [r for r in history if r.get('project') == project]
        rs = _ratios(same[-CORR_PROJECT_N:])
        if len(rs) >= CORR_MIN_N:
            return _clamp(_median(rs)), len(rs), 'project'
    rs = _ratios(history[-CORR_ALL_N:])
    if len(rs) >= CORR_MIN_N:
        return _clamp(_median(rs)), len(rs), 'all'
    return 1.0, 0, ''


def _clamp(x):
    return max(CORR_CLAMP[0], min(CORR_CLAMP[1], x))


def fmt_min(m):
    m = int(round(m))
    if m < 120:
        return f'{m}分'
    h = m / 60.0
    return (f'{h:.1f}' if h < 10 else f'{int(round(h))}') + '時間'


def fmt_range(lo, hi):
    lo, hi = int(round(lo)), int(round(hi))
    if hi <= lo:
        return fmt_min(lo)
    if hi < 120:
        return f'{lo}〜{hi}分'
    # 上限が2時間以上なら両方とも時間で（「100分〜5.0時間」のように単位を混ぜない）
    return f'{lo / 60.0:.1f}〜{hi / 60.0:.1f}時間'


def remaining(est_lo, est_hi, elapsed, done, total):
    """残り時間の幅（分）を (lo, hi) で返す。出せなければ None"""
    left = max(0, total - done)
    # 始めて1分未満は速さが決まらない（0分で1段階終わると「あと0分」になる）ので速さは使わない
    pace = (elapsed / done * left) if (done > 0 and elapsed >= 1.0) else None
    if est_lo is not None and est_hi is not None:
        if total > 0 and done > 0:
            frac = left / float(total)
            a_lo, a_hi = est_lo * frac, est_hi * frac
        else:
            a_lo, a_hi = max(0.0, est_lo - elapsed), max(0.0, est_hi - elapsed)
        if pace is None:
            return (a_lo, a_hi)
        return (min(a_lo, pace), max(a_hi, pace))
    if pace is None:
        return None
    return (pace * 0.75, pace * 1.25)


def describe(t, now=None, history=None):
    """1件の作業を表示用の辞書にする。show=False なら出さない"""
    now = now or datetime.now().astimezone()
    steps = t.get('steps') or []
    total = len(steps)
    done = sum(1 for s in steps if s.get('status') == 'completed')
    st = _parse(t.get('started_at') or '')
    fin = _parse(t.get('finished_at') or '')
    wait = _parse(t.get('waiting_since') or '') if not fin else None   # 質問で終わり、返事を待っている
    if st is None:
        return {'show': False}
    end = fin or wait or now
    elapsed = max(0.0, (end - st).total_seconds() / 60.0)
    est_lo, est_hi = t.get('estimate_min'), t.get('estimate_max')
    raw_lo, raw_hi = est_lo, est_hi
    factor, corr_n, corr_scope = 1.0, 0, ''
    if est_lo is not None and history:
        factor, corr_n, corr_scope = correction(t.get('project') or '', history)
        est_lo, est_hi = est_lo * factor, est_hi * factor
    name = (t.get('title') or t.get('project') or '作業').strip()
    out = {
        'id': t.get('session_id', ''),
        'task_id': t.get('task_id', ''),
        'name': name,
        'ai': t.get('ai', ''),
        'done': done, 'total': total,
        'pct': (100.0 * done / total) if total else 0.0,
        'elapsed': elapsed,
        'est': (raw_lo, raw_hi) if raw_lo is not None else None,
        'est_corrected': (est_lo, est_hi) if est_lo is not None else None,
        'factor': factor, 'corr_n': corr_n, 'corr_scope': corr_scope,
        'finished': bool(fin),
        'finished_at': fin,
        'waiting': bool(wait),
        'overrun': False,
        'show': True,
    }
    if wait:
        # 待っている間は時間を進めない。遅れの判定も知らせもしない
        parts = [f'{done}/{total}'] if total else []
        parts += [fmt_min(elapsed), '返事待ち']
        out['text'] = '・'.join(parts)
        return out
    if fin:
        if (now - fin).total_seconds() / 60.0 > SHOW_DONE_MIN:
            out['show'] = False
        est = f'（目安{fmt_range(raw_lo, raw_hi)}）' if raw_lo is not None else ''
        out['text'] = f'完了 {fmt_min(elapsed)}{est}'
        out['pct'] = 100.0
        return out
    rem = remaining(est_lo, est_hi, elapsed, done, total)
    if est_hi is not None and elapsed > est_hi * OVERRUN_RATIO:
        out['overrun'] = True
    parts = []
    if total:
        parts.append(f'{done}/{total}')
    parts.append(f'{fmt_min(elapsed)}経過')
    if rem is not None:
        parts.append('あと' + fmt_range(*rem))
    elif est_lo is not None:
        parts.append('目安' + fmt_range(est_lo, est_hi))
    else:
        parts.append('目安なし')
    if out['overrun']:
        parts.append('遅れ')
    out['text'] = '・'.join(parts)
    return out


def current(path=None, now=None, with_history=True):
    """表示する作業の一覧（新しい順）。補正のため history も読む"""
    history = load_history(path) if with_history else None
    items = [describe(t, now, history) for t in load(path)]
    items = [i for i in items if i.get('show')]
    items.sort(key=lambda i: (i['finished'], i.get('waiting', False), -i['elapsed']))
    return items


# ---------------------------------------------------------------- 知らせ
def due_notifications(items, notified, since, now=None):
    """
    出すべき知らせを [(kind, item)] で返し、notified（{task_id: {kind}}）を更新する。
    kind は 'finish' / 'overrun'。since（小窓を起こした時刻）より前に終わった作業の finish は出さない。
    """
    now = now or datetime.now().astimezone()
    out = []
    for it in items:
        tid = it.get('task_id') or it.get('id')
        if not tid:
            continue
        seen = notified.setdefault(tid, set()) if isinstance(notified.get(tid), set) else set(notified.get(tid, []))
        notified[tid] = seen
        if it['finished']:
            fin = it.get('finished_at')
            if 'finish' not in seen and fin is not None and (since is None or fin >= since):
                seen.add('finish')
                out.append(('finish', it))
        elif it['overrun'] and 'overrun' not in seen:
            seen.add('overrun')
            out.append(('overrun', it))
    return out


def notification_text(kind, it):
    ai = f"{it['ai']}・" if it.get('ai') else ''
    est = f"（目安{fmt_range(*it['est'])}）" if it.get('est') else ''
    if kind == 'finish':
        return '作業が終わりました', f"{ai}{it['name']}　{fmt_min(it['elapsed'])}{est}"
    return '目安を大きく超えています', f"{ai}{it['name']}　{fmt_min(it['elapsed'])}経過{est}"


_TOAST_PS = r'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($args[0])
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($args[1]).Show($toast)
'''
APP_ID = r'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'


def _xml_escape(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def toast_xml(title, body):
    # <audio silent="true"/> で音を鳴らさない（本人の決定）
    return ('<toast><visual><binding template="ToastGeneric">'
            f'<text>{_xml_escape(title)}</text><text>{_xml_escape(body)}</text>'
            '</binding></visual><audio silent="true"/></toast>')


def toast(title, body, wait=False):
    """音なしの Windows 通知。PowerShell を使うので別スレッドで出す（小窓を待たせない）"""
    xml = toast_xml(title, body)

    def run():
        try:
            subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                            '-Command', _TOAST_PS, xml, APP_ID],
                           capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception:
            pass
    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- 知らせの控え（小窓を立て直しても同じ知らせを繰り返さない）
def load_notified(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return {k: set(v) for k, v in d.items() if isinstance(v, list)}
    except Exception:
        return {}


def save_notified(path, notified, keep=200):
    try:
        keys = list(notified.keys())[-keep:]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({k: sorted(notified[k]) for k in keys}, f, ensure_ascii=False)
    except Exception:
        pass


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'toast':
        toast('作業メーターの試し', 'この知らせは音なしで出ます', wait=True)
        print('toast sent')
    else:
        hist = load_history()
        for i in current():
            corr = f"  [補正 x{i['factor']:.2f} {i['corr_scope']} n={i['corr_n']}]" if i['corr_n'] else ''
            print(i['name'], i['text'], corr)
        print(f'history: {len(hist)}件')
