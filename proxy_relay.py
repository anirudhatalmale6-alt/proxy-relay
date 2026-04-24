"""
ProxyRelay v1.0 - Local proxy relay with HTTP control API
Runs a local HTTP proxy that forwards to authenticated upstream proxies.
Chrome extension controls which upstream proxy to use via REST API.

Setup: Set AdsPower profile proxy to 127.0.0.1:8899 (HTTP)
       Extension talks to control API on 127.0.0.1:8900
"""

import tkinter as tk
import socket
import select
import base64
import threading
import json
import os
import sys
import random
import time
from http.server import HTTPServer, BaseHTTPRequestHandler


VERSION = "1.0"


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_proxies_path():
    return os.path.join(get_app_dir(), 'proxies.txt')


def get_config_path():
    return os.path.join(get_app_dir(), 'relay_config.json')


def load_config():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {'proxy_port': 8899, 'api_port': 8900}


def save_config(cfg):
    try:
        with open(get_config_path(), 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


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
                        'port': int(parts[1]),
                        'username': parts[2],
                        'password': parts[3]
                    })
                elif len(parts) == 2:
                    proxies.append({
                        'host': parts[0],
                        'port': int(parts[1]),
                        'username': None,
                        'password': None
                    })
    except Exception as e:
        print(f'[Relay] Error loading proxies: {e}')
    return proxies


class ProxyForwarder:
    def __init__(self, local_port=8899):
        self.local_port = local_port
        self.upstream_host = None
        self.upstream_port = None
        self.upstream_user = None
        self.upstream_pass = None
        self.server_socket = None
        self.running = False
        self.thread = None
        self.connections = 0

    def set_upstream(self, host, port, username=None, password=None):
        self.upstream_host = host
        self.upstream_port = int(port)
        self.upstream_user = username
        self.upstream_pass = password

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        self.server_socket = None

    def restart(self):
        self.stop()
        time.sleep(0.2)
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _run_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(1.0)
            self.server_socket.bind(('127.0.0.1', self.local_port))
            self.server_socket.listen(50)
            print(f'[Relay] Proxy listening on 127.0.0.1:{self.local_port}')

            while self.running:
                try:
                    client_sock, addr = self.server_socket.accept()
                    client_sock.settimeout(30)
                    t = threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except OSError:
                    break
        except Exception as e:
            print(f'[Relay] Server error: {e}')
        finally:
            self.running = False

    def _handle_client(self, client_sock):
        upstream_sock = None
        try:
            if not self.upstream_host:
                client_sock.sendall(b'HTTP/1.1 502 No upstream proxy configured\r\n\r\n')
                client_sock.close()
                return

            self.connections += 1
            request_data = b''
            while b'\r\n\r\n' not in request_data:
                chunk = client_sock.recv(4096)
                if not chunk:
                    client_sock.close()
                    return
                request_data += chunk

            first_line = request_data.split(b'\r\n')[0].decode('utf-8', errors='replace')
            method = first_line.split(' ')[0]

            auth_header = ''
            if self.upstream_user and self.upstream_pass:
                auth_str = f'{self.upstream_user}:{self.upstream_pass}'
                auth_b64 = base64.b64encode(auth_str.encode()).decode()
                auth_header = f'Proxy-Authorization: Basic {auth_b64}\r\n'

            upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream_sock.settimeout(30)
            upstream_sock.connect((self.upstream_host, self.upstream_port))

            if method == 'CONNECT':
                header_end = request_data.index(b'\r\n\r\n')
                headers = request_data[:header_end].decode('utf-8', errors='replace')
                lines = headers.split('\r\n')
                new_request = lines[0] + '\r\n'
                if auth_header:
                    new_request += auth_header
                for line in lines[1:]:
                    if line.lower().startswith('proxy-authorization'):
                        continue
                    new_request += line + '\r\n'
                new_request += '\r\n'

                upstream_sock.sendall(new_request.encode())

                response = b''
                while b'\r\n\r\n' not in response:
                    chunk = upstream_sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk

                status_line = response.split(b'\r\n')[0].decode('utf-8', errors='replace')
                if '200' in status_line:
                    client_sock.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                    self._relay(client_sock, upstream_sock)
                else:
                    client_sock.sendall(response)
            else:
                header_end = request_data.index(b'\r\n\r\n')
                headers_part = request_data[:header_end].decode('utf-8', errors='replace')
                body_part = request_data[header_end + 4:]

                lines = headers_part.split('\r\n')
                new_request = lines[0] + '\r\n'
                if auth_header:
                    new_request += auth_header
                for line in lines[1:]:
                    if line.lower().startswith('proxy-authorization'):
                        continue
                    new_request += line + '\r\n'
                new_request += '\r\n'

                upstream_sock.sendall(new_request.encode() + body_part)
                self._relay(client_sock, upstream_sock)

        except Exception:
            pass
        finally:
            for s in [client_sock, upstream_sock]:
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

    def _relay(self, sock1, sock2):
        sockets = [sock1, sock2]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 30)
                if errored:
                    break
                if not readable:
                    break
                for s in readable:
                    data = s.recv(8192)
                    if not data:
                        return
                    target = sock2 if s is sock1 else sock1
                    target.sendall(data)
        except Exception:
            pass
        finally:
            for s in sockets:
                try:
                    s.close()
                except Exception:
                    pass


class RelayApp:
    def __init__(self):
        self.proxies = []
        self.current_proxy = None
        self.connected = False
        self.config = load_config()
        self.forwarder = ProxyForwarder(self.config.get('proxy_port', 8899))
        self.api_server = None
        self.log_lines = []

        self._load_proxies()
        self._start_api()
        self.forwarder.start()
        self._build_ui()

    def _log(self, msg):
        ts = time.strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        self.log_lines.append(line)
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-100:]
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
            self._log(f'Loaded {len(self.proxies)} proxies')
        else:
            self._log('No proxies.txt found - place it next to this .exe')

    def _save_proxies(self, proxy_lines):
        path = get_proxies_path()
        try:
            with open(path, 'w') as f:
                f.write(proxy_lines)
            self.proxies = load_proxies_from_file(path)
            self._log(f'Saved {len(self.proxies)} proxies')
        except Exception as e:
            self._log(f'Save error: {e}')

    def connect(self, proxy=None):
        if not self.proxies:
            self._log('No proxies loaded')
            return False

        if proxy is None:
            proxy = random.choice(self.proxies)

        self.forwarder.set_upstream(
            proxy['host'], proxy['port'],
            proxy.get('username'), proxy.get('password')
        )

        if not self.forwarder.running:
            self.forwarder.start()

        self.current_proxy = proxy
        self.connected = True
        display = f"{proxy['host']}:{proxy['port']}"
        self._log(f'Upstream -> {display}')
        self._update_ui()
        return True

    def rotate(self):
        if not self.proxies:
            self._log('No proxies to rotate')
            return False

        if len(self.proxies) > 1 and self.current_proxy:
            available = [p for p in self.proxies
                         if p['host'] != self.current_proxy['host'] or
                            p['port'] != self.current_proxy['port']]
            proxy = random.choice(available) if available else random.choice(self.proxies)
        else:
            proxy = random.choice(self.proxies)

        return self.connect(proxy)

    def disconnect(self):
        self.forwarder.set_upstream(None, None)
        self.current_proxy = None
        self.connected = False
        self._log('Disconnected - no upstream')
        self._update_ui()

    def get_status(self):
        return {
            'connected': self.connected,
            'proxy': f"{self.current_proxy['host']}:{self.current_proxy['port']}" if self.current_proxy else None,
            'proxy_count': len(self.proxies),
            'proxy_port': self.config.get('proxy_port', 8899),
            'version': VERSION
        }

    def _start_api(self):
        app = self
        api_port = self.config.get('api_port', 8900)

        class APIHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def _cors(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')

            def _json_response(self, data, code=200):
                self.send_response(code)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self):
                if self.path == '/status':
                    self._json_response(app.get_status())
                elif self.path == '/proxies':
                    lines = []
                    for p in app.proxies:
                        if p.get('username') and p.get('password'):
                            lines.append(f"{p['host']}:{p['port']}:{p['username']}:{p['password']}")
                        else:
                            lines.append(f"{p['host']}:{p['port']}")
                    self._json_response({'proxies': lines, 'count': len(lines)})
                else:
                    self._json_response({'error': 'not found'}, 404)

            def do_POST(self):
                if self.path == '/connect':
                    ok = app.connect()
                    self._json_response({'success': ok, 'status': app.get_status()})
                elif self.path == '/rotate':
                    ok = app.rotate()
                    self._json_response({'success': ok, 'status': app.get_status()})
                elif self.path == '/disconnect':
                    app.disconnect()
                    self._json_response({'success': True, 'status': app.get_status()})
                elif self.path == '/proxies':
                    length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(length).decode('utf-8', errors='replace')
                    try:
                        data = json.loads(body)
                        proxy_text = data.get('proxies', '')
                        app._save_proxies(proxy_text)
                        self._json_response({'success': True, 'count': len(app.proxies)})
                    except Exception as e:
                        self._json_response({'success': False, 'error': str(e)}, 400)
                else:
                    self._json_response({'error': 'not found'}, 404)

        def run_api():
            try:
                server = HTTPServer(('127.0.0.1', api_port), APIHandler)
                self.api_server = server
                self._log(f'API listening on 127.0.0.1:{api_port}')
                server.serve_forever()
            except Exception as e:
                self._log(f'API error: {e}')

        t = threading.Thread(target=run_api, daemon=True)
        t.start()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title(f'ProxyRelay v{VERSION}')
        self.root.geometry('380x420')
        self.root.resizable(False, False)
        self.root.configure(bg='#1a1a2e')

        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        # Title
        tf = tk.Frame(self.root, bg='#1a1a2e')
        tf.pack(fill='x', padx=15, pady=(10, 5))
        tk.Label(tf, text='PROXY RELAY', font=('Segoe UI', 16, 'bold'),
                 fg='#e94560', bg='#1a1a2e').pack()
        tk.Label(tf, text=f'v{VERSION} - Local proxy forwarder for AdsPower',
                 font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack()

        # Status
        sf = tk.Frame(self.root, bg='#16213e', highlightbackground='#0f3460', highlightthickness=1)
        sf.pack(fill='x', padx=15, pady=8)
        self.status_label = tk.Label(sf, text='NOT CONNECTED', font=('Segoe UI', 13, 'bold'),
                                     fg='#ff6b6b', bg='#16213e')
        self.status_label.pack(pady=(10, 2))
        self.proxy_label = tk.Label(sf, text='No upstream proxy', font=('Consolas', 10),
                                    fg='#8888aa', bg='#16213e')
        self.proxy_label.pack(pady=(0, 4))
        self.count_label = tk.Label(sf, text=f'Proxies: {len(self.proxies)}',
                                     font=('Segoe UI', 9), fg='#8888aa', bg='#16213e')
        self.count_label.pack(pady=(0, 10))

        # Port info
        pf = tk.Frame(self.root, bg='#1a1a2e')
        pf.pack(fill='x', padx=15, pady=2)
        proxy_port = self.config.get('proxy_port', 8899)
        api_port = self.config.get('api_port', 8900)
        tk.Label(pf, text=f'Proxy: 127.0.0.1:{proxy_port}  |  API: 127.0.0.1:{api_port}',
                 font=('Consolas', 8), fg='#666', bg='#1a1a2e').pack()

        # Buttons
        bf = tk.Frame(self.root, bg='#1a1a2e')
        bf.pack(fill='x', padx=15, pady=8)

        self.connect_btn = tk.Button(bf, text='CONNECT', font=('Segoe UI', 11, 'bold'),
                                      fg='#ffffff', bg='#4CAF50', activebackground='#66BB6A',
                                      activeforeground='#ffffff', border=0, pady=8,
                                      cursor='hand2', command=self._on_connect)
        self.connect_btn.pack(fill='x', pady=2)

        self.rotate_btn = tk.Button(bf, text='ROTATE PROXY', font=('Segoe UI', 10, 'bold'),
                                     fg='#ffffff', bg='#FF9800', activebackground='#FFB74D',
                                     activeforeground='#ffffff', border=0, pady=6,
                                     cursor='hand2', command=self._on_rotate, state='disabled')
        self.rotate_btn.pack(fill='x', pady=2)

        self.disconnect_btn = tk.Button(bf, text='DISCONNECT', font=('Segoe UI', 10, 'bold'),
                                         fg='#ffffff', bg='#f44336', activebackground='#EF5350',
                                         activeforeground='#ffffff', border=0, pady=6,
                                         cursor='hand2', command=self._on_disconnect, state='disabled')
        self.disconnect_btn.pack(fill='x', pady=2)

        # Log
        lf = tk.Frame(self.root, bg='#1a1a2e')
        lf.pack(fill='both', expand=True, padx=15, pady=(4, 10))
        tk.Label(lf, text='Log', font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack(anchor='w')
        self.log_text = tk.Text(lf, height=5, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                insertbackground='#44dd44', border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='both', expand=True, pady=2)

        for line in self.log_lines:
            self.log_text.configure(state='normal')
            self.log_text.insert('end', line + '\n')
            self.log_text.configure(state='disabled')

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _update_ui(self):
        if not hasattr(self, 'status_label'):
            return
        try:
            if self.connected and self.current_proxy:
                self.status_label.configure(text='CONNECTED', fg='#4CAF50')
                self.proxy_label.configure(
                    text=f"{self.current_proxy['host']}:{self.current_proxy['port']}",
                    fg='#44dd44')
                self.connect_btn.configure(state='disabled')
                self.rotate_btn.configure(state='normal')
                self.disconnect_btn.configure(state='normal')
            else:
                self.status_label.configure(text='NOT CONNECTED', fg='#ff6b6b')
                self.proxy_label.configure(text='No upstream proxy', fg='#8888aa')
                self.connect_btn.configure(state='normal')
                self.rotate_btn.configure(state='disabled')
                self.disconnect_btn.configure(state='disabled')
            self.count_label.configure(text=f'Proxies: {len(self.proxies)}')
        except Exception:
            pass

    def _on_connect(self):
        self.connect()

    def _on_rotate(self):
        self.rotate()

    def _on_disconnect(self):
        self.disconnect()

    def _on_close(self):
        self.forwarder.stop()
        if self.api_server:
            self.api_server.shutdown()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = RelayApp()
    app.run()
