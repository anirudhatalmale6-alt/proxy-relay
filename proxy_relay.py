"""
ProxyRotator v6.0 - Instant Proxy Rotation for AdsPower
ADD = sets up relay + one restart. After that, ROTATE is instant (no restart).
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
import socket
import base64
import select

try:
    import urllib.request
    import urllib.error
    import urllib.parse
except ImportError:
    pass

VERSION = "6.0"
API_BASE = "http://127.0.0.1:50325"
CONFIG_FILE = "proxyrotator.json"
BASE_PORT = 10100


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
        with urllib.request.urlopen(req, timeout=15) as resp:
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


def stop_browser(user_id):
    for fn in [
        lambda: api_get(f'/api/v1/browser/stop?user_id={user_id}'),
        lambda: api_post('/api/v1/browser/stop', {'user_id': user_id}),
    ]:
        r = fn()
        if r.get('code') == 0:
            return True
    return False


def start_browser(user_id):
    return api_get(f'/api/v1/browser/start?user_id={user_id}')


class RelayProxy:
    def __init__(self, port):
        self.port = port
        self.upstream_host = ''
        self.upstream_port = 0
        self.upstream_user = ''
        self.upstream_pass = ''
        self.server_socket = None
        self.running = False

    def set_upstream(self, host, port, user='', password=''):
        self.upstream_host = host
        self.upstream_port = int(port) if port else 0
        self.upstream_user = user
        self.upstream_pass = password

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1)
        self.server_socket.bind(('127.0.0.1', self.port))
        self.server_socket.listen(50)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.server_socket.accept()
                client.settimeout(30)
                threading.Thread(target=self._handle, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    continue
                break

    def _handle(self, client):
        proxy_sock = None
        try:
            data = b''
            while b'\r\n' not in data:
                chunk = client.recv(8192)
                if not chunk:
                    return
                data += chunk

            if not self.upstream_host or not self.upstream_port:
                client.close()
                return

            proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_sock.settimeout(15)
            proxy_sock.connect((self.upstream_host, self.upstream_port))

            if self.upstream_user:
                creds = f'{self.upstream_user}:{self.upstream_pass}'
                auth = base64.b64encode(creds.encode()).decode()
                auth_line = f'Proxy-Authorization: Basic {auth}\r\n'.encode()
                idx = data.find(b'\r\n') + 2
                data = data[:idx] + auth_line + data[idx:]

            proxy_sock.sendall(data)
            self._relay(client, proxy_sock)
        except Exception:
            pass
        finally:
            for s in [client, proxy_sock]:
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

    def _relay(self, s1, s2):
        sockets = [s1, s2]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 30)
                if errored:
                    break
                if not readable:
                    break
                for s in readable:
                    data = s.recv(65536)
                    if not data:
                        return
                    dst = s2 if s is s1 else s1
                    dst.sendall(data)
        except Exception:
            pass


class ProxyRotatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'ProxyRotator v{VERSION}')
        self.root.geometry('780x600')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')

        self.proxies = []
        self.profile_widgets = {}
        self.dashboard = {}
        self.relays = {}

        self._load_config_data()
        self._auto_load_proxies()
        self._build_ui()
        self._start_saved_relays()

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

    def _next_port(self):
        used = set()
        for info in self.dashboard.values():
            p = info.get('relay_port', 0)
            if p:
                used.add(p)
        port = BASE_PORT
        while port in used:
            port += 1
        return port

    def _start_saved_relays(self):
        started = 0
        for uid, info in self.dashboard.items():
            port = info.get('relay_port')
            if not port:
                continue

            relay = RelayProxy(port)

            if info.get('rotated') and info.get('rotated_proxy'):
                rp = info['rotated_proxy']
                relay.set_upstream(rp.get('host', ''), rp.get('port', 0),
                                   rp.get('username', ''), rp.get('password', ''))
            else:
                oc = info.get('original_config', {})
                relay.set_upstream(oc.get('proxy_host', ''), oc.get('proxy_port', 0),
                                   oc.get('proxy_user', ''), oc.get('proxy_password', ''))

            try:
                relay.start()
                self.relays[uid] = relay
                started += 1
            except Exception as e:
                print(f'Failed relay port {port}: {e}')

        if started:
            self._log(f'Restored {started} relay(s) from last session')

    def _build_ui(self):
        tf = tk.Frame(self.root, bg='#1a1a2e')
        tf.pack(fill='x', padx=15, pady=(10, 5))
        tk.Label(tf, text='PROXY ROTATOR', font=('Segoe UI', 16, 'bold'),
                 fg='#e94560', bg='#1a1a2e').pack()
        tk.Label(tf, text=f'v{VERSION} - ADD once (restarts), then ROTATE is instant',
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

        tk.Label(sf, text='Serial #:', font=('Segoe UI', 10, 'bold'),
                 fg='#FFD700', bg='#1a1a2e').pack(side='left')

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(sf, textvariable=self.search_var, font=('Consolas', 12),
                                bg='#0a0a1a', fg='#FFD700', insertbackground='#FFD700',
                                border=1, relief='solid', width=20)
        self.search_entry.pack(side='left', padx=(6, 4))
        self.search_entry.bind('<Return>', lambda e: self._add_profile())

        self.search_btn = tk.Button(sf, text='ADD', font=('Segoe UI', 10, 'bold'),
                  fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                  border=0, padx=14, pady=4,
                  cursor='hand2', command=self._add_profile)
        self.search_btn.pack(side='left', padx=4)

        tk.Label(sf, text='(restarts once to set up relay)',
                 font=('Segoe UI', 8), fg='#666', bg='#1a1a2e').pack(side='left', padx=4)

        info = tk.Label(self.root,
            text='ROTATE = instant proxy change (no restart!)  |  RESTORE = original (instant)  |  CLOSE+REST = close & restore',
            font=('Segoe UI', 7), fg='#FFD700', bg='#0f3460', pady=3)
        info.pack(fill='x', padx=15, pady=(5, 0))

        hf = tk.Frame(self.root, bg='#16213e')
        hf.pack(fill='x', padx=15, pady=(0, 0))
        for text, w in [('Serial', 7), ('Original Proxy', 16), ('Active Proxy', 16), ('Status', 8), ('', 28)]:
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
        self.log_text = tk.Text(lf, height=5, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                insertbackground='#44dd44', border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='x', pady=2)

        if self.proxies:
            self._log(f'Loaded {len(self.proxies)} proxies')
        else:
            self._log('No proxies found. Place proxies.txt next to exe or click "Load proxies.txt"')

        if self.dashboard:
            self._log(f'{len(self.dashboard)} profile(s) from last session - relays active')

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

    def _add_profile(self):
        raw = self.search_var.get().strip()
        if not raw:
            return

        serials = [s.strip() for s in raw.replace(' ', ',').split(',') if s.strip()]
        self.search_btn.configure(state='disabled', text='...')

        def do_add():
            for serial in serials:
                if any(d.get('serial') == serial for d in self.dashboard.values()):
                    self._log(f'{serial}: already in dashboard - ready to rotate')
                    continue

                self.root.after(0, lambda s=serial: self._log(f'{s}: looking up...'))
                resp = api_get(f'/api/v1/user/list?serial_number={serial}')
                if resp.get('code') != 0 or not resp.get('data', {}).get('list'):
                    self.root.after(0, lambda s=serial: self._log(f'{s}: not found in AdsPower'))
                    continue

                p = resp['data']['list'][0]
                uid = p.get('user_id', '')
                sn = str(p.get('serial_number', ''))
                proxy_cfg = p.get('user_proxy_config', {})
                ph = proxy_cfg.get('proxy_host', '')
                pp = proxy_cfg.get('proxy_port', '')
                orig_display = f'{ph}:{pp}' if ph else 'no proxy'

                port = self._next_port()
                relay = RelayProxy(port)
                if ph:
                    relay.set_upstream(ph, pp,
                                       proxy_cfg.get('proxy_user', ''),
                                       proxy_cfg.get('proxy_password', ''))
                try:
                    relay.start()
                except Exception as e:
                    self.root.after(0, lambda s=sn, e=e: self._log(f'{s}: relay failed - {e}'))
                    continue

                self.relays[uid] = relay

                local_proxy = {
                    'proxy_soft': 'other',
                    'proxy_type': 'http',
                    'proxy_host': '127.0.0.1',
                    'proxy_port': str(port),
                    'proxy_user': '',
                    'proxy_password': ''
                }

                self.root.after(0, lambda s=sn, pt=port: self._log(
                    f'{s}: setting relay on port {pt}...'))

                resp2 = api_post('/api/v1/user/update', {
                    'user_id': uid,
                    'user_proxy_config': local_proxy
                })

                if resp2.get('code') != 0:
                    self.root.after(0, lambda s=sn, m=resp2.get('msg', ''): self._log(
                        f'{s}: FAILED to set relay - {m}'))
                    relay.stop()
                    del self.relays[uid]
                    continue

                self.root.after(0, lambda s=sn: self._log(f'{s}: restarting browser (one time)...'))
                stop_browser(uid)
                time.sleep(0.5)
                start_browser(uid)

                self.dashboard[uid] = {
                    'serial': sn,
                    'user_id': uid,
                    'original_proxy': orig_display,
                    'original_config': dict(proxy_cfg),
                    'current_proxy': orig_display,
                    'relay_port': port,
                    'rotated': False,
                    'rotated_proxy': None,
                }
                self._save_dashboard()
                self.root.after(0, lambda s=sn: self._log(
                    f'{s}: READY! Click ROTATE for instant proxy change'))

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
                text='No profiles yet.\n\nType a serial number and click ADD.\n'
                     'Browser restarts ONCE to set up relay.\n'
                     'After that, ROTATE is instant - no restart!',
                font=('Segoe UI', 10), fg='#888', bg='#16213e', pady=30).pack()
            return

        for i, (uid, info) in enumerate(self.dashboard.items()):
            bg = '#1a2744' if i % 2 == 0 else '#16213e'
            row = tk.Frame(self.profiles_frame, bg=bg)
            row.pack(fill='x', padx=2, pady=1)

            tk.Label(row, text=info['serial'], font=('Consolas', 9, 'bold'),
                     fg='#ddd', bg=bg, width=7, anchor='w').pack(side='left', padx=(6, 0))

            orig = info.get('original_proxy', '?')
            if len(orig) > 16:
                orig = orig[:16] + '..'
            tk.Label(row, text=orig, font=('Consolas', 8), fg='#8888aa',
                     bg=bg, width=16, anchor='w').pack(side='left')

            cur = info.get('current_proxy', '?')
            if len(cur) > 16:
                cur = cur[:16] + '..'
            cur_color = '#FF9800' if info.get('rotated') else '#44dd44'
            cur_lbl = tk.Label(row, text=cur, font=('Consolas', 8, 'bold'),
                               fg=cur_color, bg=bg, width=16, anchor='w')
            cur_lbl.pack(side='left')

            status = 'ROTATED' if info.get('rotated') else 'ready'
            st_color = '#FF9800' if info.get('rotated') else '#44dd44'
            status_lbl = tk.Label(row, text=status, font=('Consolas', 8, 'bold'),
                                   fg=st_color, bg=bg, width=8, anchor='w')
            status_lbl.pack(side='left')

            remove_btn = tk.Button(row, text='X', font=('Segoe UI', 7, 'bold'),
                                    fg='#ff6b6b', bg=bg, border=0, padx=3,
                                    cursor='hand2',
                                    command=lambda u=uid: self._remove_profile(u))
            remove_btn.pack(side='right', padx=1, pady=2)

            rc_btn = tk.Button(row, text='CLOSE+REST', font=('Segoe UI', 7, 'bold'),
                                fg='#fff', bg='#607D8B', activebackground='#78909C',
                                border=0, padx=4, pady=2, cursor='hand2',
                                state='normal' if info.get('rotated') else 'disabled',
                                command=lambda u=uid: self._close_and_restore(u))
            rc_btn.pack(side='right', padx=1, pady=2)

            restore_btn = tk.Button(row, text='RESTORE', font=('Segoe UI', 7, 'bold'),
                                     fg='#fff', bg='#4CAF50', activebackground='#66BB6A',
                                     border=0, padx=4, pady=2, cursor='hand2',
                                     state='normal' if info.get('rotated') else 'disabled',
                                     command=lambda u=uid: self._restore_profile(u))
            restore_btn.pack(side='right', padx=1, pady=2)

            rotate_btn = tk.Button(row, text='ROTATE', font=('Segoe UI', 7, 'bold'),
                                    fg='#fff', bg='#FF9800', activebackground='#FFB74D',
                                    border=0, padx=4, pady=2, cursor='hand2',
                                    command=lambda u=uid: self._rotate_profile(u))
            rotate_btn.pack(side='right', padx=1, pady=2)

            self.profile_widgets[uid] = {
                'cur_lbl': cur_lbl,
                'status_lbl': status_lbl,
                'rotate_btn': rotate_btn,
                'restore_btn': restore_btn,
                'rc_btn': rc_btn,
            }

        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _rotate_profile(self, user_id):
        if not self.proxies:
            self._log('No proxies loaded!')
            messagebox.showwarning('No Proxies', 'Load proxies.txt first.')
            return

        relay = self.relays.get(user_id)
        if not relay:
            self._log('Relay not running - remove and re-add this profile')
            return

        info = self.dashboard.get(user_id)
        if not info:
            return

        serial = info.get('serial', '?')
        proxy = random.choice(self.proxies)
        display = f"{proxy['host']}:{proxy['port']}"

        relay.set_upstream(proxy['host'], proxy['port'],
                           proxy.get('username', ''), proxy.get('password', ''))

        self.dashboard[user_id]['current_proxy'] = display
        self.dashboard[user_id]['rotated'] = True
        self.dashboard[user_id]['rotated_proxy'] = dict(proxy)
        self._save_dashboard()

        self._log(f'{serial}: ROTATED to {display} (instant)')
        self._render_dashboard()

    def _restore_profile(self, user_id):
        info = self.dashboard.get(user_id)
        if not info or not info.get('rotated'):
            return

        relay = self.relays.get(user_id)
        if not relay:
            self._log('Relay not running')
            return

        serial = info.get('serial', '?')
        orig_cfg = info.get('original_config', {})

        relay.set_upstream(
            orig_cfg.get('proxy_host', ''),
            orig_cfg.get('proxy_port', 0),
            orig_cfg.get('proxy_user', ''),
            orig_cfg.get('proxy_password', '')
        )

        self.dashboard[user_id]['current_proxy'] = info.get('original_proxy', '?')
        self.dashboard[user_id]['rotated'] = False
        self.dashboard[user_id]['rotated_proxy'] = None
        self._save_dashboard()

        self._log(f'{serial}: RESTORED to original (instant)')
        self._render_dashboard()

    def _close_and_restore(self, user_id):
        info = self.dashboard.get(user_id)
        if not info:
            return

        serial = info.get('serial', '?')
        orig_cfg = info.get('original_config', {})

        def do_close():
            self.root.after(0, lambda: self._log(f'{serial}: restoring original proxy...'))
            api_post('/api/v1/user/update', {
                'user_id': user_id,
                'user_proxy_config': orig_cfg
            })

            self.root.after(0, lambda: self._log(f'{serial}: closing browser...'))
            stop_browser(user_id)

            relay = self.relays.pop(user_id, None)
            if relay:
                relay.stop()

            self.dashboard.pop(user_id, None)
            self._save_dashboard()

            self.root.after(0, lambda: self._log(
                f'{serial}: CLOSED & RESTORED - proxy back to original, removed from dashboard'))
            self.root.after(0, self._render_dashboard)

        threading.Thread(target=do_close, daemon=True).start()

    def _remove_profile(self, user_id):
        info = self.dashboard.get(user_id, {})
        serial = info.get('serial', '?')
        orig_cfg = info.get('original_config')

        def do_remove():
            if orig_cfg:
                api_post('/api/v1/user/update', {
                    'user_id': user_id,
                    'user_proxy_config': orig_cfg
                })

            relay = self.relays.pop(user_id, None)
            if relay:
                relay.stop()

            self.dashboard.pop(user_id, None)
            self._save_dashboard()
            self.root.after(0, lambda: self._log(f'{serial}: removed (proxy restored)'))
            self.root.after(0, self._render_dashboard)

        threading.Thread(target=do_remove, daemon=True).start()

    def _on_close(self):
        for uid, info in list(self.dashboard.items()):
            orig_cfg = info.get('original_config')
            if orig_cfg:
                try:
                    api_post('/api/v1/user/update', {
                        'user_id': uid,
                        'user_proxy_config': orig_cfg
                    })
                except Exception:
                    pass

        for relay in self.relays.values():
            relay.stop()

        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = ProxyRotatorApp()
    app.run()
