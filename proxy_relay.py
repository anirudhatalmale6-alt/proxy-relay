"""
ProxyRotator v2.0 - Per-Profile Proxy Rotation for AdsPower
Each profile gets its own ROTATE button.
Uses AdsPower API to update proxy + restart browser.

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

VERSION = "2.0"
API_BASE = "http://127.0.0.1:50325"


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_proxies_path():
    return os.path.join(get_app_dir(), 'proxies.txt')


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
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def api_post(path, data=None):
    try:
        url = API_BASE + path
        body = json.dumps(data or {}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


class ProxyRotatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'ProxyRotator v{VERSION}')
        self.root.geometry('580x520')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')

        self.proxies = []
        self.profiles = []
        self.profile_proxies = {}
        self.profile_widgets = {}

        self._load_proxies()
        self._build_ui()
        self._refresh_profiles()

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

    def _load_proxies(self):
        path = get_proxies_path()
        if os.path.exists(path):
            self.proxies = load_proxies_from_file(path)
            print(f'Loaded {len(self.proxies)} proxies from {path}')
        else:
            print(f'No proxies.txt at {path}')

    def _build_ui(self):
        # Title
        tf = tk.Frame(self.root, bg='#1a1a2e')
        tf.pack(fill='x', padx=15, pady=(10, 5))
        tk.Label(tf, text='PROXY ROTATOR', font=('Segoe UI', 16, 'bold'),
                 fg='#e94560', bg='#1a1a2e').pack()
        tk.Label(tf, text=f'v{VERSION} - Per-profile proxy rotation for AdsPower',
                 font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack()

        # Proxy count + buttons
        cf = tk.Frame(self.root, bg='#1a1a2e')
        cf.pack(fill='x', padx=15, pady=5)

        self.count_label = tk.Label(cf, text=f'Proxies: {len(self.proxies)}',
                                     font=('Segoe UI', 10, 'bold'),
                                     fg='#44dd44' if self.proxies else '#ff6b6b',
                                     bg='#1a1a2e')
        self.count_label.pack(side='left')

        tk.Button(cf, text='Load proxies.txt', font=('Segoe UI', 8),
                  fg='#fff', bg='#0f3460', border=0, padx=8, pady=2,
                  cursor='hand2', command=self._browse_proxies).pack(side='right', padx=4)

        tk.Button(cf, text='Refresh Profiles', font=('Segoe UI', 8),
                  fg='#fff', bg='#0f3460', border=0, padx=8, pady=2,
                  cursor='hand2', command=self._refresh_profiles).pack(side='right', padx=4)

        # Profiles list header
        hf = tk.Frame(self.root, bg='#0f3460')
        hf.pack(fill='x', padx=15, pady=(8, 0))
        tk.Label(hf, text='Profile', font=('Segoe UI', 9, 'bold'), fg='#fff',
                 bg='#0f3460', width=20, anchor='w').pack(side='left', padx=(8, 0))
        tk.Label(hf, text='Current Proxy', font=('Segoe UI', 9, 'bold'), fg='#fff',
                 bg='#0f3460', width=25, anchor='w').pack(side='left')
        tk.Label(hf, text='', font=('Segoe UI', 9), bg='#0f3460',
                 width=10).pack(side='right', padx=4)

        # Scrollable profiles area
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

        # No profiles message
        self.no_profiles_label = tk.Label(self.profiles_frame,
            text='No active profiles found.\nStart some profiles in AdsPower first.',
            font=('Segoe UI', 10), fg='#666', bg='#16213e', pady=20)

        # Log area
        lf = tk.Frame(self.root, bg='#1a1a2e')
        lf.pack(fill='x', padx=15, pady=(0, 10))
        tk.Label(lf, text='Log', font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack(anchor='w')
        self.log_text = tk.Text(lf, height=4, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                insertbackground='#44dd44', border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='x', pady=2)

        if self.proxies:
            self._log(f'Loaded {len(self.proxies)} proxies')
        else:
            path = get_proxies_path()
            self._log(f'No proxies.txt found at: {path}')
            self._log('Click "Load proxies.txt" or place the file next to this .exe')

    def _browse_proxies(self):
        filepath = filedialog.askopenfilename(
            title='Select Proxy List',
            filetypes=[('Text files', '*.txt'), ('All files', '*.*')]
        )
        if filepath:
            self.proxies = load_proxies_from_file(filepath)
            self.count_label.configure(
                text=f'Proxies: {len(self.proxies)}',
                fg='#44dd44' if self.proxies else '#ff6b6b')
            self._log(f'Loaded {len(self.proxies)} proxies from {os.path.basename(filepath)}')

    def _refresh_profiles(self):
        def do_refresh():
            self._log('Fetching active profiles from AdsPower...')

            resp = api_get('/api/v1/browser/active?page=1&page_size=100')
            if resp.get('code') != 0:
                self._log(f'AdsPower API error: {resp.get("msg", "unknown")}')
                self.root.after(0, lambda: self.no_profiles_label.pack(pady=20))
                return

            data = resp.get('data', {})
            profile_list = data.get('list', [])
            if not profile_list:
                self._log('No active profiles found')
                self.root.after(0, lambda: self.no_profiles_label.pack(pady=20))
                return

            self.profiles = []
            for p in profile_list:
                user_id = p.get('user_id', '')
                serial = p.get('serial_number', '')
                name = p.get('name', '') or p.get('remark', '') or serial or user_id

                profile_resp = api_get(f'/api/v1/user/list?user_id={user_id}')
                current_proxy = 'unknown'
                if profile_resp.get('code') == 0:
                    plist = profile_resp.get('data', {}).get('list', [])
                    if plist:
                        proxy_cfg = plist[0].get('user_proxy_config', {})
                        ph = proxy_cfg.get('proxy_host', '')
                        pp = proxy_cfg.get('proxy_port', '')
                        if ph:
                            current_proxy = f'{ph}:{pp}'
                        else:
                            current_proxy = 'no proxy'

                self.profiles.append({
                    'user_id': user_id,
                    'serial': serial,
                    'name': name,
                    'current_proxy': current_proxy
                })

            self._log(f'Found {len(self.profiles)} active profiles')
            self.root.after(0, self._render_profiles)

        threading.Thread(target=do_refresh, daemon=True).start()

    def _render_profiles(self):
        for w in self.profiles_frame.winfo_children():
            w.destroy()
        self.profile_widgets = {}

        if not self.profiles:
            self.no_profiles_label = tk.Label(self.profiles_frame,
                text='No active profiles found.\nStart some profiles in AdsPower first.',
                font=('Segoe UI', 10), fg='#666', bg='#16213e', pady=20)
            self.no_profiles_label.pack()
            return

        for i, profile in enumerate(self.profiles):
            bg = '#1a2744' if i % 2 == 0 else '#16213e'
            row = tk.Frame(self.profiles_frame, bg=bg)
            row.pack(fill='x', padx=2, pady=1)

            display_name = profile['serial'] or profile['name']
            if len(display_name) > 18:
                display_name = display_name[:18] + '..'

            name_lbl = tk.Label(row, text=display_name, font=('Consolas', 9),
                                fg='#ddd', bg=bg, width=20, anchor='w')
            name_lbl.pack(side='left', padx=(8, 0))

            proxy_lbl = tk.Label(row, text=profile['current_proxy'],
                                 font=('Consolas', 9), fg='#8888aa', bg=bg,
                                 width=25, anchor='w')
            proxy_lbl.pack(side='left')

            uid = profile['user_id']
            rotate_btn = tk.Button(row, text='ROTATE', font=('Segoe UI', 8, 'bold'),
                                    fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                                    activeforeground='#fff', border=0, padx=10, pady=2,
                                    cursor='hand2',
                                    command=lambda u=uid: self._rotate_profile(u))
            rotate_btn.pack(side='right', padx=6, pady=3)

            self.profile_widgets[uid] = {
                'name_lbl': name_lbl,
                'proxy_lbl': proxy_lbl,
                'rotate_btn': rotate_btn,
                'row': row
            }

        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _rotate_profile(self, user_id):
        if not self.proxies:
            self._log('No proxies loaded! Load proxies.txt first.')
            messagebox.showwarning('No Proxies', 'Load proxies.txt first.')
            return

        widgets = self.profile_widgets.get(user_id)
        if widgets:
            widgets['rotate_btn'].configure(state='disabled', text='...')
            widgets['proxy_lbl'].configure(text='rotating...', fg='#FFD700')

        def do_rotate():
            proxy = random.choice(self.proxies)
            display = f"{proxy['host']}:{proxy['port']}"
            self._log(f'Rotating {user_id} -> {display}')

            proxy_config = {
                'proxy_soft': 'other',
                'proxy_type': 'http',
                'proxy_host': proxy['host'],
                'proxy_port': str(proxy['port']),
                'proxy_user': proxy.get('username', ''),
                'proxy_password': proxy.get('password', '')
            }

            resp = api_post('/api/v1/user/update', {
                'user_id': user_id,
                'user_proxy_config': proxy_config
            })

            if resp.get('code') != 0:
                self._log(f'Update failed: {resp.get("msg", "unknown")}')
                self.root.after(0, lambda: self._update_profile_ui(user_id, 'FAILED', '#ff4444'))
                return

            self._log(f'Proxy updated for {user_id}. Restarting browser...')

            stop_resp = api_post('/api/v1/browser/stop', {'user_id': user_id})
            if stop_resp.get('code') != 0:
                self._log(f'Stop warning: {stop_resp.get("msg", "")}')

            time.sleep(1.5)

            start_resp = api_get(f'/api/v1/browser/start?user_id={user_id}')
            if start_resp.get('code') == 0:
                self._log(f'Profile {user_id} restarted with {display}')
                self.root.after(0, lambda: self._update_profile_ui(user_id, display, '#44dd44'))
            else:
                self._log(f'Start failed: {start_resp.get("msg", "")}')
                self._log(f'Proxy was updated to {display} - restart manually in AdsPower')
                self.root.after(0, lambda: self._update_profile_ui(user_id, f'{display} (restart)', '#FFD700'))

        threading.Thread(target=do_rotate, daemon=True).start()

    def _update_profile_ui(self, user_id, proxy_text, color):
        widgets = self.profile_widgets.get(user_id)
        if widgets:
            widgets['proxy_lbl'].configure(text=proxy_text, fg=color)
            widgets['rotate_btn'].configure(state='normal', text='ROTATE')

    def _on_close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = ProxyRotatorApp()
    app.run()
