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
check('f 2026-11-24 日付が変わっても押した線（10分）のまま', AL.state(F, NOW + timedelta(days=1)) == (10, False), str(AL.load(F)))
AL.toggle_no_ask(F, NOW)
check('f 聞かないも翌日以降に残る', AL.state(F, NOW + timedelta(days=5)) == (10, True))
check('f トレイの文字', AL.tooltip(F, NOW) == '聞く線：聞かない', AL.tooltip(F, NOW))
check('f 時間を押すと 5分 に戻り、聞かないも外れる', AL.reset(F, NOW) == (5, False) and AL.state(F, NOW + timedelta(days=1)) == (5, False))
check('g 表示', AL.fmt(5) == '5分' and AL.fmt(60) == '1時間' and AL.fmt(90) == '1.5時間' and AL.fmt(180) == '3時間')
open(F, 'w', encoding='utf-8').write('{壊れ')
check('h 壊れたファイルでも 5分 で動き、押せば直る', AL.state(F, NOW) == (5, False) and AL.bump(+1, F, NOW) == (10, False))

# チャットで「今日」と決めた分（フックが書く today）は今日だけ勝ち、翌日は小窓の線に戻る
os.remove(F)
AL.bump(+1, F, NOW)                                 # ずっと 10分
d = AL.load(F); d['today'] = {'date': NOW.strftime('%Y-%m-%d'), 'min': 60, 'no_ask': False, 'set': NOW.isoformat()}; AL.save(d, F)
check('j チャットの今日の分は今日だけ', AL.state(F, NOW) == (60, False) and AL.state(F, NOW + timedelta(days=1)) == (10, False))
check('j トレイの文字（今日だけ）', AL.tooltip(F, NOW) == '聞く線：1時間（今日だけ）', AL.tooltip(F, NOW))
AL.bump(+1, F, NOW)
check('j 小窓を押すと（見えている1時間から＋で1.5時間）、今日の分は消えて押した線がずっと残る', AL.state(F, NOW) == (90, False) and 'today' not in AL.load(F) and AL.state(F, NOW + timedelta(days=2)) == (90, False), str(AL.load(F)))

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
    check('i 小窓を押すと、前に決めたこのチャットの分より小窓が勝つ', HL.current(D, 'chatA', now=T0) == (10, 'default'), str(AL.load(HF)))
    AL.toggle_no_ask(HF, T0 + timedelta(minutes=2))
    check('i 小窓の聞かないをフックは「聞かない」と読む', HL.current(D, 'chatB', now=T0)[0] == HL.NO_ASK and HL.current_text(D, 'chatB', now=T0)[0] == '聞かない（ずっと）')
    HL.on_stop(D, 'chatA', '聞く線を変更：45分（このチャット）', now=T0 + timedelta(minutes=3))
    check('i 小窓より後にチャットで決めた分は勝つ', HL.current(D, 'chatA', now=T0) == (45, 'chat'))
    HL.on_stop(D, 'chatB', '聞く線を変更：2時間（今日）', now=T0 + timedelta(minutes=4))
    check('i チャットの「今日」を小窓が読む', AL.state(HF, T0) == (120, False), str(AL.load(HF)))
    # ずっと（2026-11-19）
    T1 = T0 + timedelta(minutes=10)
    AL.bump(-1, HF, T1)                                # ずっと 90分
    NEXT = T0 + timedelta(days=1)
    check('k 小窓の「ずっと」をフックは翌日も読む', HL.current_text(D, 'chatB', now=NEXT) == ('1.5時間（ずっと）', 90), str(HL.current_text(D, 'chatB', now=NEXT)))
    AL.toggle_no_ask(HF, T1)
    check('k 小窓の「聞かない（ずっと）」をフックは翌日も聞かないと読む', HL.current_text(D, 'chatB', now=NEXT) == ('聞かない（ずっと）', HL.NO_ASK))
    check('k 小窓をずっとで押すと、前に決めたこのチャットの分より小窓が勝つ', HL.current(D, 'chatA', now=NEXT) == (HL.NO_ASK, 'default'))
    HL.on_stop(D, 'chatC', '聞く線を変更：10分（ずっと）', now=T1 + timedelta(minutes=1))
    check('k チャットの「ずっと」を小窓が読む（聞かないも外れる）', AL.state(HF, NEXT) == (10, False), str(AL.load(HF)))
    AL.reset(HF, T1 + timedelta(minutes=2))
    check('k ずっとで時間を押すとフックも「5分（ふだん）」', HL.current_text(D, 'chatB', now=NEXT) == ('5分（ふだん）', 5))
else:
    print('--  フック側が無いので i は飛ばす')

print('RESULT:', 'ALL OK' if not fails else f'{len(fails)} failed: {fails}')
