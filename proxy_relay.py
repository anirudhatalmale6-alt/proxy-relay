"""
ProxyRotator v2.5 - Per-Profile Proxy Rotation for AdsPower
Search by serial number. Tries multiple methods to rotate proxy.
Each profile gets its own ROTATE button.

Place proxies.txt next to this .exe (format: host:port:user:pass)
Requires AdsPower API Key (Settings > Security > API Key)
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

VERSION = "2.6"
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


def api_get(path, api_key=''):
    try:
        if api_key:
            sep = '&' if '?' in path else '?'
            path = f'{path}{sep}api_key={api_key}'
        url = API_BASE + path
        req = urllib.request.Request(url, method='GET')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def api_post(path, data=None, api_key=''):
    try:
        if api_key:
            sep = '&' if '?' in path else '?'
            path = f'{path}{sep}api_key={api_key}'
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
        self.profile_widgets = {}
        self.api_key = ''

        self._load_config()
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

    def _load_config(self):
        cfg = load_config()
        self.api_key = cfg.get('api_key', '')

    def _save_api_key(self):
        self.api_key = self.api_key_var.get().strip()
        cfg = load_config()
        cfg['api_key'] = self.api_key
        save_config(cfg)
        if self.api_key:
            self._log(f'API key saved ({len(self.api_key)} chars)')
            self.key_status.configure(text='Saved', fg='#44dd44')
        else:
            self._log('API key cleared')
            self.key_status.configure(text='No key', fg='#ff6b6b')

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

        # API Key row
        kf = tk.Frame(self.root, bg='#1a1a2e')
        kf.pack(fill='x', padx=15, pady=(5, 2))

        tk.Label(kf, text='API Key:', font=('Segoe UI', 9, 'bold'),
                 fg='#ddd', bg='#1a1a2e').pack(side='left')

        self.api_key_var = tk.StringVar(value=self.api_key)
        key_entry = tk.Entry(kf, textvariable=self.api_key_var, font=('Consolas', 9),
                             bg='#0a0a1a', fg='#44dd44', insertbackground='#44dd44',
                             border=1, relief='solid', width=30, show='*')
        key_entry.pack(side='left', padx=(6, 4), fill='x', expand=True)

        tk.Button(kf, text='Save', font=('Segoe UI', 8),
                  fg='#fff', bg='#0f3460', border=0, padx=8, pady=2,
                  cursor='hand2', command=self._save_api_key).pack(side='left', padx=2)

        self.key_status = tk.Label(kf, font=('Segoe UI', 8, 'bold'), bg='#1a1a2e',
                                    text='Saved' if self.api_key else 'No key',
                                    fg='#44dd44' if self.api_key else '#ff6b6b')
        self.key_status.pack(side='left', padx=4)

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

        # Search row - main interaction
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

        tk.Label(sf, text='Enter serial numbers\nseparated by commas',
                 font=('Segoe UI', 7), fg='#666', bg='#1a1a2e', justify='left').pack(side='left', padx=8)

        # Profiles list header
        hf = tk.Frame(self.root, bg='#0f3460')
        hf.pack(fill='x', padx=15, pady=(8, 0))
        self.header_label = tk.Label(hf, text='Profile', font=('Segoe UI', 9, 'bold'),
                 fg='#fff', bg='#0f3460', width=20, anchor='w')
        self.header_label.pack(side='left', padx=(8, 0))
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

        # Initial message
        tk.Label(self.profiles_frame,
            text='Enter serial number(s) above and click FIND\n\n'
                 'Example: 27764\n'
                 'Multiple: 27764, 27763, 27762, 27761',
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

        if self.api_key:
            self._log(f'API key loaded from config')
        else:
            self._log('No API key set - enter your AdsPower API key above')

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
                resp = api_get(f'/api/v1/user/list?serial_number={serial}',
                               api_key=self.api_key)
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
                self._log('Make sure you entered the correct serial number')

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

    def _try_update_proxy(self, user_id, proxy_config):
        self._log('Method 1: user/update without API key...')
        resp = api_post('/api/v1/user/update', {
            'user_id': user_id,
            'user_proxy_config': proxy_config
        })
        if resp.get('code') == 0:
            return True, 'update_no_key'

        self._log(f'Method 1 failed: {resp.get("msg", "")}')

        if self.api_key:
            self._log('Method 2: user/update with API key...')
            resp = api_post('/api/v1/user/update', {
                'user_id': user_id,
                'user_proxy_config': proxy_config
            }, api_key=self.api_key)
            if resp.get('code') == 0:
                return True, 'update_with_key'
            self._log(f'Method 2 failed: {resp.get("msg", "")}')

        self._log('Method 3: stop + start with proxy config...')
        stop_resp = api_post('/api/v1/browser/stop', {'user_id': user_id},
                             api_key=self.api_key)
        self._log(f'Stop: {stop_resp.get("msg", "ok") if stop_resp.get("code") != 0 else "ok"}')
        time.sleep(1.5)

        proxy_json = json.dumps(proxy_config)
        encoded = urllib.parse.quote(proxy_json)
        start_resp = api_get(
            f'/api/v1/browser/start?user_id={user_id}&user_proxy_config={encoded}',
            api_key=self.api_key)
        if start_resp.get('code') == 0:
            return True, 'start_with_proxy'
        self._log(f'Method 3 failed: {start_resp.get("msg", "")}')

        self._log('Method 4: stop + start with launch args...')
        proxy_host = proxy_config.get('proxy_host', '')
        proxy_port = proxy_config.get('proxy_port', '')
        proxy_user = proxy_config.get('proxy_user', '')
        proxy_pass = proxy_config.get('proxy_password', '')

        if proxy_user:
            proxy_url = f'http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}'
        else:
            proxy_url = f'http://{proxy_host}:{proxy_port}'

        launch_args = json.dumps([f'--proxy-server={proxy_url}'])
        encoded_args = urllib.parse.quote(launch_args)
        start_resp2 = api_get(
            f'/api/v1/browser/start?user_id={user_id}&launch_args={encoded_args}',
            api_key=self.api_key)
        if start_resp2.get('code') == 0:
            return True, 'start_with_args'
        self._log(f'Method 4 failed: {start_resp2.get("msg", "")}')

        return False, None

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

            success, method = self._try_update_proxy(user_id, proxy_config)

            if not success:
                self._log(f'All methods failed for {user_id}')
                self._log('Try: AdsPower > API & MCP > Enable "API verification"')
                self.root.after(0, lambda: self._update_profile_ui(user_id, 'FAILED', '#ff4444'))
                return

            self._log(f'Success via {method}!')

            if method.startswith('update'):
                self._log(f'Proxy updated. Restarting browser...')
                stop_resp = api_post('/api/v1/browser/stop', {'user_id': user_id},
                                     api_key=self.api_key)
                if stop_resp.get('code') != 0:
                    self._log(f'Stop warning: {stop_resp.get("msg", "")}')
                time.sleep(1.5)
                start_resp = api_get(f'/api/v1/browser/start?user_id={user_id}',
                                     api_key=self.api_key)
                if start_resp.get('code') == 0:
                    self._log(f'Profile {user_id} restarted with {display}')
                else:
                    self._log(f'Browser restart failed - restart manually')
            else:
                self._log(f'Profile {user_id} started with {display}')

            self.root.after(0, lambda: self._update_profile_ui(user_id, display, '#44dd44'))

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
