# -*- coding: utf-8 -*-
"""
聞く線のボタン（2026-11-11）。小窓に「聞く線 [－] 30分 [＋] [聞かない]」を出し、押すと
進捗フックの %USERPROFILE%\\.claude\\ProgressHooks\\ask_line.json の "today" を書き換える。

聞く線＝作業の目安の上限がこれを超えたら、シロが「進めて大丈夫ですか？」と聞く（スキル work-estimate）。
押した線は全部のチャットにすぐ効き、日付が変わるとふだんの線（5分）に戻る。
書き方はフック側 C:\\AI\\ProgressHooks\\ask_line.py と同じ形にそろえる：
    "today": {"date": "2026-11-11", "min": 30, "no_ask": false, "set": "2026-11-11T10:50:00"}
"""
import json
import os
from datetime import datetime

DEFAULT_FILE = os.path.join(os.environ.get('PROGRESS_HOOK_STATE') or os.path.join(
    os.environ.get('USERPROFILE', os.path.expanduser('~')), '.claude', 'ProgressHooks'), 'ask_line.json')
DEFAULT_MIN = 5
STEPS = [5, 10, 15, 30, 45, 60, 90, 120, 180]


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


def state(path=None, now=None):
    """小窓に出す (minutes, no_ask)。今日の分が無ければふだんの線"""
    d = load(path)
    t = d.get('today')
    today = (now or datetime.now()).strftime('%Y-%m-%d')
    if isinstance(t, dict) and t.get('date') == today and isinstance(t.get('min'), int):
        if t['min'] > 0:
            return t['min'], bool(t.get('no_ask'))
        return _default(d), True        # 古い形（min=-1 が聞かない）
    return _default(d), False


def _write(minutes, no_ask, path=None, now=None):
    now = now or datetime.now()
    d = load(path)
    d['today'] = {'date': now.strftime('%Y-%m-%d'), 'min': int(minutes), 'no_ask': bool(no_ask),
                  'set': now.isoformat(timespec='seconds'), 'by': 'overlay'}
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
    """時間を押したとき：ふだんの線に戻し、聞かないも外す"""
    d = load(path)
    return _write(_default(d), False, path, now)


def toggle_no_ask(path=None, now=None):
    m, na = state(path, now)
    return _write(m, not na, path, now)


def fmt(minutes):
    if minutes >= 60 and minutes % 60 == 0:
        return f'{minutes // 60}時間'
    if minutes > 60:
        return f'{minutes / 60:g}時間'
    return f'{minutes}分'
