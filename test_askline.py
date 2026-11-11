# -*- coding: utf-8 -*-
"""askline.py の机上テスト（tkinter なし）。python test_askline.py
フック側 C:\\AI\\ProgressHooks\\ask_line.py があれば、小窓が書いた形をフックが同じに読むかも確かめる。"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import askline as AL  # noqa: E402

fails = []


def check(name, cond, detail=''):
    print(('OK  ' if cond else 'NG  ') + name + ('' if cond else f'  <- {detail}'))
    if not cond:
        fails.append(name)


TMP = tempfile.mkdtemp(prefix='askline_test_')
F = os.path.join(TMP, 'ask_line.json')
NOW = datetime(2026, 11, 11, 10, 50, 0)

check('a 何も無ければ 5分・聞く', AL.state(F, NOW) == (5, False))
check('b ＋で 10分', AL.bump(+1, F, NOW) == (10, False) and AL.state(F, NOW) == (10, False))
for _ in range(4):
    AL.bump(+1, F, NOW)
check('b ＋を続けて 1時間', AL.state(F, NOW) == (60, False), str(AL.state(F, NOW)))
for _ in range(10):
    AL.bump(+1, F, NOW)
check('b 上は 3時間で止まる', AL.state(F, NOW) == (180, False))
AL.bump(-1, F, NOW)
check('c －で 2時間', AL.state(F, NOW) == (120, False))
check('c 段の間の値は近い段へ', AL.step(20, +1) == 30 and AL.step(20, -1) == 15 and AL.step(5, -1) == 5)
check('d 聞かないを押すと印が付き、時間は残る', AL.toggle_no_ask(F, NOW) == (120, True))
AL.bump(-1, F, NOW)
check('d 聞かないのまま時間を動かせる', AL.state(F, NOW) == (90, True))
check('d もう一度押すと外れて 1時間半に戻る', AL.toggle_no_ask(F, NOW) == (90, False))
check('e 時間を押すとふだんの 5分 に戻る', AL.reset(F, NOW) == (5, False))
AL.bump(+1, F, NOW)
check('f 日付が変わったらふだんの線', AL.state(F, NOW + timedelta(days=1)) == (5, False))
d = AL.load(F)
d['default'] = 10
AL.save(d, F)
check('f ふだんを 10分 にしてあれば、翌日は 10分', AL.state(F, NOW + timedelta(days=1)) == (10, False))
check('g 表示', AL.fmt(5) == '5分' and AL.fmt(60) == '1時間' and AL.fmt(90) == '1.5時間' and AL.fmt(180) == '3時間')
open(F, 'w', encoding='utf-8').write('{壊れ')
check('h 壊れたファイルでも 5分 で動き、押せば直る', AL.state(F, NOW) == (5, False) and AL.bump(+1, F, NOW) == (10, False))

# フック側と同じに読めるか
HOOK_DIR = r'C:\AI\ProgressHooks'
if os.path.isfile(os.path.join(HOOK_DIR, 'ask_line.py')):
    sys.path.insert(0, HOOK_DIR)
    import ask_line as HL  # noqa: E402
    D = os.path.join(TMP, 'hook')
    HF = os.path.join(D, 'ask_line.json')
    T0 = datetime(2026, 11, 11, 10, 0, 0)
    HL.on_stop(D, 'chatA', '聞く線を変更：30分（このチャット）', now=T0)
    AL.bump(+1, HF, T0 + timedelta(minutes=1))   # 5 → 10
    check('i 小窓を押すと、前に決めたこのチャットの分より小窓が勝つ', HL.current(D, 'chatA', now=T0) == (10, 'today'), str(AL.load(HF)))
    AL.toggle_no_ask(HF, T0 + timedelta(minutes=2))
    check('i 小窓の聞かないをフックは「聞かない」と読む', HL.current(D, 'chatB', now=T0)[0] == HL.NO_ASK and HL.current_text(D, 'chatB', now=T0)[0] == '聞かない（今日だけ）')
    HL.on_stop(D, 'chatA', '聞く線を変更：45分（このチャット）', now=T0 + timedelta(minutes=3))
    check('i 小窓より後にチャットで決めた分は勝つ', HL.current(D, 'chatA', now=T0) == (45, 'chat'))
    HL.on_stop(D, 'chatB', '聞く線を変更：2時間（今日）', now=T0 + timedelta(minutes=4))
    check('i チャットの「今日」を小窓が読む', AL.state(HF, T0) == (120, False), str(AL.load(HF)))
else:
    print('--  フック側が無いので i は飛ばす')

print('RESULT:', 'ALL OK' if not fails else f'{len(fails)} failed: {fails}')
