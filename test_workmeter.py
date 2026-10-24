# -*- coding: utf-8 -*-
"""workmeter.py の机上テスト（tkinter なし・通知は出さない）。python test_workmeter.py"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workmeter as WM  # noqa: E402

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 24, 15, 0, tzinfo=JST)
fails = []


def check(name, cond, detail=''):
    print(('OK  ' if cond else 'NG  ') + name + ('' if cond else f'  <- {detail}'))
    if not cond:
        fails.append(name)


def task(**k):
    t = {'session_id': 's1', 'task_id': 's1-1', 'ai': 'シロ', 'project': 'P023', 'title': 'P023 作業メーター',
         'started_at': (NOW - timedelta(minutes=12)).isoformat(), 'finished_at': None,
         'estimate_min': 15, 'estimate_max': 25,
         'steps': [{'status': 'completed'}] * 3 + [{'status': 'in_progress'}] + [{'status': 'pending'}] * 3}
    t.update(k)
    return t


def rec(i, project='P023', est=(10, 20), actual=30, tid=None):
    return {'task_id': tid or f't{i}', 'project': project, 'estimate_min': est[0], 'estimate_max': est[1],
            'actual_min': actual, 'finished_at': (NOW - timedelta(days=10 - i)).isoformat()}


# ---- 表示（補正なし）
d = WM.describe(task(), NOW)
check('1a 3/7・12分経過・あと（目安と速さの幅）', d['text'] == '3/7・12分経過・あと9〜16分', d['text'])
d = WM.describe(task(steps=[{'status': 'in_progress'}] + [{'status': 'pending'}] * 4), NOW)
check('1b 段階が終わっていない: 目安−経過', 'あと3〜13分' in d['text'], d['text'])
d = WM.describe(task(estimate_min=None, estimate_max=None), NOW)
check('1c 目安なし: 速さだけ ±25%', 'あと12〜20分' in d['text'], d['text'])
d = WM.describe(task(estimate_min=None, estimate_max=None, steps=[{'status': 'in_progress'}]), NOW)
check('1d 目安も速さも無い: 目安なし', '目安なし' in d['text'], d['text'])
d = WM.describe(task(started_at=(NOW - timedelta(seconds=20)).isoformat()), NOW)
check('1e 始めて1分未満は速さを使わない（あと0分にならない）', 'あと9〜14分' in d['text'], d['text'])
d = WM.describe(task(started_at=(NOW - timedelta(minutes=40)).isoformat()), NOW)
check('1f 目安上限の1.5倍超え: 遅れ', d['overrun'] and d['text'].endswith('・遅れ'), d['text'])
d = WM.describe(task(started_at=(NOW - timedelta(minutes=25)).isoformat(),
                     finished_at=(NOW - timedelta(minutes=3)).isoformat()), NOW)
check('1g 完了 22分（目安15〜25分）・10分は出す', d['show'] and d['text'] == '完了 22分（目安15〜25分）', d['text'])
d = WM.describe(task(finished_at=(NOW - timedelta(minutes=30)).isoformat()), NOW)
check('1h 終わって10分過ぎたら出さない', not d['show'], '')
check('1i 上限が2時間以上なら両方とも時間で', WM.fmt_range(100, 300) == '1.7〜5.0時間' and WM.fmt_min(130) == '2.2時間'
      and WM.fmt_range(150, 210) == '2.5〜3.5時間', WM.fmt_range(100, 300))

d = WM.describe(task(waiting_since=(NOW - timedelta(minutes=2)).isoformat()), NOW)
check('1j 返事待ち: 時間を止めて「返事待ち」・遅れにしない', d['waiting'] and d['text'] == '3/7・10分・返事待ち' and not d['overrun'], d['text'])
d = WM.describe(task(waiting_since=(NOW - timedelta(minutes=2)).isoformat(),
                     started_at=(NOW - timedelta(minutes=60)).isoformat()), NOW)
check('1j 返事待ちなら目安を大きく超えていても知らせない', not d['overrun'] and WM.due_notifications([d], {}, NOW - timedelta(hours=1), NOW) == [], d['text'])

# ---- 実績による補正
hist0 = [rec(1), rec(2)]
f, n, sc = WM.correction('P023', hist0)
check('2a 実績2件では補正しない', f == 1.0 and n == 0 and sc == '', f'{f} {n} {sc}')
hist3 = [rec(1, actual=30), rec(2, actual=45), rec(3, actual=22)]   # 目安の真ん中15 → 比 2.0 / 3.0 / 1.47 → 中央値 2.0
f, n, sc = WM.correction('P023', hist3)
check('2b 同じプロジェクト3件: 中央値 ×2.0', abs(f - 2.0) < 1e-6 and n == 3 and sc == 'project', f'{f} {n} {sc}')
d = WM.describe(task(steps=[{'status': 'in_progress'}] + [{'status': 'pending'}] * 4), NOW, hist3)
check('2c 目安15〜25 → 補正後 30〜50、残り＝補正後−経過12 = 18〜38', d['est_corrected'] == (30, 50) and 'あと18〜38分' in d['text'],
      f"{d['est_corrected']} {d['text']}")
check('2c 元の目安はそのまま持つ（完了表示用）', d['est'] == (15, 25), str(d['est']))
other = [rec(1, project='P011', actual=15), rec(2, project='P011', actual=15), rec(3, project='P011', actual=15)]
f, n, sc = WM.correction('P023', other)
check('2d 同じプロジェクトが無ければ全体の直近（×1.0・all）', abs(f - 1.0) < 1e-6 and sc == 'all' and n == 3, f'{f} {n} {sc}')
f, n, sc = WM.correction('P023', [rec(i, actual=0) for i in range(5)])
check('2e 1分未満の実績は数えない', n == 0, f'{f} {n}')
f, n, sc = WM.correction('P023', [rec(i, est=(1, 2), actual=20) for i in range(5)])
check('2e 目安3分未満の小さな作業も数えない', n == 0, f'{f} {n}')
f, n, sc = WM.correction('P023', [rec(i, actual=900) for i in range(3)])
check('2f 比は3.0までに収める', f == 3.0, str(f))
f, n, sc = WM.correction('P023', [rec(i, actual=1) for i in range(3)])
check('2f 比は0.5より下げない', f == 0.5, str(f))
many = [rec(i, actual=15) for i in range(1, 6)] + [rec(i, actual=60) for i in range(6, 11)]
f, n, sc = WM.correction('P023', many)
check('2g 同じプロジェクトは直近5件だけ見る（古い×1.0は捨てて×4.0→3.0に収める）', f == 3.0 and n == 5, f'{f} {n}')
# history.jsonl の読み（同じ task_id は最後の行）
tmp = tempfile.mkdtemp()
cur_p = os.path.join(tmp, 'current.json')
with open(os.path.join(tmp, 'history.jsonl'), 'w', encoding='utf-8') as fh:
    fh.write(json.dumps(rec(1, actual=5, tid='same')) + '\n')
    fh.write('こわれた行\n')
    fh.write(json.dumps(rec(2, actual=40, tid='same')) + '\n')
    fh.write(json.dumps(rec(3, actual=20)) + '\n')
h = WM.load_history(cur_p)
check('2h 同じ task_id は最後の行だけ・壊れた行は飛ばす', len(h) == 2 and {r['actual_min'] for r in h} == {40, 20}, str(h))
json.dump({'version': 1, 'tasks': {'s1': task()}}, open(cur_p, 'w', encoding='utf-8'))
items = WM.current(cur_p, NOW)
check('2i current() は history を読んで補正に使う（2件なので補正なし）', len(items) == 1 and items[0]['corr_n'] == 0, str(items[0]['corr_n']))
check('2j 無いファイル', WM.current(os.path.join(tmp, 'none', 'current.json')) == [], '')

# ---- 知らせの判断
since = NOW - timedelta(minutes=5)
notified = {}
running = WM.describe(task(), NOW)
due = WM.due_notifications([running], notified, since, NOW)
check('3a 動いている作業: 知らせなし', due == [], str(due))
late = WM.describe(task(started_at=(NOW - timedelta(minutes=40)).isoformat()), NOW)
due = WM.due_notifications([late], notified, since, NOW)
check('3b 1.5倍超え: overrun を1回', [k for k, _ in due] == ['overrun'], str(due))
due = WM.due_notifications([late], notified, since, NOW)
check('3b 2回目は出さない', due == [], str(due))
fin = WM.describe(task(started_at=(NOW - timedelta(minutes=40)).isoformat(),
                       finished_at=(NOW - timedelta(minutes=1)).isoformat()), NOW)
due = WM.due_notifications([fin], notified, since, NOW)
check('3c 終わったら finish を1回（同じ作業の overrun の後でも）', [k for k, _ in due] == ['finish'], str(due))
due = WM.due_notifications([fin], notified, since, NOW)
check('3c finish も2回目は出さない', due == [], str(due))
old = WM.describe(task(task_id='old', started_at=(NOW - timedelta(minutes=30)).isoformat(),
                       finished_at=(NOW - timedelta(minutes=8)).isoformat()), NOW)
due = WM.due_notifications([old], {}, since, NOW)
check('3d 小窓を起こす前に終わっていた作業は知らせない', due == [], str(due))
ttl, body = WM.notification_text('finish', fin)
check('3e 終了の文', ttl == '作業が終わりました' and body == 'シロ・P023 作業メーター　39分（目安15〜25分）', body)
ttl, body = WM.notification_text('overrun', late)
check('3e 超えたときの文', ttl == '目安を大きく超えています' and body == 'シロ・P023 作業メーター　40分経過（目安15〜25分）', body)
x = WM.toast_xml('a<b', 'c&d')
check('3f 通知は音なし（audio silent）・XML を壊す字は逃がす', '<audio silent="true"/>' in x and 'a&lt;b' in x and 'c&amp;d' in x, x)
np = os.path.join(tmp, 'notified.json')
WM.save_notified(np, {'t1': {'finish', 'overrun'}, 't2': {'overrun'}})
check('3g 知らせの控えを書いて読める', WM.load_notified(np) == {'t1': {'finish', 'overrun'}, 't2': {'overrun'}}, str(WM.load_notified(np)))
check('3g 無い控えは空', WM.load_notified(os.path.join(tmp, 'x.json')) == {}, '')

print()
print('RESULT:', 'ALL OK' if not fails else f'{len(fails)} failed: {fails}')
sys.exit(1 if fails else 0)
