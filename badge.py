# -*- coding: utf-8 -*-
"""AI 使用量オーバーレイ（テーマ切替対応）.
複数AIの 5時間枠・週間枠 を常時最前面の小窓で表示。API/トークン不要。
テーマ: pastel / pop / neon を設定で切替。
"""
import os, sys, json, threading, time, webbrowser
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser
import providers as P

if getattr(sys, 'frozen', False):          # PyInstaller の .exe で実行時
    BASE = os.path.dirname(sys.executable)  # 設定は exe と同じ場所に置く
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, 'badge_config.json')
KEY = '#ff00fe'  # 透明色キー（角丸のため）

DEFAULT_CFG = {
    "x": None, "y": None,
    "alpha": 0.95,
    "interval_ms": 15000,
    "scale": 1.0,
    "theme": "pop",
    "level_color": True,
    "selected": "all",
    "providers": [
        {"id": "claude",  "name": "Claude",  "type": "claude_local", "enabled": True,  "icon": "moon", "color": "#c58af9"},
        {"id": "chatgpt", "name": "ChatGPT", "type": "codex_local",  "enabled": True,  "icon": "bolt", "color": "#3fb6ff"},
        {"id": "gemini",  "name": "Gemini",  "type": "none",         "enabled": False, "icon": "hex",  "color": "#9be15d"},
    ],
}

ICON_MOTIFS = ["moon", "star", "crystal", "bolt", "hex", "wave",
               "ring", "triangle", "square", "orb", "orbit", "dots"]
PALETTE = ["#c58af9", "#3fb6ff", "#9be15d", "#ff9f43", "#4dd6c1",
           "#ff6b9d", "#ffd93d", "#7c9cff"]

THEMES = {
    "simple": {
        # 無彩色ミニマル。バーもグレー、色はアイコンだけ。角ばって密
        "card": "#ffffff", "border": "#dcdce2",
        "text": "#33333b", "label": "#9a9aa4", "foot": "#b6b6c0",
        "sel": "#4a4a54", "sp": "#adadb8", "track": "#e8e8ec", "div": "#ededf0",
        "bar_h": 5, "radius": 6, "icon_tile": False, "glow": False,
        "bar_soft": 0.0, "tint_track": False, "bar_neutral": "#9fa0ab", "row_gap": 2,
        "font": "Segoe UI", "font_num": "Consolas", "name_w": "normal",
        "dn": -1, "dv": 0, "dl": -1, "border_w": 1, "icon_bg": None,
    },
    "pastel": {
        # 淡い色付きカード＋キャンディ色。ふんわり・広め・低コントラスト
        "card": "#f0e8fb", "border": "#ddc9f2",
        "text": "#6f6389", "label": "#b3a9c8", "foot": "#c4bbd8",
        "sel": "#9a7fd8", "sp": "#c4bbd8", "track": "#e6dbf4", "div": "#e4d8f2",
        "bar_h": 11, "radius": 24, "icon_tile": False, "glow": False,
        "bar_soft": 0.34, "tint_track": True, "row_gap": 8,
        "font": "Yu Gothic UI", "font_num": "Yu Gothic UI", "name_w": "normal",
        "dn": 1, "dv": 1, "dl": 0, "border_w": 2, "icon_bg": "halo",
    },
    "pop": {
        # 各AIを色バブルの行に。タイル入りアイコン＋極太バー。元気なトイ調
        "card": "#ffffff", "border": "#ffd0e4",
        "text": "#7a5266", "label": "#b57e99", "foot": "#d3a6bd",
        "sel": "#f2569b", "sp": "#d3a6bd", "track": "#f7e4ee", "div": "#ffe6ef",
        "bar_h": 14, "radius": 22, "icon_tile": True, "glow": False,
        "bar_soft": 0.0, "tint_track": False, "row_wash": 0.90, "row_gap": 6,
        "font": "Yu Gothic UI", "font_num": "Yu Gothic UI", "name_w": "bold",
        "dn": 3, "dv": 1, "dl": 0, "border_w": 3, "icon_bg": "tile",
    },
    "neon": {
        "card": "#141320", "border": "#2c2942",
        "text": "#e8e6f5", "label": "#8b85a6", "foot": "#6a6486",
        "sel": "#b9a9ff", "sp": "#8b85a6", "track": "#221f33", "div": "#2a2740",
        "bar_h": 7, "radius": 16, "icon_tile": False, "glow": True,
        "bar_soft": 0.0, "tint_track": False,
        "font": "Segoe UI", "font_num": "Consolas", "name_w": "bold",
        "dn": 0, "dv": 0, "dl": 0, "border_w": 1, "icon_bg": None,
    },
}


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    try:
        with open(CFG, encoding='utf-8') as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if k != 'providers'})
        if isinstance(user.get('providers'), list) and user['providers']:
            cfg['providers'] = user['providers']
    except Exception:
        pass
    return cfg


def save_cfg(cfg):
    try:
        with open(CFG, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def color_for(pct, cfg, theme):
    if not cfg.get('level_color', True):
        return theme['text']
    if pct is None:
        return theme['label']
    if pct <= 10:
        return '#ff5964'
    if pct <= 30:
        return '#ff9f2e'
    if pct <= 60:
        return '#ffcf33' if cfg.get('theme') == 'neon' else '#e0a800'
    return '#33c46f'


def _h2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(c1, c2, t):
    a, b = _h2rgb(c1), _h2rgb(c2)
    return '#%02x%02x%02x' % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_icon(cv, motif, color, size, bg=None, bgcol=None):
    cv.delete('all')
    import math
    if bg == 'tile':
        rr_on(cv, 1, 1, size - 1, size - 1, max(4, size * 0.32), fill=bgcol, outline='')
        pad = size * 0.22
    elif bg == 'halo':
        cv.create_oval(1, 1, size - 1, size - 1, fill=bgcol, outline='')
        pad = size * 0.20
    else:
        pad = 0
    c = size / 2.0
    r = (size - pad * 2) * 0.34
    cut = bgcol or cv['bg']
    def poly(pts, **kw):
        cv.create_polygon(pts, **kw)
    if motif == 'moon':
        cv.create_oval(c - r, c - r, c + r, c + r, fill=color, outline='')
        cv.create_oval(c - r * 0.3, c - r, c + r * 1.7, c + r, fill=cut, outline='')
    elif motif == 'star':
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.42
            a = -math.pi / 2 + i * math.pi / 5
            pts += [c + rr * math.cos(a), c + rr * math.sin(a)]
        poly(pts, fill=color, outline='')
    elif motif == 'crystal':
        poly([c, c - r, c + r * 0.8, c, c, c + r, c - r * 0.8, c], fill=color, outline='')
    elif motif == 'bolt':
        poly([c - r * 0.2, c - r, c + r * 0.55, c - r * 0.1, c + r * 0.05, c - r * 0.1,
              c + r * 0.35, c + r, c - r * 0.55, c + r * 0.15, c - r * 0.05, c + r * 0.15],
             fill=color, outline='')
    elif motif == 'hex':
        pts = []
        for i in range(6):
            a = -math.pi / 2 + i * math.pi / 3
            pts += [c + r * math.cos(a), c + r * math.sin(a)]
        poly(pts, fill=color, outline='')
    elif motif == 'wave':
        w = max(2, int(size * 0.09))
        cv.create_arc(c - r, c - r * 0.2, c, c + r * 0.8, start=0, extent=180, style='arc', outline=color, width=w)
        cv.create_arc(c, c - r * 0.2, c + r, c + r * 0.8, start=180, extent=180, style='arc', outline=color, width=w)
    elif motif == 'ring':
        cv.create_oval(c - r, c - r, c + r, c + r, outline=color, width=max(2, int(size * 0.11)))
    elif motif == 'triangle':
        pts = []
        for i in range(3):
            a = -math.pi / 2 + i * 2 * math.pi / 3
            pts += [c + r * math.cos(a), c + r * math.sin(a)]
        poly(pts, fill=color, outline='')
    elif motif == 'square':
        rr_on(cv, c - r * 0.85, c - r * 0.85, c + r * 0.85, c + r * 0.85, r * 0.35, fill=color, outline='')
    elif motif == 'orb':
        cv.create_oval(c - r, c - r, c + r, c + r, fill=color, outline='')
        cv.create_oval(c - r * 0.4, c - r * 0.6, c, c - r * 0.2, fill='#ffffff', outline='')
    elif motif == 'orbit':
        cv.create_oval(c - r * 0.32, c - r * 0.32, c + r * 0.32, c + r * 0.32, fill=color, outline='')
        cv.create_oval(c - r, c - r * 0.42, c + r, c + r * 0.42, outline=color, width=max(2, int(size * 0.07)))
    elif motif == 'dots':
        d = r * 0.32
        for dx, dy in [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)]:
            x, y = c + dx * r * 0.62, c + dy * r * 0.62
            cv.create_oval(x - d, y - d, x + d, y + d, fill=color, outline='')
    else:
        cv.create_oval(c - r, c - r, c + r, c + r, fill=color, outline='')


def rr_on(cv, x0, y0, x1, y1, rad, **kw):
    """Canvas に角丸矩形を描く。"""
    rad = min(rad, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = [x0 + rad, y0, x1 - rad, y0, x1, y0, x1, y0 + rad, x1, y1 - rad, x1, y1,
           x1 - rad, y1, x0 + rad, y1, x0, y1, x0, y1 - rad, x0, y0 + rad, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


def draw_bar(cv, w, h, pct, color, track, glow=False):
    cv.delete('all')
    rr_on(cv, 1, 1, w - 1, h - 1, h / 2, fill=track, outline='')
    if pct is None:
        return
    fw = max(h, (min(100, max(0, pct)) / 100.0) * (w - 2)) + 1
    if glow:
        rr_on(cv, 1, 1, fw, h - 1, h / 2, fill=blend(color, '#000000', 0.25), outline='')
    rr_on(cv, 1, 1, fw, h - 1, h / 2, fill=color, outline='')


def draw_clock(cv, size, color):
    """小さな時計マーク（円＋針）。"""
    cv.delete('all')
    c = size / 2.0
    r = size * 0.42
    wd = max(1, int(size * 0.09))
    cv.create_oval(c - r, c - r, c + r, c + r, outline=color, width=wd)
    cv.create_line(c, c, c, c - r * 0.55, fill=color, width=wd)
    cv.create_line(c, c, c + r * 0.45, c + r * 0.18, fill=color, width=wd)


def single_instance():
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, 'AIUsageOverlay_Mutex_v2')
    return ctypes.windll.kernel32.GetLastError() != 183


def fmt_reset(ts):
    if not ts:
        return ''
    left = ts - time.time()
    if left <= 0:
        return 'まもなくリセット'
    h = int(left // 3600); m = int((left % 3600) // 60)
    if h >= 24:
        return '%d日後' % (h // 24)
    return '%dh%02dm後' % (h, m)


class Overlay:
    def __init__(self):
        self.cfg = load_cfg()
        self.root = tk.Tk()
        self.root.title('AI使用量')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        try:
            self.root.attributes('-alpha', float(self.cfg['alpha']))
        except Exception:
            pass
        try:
            self.root.wm_attributes('-transparentcolor', KEY)
        except Exception:
            pass
        self.root.configure(bg=KEY)
        self.cv = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack()
        self.content = None
        self._winid = None
        self._drag = None
        self.tray = None
        self.build()
        self.refresh()
        self.root.after(int(self.cfg['interval_ms']), self.tick)
        self.start_tray()

    def theme(self):
        return THEMES.get(self.cfg.get('theme', 'pop'), THEMES['pop'])

    # ---------- 描画 ----------
    def build(self):
        T = self.theme()
        if self.content:
            self.cv.delete('all')
            self.content.destroy()
            self._winid = None
        s = float(self.cfg.get('scale', 1.0))
        fam = T.get('font', 'Yu Gothic UI')
        num = T.get('font_num', fam)
        dn, dv, dl = T.get('dn', 0), T.get('dv', 0), T.get('dl', 0)
        self.f_label = tkfont.Font(family=fam, size=max(7, int((9 + dl) * s)))
        self.f_val = tkfont.Font(family=num, size=max(8, int((11 + dv) * s)), weight='bold')
        self.f_small = tkfont.Font(family=fam, size=max(6, int(7 * s)))
        self.f_name = tkfont.Font(family=fam, size=max(8, int((10 + dn) * s)), weight=T.get('name_w', 'bold'))
        self.f_sel = tkfont.Font(family=fam, size=max(8, int(10 * s)), weight='bold')

        self.content = tk.Frame(self.cv, bg=T['card'])
        pad = int(9 * s)
        inner = tk.Frame(self.content, bg=T['card'])
        inner.pack(padx=pad, pady=int(6 * s))

        head = tk.Frame(inner, bg=T['card'])
        head.pack(fill='x')
        self.sel_var = tk.StringVar(value=self.selected_label())
        self.menu_btn = tk.Menubutton(head, textvariable=self.sel_var, bg=T['card'], fg=T['sel'],
                                      activebackground=T['card'], activeforeground=T['sel'],
                                      font=self.f_sel, relief='flat', bd=0, padx=0)
        m = tk.Menu(self.menu_btn, tearoff=0, bg=T['card'], fg=T['text'],
                    activebackground=T['sel'], activeforeground=T['card'])
        for label in ['すべて'] + [p['name'] for p in self.enabled_providers()]:
            m.add_command(label=label, command=lambda l=label: self.on_select(l))
        self.menu_btn.config(menu=m)
        self.menu_btn.pack(side='left')
        tk.Label(head, text=' ▾', bg=T['card'], fg=T['sp'], font=self.f_small).pack(side='left')

        cl = tk.Label(head, text='✕', bg=T['card'], fg=T['sp'], font=self.f_label, cursor='hand2')
        cl.pack(side='right'); cl.bind('<Button-1>', lambda e: self.hide_to_tray())
        st = tk.Label(head, text='⚙', bg=T['card'], fg=T['sp'], font=self.f_label, cursor='hand2')
        st.pack(side='right', padx=(0, int(6 * s))); st.bind('<Button-1>', lambda e: self.open_settings())
        self.refresh_btn = tk.Label(head, text='↻ 更新', bg=T['card'], fg=T['sel'],
                                    font=self.f_label, cursor='hand2')
        self.refresh_btn.pack(side='right', padx=(0, int(7 * s)))
        self.refresh_btn.bind('<Button-1>', lambda e: self.manual_refresh())

        self.body = tk.Frame(inner, bg=T['card'])
        self.body.pack(fill='x')
        self.foot = tk.Label(inner, text='', bg=T['card'], fg=T['foot'], font=self.f_small, anchor='w')
        self.foot.pack(fill='x', pady=(int(3 * s), 0))

        self.rows = {}
        self.build_rows()
        self.fit()
        self._bind_drag_tree(self.content)
        self.cv.bind('<Button-1>', self.start_move, add='+')
        self.cv.bind('<B1-Motion>', self.on_move, add='+')
        self.cv.bind('<ButtonRelease-1>', self.end_move, add='+')
        self.cv.bind('<Button-3>', self.popup, add='+')

    def build_rows(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.rows = {}
        T = self.theme()
        s = float(self.cfg.get('scale', 1.0))
        ibg = T.get('icon_bg')
        isz = int((30 if ibg else 24) * s)
        barw = int(66 * s); barh = int(T['bar_h'] * s)
        wash = T.get('row_wash')
        gap = int(T.get('row_gap', 3) * s)
        clk = int(13 * s)
        shown = self.shown_providers()
        for idx, p in enumerate(shown):
            pc = p.get('color', '#c58af9')
            rbg = blend(pc, T['card'], wash) if wash else T['card']
            ip = int(5 * s) if wash else 0
            if idx > 0 and not wash:
                dv = tk.Frame(self.body, bg=T['div'], height=1)
                dv.pack(fill='x', pady=int(4 * s))
            blk = tk.Frame(self.body, bg=rbg)
            blk.pack(fill='x', pady=(gap, 0), ipady=ip, ipadx=ip)
            if ibg == 'tile':
                bgcol = '#ffffff' if wash else blend(pc, T['card'], 0.82)
            elif ibg == 'halo':
                bgcol = blend(pc, T['card'], 0.58)
            else:
                bgcol = None
            icv = tk.Canvas(blk, width=isz, height=isz, bg=rbg, highlightthickness=0, bd=0)
            icv.grid(row=0, column=0, rowspan=2, padx=(0, int(8 * s)), sticky='n', pady=(int(2 * s), 0))
            draw_icon(icv, p.get('icon', 'ring'), pc, isz, bg=ibg, bgcol=bgcol)
            nm = tk.Label(blk, text=p['name'], bg=rbg, fg=pc, font=self.f_name)
            nm.grid(row=0, column=1, sticky='w')
            ccv = tk.Canvas(blk, width=clk, height=clk, bg=rbg, highlightthickness=0, bd=0, cursor='hand2')
            ccv.grid(row=0, column=2, sticky='w', padx=(int(5 * s), 0))
            draw_clock(ccv, clk, T['label'])
            ccv.bind('<Button-1>', lambda e, pid=p['id']: self.provider_action(pid))
            grid = tk.Frame(blk, bg=rbg)
            grid.grid(row=1, column=1, columnspan=2, sticky='w')
            bars = {}
            for j, (lab, kk) in enumerate([('5時間残り', 'v5'), ('週間残り', 'vw')]):
                tk.Label(grid, text=lab, bg=rbg, fg=T['label'], font=self.f_label
                         ).grid(row=j, column=0, sticky='w', padx=(0, int(7 * s)))
                bc = tk.Canvas(grid, width=barw, height=barh, bg=rbg, highlightthickness=0, bd=0)
                bc.grid(row=j, column=1, pady=int(2 * s))
                pl = tk.Label(grid, text='--', bg=rbg, font=self.f_val, width=4, anchor='e')
                pl.grid(row=j, column=2, sticky='e', padx=(int(7 * s), 0))
                pl.bind('<Button-1>', lambda e, pid=p['id']: self.open_provider_url(pid))
                bars[kk] = (bc, pl)
            nm.bind('<Button-1>', lambda e, pid=p['id']: self.open_provider_url(pid))
            self.rows[p['id']] = {'nm': nm, 'clock': ccv, 'bars': bars, 'color': pc, 'rbg': rbg,
                                  'reset5': None, 'resetw': None, 'ptype': p['type'], 'url': None}

    def _bind_drag_tree(self, w):
        w.bind('<Button-1>', self.start_move, add='+')
        w.bind('<B1-Motion>', self.on_move, add='+')
        w.bind('<ButtonRelease-1>', self.end_move, add='+')
        w.bind('<Button-3>', self.popup, add='+')
        for c in w.winfo_children():
            self._bind_drag_tree(c)

    def fit(self):
        T = self.theme()
        self.content.update_idletasks()
        w = self.content.winfo_reqwidth(); h = self.content.winfo_reqheight()
        R = int(T['radius']); M = R
        W, H = w + 2 * M, h + 2 * M
        self.cv.config(width=W, height=H)
        self.cv.delete('bg')
        bw = int(T.get('border_w', 1))
        rr_on(self.cv, bw, bw, W - bw, H - bw, R, fill=T['card'], outline=T['border'], width=bw, tags='bg')
        if self._winid is None:
            self._winid = self.cv.create_window(M, M, window=self.content, anchor='nw')
        else:
            self.cv.coords(self._winid, M, M)
        self.cv.tag_lower('bg')
        self.place_window(W, H)

    def place_window(self, W, H):
        x, y = self.cfg.get('x'), self.cfg.get('y')
        if x is None or y is None:
            sh = self.root.winfo_screenheight()
            x = 14; y = sh - H - 60
        self.cfg['x'], self.cfg['y'] = int(x), int(y)
        self.root.geometry('%dx%d+%d+%d' % (W, H, int(x), int(y)))

    # ---------- providers / selection ----------
    def enabled_providers(self):
        return [p for p in self.cfg['providers'] if p.get('enabled')]

    def shown_providers(self):
        sel = self.cfg.get('selected', 'all')
        eps = self.enabled_providers()
        if sel == 'all':
            return eps
        got = [p for p in eps if p['id'] == sel]
        return got if got else eps

    def selected_label(self):
        sel = self.cfg.get('selected', 'all')
        if sel == 'all':
            return 'すべて'
        for p in self.cfg['providers']:
            if p['id'] == sel:
                return p['name']
        return 'すべて'

    def on_select(self, label):
        if label == 'すべて':
            self.cfg['selected'] = 'all'
        else:
            for p in self.cfg['providers']:
                if p['name'] == label:
                    self.cfg['selected'] = p['id']; break
        self.sel_var.set(label)
        save_cfg(self.cfg)
        self.build_rows(); self.fit(); self.refresh()
        self._bind_drag_tree(self.content)

    # ---------- move ----------
    def start_move(self, e):
        self._drag = (e.x_root, e.y_root, int(self.cfg['x']), int(self.cfg['y']))

    def on_move(self, e):
        if not self._drag:
            return
        x0, y0, wx, wy = self._drag
        nx, ny = wx + (e.x_root - x0), wy + (e.y_root - y0)
        self.root.geometry('+%d+%d' % (nx, ny))
        self.cfg['x'], self.cfg['y'] = nx, ny

    def end_move(self, e):
        if self._drag:
            self._drag = None
            save_cfg(self.cfg)

    def popup(self, e):
        T = self.theme()
        menu = tk.Menu(self.root, tearoff=0, bg=T['card'], fg=T['text'],
                       activebackground=T['sel'], activeforeground=T['card'])
        menu.add_command(label='今すぐ更新', command=self.refresh)
        menu.add_command(label='設定…', command=self.open_settings)
        menu.add_separator()
        menu.add_command(label='トレイに格納', command=self.hide_to_tray)
        menu.add_command(label='終了', command=self.quit)
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def open_provider_url(self, pid):
        row = self.rows.get(pid)
        url = row.get('url') if row else None
        if not url:
            return
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass

    def provider_action(self, pid):
        row = self.rows.get(pid)
        if row and row.get('url'):
            self.open_provider_url(pid)
        else:
            self.show_reset(pid)

    # ---------- data ----------
    def refresh(self):
        T = self.theme()
        s = float(self.cfg.get('scale', 1.0))
        barw = int(66 * s); barh = int(T['bar_h'] * s)
        soft = T.get('bar_soft', 0.0)
        tint = T.get('tint_track', False)
        wash = T.get('row_wash')
        neutral = T.get('bar_neutral')
        newest = 0
        for p in self.shown_providers():
            row = self.rows.get(p['id'])
            if not row:
                continue
            pc = row['color']
            if neutral:
                fill = neutral
            elif soft:
                fill = blend(pc, '#ffffff', soft)
            else:
                fill = pc
            if wash:
                track = blend(pc, '#ffffff', 0.60)
            elif tint:
                track = blend(pc, T['card'], 0.85)
            else:
                track = T['track']
            r = P.read_provider(p['type'])
            row['stale'] = bool(r.get('stale'))
            row['reset5'] = r.get('reset_five')
            row['resetw'] = r.get('reset_week')
            row['url'] = r.get('url')
            if not r['ok']:
                row['nm'].config(text=p['name'] + '（' + r.get('note', '') + '）')
                for kk in ('v5', 'vw'):
                    bc, pl = row['bars'][kk]
                    draw_bar(bc, barw, barh, None, fill, track, T['glow'])
                    if row['url']:
                        pl.config(text='開く', fg=pc, cursor='hand2')
                        row['nm'].config(cursor='hand2')
                    else:
                        pl.config(text='—', fg=T['label'], cursor='')
                        row['nm'].config(cursor='')
                continue
            shown_name = p['name'] + ('（更新待ち）' if row['stale'] else '')
            row['nm'].config(text=shown_name, cursor='')
            for kk, used in (('v5', r['five']), ('vw', r['week'])):
                bc, pl = row['bars'][kk]
                remaining = (max(0, min(100, 100 - used))
                             if isinstance(used, (int, float)) else None)
                draw_bar(bc, barw, barh, remaining, fill, track, T['glow'])
                pl.config(text=(('%d%%' % remaining) if remaining is not None else '—'),
                          fg=color_for(remaining, self.cfg, T), cursor='')
            newest = max(newest, r.get('t', 0))
        if newest:
            age = int((time.time() * 1000 - newest) / 60000)
            self.foot.config(text='%d分前に更新' % max(0, age))
        else:
            self.foot.config(text='')

    def tick(self):
        self.refresh()
        self.root.after(int(self.cfg['interval_ms']), self.tick)

    def manual_refresh(self):
        """画面上の更新ボタンから、待ち時間なしで再読み込みする。"""
        try:
            self.refresh_btn.config(text='↻ 更新中…')
            self.root.update_idletasks()
            self.refresh()
            claude = self.rows.get('claude')
            if claude and claude.get('stale'):
                if P.launch_claude_desktop():
                    self.refresh_btn.config(text='Claude更新中…')
                    self.root.after(1000, lambda: self._poll_claude_refresh(0))
                else:
                    self.refresh_btn.config(text='Claudeを開いて')
                return
            self.refresh_btn.config(text='✓ 更新済み')
            self.root.after(1400, lambda: self.refresh_btn.config(text='↻ 更新'))
        except Exception:
            self.refresh_btn.config(text='↻ 再試行')

    def _poll_claude_refresh(self, attempt):
        """Claude起動後、公式ファイルが新しくなるまで短時間だけ待つ。"""
        self.refresh()
        claude = self.rows.get('claude')
        if not claude or not claude.get('stale'):
            self.refresh_btn.config(text='✓ 更新済み')
            self.root.after(1400, lambda: self.refresh_btn.config(text='↻ 更新'))
        elif attempt < 29:
            self.root.after(1000, lambda: self._poll_claude_refresh(attempt + 1))
        else:
            self.refresh_btn.config(text='Claudeを開いて')

    # ---------- tray ----------
    def start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            self.tray = None; return

        def make_image():
            img = Image.new('RGB', (64, 64), (21, 23, 27))
            d = ImageDraw.Draw(img)
            d.ellipse((12, 12, 52, 52), fill=(197, 138, 249))
            return img

        menu = pystray.Menu(
            pystray.MenuItem('表示', self._tray_show, default=True),
            pystray.MenuItem('今すぐ更新', lambda i, it: self.root.after(0, self.refresh)),
            pystray.MenuItem('設定', lambda i, it: self.root.after(0, self.open_settings)),
            pystray.MenuItem('終了', self._tray_quit),
        )
        self.tray = pystray.Icon('ai_usage', make_image(), 'AI使用量オーバーレイ', menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self.show_window)

    def _tray_quit(self, icon=None, item=None):
        self.root.after(0, self.quit)

    def show_window(self):
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self.refresh()

    def hide_to_tray(self):
        self.root.withdraw()

    def quit(self):
        save_cfg(self.cfg)
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

    # ---------- 設定 ----------
    def open_settings(self):
        if getattr(self, '_settings', None) and tk.Toplevel.winfo_exists(self._settings):
            self._settings.lift(); return
        T = self.theme()
        w = tk.Toplevel(self.root); self._settings = w
        w.title('設定'); w.configure(bg=T['card']); w.attributes('-topmost', True); w.resizable(False, False)
        fnt = ('Yu Gothic UI', 10)
        FG = T['text']

        def header(t, r):
            tk.Label(w, text=t, bg=T['card'], fg=T['sel'], font=('Yu Gothic UI', 10, 'bold')
                     ).grid(row=r, column=0, columnspan=4, sticky='w', padx=10, pady=(12, 2))

        header('テーマ', 0)
        self._sv_theme = tk.StringVar(value=self.cfg.get('theme', 'pop'))
        tf = tk.Frame(w, bg=T['card']); tf.grid(row=1, column=0, columnspan=4, sticky='w', padx=16)
        for val, lab in [('simple', 'シンプル'), ('pastel', 'パステル'), ('pop', 'ポップ'), ('neon', 'ネオン')]:
            tk.Radiobutton(tf, text=lab, variable=self._sv_theme, value=val, bg=T['card'], fg=FG,
                           selectcolor=T['track'], activebackground=T['card'], activeforeground=FG,
                           font=fnt, command=self._live_theme).pack(side='left', padx=(0, 8))

        header('表示するAI（名前は変更可）', 2)
        self._sv_enabled = {}; self._nv = {}; self._pcolors = {}; self._csw = {}
        r = 3
        for p in self.cfg['providers']:
            var = tk.BooleanVar(value=bool(p.get('enabled')))
            self._sv_enabled[p['id']] = var
            tk.Checkbutton(w, variable=var, bg=T['card'], activebackground=T['card'],
                           selectcolor=T['track']).grid(row=r, column=0, sticky='w', padx=(16, 0))
            nv = tk.StringVar(value=p['name']); self._nv[p['id']] = nv
            tk.Entry(w, textvariable=nv, width=13, bg=T['track'], fg=FG, insertbackground=FG,
                     relief='flat', font=fnt).grid(row=r, column=1, sticky='w')
            self._pcolors[p['id']] = p.get('color', '#c58af9')
            sw = tk.Label(w, text='  ', bg=p.get('color', '#c58af9'), relief='solid', bd=1, cursor='hand2')
            sw.grid(row=r, column=2, sticky='w', padx=6)
            sw.bind('<Button-1>', lambda e, pid=p['id']: self._pick_pc(pid))
            self._csw[p['id']] = sw
            if p['type'] == 'none':
                tk.Label(w, text='源なし', bg=T['card'], fg=T['label'], font=('Yu Gothic UI', 8)
                         ).grid(row=r, column=3, sticky='w')
            r += 1

        header('表示モード', r); r += 1
        self._sv_mode = tk.StringVar(value=('all' if self.cfg.get('selected') == 'all' else 'single'))
        tk.Radiobutton(w, text='全部表示', variable=self._sv_mode, value='all', bg=T['card'], fg=FG,
                       selectcolor=T['track'], activebackground=T['card'], font=fnt
                       ).grid(row=r, column=0, columnspan=2, sticky='w', padx=16); r += 1
        tk.Radiobutton(w, text='選んだ1つだけ', variable=self._sv_mode, value='single', bg=T['card'], fg=FG,
                       selectcolor=T['track'], activebackground=T['card'], font=fnt
                       ).grid(row=r, column=0, columnspan=2, sticky='w', padx=16); r += 1

        header('見た目', r); r += 1
        self._sv_level = tk.BooleanVar(value=bool(self.cfg.get('level_color', True)))
        tk.Checkbutton(w, text='残り%で数値を色分け', variable=self._sv_level, bg=T['card'], fg=FG,
                       selectcolor=T['track'], activebackground=T['card'], font=fnt
                       ).grid(row=r, column=0, columnspan=4, sticky='w', padx=16); r += 1
        tk.Label(w, text='不透明度', bg=T['card'], fg=FG, font=fnt).grid(row=r, column=0, sticky='w', padx=16)
        self._sc_alpha = tk.Scale(w, from_=30, to=100, orient='horizontal', bg=T['card'], fg=FG,
                                  highlightthickness=0, troughcolor=T['track'], length=150)
        self._sc_alpha.set(int(float(self.cfg.get('alpha', 0.95)) * 100))
        self._sc_alpha.grid(row=r, column=1, columnspan=3, sticky='w'); r += 1
        tk.Label(w, text='サイズ', bg=T['card'], fg=FG, font=fnt).grid(row=r, column=0, sticky='w', padx=16)
        self._sc_scale = tk.Scale(w, from_=80, to=200, orient='horizontal', bg=T['card'], fg=FG,
                                  highlightthickness=0, troughcolor=T['track'], length=150)
        self._sc_scale.set(int(float(self.cfg.get('scale', 1.0)) * 100))
        self._sc_scale.grid(row=r, column=1, columnspan=3, sticky='w'); r += 1
        tk.Label(w, text='更新間隔(秒)', bg=T['card'], fg=FG, font=fnt).grid(row=r, column=0, sticky='w', padx=16)
        self._sc_int = tk.Scale(w, from_=15, to=300, orient='horizontal', bg=T['card'], fg=FG,
                                highlightthickness=0, troughcolor=T['track'], length=150)
        self._sc_int.set(int(int(self.cfg.get('interval_ms', 15000)) / 1000))
        self._sc_int.grid(row=r, column=1, columnspan=3, sticky='w'); r += 1

        tk.Button(w, text='適用して閉じる', command=self._apply, bg=T['sel'], fg=T['card'],
                  font=('Yu Gothic UI', 10, 'bold'), relief='flat'
                  ).grid(row=r, column=0, columnspan=4, pady=12, padx=16, sticky='we')

    def show_reset(self, pid):
        """時計マーク: 5時間枠/週間枠の回復までを表示。"""
        row = self.rows.get(pid)
        if not row:
            return
        T = self.theme()
        name = next((p['name'] for p in self.cfg['providers'] if p['id'] == pid), '')
        pt = row.get('ptype')

        def line(lbl, ts, five):
            if ts:
                return '%s: %s' % (lbl, fmt_reset(ts))
            if pt == 'claude_local':
                return '%s: 目安%s（時刻は非公開）' % (lbl, '5時間サイクル' if five else '週次')
            return '%s: 回復時刻 不明' % lbl

        m = tk.Menu(self.root, tearoff=0, bg=T['card'], fg=T['text'],
                    activebackground=T['sel'], activeforeground=T['card'])
        m.add_command(label='%s の回復まで' % name, state='disabled')
        m.add_separator()
        m.add_command(label=line('5時間枠', row.get('reset5'), True), state='disabled')
        m.add_command(label=line('週間枠', row.get('resetw'), False), state='disabled')
        px, py = self.root.winfo_pointerxy()
        try:
            m.tk_popup(px, py)
        finally:
            m.grab_release()

    def _live_theme(self):
        """テーマを選んだ瞬間にオーバーレイへ反映（適用ボタン不要）。"""
        self.cfg['theme'] = self._sv_theme.get()
        save_cfg(self.cfg)
        self.build(); self.refresh()
        try:
            self._settings.lift()
            self._settings.attributes('-topmost', True)
        except Exception:
            pass

    def _pick_pc(self, pid):
        c = colorchooser.askcolor(color=self._pcolors.get(pid), parent=self._settings)[1]
        if c:
            self._pcolors[pid] = c; self._csw[pid].config(bg=c)

    def _apply(self):
        self.cfg['theme'] = self._sv_theme.get()
        for p in self.cfg['providers']:
            p['enabled'] = bool(self._sv_enabled[p['id']].get())
            nm = self._nv[p['id']].get().strip()
            if nm:
                p['name'] = nm
            p['color'] = self._pcolors.get(p['id'], p.get('color'))
        if self._sv_mode.get() == 'all':
            self.cfg['selected'] = 'all'
        elif self.cfg.get('selected', 'all') == 'all':
            eps = self.enabled_providers()
            self.cfg['selected'] = eps[0]['id'] if eps else 'all'
        self.cfg['level_color'] = bool(self._sv_level.get())
        self.cfg['alpha'] = self._sc_alpha.get() / 100.0
        self.cfg['scale'] = self._sc_scale.get() / 100.0
        self.cfg['interval_ms'] = int(self._sc_int.get()) * 1000
        save_cfg(self.cfg)
        try:
            self.root.attributes('-alpha', float(self.cfg['alpha']))
        except Exception:
            pass
        self.build(); self.refresh()
        try:
            self._settings.destroy()
        except Exception:
            pass


if __name__ == '__main__':
    if not single_instance():
        raise SystemExit(0)
    Overlay().run()
