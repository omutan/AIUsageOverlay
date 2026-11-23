# -*- coding: utf-8 -*-
"""
聞く線のボタン（2026-11-11）。小窓に「聞く線 [－] 30分 [＋] [聞かない]」を出し、押すと
進捗フックの %USERPROFILE%\\.claude\\ProgressHooks\\ask_line.json を書き換える。

聞く線＝作業の目安の上限がこれを超えたら、シロが「進めて大丈夫ですか？」と聞く（スキル work-estimate）。
押した線は全部のチャットにすぐ効く。

2026-11-19 「効く長さ [今日だけ] [ずっと]」を足した（どちらで書くかは overlay_scope に覚える）。
2026-11-24 本人「日付は関係ないようにしてほしい」→ 小窓の行は消し、ふだんは「ずっと」で書く
（overlay_scope が "today" のときだけ今日の分に書く。今は小窓から today にする手段は出していない）。
    今日だけ … "today" を書く。日付が変わるとずっと（ふだん）の線に戻る
    ずっと   … "default"（分）と "default_no_ask"（聞かないの印）を書き、今日の分は消す。翌日も残る
書き方はフック側 C:\\AI\\ProgressHooks\\ask_line.py と同じ形にそろえる：
    "today": {"date": "2026-11-11", "min": 30, "no_ask": false, "set": "2026-11-11T10:50:00"}
    "default": 30, "default_no_ask": false, "default_set": "2026-11-19T16:00:00"
"""
import json
import os
from datetime import datetime

DEFAULT_FILE = os.path.join(os.environ.get('PROGRESS_HOOK_STATE') or os.path.join(
    os.environ.get('USERPROFILE', os.path.expanduser('~')), '.claude', 'ProgressHooks'), 'ask_line.json')
DEFAULT_MIN = 5
STEPS = [5, 10, 15, 30, 45, 60, 90, 120, 180]
TODAY, ALWAYS = 'today', 'always'


def load(path=None):
    try:
        with open(path or DEFAULT_FILE, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(d, path=None):
    path = path or DEFAULT_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _default(d):
    dm = d.get('default')
    return dm if isinstance(dm, int) and dm > 0 else DEFAULT_MIN


def scope(path=None):
    """小窓のボタンがどちらに書くか（today / always）"""
    return TODAY if load(path).get('overlay_scope') == TODAY else ALWAYS


def _state(d, now=None):
    """(minutes, no_ask, 効いている所)。効いている所は today / always"""
    t = d.get('today')
    today = (now or datetime.now()).strftime('%Y-%m-%d')
    if isinstance(t, dict) and t.get('date') == today and isinstance(t.get('min'), int):
        if t['min'] > 0:
            return t['min'], bool(t.get('no_ask')), TODAY
        return _default(d), True, TODAY        # 古い形（min=-1 が聞かない）
    return _default(d), bool(d.get('default_no_ask')), ALWAYS


def state(path=None, now=None):
    """小窓に出す (minutes, no_ask)。今日の分が無ければずっと（ふだん）の線"""
    m, na, _ = _state(load(path), now)
    return m, na


def _write(minutes, no_ask, path=None, now=None):
    now = now or datetime.now()
    d = load(path)
    stamp = now.isoformat(timespec='seconds')
    if d.get('overlay_scope') != TODAY:
        d['default'] = int(minutes)
        d['default_no_ask'] = bool(no_ask)
        d['default_set'] = stamp
        d.pop('today', None)       # 今日の分が残っていると、そちらが勝ってしまう
    else:
        d['today'] = {'date': now.strftime('%Y-%m-%d'), 'min': int(minutes), 'no_ask': bool(no_ask),
                      'set': stamp, 'by': 'overlay'}
    save(d, path)
    return int(minutes), bool(no_ask)


def step(minutes, delta):
    """STEPS の上で一段動かす。段の間の値は近い方の段へ"""
    if delta > 0:
        for s in STEPS:
            if s > minutes:
                return s
        return STEPS[-1]
    for s in reversed(STEPS):
        if s < minutes:
            return s
    return STEPS[0]


def bump(delta, path=None, now=None):
    """[－]／[＋]。聞かないの印はそのまま"""
    m, na = state(path, now)
    return _write(step(m, delta), na, path, now)


def reset(path=None, now=None):
    """時間を押したとき。今日だけ：ずっとの線に戻す／ずっと：5分に戻す。どちらも聞かないを外す"""
    d = load(path)
    if d.get('overlay_scope') != TODAY:
        for k in ('default', 'default_no_ask', 'default_set', 'today'):
            d.pop(k, None)
        save(d, path)
        return DEFAULT_MIN, False
    return _write(_default(d), False, path, now)


def toggle_no_ask(path=None, now=None):
    m, na = state(path, now)
    return _write(m, not na, path, now)


def set_scope(new, path=None, now=None):
    """[今日だけ]／[ずっと] を押したとき。今見えている線はそのまま、書く先だけ替える。
    ずっとにしたときは、今の線をそのままずっとの線にする（押した瞬間に見た目が変わらないように）"""
    now = now or datetime.now()
    d = load(path)
    old = TODAY if d.get('overlay_scope') == TODAY else ALWAYS
    if new == old:
        return new
    m, na, _ = _state(d, now)
    d['overlay_scope'] = new
    save(d, path)
    if new == ALWAYS:
        _write(m, na, path, now)
    return new


def fmt(minutes):
    if minutes >= 60 and minutes % 60 == 0:
        return f'{minutes // 60}時間'
    if minutes > 60:
        return f'{minutes / 60:g}時間'
    return f'{minutes}分'


def tooltip(path=None, now=None):
    """トレイのアイコンに出す1行。例「聞く線：30分（ずっと）」「聞く線：聞かない（今日だけ）」"""
    m, na, where = _state(load(path), now)
    # 2026-11-24 小窓で決めた線はずっと残るので、ふだんは時間だけ。チャットで「今日」と決めた分だけ印を付ける
    return f"聞く線：{'聞かない' if na else fmt(m)}" + ('（今日だけ）' if where == TODAY else '')
