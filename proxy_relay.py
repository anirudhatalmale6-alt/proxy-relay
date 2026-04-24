"""
ProxyRotator v5.0 - Instant Proxy Rotation for AdsPower
Auto-detects open profiles. Rotate via API - no relay, no restart.
Place proxies.txt next to this .exe (format: host:port:user:pass)
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import json
import os
import sys
import random
import time

try:
    import urllib.request
    import urllib.error
    import urllib.parse
except ImportError:
    pass

VERSION = "5.0"
API_BASE = "http://127.0.0.1:50325"
CONFIG_FILE = "proxyrotator.json"


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_proxies_path():
    return os.path.join(get_app_dir(), 'proxies.txt')


def get_config_path():
    return os.path.join(get_app_dir(), CONFIG_FILE)


def load_config():
    path = get_config_path()
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(cfg):
    path = get_config_path()
    try:
        with open(path, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f'Error saving config: {e}')


def load_proxies_from_file(filepath):
    proxies = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(':')
                if len(parts) >= 4:
                    proxies.append({
                        'host': parts[0],
                        'port': parts[1],
                        'username': parts[2],
                        'password': parts[3]
                    })
                elif len(parts) == 2:
                    proxies.append({
                        'host': parts[0],
                        'port': parts[1],
                        'username': '',
                        'password': ''
                    })
    except Exception as e:
        print(f'Error loading proxies: {e}')
    return proxies


def api_get(path):
    try:
        url = API_BASE + path
        req = urllib.request.Request(url, method='GET')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def api_post(path, data=None):
    try:
        url = API_BASE + path
        body = json.dumps(data or {}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def fetch_open_profiles():
    page = 1
    all_open = []
    while True:
        resp = api_get(f'/api/v1/user/list?page={page}&page_size=100')
        if resp.get('code') != 0:
            break
        profiles = resp.get('data', {}).get('list', [])
        if not profiles:
            break
        for p in profiles:
            uid = p.get('user_id', '')
            active = api_get(f'/api/v1/browser/active?user_id={uid}')
            if active.get('code') == 0 and active.get('data', {}).get('status') == 'Active':
                all_open.append(p)
        page += 1
    return all_open


class ProxyRotatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'ProxyRotator v{VERSION}')
        self.root.geometry('750x580')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')

        self.proxies = []
        self.profile_widgets = {}
        self.dashboard = {}
        self.scanning = False

        self._load_config_data()
        self._auto_load_proxies()
        self._build_ui()

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _log(self, msg):
        ts = time.strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        print(line)
        if hasattr(self, 'log_text'):
            self.log_text.configure(state='normal')
            self.log_text.insert('end', line + '\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')

    def _load_config_data(self):
        cfg = load_config()
        self.dashboard = cfg.get('dashboard', {})
        self.last_proxy_file = cfg.get('last_proxy_file', '')

    def _save_dashboard(self):
        cfg = load_config()
        cfg['dashboard'] = self.dashboard
        cfg['last_proxy_file'] = self.last_proxy_file
        save_config(cfg)

    def _auto_load_proxies(self):
        path = get_proxies_path()
        if os.path.exists(path):
            self.proxies = load_proxies_from_file(path)
            self.last_proxy_file = path
            return

        if self.last_proxy_file and os.path.exists(self.last_proxy_file):
            self.proxies = load_proxies_from_file(self.last_proxy_file)
            return

        app_dir = get_app_dir()
        try:
            for f in os.listdir(app_dir):
                if f.lower().endswith('.txt') and 'proxy' in f.lower():
                    fp = os.path.join(app_dir, f)
                    loaded = load_proxies_from_file(fp)
                    if loaded:
                        self.proxies = loaded
                        self.last_proxy_file = fp
                        return
        except Exception:
            pass

    def _build_ui(self):
        tf = tk.Frame(self.root, bg='#1a1a2e')
        tf.pack(fill='x', padx=15, pady=(10, 5))
        tk.Label(tf, text='PROXY ROTATOR', font=('Segoe UI', 16, 'bold'),
                 fg='#e94560', bg='#1a1a2e').pack()
        tk.Label(tf, text=f'v{VERSION} - Auto-detect open profiles, instant rotation',
                 font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack()

        cf = tk.Frame(self.root, bg='#1a1a2e')
        cf.pack(fill='x', padx=15, pady=3)

        self.count_label = tk.Label(cf, text=f'Proxies: {len(self.proxies)}',
                                     font=('Segoe UI', 10, 'bold'),
                                     fg='#44dd44' if self.proxies else '#ff6b6b',
                                     bg='#1a1a2e')
        self.count_label.pack(side='left')

        tk.Button(cf, text='Load proxies.txt', font=('Segoe UI', 8),
                  fg='#fff', bg='#0f3460', border=0, padx=8, pady=2,
                  cursor='hand2', command=self._browse_proxies).pack(side='right', padx=4)

        sf = tk.Frame(self.root, bg='#1a1a2e')
        sf.pack(fill='x', padx=15, pady=(5, 2))

        self.scan_btn = tk.Button(sf, text='SCAN OPEN PROFILES', font=('Segoe UI', 10, 'bold'),
                  fg='#fff', bg='#e94560', activebackground='#ff6b8a',
                  border=0, padx=16, pady=4,
                  cursor='hand2', command=self._scan_profiles)
        self.scan_btn.pack(side='left')

        tk.Label(sf, text='or add serial #:', font=('Segoe UI', 9),
                 fg='#888', bg='#1a1a2e').pack(side='left', padx=(12, 4))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(sf, textvariable=self.search_var, font=('Consolas', 11),
                                bg='#0a0a1a', fg='#FFD700', insertbackground='#FFD700',
                                border=1, relief='solid', width=12)
        self.search_entry.pack(side='left', padx=(0, 4))
        self.search_entry.bind('<Return>', lambda e: self._add_profile())

        self.search_btn = tk.Button(sf, text='ADD', font=('Segoe UI', 9, 'bold'),
                  fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                  border=0, padx=10, pady=3,
                  cursor='hand2', command=self._add_profile)
        self.search_btn.pack(side='left')

        info = tk.Label(self.root,
            text='ROTATE = change proxy (no restart)  |  RESTORE = back to original  |  X = remove from list',
            font=('Segoe UI', 8), fg='#FFD700', bg='#0f3460', pady=3)
        info.pack(fill='x', padx=15, pady=(5, 0))

        hf = tk.Frame(self.root, bg='#16213e')
        hf.pack(fill='x', padx=15, pady=(0, 0))
        for text, w in [('Serial', 7), ('Original Proxy', 18), ('Active Proxy', 18), ('Status', 8), ('', 20)]:
            tk.Label(hf, text=text, font=('Segoe UI', 8, 'bold'), fg='#aaa',
                     bg='#16213e', width=w, anchor='w').pack(side='left', padx=(4 if text == 'Serial' else 0, 0))

        canvas_frame = tk.Frame(self.root, bg='#1a1a2e')
        canvas_frame.pack(fill='both', expand=True, padx=15, pady=(0, 5))

        self.canvas = tk.Canvas(canvas_frame, bg='#16213e', highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient='vertical', command=self.canvas.yview)
        self.profiles_frame = tk.Frame(self.canvas, bg='#16213e')

        self.profiles_frame.bind('<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

        self.canvas.create_window((0, 0), window=self.profiles_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        lf = tk.Frame(self.root, bg='#1a1a2e')
        lf.pack(fill='x', padx=15, pady=(0, 10))
        tk.Label(lf, text='Log', font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack(anchor='w')
        self.log_text = tk.Text(lf, height=4, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                insertbackground='#44dd44', border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='x', pady=2)

        if self.proxies:
            self._log(f'Loaded {len(self.proxies)} proxies')
        else:
            self._log('No proxies found. Click "Load proxies.txt"')

        if self.dashboard:
            self._log(f'{len(self.dashboard)} profile(s) from last session')

        self._render_dashboard()

    def _browse_proxies(self):
        filepath = filedialog.askopenfilename(
            title='Select Proxy List',
            filetypes=[('Text files', '*.txt'), ('All files', '*.*')]
        )
        if filepath:
            self.proxies = load_proxies_from_file(filepath)
            self.last_proxy_file = filepath
            self._save_dashboard()
            self.count_label.configure(
                text=f'Proxies: {len(self.proxies)}',
                fg='#44dd44' if self.proxies else '#ff6b6b')
            self._log(f'Loaded {len(self.proxies)} proxies')

    def _scan_profiles(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.configure(state='disabled', text='Scanning...')
        self._log('Scanning for open profiles...')

        def do_scan():
            page = 1
            found = 0
            checked = 0
            while True:
                resp = api_get(f'/api/v1/user/list?page={page}&page_size=100')
                if resp.get('code') != 0:
                    break
                profiles = resp.get('data', {}).get('list', [])
                if not profiles:
                    break

                for p in profiles:
                    uid = p.get('user_id', '')
                    sn = str(p.get('serial_number', ''))
                    checked += 1

                    if uid in self.dashboard:
                        continue

                    active = api_get(f'/api/v1/browser/active?user_id={uid}')
                    if active.get('code') == 0 and active.get('data', {}).get('status') == 'Active':
                        proxy_cfg = p.get('user_proxy_config', {})
                        ph = proxy_cfg.get('proxy_host', '')
                        pp = proxy_cfg.get('proxy_port', '')
                        orig_display = f'{ph}:{pp}' if ph else 'no proxy'

                        self.dashboard[uid] = {
                            'serial': sn,
                            'user_id': uid,
                            'original_proxy': orig_display,
                            'original_config': dict(proxy_cfg),
                            'current_proxy': orig_display,
                            'rotated': False,
                        }
                        found += 1
                        self.root.after(0, lambda s=sn: self._log(f'Found open: {s}'))

                    if checked % 20 == 0:
                        self.root.after(0, lambda c=checked: self.scan_btn.configure(
                            text=f'Checking... ({c})'))

                page += 1

            if found > 0:
                self._save_dashboard()
            self.root.after(0, lambda: self._log(f'Scan done. Found {found} new open profile(s). Checked {checked} total.'))
            self.root.after(0, self._render_dashboard)
            self.root.after(0, lambda: self.scan_btn.configure(state='normal', text='SCAN OPEN PROFILES'))
            self.scanning = False

        threading.Thread(target=do_scan, daemon=True).start()

    def _add_profile(self):
        raw = self.search_var.get().strip()
        if not raw:
            return

        serials = [s.strip() for s in raw.replace(' ', ',').split(',') if s.strip()]
        self.search_btn.configure(state='disabled', text='...')

        def do_add():
            for serial in serials:
                if any(d.get('serial') == serial for d in self.dashboard.values()):
                    self._log(f'{serial} already in dashboard')
                    continue

                resp = api_get(f'/api/v1/user/list?serial_number={serial}')
                if resp.get('code') != 0 or not resp.get('data', {}).get('list'):
                    self._log(f'Profile {serial} not found')
                    continue

                p = resp['data']['list'][0]
                uid = p.get('user_id', '')
                sn = str(p.get('serial_number', ''))
                proxy_cfg = p.get('user_proxy_config', {})
                ph = proxy_cfg.get('proxy_host', '')
                pp = proxy_cfg.get('proxy_port', '')
                orig_display = f'{ph}:{pp}' if ph else 'no proxy'

                self.dashboard[uid] = {
                    'serial': sn,
                    'user_id': uid,
                    'original_proxy': orig_display,
                    'original_config': dict(proxy_cfg),
                    'current_proxy': orig_display,
                    'rotated': False,
                }
                self._save_dashboard()
                self._log(f'{sn}: added to dashboard')

            self.root.after(0, self._render_dashboard)
            self.root.after(0, lambda: self.search_btn.configure(state='normal', text='ADD'))
            self.root.after(0, lambda: self.search_var.set(''))

        threading.Thread(target=do_add, daemon=True).start()

    def _render_dashboard(self):
        for w in self.profiles_frame.winfo_children():
            w.destroy()
        self.profile_widgets = {}

        if not self.dashboard:
            tk.Label(self.profiles_frame,
                text='No profiles yet.\n\nClick "SCAN OPEN PROFILES" to auto-detect running profiles,\n'
                     'or type a serial number and click ADD.',
                font=('Segoe UI', 10), fg='#888', bg='#16213e', pady=30).pack()
            return

        for i, (uid, info) in enumerate(self.dashboard.items()):
            bg = '#1a2744' if i % 2 == 0 else '#16213e'
            row = tk.Frame(self.profiles_frame, bg=bg)
            row.pack(fill='x', padx=2, pady=1)

            tk.Label(row, text=info['serial'], font=('Consolas', 9, 'bold'),
                     fg='#ddd', bg=bg, width=7, anchor='w').pack(side='left', padx=(6, 0))

            orig = info.get('original_proxy', '?')
            if len(orig) > 18:
                orig = orig[:18] + '..'
            tk.Label(row, text=orig, font=('Consolas', 8), fg='#8888aa',
                     bg=bg, width=18, anchor='w').pack(side='left')

            cur = info.get('current_proxy', '?')
            if len(cur) > 18:
                cur = cur[:18] + '..'
            cur_color = '#FF9800' if info.get('rotated') else '#44dd44'
            cur_lbl = tk.Label(row, text=cur, font=('Consolas', 8, 'bold'),
                               fg=cur_color, bg=bg, width=18, anchor='w')
            cur_lbl.pack(side='left')

            status = 'ROTATED' if info.get('rotated') else 'ready'
            st_color = '#FF9800' if info.get('rotated') else '#44dd44'
            status_lbl = tk.Label(row, text=status, font=('Consolas', 8, 'bold'),
                                   fg=st_color, bg=bg, width=8, anchor='w')
            status_lbl.pack(side='left')

            remove_btn = tk.Button(row, text='X', font=('Segoe UI', 7, 'bold'),
                                    fg='#ff6b6b', bg=bg, border=0, padx=4,
                                    cursor='hand2',
                                    command=lambda u=uid: self._remove_profile(u))
            remove_btn.pack(side='right', padx=2, pady=2)

            restore_btn = tk.Button(row, text='RESTORE', font=('Segoe UI', 8, 'bold'),
                                     fg='#fff', bg='#4CAF50', activebackground='#66BB6A',
                                     border=0, padx=6, pady=2, cursor='hand2',
                                     state='normal' if info.get('rotated') else 'disabled',
                                     command=lambda u=uid: self._restore_profile(u))
            restore_btn.pack(side='right', padx=2, pady=2)

            rotate_btn = tk.Button(row, text='ROTATE', font=('Segoe UI', 8, 'bold'),
                                    fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                                    border=0, padx=6, pady=2, cursor='hand2',
                                    command=lambda u=uid: self._rotate_profile(u))
            rotate_btn.pack(side='right', padx=2, pady=2)

            self.profile_widgets[uid] = {
                'cur_lbl': cur_lbl,
                'status_lbl': status_lbl,
                'rotate_btn': rotate_btn,
                'restore_btn': restore_btn,
            }

        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _rotate_profile(self, user_id):
        if not self.proxies:
            self._log('No proxies loaded!')
            messagebox.showwarning('No Proxies', 'Load proxies.txt first.')
            return

        info = self.dashboard.get(user_id)
        if not info:
            return

        serial = info.get('serial', '?')
        proxy = random.choice(self.proxies)
        display = f"{proxy['host']}:{proxy['port']}"

        def do_rotate():
            new_proxy_cfg = {
                'proxy_soft': 'other',
                'proxy_type': 'http',
                'proxy_host': proxy['host'],
                'proxy_port': str(proxy['port']),
                'proxy_user': proxy.get('username', ''),
                'proxy_password': proxy.get('password', '')
            }

            resp = api_post('/api/v1/user/update', {
                'user_id': user_id,
                'user_proxy_config': new_proxy_cfg
            })

            if resp.get('code') == 0:
                self.dashboard[user_id]['current_proxy'] = display
                self.dashboard[user_id]['rotated'] = True
                self.dashboard[user_id]['rotated_proxy'] = dict(proxy)
                self._save_dashboard()
                self.root.after(0, lambda: self._log(f'{serial}: rotated to {display}'))
            else:
                self.root.after(0, lambda: self._log(f'{serial}: FAILED - {resp.get("msg", "unknown error")}'))

            self.root.after(0, self._render_dashboard)

        threading.Thread(target=do_rotate, daemon=True).start()

    def _restore_profile(self, user_id):
        info = self.dashboard.get(user_id)
        if not info:
            return

        serial = info.get('serial', '?')
        orig_cfg = info.get('original_config', {})

        def do_restore():
            resp = api_post('/api/v1/user/update', {
                'user_id': user_id,
                'user_proxy_config': orig_cfg
            })

            if resp.get('code') == 0:
                self.dashboard[user_id]['current_proxy'] = info.get('original_proxy', '?')
                self.dashboard[user_id]['rotated'] = False
                self.dashboard[user_id].pop('rotated_proxy', None)
                self._save_dashboard()
                self.root.after(0, lambda: self._log(f'{serial}: restored to original'))
            else:
                self.root.after(0, lambda: self._log(f'{serial}: restore FAILED - {resp.get("msg", "")}'))

            self.root.after(0, self._render_dashboard)

        threading.Thread(target=do_restore, daemon=True).start()

    def _remove_profile(self, user_id):
        info = self.dashboard.get(user_id, {})
        serial = info.get('serial', '?')

        if info.get('rotated'):
            orig_cfg = info.get('original_config')
            if orig_cfg:
                api_post('/api/v1/user/update', {
                    'user_id': user_id,
                    'user_proxy_config': orig_cfg
                })

        self.dashboard.pop(user_id, None)
        self._save_dashboard()
        self._log(f'{serial}: removed')
        self._render_dashboard()

    def _on_close(self):
        for uid, info in list(self.dashboard.items()):
            if info.get('rotated'):
                orig_cfg = info.get('original_config')
                if orig_cfg:
                    try:
                        api_post('/api/v1/user/update', {
                            'user_id': uid,
                            'user_proxy_config': orig_cfg
                        })
                    except Exception:
                        pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = ProxyRotatorApp()
    app.run()
