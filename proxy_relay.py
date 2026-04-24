"""
ProxyRotator v3.0 - Per-Profile Proxy Rotation for AdsPower
ROTATE = change proxy setting (close & reopen profile to apply)
RESTORE = put back the original proxy

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

VERSION = "3.0"
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
        self.root.geometry('620x520')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')

        self.proxies = []
        self.profiles = []
        self.profile_widgets = {}
        self.original_proxies = {}

        self._load_proxies()
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

        # Proxy count + load button
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

        # Search row
        sf = tk.Frame(self.root, bg='#1a1a2e')
        sf.pack(fill='x', padx=15, pady=(8, 2))

        tk.Label(sf, text='Serial #:', font=('Segoe UI', 10, 'bold'),
                 fg='#FFD700', bg='#1a1a2e').pack(side='left')

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(sf, textvariable=self.search_var, font=('Consolas', 12),
                                bg='#0a0a1a', fg='#FFD700', insertbackground='#FFD700',
                                border=1, relief='solid', width=25)
        self.search_entry.pack(side='left', padx=(6, 4))
        self.search_entry.bind('<Return>', lambda e: self._do_search())

        self.search_btn = tk.Button(sf, text='FIND', font=('Segoe UI', 9, 'bold'),
                  fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                  border=0, padx=12, pady=3,
                  cursor='hand2', command=self._do_search)
        self.search_btn.pack(side='left', padx=4)

        tk.Label(sf, text='e.g. 27764, 27763',
                 font=('Segoe UI', 8), fg='#666', bg='#1a1a2e').pack(side='left', padx=8)

        # Info bar
        self.info_label = tk.Label(self.root, text='ROTATE = change proxy | RESTORE = put back original | Close & reopen profile to apply',
                 font=('Segoe UI', 8), fg='#FFD700', bg='#0f3460', pady=3)
        self.info_label.pack(fill='x', padx=15, pady=(5, 0))

        # Profiles list header
        hf = tk.Frame(self.root, bg='#0f3460')
        hf.pack(fill='x', padx=15, pady=(0, 0))
        self.header_label = tk.Label(hf, text='Profile', font=('Segoe UI', 9, 'bold'),
                 fg='#fff', bg='#0f3460', width=12, anchor='w')
        self.header_label.pack(side='left', padx=(8, 0))
        tk.Label(hf, text='Original Proxy', font=('Segoe UI', 9, 'bold'), fg='#fff',
                 bg='#0f3460', width=18, anchor='w').pack(side='left')
        tk.Label(hf, text='Status', font=('Segoe UI', 9, 'bold'), fg='#fff',
                 bg='#0f3460', width=18, anchor='w').pack(side='left')
        tk.Label(hf, text='', font=('Segoe UI', 9), bg='#0f3460',
                 width=16).pack(side='right', padx=4)

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

        # Initial message
        tk.Label(self.profiles_frame,
            text='Enter serial number(s) above and click FIND\n\n'
                 'Example: 27764\n'
                 'Multiple: 27764, 27763, 27762',
            font=('Segoe UI', 10), fg='#888', bg='#16213e', pady=30).pack()

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

    def _do_search(self):
        raw = self.search_var.get().strip()
        if not raw:
            self._log('Enter a serial number to search')
            return

        serials = [s.strip() for s in raw.replace(' ', ',').split(',') if s.strip()]
        if not serials:
            return

        self.search_btn.configure(state='disabled', text='...')
        self._log(f'Searching for: {", ".join(serials)}')

        def do_search():
            found = []
            for serial in serials:
                resp = api_get(f'/api/v1/user/list?serial_number={serial}')
                if resp.get('code') == 0:
                    data = resp.get('data', {})
                    profiles = data.get('list', [])
                    if not profiles and isinstance(data, list):
                        profiles = data
                    for p in profiles:
                        user_id = p.get('user_id', '')
                        sn = p.get('serial_number', '')
                        name = p.get('name', '') or p.get('remark', '') or str(sn) or user_id

                        proxy_cfg = p.get('user_proxy_config', {})
                        ph = proxy_cfg.get('proxy_host', '')
                        pp = proxy_cfg.get('proxy_port', '')
                        current_proxy = f'{ph}:{pp}' if ph else 'no proxy'

                        self.original_proxies[user_id] = dict(proxy_cfg)

                        found.append({
                            'user_id': user_id,
                            'serial': str(sn),
                            'name': name,
                            'current_proxy': current_proxy
                        })
                else:
                    self._log(f'API error for {serial}: {resp.get("msg", "unknown")}')

            if not found:
                self._log(f'No profiles found for: {", ".join(serials)}')
            else:
                self._log(f'Found {len(found)} profile(s). Original proxies saved.')

            self.profiles = found
            self.root.after(0, self._render_profiles)
            self.root.after(0, lambda: self.search_btn.configure(state='normal', text='FIND'))

        threading.Thread(target=do_search, daemon=True).start()

    def _render_profiles(self):
        for w in self.profiles_frame.winfo_children():
            w.destroy()
        self.profile_widgets = {}

        if not self.profiles:
            tk.Label(self.profiles_frame,
                text='No profiles found.\nCheck the serial number and try again.',
                font=('Segoe UI', 10), fg='#666', bg='#16213e', pady=20).pack()
            return

        self.header_label.configure(text=f'Found ({len(self.profiles)})')

        for i, profile in enumerate(self.profiles):
            bg = '#1a2744' if i % 2 == 0 else '#16213e'
            row = tk.Frame(self.profiles_frame, bg=bg)
            row.pack(fill='x', padx=2, pady=1)

            display_name = profile['serial'] or profile['name']
            if len(display_name) > 10:
                display_name = display_name[:10] + '..'

            name_lbl = tk.Label(row, text=display_name, font=('Consolas', 9),
                                fg='#ddd', bg=bg, width=12, anchor='w')
            name_lbl.pack(side='left', padx=(8, 0))

            orig_proxy = profile['current_proxy']
            if len(orig_proxy) > 18:
                orig_proxy = orig_proxy[:18] + '..'
            orig_lbl = tk.Label(row, text=orig_proxy,
                                font=('Consolas', 8), fg='#8888aa', bg=bg,
                                width=18, anchor='w')
            orig_lbl.pack(side='left')

            status_lbl = tk.Label(row, text='original',
                                   font=('Consolas', 9), fg='#8888aa', bg=bg,
                                   width=18, anchor='w')
            status_lbl.pack(side='left')

            uid = profile['user_id']

            restore_btn = tk.Button(row, text='RESTORE', font=('Segoe UI', 8, 'bold'),
                                     fg='#fff', bg='#4CAF50', activebackground='#66BB6A',
                                     activeforeground='#fff', border=0, padx=6, pady=2,
                                     cursor='hand2', state='disabled',
                                     command=lambda u=uid: self._restore_profile(u))
            restore_btn.pack(side='right', padx=3, pady=3)

            rotate_btn = tk.Button(row, text='ROTATE', font=('Segoe UI', 8, 'bold'),
                                    fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                                    activeforeground='#fff', border=0, padx=6, pady=2,
                                    cursor='hand2',
                                    command=lambda u=uid: self._rotate_profile(u))
            rotate_btn.pack(side='right', padx=3, pady=3)

            self.profile_widgets[uid] = {
                'name_lbl': name_lbl,
                'orig_lbl': orig_lbl,
                'status_lbl': status_lbl,
                'rotate_btn': rotate_btn,
                'restore_btn': restore_btn,
                'row': row
            }

        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _update_proxy(self, user_id, proxy_config):
        resp = api_post('/api/v1/user/update', {
            'user_id': user_id,
            'user_proxy_config': proxy_config
        })
        return resp.get('code') == 0, resp.get('msg', 'unknown')

    def _rotate_profile(self, user_id):
        if not self.proxies:
            self._log('No proxies loaded! Load proxies.txt first.')
            messagebox.showwarning('No Proxies', 'Load proxies.txt first.')
            return

        widgets = self.profile_widgets.get(user_id)
        if widgets:
            widgets['rotate_btn'].configure(state='disabled', text='...')
            widgets['status_lbl'].configure(text='rotating...', fg='#FFD700')

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

            ok, msg = self._update_proxy(user_id, proxy_config)

            if ok:
                self._log(f'Proxy set to {display}')
                self._log('Close & reopen the profile in AdsPower to use the new proxy')
                self.root.after(0, lambda: self._set_rotated_ui(user_id, display))
            else:
                self._log(f'Failed: {msg}')
                self.root.after(0, lambda: self._set_failed_ui(user_id))

        threading.Thread(target=do_rotate, daemon=True).start()

    def _restore_profile(self, user_id):
        orig = self.original_proxies.get(user_id)
        if not orig:
            self._log(f'No original proxy saved for {user_id}')
            return

        widgets = self.profile_widgets.get(user_id)
        if widgets:
            widgets['restore_btn'].configure(state='disabled', text='...')
            widgets['status_lbl'].configure(text='restoring...', fg='#FFD700')

        def do_restore():
            self._log(f'Restoring original proxy for {user_id}...')

            ok, msg = self._update_proxy(user_id, orig)

            if ok:
                ph = orig.get('proxy_host', '')
                pp = orig.get('proxy_port', '')
                display = f'{ph}:{pp}' if ph else 'no proxy'
                self._log(f'Restored to {display}')
                self._log('Close & reopen the profile to apply')
                self.root.after(0, lambda: self._set_restored_ui(user_id))
            else:
                self._log(f'Restore failed: {msg}')
                self.root.after(0, lambda: self._set_failed_ui(user_id))

        threading.Thread(target=do_restore, daemon=True).start()

    def _set_rotated_ui(self, user_id, new_proxy):
        widgets = self.profile_widgets.get(user_id)
        if widgets:
            if len(new_proxy) > 18:
                new_proxy = new_proxy[:18] + '..'
            widgets['status_lbl'].configure(text=f'-> {new_proxy}', fg='#FF9800')
            widgets['rotate_btn'].configure(state='normal', text='ROTATE')
            widgets['restore_btn'].configure(state='normal')

    def _set_restored_ui(self, user_id):
        widgets = self.profile_widgets.get(user_id)
        if widgets:
            widgets['status_lbl'].configure(text='restored', fg='#44dd44')
            widgets['rotate_btn'].configure(state='normal', text='ROTATE')
            widgets['restore_btn'].configure(state='disabled')

    def _set_failed_ui(self, user_id):
        widgets = self.profile_widgets.get(user_id)
        if widgets:
            widgets['status_lbl'].configure(text='FAILED', fg='#ff4444')
            widgets['rotate_btn'].configure(state='normal', text='ROTATE')
            widgets['restore_btn'].configure(state='normal')

    def _on_close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = ProxyRotatorApp()
    app.run()
