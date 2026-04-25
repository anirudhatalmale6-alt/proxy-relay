"""
AdsPower Queue Dashboard v3.0
Fully self-sufficient: scans for Chrome debug ports directly, evaluates
queue JS via CDP. Also listens on port 12345 for extension push data
as a bonus. No dependency on AdsPower API or extension being active.
"""

import tkinter as tk
from tkinter import messagebox
import threading
import json
import time
import re
import socket
import subprocess

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

from http.server import HTTPServer, BaseHTTPRequestHandler

VERSION = "3.0"
API_BASE = "http://127.0.0.1:50325"
LISTEN_PORT = 12345
SCAN_INTERVAL = 8

_app_ref = None

QUEUE_JS = r"""(function() {
    function parseNum(str) {
        var n = parseInt(String(str || '').replace(/,/g, ''), 10);
        return (n > 0 && n < 100000000) ? n : null;
    }
    var selectors = [
        '#MainPart_lbQueueNumber', '#lbQueueNumber', '[id*="lbQueueNumber"]',
        '#MainPart_h2HeaderSubText', '#h2-main', '.queue-position',
        '[class*="queue-position"]', '[class*="queuePosition"]',
        '[id*="queue-position"]', '[id*="queuePosition"]',
        '[class*="queueNumber"]', '[id*="queueNumber"]',
        '[class*="waiting-number"]', '[id*="waiting-number"]',
        '[class*="place-in-line"]', '[class*="placeInLine"]',
        '[class*="spot-number"]', '[data-queue-number]',
        '.number-display', '#queue-number'
    ];
    var patterns = [
        /you\s+are\s+(?:now\s+)?in\s+the\s+queue\s*#?\s*([\d,]{1,8})/i,
        /\bin\s+the\s+queue\s*#\s*([\d,]{1,8})/i,
        /([\d,]{1,8})\s+people\s+ahead\s+of\s+you/i,
        /([\d,]{1,8})\s+people?\s+ahead/i,
        /([\d,]{1,8})\s+waiting\s+ahead/i,
        /you\s+are\s+(?:now\s+)?(?:number\s+|#\s*)?([\d,]{1,8})\s+in/i,
        /(?:your\s+)?(?:queue\s+)?position\s+(?:is\s+)?(?:number\s+|#\s*)?([\d,]{1,8})/i,
        /you(?:'re| are)(?: currently)?\s+(?:number|#|position)\s*([\d,]{1,8})/i,
        /\bplace\s+#?([\d,]{1,8})/i,
        /#([\d,]{1,8})\s+in\s+(?:line|queue)/i,
        /there\s+are\s+([\d,]{1,8})\s+people/i
    ];
    function fromText(text) {
        text = String(text || '');
        for (var i = 0; i < patterns.length; i++) {
            var m = text.match(patterns[i]);
            if (m) { var n = parseNum(m[1]); if (n !== null) return n; }
        }
        return null;
    }
    for (var s = 0; s < selectors.length; s++) {
        try {
            var el = document.querySelector(selectors[s]);
            if (!el) continue;
            var cleaned = String(el.textContent || '').replace(/,/g, '').match(/\d+/);
            if (cleaned) { var n1 = parseNum(cleaned[0]); if (n1 !== null) return JSON.stringify({q: n1, u: location.href, t: document.title}); }
        } catch(e) {}
    }
    var text = document.body ? document.body.innerText : '';
    var textNum = fromText(text);
    if (textNum !== null) return JSON.stringify({q: textNum, u: location.href, t: document.title});
    return JSON.stringify({q: 0, u: location.href, t: document.title});
})()"""


def api_get(path):
    try:
        url = API_BASE + path
        req = urllib.request.Request(url, method='GET')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=4) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def http_get_json(url, timeout=3):
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except:
        return None


def cdp_evaluate(ws_url, expression, timeout=5):
    import hashlib
    msg_id = int(hashlib.md5(ws_url.encode()).hexdigest()[:8], 16) % 900000 + 100000
    try:
        host_port = ws_url.replace('ws://', '').split('/')[0]
        host, port = host_port.split(':')
        port = int(port)
        path = '/' + '/'.join(ws_url.replace('ws://', '').split('/')[1:])

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))

        import base64, os
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(handshake.encode())

        resp_data = b''
        while b'\r\n\r\n' not in resp_data:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                return None
            resp_data += chunk

        cmd = json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True}
        })
        frame = bytearray()
        payload = cmd.encode('utf-8')
        frame.append(0x81)
        mask_key = os.urandom(4)
        length = len(payload)
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, 'big'))
        else:
            frame.append(0x80 | 127)
            frame.extend(length.to_bytes(8, 'big'))
        frame.extend(mask_key)
        masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        frame.extend(masked)
        sock.sendall(frame)

        result_data = b''
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                result_data += chunk
                text = result_data.decode('utf-8', errors='ignore')
                if f'"id":{msg_id}' in text or f'"id": {msg_id}' in text:
                    break
            except socket.timeout:
                break

        sock.close()

        text = result_data.decode('utf-8', errors='ignore')
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            brace = line.find('{')
            if brace >= 0:
                candidate = line[brace:]
                try:
                    msg = json.loads(candidate)
                    if msg.get('id') == msg_id:
                        val = msg.get('result', {}).get('result', {}).get('value')
                        return val
                except:
                    pass
        return None
    except:
        return None


def clean_event_title(raw, url=''):
    if not raw:
        return event_from_url(url)
    cleaned = re.sub(r'\s*[|\-–—]\s*ticketmaster.*$', '', raw, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*[|\-–—]\s*livenation.*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*[|\-–—]\s*queue.*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if not cleaned or re.match(r'^\d[\d,\s]*$', cleaned):
        return event_from_url(url)
    return cleaned[:50]


def event_from_url(url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split('/') if p]
        skip = {'event', 'events', 'queue', 'checkout', 'tickets', 'signup', 'thewaitingroom', 'waitingroom'}
        for p in reversed(parts):
            if p.lower() not in skip and not re.match(r'^[0-9a-f]{8,}$', p, re.IGNORECASE) and not p.isdigit():
                return p.replace('-', ' ').replace('_', ' ').title()[:50]
    except:
        pass
    return ''


def is_tm_url(url):
    return bool(re.search(r'ticketmaster|livenation|queue-it', url, re.IGNORECASE))


def strip_prefix(key):
    if key and len(key) > 2 and key[1] == ':':
        return key[2:]
    return key


def find_chrome_debug_ports():
    """Find Chrome/Chromium debug ports by checking listening ports via netstat."""
    ports = set()
    try:
        output = subprocess.check_output(
            'netstat -ano | findstr "LISTENING" | findstr "127.0.0.1"',
            shell=True, timeout=5, stderr=subprocess.DEVNULL
        ).decode('utf-8', errors='ignore')
        for line in output.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                addr = parts[1]
                if ':' in addr:
                    try:
                        port = int(addr.split(':')[-1])
                        if 10000 <= port <= 60000 and port != LISTEN_PORT and port != 50325:
                            ports.add(port)
                    except:
                        pass
    except:
        pass
    return sorted(ports)


def check_debug_port(port):
    """Check if a port is a Chrome debug port by requesting /json."""
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{port}/json/version', method='GET')
        with urllib.request.urlopen(req, timeout=1) as resp:
            data = json.loads(resp.read().decode())
            browser = data.get('Browser', '')
            if 'Chrome' in browser or 'Chromium' in browser or 'SunBrowser' in browser:
                return True
    except:
        pass
    return False


class PushHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path != '/push':
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b''
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

        if _app_ref and body:
            try:
                data = json.loads(body.decode('utf-8'))
                _app_ref.root.after(0, lambda d=data: _app_ref._handle_push(d))
            except:
                pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b'{"status":"running","app":"QueueDashboard"}')


class ProfileRow:
    def __init__(self, debug_port, name='', serial='', uid=''):
        self.debug_port = debug_port
        self.serial = serial
        self.name = name
        self.uid = uid
        self.queue_num = 0
        self.event = ''
        self.link = ''
        self.status = 'Scanning...'
        self.last_update = 0
        self.ext_keys = set()


class QueueDashboardApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'AdsPower Queue Dashboard v{VERSION}')
        self.root.geometry('960x620')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')
        self.profiles = {}
        self.known_debug_ports = set()
        self.push_count = 0
        self.last_push_time = 0
        self.scanning = False
        self._build_ui()
        self._start_server()
        self._check_connection_loop()
        self.root.after(2000, self._scan_loop)

    def _log(self, msg):
        ts = time.strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        print(line)
        self.log_text.configure(state='normal')
        self.log_text.insert('end', line + '\n')
        self.log_text.see('end')
        if int(self.log_text.index('end-1c').split('.')[0]) > 200:
            self.log_text.delete('1.0', '50.0')
        self.log_text.configure(state='disabled')

    def _build_ui(self):
        top = tk.Frame(self.root, bg='#1a1a2e')
        top.pack(fill='x', padx=10, pady=(10, 3))

        tk.Label(top, text='QUEUE DASHBOARD',
                 font=('Segoe UI', 16, 'bold'),
                 fg='#e94560', bg='#1a1a2e').pack(side='left')

        tk.Label(top, text=f'v{VERSION}',
                 font=('Segoe UI', 9), fg='#555', bg='#1a1a2e').pack(side='left', padx=8)

        self.status_label = tk.Label(top, text='Starting...',
                                      font=('Segoe UI', 9), fg='#888', bg='#1a1a2e')
        self.status_label.pack(side='right')

        self.conn_indicator = tk.Label(top, text='●', font=('Segoe UI', 12),
                                        fg='#ff4444', bg='#1a1a2e')
        self.conn_indicator.pack(side='right', padx=(0, 8))

        btn_frame = tk.Frame(self.root, bg='#1a1a2e')
        btn_frame.pack(fill='x', padx=10, pady=3)

        tk.Button(btn_frame, text='Refresh All Tabs', font=('Segoe UI', 9, 'bold'),
                  fg='#fff', bg='#0f3460', border=0, padx=10, pady=4,
                  cursor='hand2', command=self._refresh_all).pack(side='left', padx=2)

        tk.Button(btn_frame, text='Scan Now', font=('Segoe UI', 9, 'bold'),
                  fg='#fff', bg='#28a745', border=0, padx=10, pady=4,
                  cursor='hand2', command=self._force_scan).pack(side='left', padx=2)

        tk.Button(btn_frame, text='Clear Data', font=('Segoe UI', 9),
                  fg='#fff', bg='#333', border=0, padx=10, pady=4,
                  cursor='hand2', command=self._clear_data).pack(side='left', padx=2)

        discord_frame = tk.Frame(btn_frame, bg='#1a1a2e')
        discord_frame.pack(side='right')

        tk.Label(discord_frame, text='Discord:', font=('Segoe UI', 8),
                 fg='#888', bg='#1a1a2e').pack(side='left')
        self.discord_name_entry = tk.Entry(discord_frame, font=('Segoe UI', 8),
                                            bg='#0a0a1a', fg='#fff', insertbackground='#fff',
                                            width=10, border=1)
        self.discord_name_entry.pack(side='left', padx=2)
        self.discord_name_entry.insert(0, 'Name')

        self.discord_hook_entry = tk.Entry(discord_frame, font=('Segoe UI', 8),
                                            bg='#0a0a1a', fg='#fff', insertbackground='#fff',
                                            width=30, border=1, show='*')
        self.discord_hook_entry.pack(side='left', padx=2)
        self.discord_hook_entry.insert(0, 'Webhook URL')
        self.discord_hook_entry.bind('<FocusIn>', lambda e: (
            self.discord_hook_entry.configure(show=''),
            self.discord_hook_entry.delete(0, 'end') if self.discord_hook_entry.get() == 'Webhook URL' else None
        ))

        tk.Button(discord_frame, text='Send', font=('Segoe UI', 8, 'bold'),
                  fg='#fff', bg='#5865F2', border=0, padx=8, pady=2,
                  cursor='hand2', command=self._send_discord).pack(side='left', padx=2)

        header_frame = tk.Frame(self.root, bg='#16213e')
        header_frame.pack(fill='x', padx=10, pady=(8, 0))

        cols = [('#', 30), ('Port', 55), ('Serial', 70), ('Name', 150), ('Queue #', 70),
                ('Event', 180), ('Link', 190), ('Status', 75), ('', 40)]
        for text, w in cols:
            tk.Label(header_frame, text=text, font=('Segoe UI', 9, 'bold'),
                     fg='#FFD700', bg='#16213e', width=w // 7, anchor='w').pack(side='left', padx=1)

        table_container = tk.Frame(self.root, bg='#1a1a2e')
        table_container.pack(fill='both', expand=True, padx=10, pady=2)

        self.table_canvas = tk.Canvas(table_container, bg='#0a0a1a', highlightthickness=0)
        scrollbar = tk.Scrollbar(table_container, orient='vertical', command=self.table_canvas.yview)
        self.table_inner = tk.Frame(self.table_canvas, bg='#0a0a1a')

        self.table_inner.bind('<Configure>',
                               lambda e: self.table_canvas.configure(scrollregion=self.table_canvas.bbox('all')))
        self.table_canvas.create_window((0, 0), window=self.table_inner, anchor='nw')
        self.table_canvas.configure(yscrollcommand=scrollbar.set)

        self.table_canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.table_canvas.bind_all('<MouseWheel>',
                                    lambda e: self.table_canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

        log_frame = tk.Frame(self.root, bg='#1a1a2e')
        log_frame.pack(fill='x', padx=10, pady=(3, 10))
        tk.Label(log_frame, text='Log', font=('Segoe UI', 8), fg='#888', bg='#1a1a2e').pack(anchor='w')
        self.log_text = tk.Text(log_frame, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                 height=5, border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='x')

        self._log(f'Queue Dashboard v{VERSION} started')
        self._log(f'Scanning for Chrome debug ports + listening on port {LISTEN_PORT}')

    def _start_server(self):
        global _app_ref
        _app_ref = self

        def run_server():
            try:
                server = HTTPServer(('127.0.0.1', LISTEN_PORT), PushHandler)
                server.serve_forever()
            except OSError as e:
                self.root.after(0, lambda: self._log(f'Port {LISTEN_PORT} in use: {e}'))

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

    def _check_connection_loop(self):
        now = time.time()
        if self.last_push_time > 0 and (now - self.last_push_time) < 15:
            self.conn_indicator.configure(fg='#44dd44')
        elif len(self.profiles) > 0:
            self.conn_indicator.configure(fg='#44dd44')
        else:
            self.conn_indicator.configure(fg='#ff4444')
        self.root.after(5000, self._check_connection_loop)

    def _handle_push(self, data):
        self.push_count += 1
        self.last_push_time = time.time()

        queue_map = data.get('profileQueueMap', {})
        link_map = data.get('profileLinkMap', {})
        event_map = data.get('profileEventMap', {})

        if self.push_count <= 3:
            self._log(f'Extension push #{self.push_count}: Q={len(queue_map)} L={len(link_map)} E={len(event_map)}')

        for key, profile in self.profiles.items():
            lookup_keys = set(profile.ext_keys)
            if profile.serial:
                lookup_keys.add('s:' + profile.serial)
            if profile.uid:
                lookup_keys.add('u:' + profile.uid)
            lookup_keys.add(key)
            lookup_keys.discard('')

            for lk in lookup_keys:
                q = queue_map.get(lk)
                if q is not None and isinstance(q, (int, float)) and q > 0:
                    profile.queue_num = int(q)
                    profile.status = 'In Queue'
                    profile.last_update = time.time()
                    break

            for lk in lookup_keys:
                link = link_map.get(lk)
                if link:
                    profile.link = str(link)
                    break

            for lk in lookup_keys:
                evt = event_map.get(lk)
                if evt:
                    profile.event = clean_event_title(str(evt), profile.link)
                    break

        self._update_status_bar()
        self._render_table()

    def _scan_loop(self):
        if not self.scanning:
            self.scanning = True
            threading.Thread(target=self._do_scan, daemon=True).start()
        self.root.after(SCAN_INTERVAL * 1000, self._scan_loop)

    def _force_scan(self):
        if not self.scanning:
            self.scanning = True
            self._log('Manual scan triggered...')
            threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        try:
            debug_ports = self._find_profile_ports()
            if not debug_ports and not self.profiles:
                self.root.after(0, lambda: self.status_label.configure(
                    text=f'No profiles found | {time.strftime("%H:%M:%S")}'))
                return

            current_ports = set()
            for port in debug_ports:
                current_ports.add(port)
                key = str(port)

                if key not in self.profiles:
                    name, serial, uid = self._get_profile_info(port)
                    self.profiles[key] = ProfileRow(port, name, serial, uid)
                    ext_keys = set()
                    if serial:
                        ext_keys.add('s:' + serial)
                    if uid:
                        ext_keys.add('u:' + uid)
                    self.profiles[key].ext_keys = ext_keys
                    self.root.after(0, lambda p=port, n=name, s=serial: self._log(
                        f'Found profile on port {p}: {s} ({n})'))

                self._scan_profile_tabs(self.profiles[key])
                time.sleep(0.3)

            stale = [k for k in self.profiles if k not in [str(p) for p in current_ports]]
            for k in stale:
                del self.profiles[k]

            self.root.after(0, self._update_status_bar)
            self.root.after(0, self._render_table)

        except Exception as e:
            self.root.after(0, lambda: self._log(f'Scan error: {e}'))
        finally:
            self.scanning = False

    def _find_profile_ports(self):
        """Find debug ports - try AdsPower API first, then scan ports directly."""
        ports = []

        for base in [API_BASE, 'http://local.adspower.net:50325']:
            try:
                req = urllib.request.Request(base + '/api/v1/browser/active?page=1&page_size=100')
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                if data.get('code') == 0:
                    d = data.get('data', {})
                    lst = d.get('list', []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
                    for p in lst:
                        dp = p.get('debug_port', 0)
                        if dp:
                            ports.append(int(str(dp)))
                            continue
                        ws = p.get('ws', {})
                        if isinstance(ws, dict):
                            ws_url = ws.get('puppeteer', ws.get('selenium', ''))
                            if ws_url:
                                m = re.search(r':(\d+)/', ws_url)
                                if m:
                                    ports.append(int(m.group(1)))
                    if ports:
                        return ports
            except:
                continue

        candidate_ports = find_chrome_debug_ports()
        for port in candidate_ports:
            if check_debug_port(port):
                ports.append(port)
            if len(ports) >= 50:
                break

        return ports

    def _get_profile_info(self, debug_port):
        """Try to get profile name/serial from AdsPower API or from tab titles."""
        name = ''
        serial = ''
        uid = ''

        tabs = http_get_json(f'http://127.0.0.1:{debug_port}/json')
        if tabs and isinstance(tabs, list):
            for tab in tabs:
                url = tab.get('url', '')
                if 'start.adspower.net' in url or 'start.adspower.com' in url:
                    m = re.search(r'[?&]id=([^&]+)', url)
                    if m:
                        uid = m.group(1)
                title = tab.get('title', '')
                if '@' in title and '.' in title:
                    name = title.strip()

        if uid:
            try:
                for base in [API_BASE, 'http://local.adspower.net:50325']:
                    r = http_get_json(f'{base}/api/v1/user/list?user_id={uid}')
                    if r and r.get('code') == 0:
                        lst = r.get('data', {}).get('list', [])
                        if lst:
                            p = lst[0]
                            serial = str(p.get('serial_number', p.get('serialnumber', '')))
                            if not name:
                                name = str(p.get('name', ''))
                            break
            except:
                pass

        return name, serial, uid

    def _scan_profile_tabs(self, profile):
        """Scan a profile's tabs for TM queue pages."""
        port = profile.debug_port
        if not port:
            return

        tabs = http_get_json(f'http://127.0.0.1:{port}/json')
        if not tabs or not isinstance(tabs, list):
            profile.status = 'No tabs'
            return

        page_tabs = [t for t in tabs if t.get('webSocketDebuggerUrl') and
                     t.get('type', 'page') == 'page' and
                     not re.match(r'^(devtools:|chrome:|chrome-extension:|about:|edge:)',
                                  t.get('url', ''), re.IGNORECASE)]

        if not page_tabs:
            profile.status = 'No tabs'
            return

        tm_tabs = [t for t in page_tabs if is_tm_url(t.get('url', ''))]

        if tm_tabs:
            for tab in tm_tabs:
                ws_url = tab.get('webSocketDebuggerUrl', '')
                if not ws_url:
                    continue

                profile.link = tab.get('url', '')
                profile.event = clean_event_title(tab.get('title', ''), profile.link)

                result = cdp_evaluate(ws_url, QUEUE_JS)
                if result:
                    try:
                        data = json.loads(result) if isinstance(result, str) else result
                        q = data.get('q', 0)
                        if q and q > 0:
                            profile.queue_num = q
                            profile.link = data.get('u', profile.link)
                            profile.event = clean_event_title(data.get('t', ''), profile.link)
                            profile.status = 'In Queue'
                            profile.last_update = time.time()
                            return
                    except:
                        pass

                profile.status = 'Waiting'
        else:
            tab = page_tabs[0]
            profile.link = tab.get('url', '')
            profile.event = clean_event_title(tab.get('title', ''), profile.link)
            profile.status = 'No TM page'

    def _update_status_bar(self):
        active_in_queue = sum(1 for p in self.profiles.values() if p.queue_num and p.queue_num > 0)
        ext = f' | Ext #{self.push_count}' if self.push_count > 0 else ''
        self.status_label.configure(
            text=f'{len(self.profiles)} profiles | {active_in_queue} in queue{ext} | {time.strftime("%H:%M:%S")}')

    def _render_table(self):
        for widget in self.table_inner.winfo_children():
            widget.destroy()

        sorted_profiles = sorted(self.profiles.values(),
                                  key=lambda p: (-(p.queue_num or 999999), p.serial or str(p.debug_port)))

        for idx, p in enumerate(sorted_profiles):
            bg = '#111122' if idx % 2 == 0 else '#0a0a1a'
            row = tk.Frame(self.table_inner, bg=bg)
            row.pack(fill='x', pady=0)

            tk.Label(row, text=str(idx + 1), font=('Consolas', 9),
                     fg='#666', bg=bg, width=4, anchor='w').pack(side='left', padx=1)

            tk.Label(row, text=str(p.debug_port), font=('Consolas', 8),
                     fg='#666', bg=bg, width=7, anchor='w').pack(side='left', padx=1)

            tk.Label(row, text=p.serial or '--', font=('Consolas', 9),
                     fg='#aaa', bg=bg, width=9, anchor='w').pack(side='left', padx=1)

            tk.Label(row, text=(p.name or '--')[:20], font=('Segoe UI', 9),
                     fg='#ddd', bg=bg, width=20, anchor='w').pack(side='left', padx=1)

            q_color = '#44dd44' if p.queue_num and p.queue_num > 0 else '#666'
            q_text = str(p.queue_num) if p.queue_num and p.queue_num > 0 else '--'
            tk.Label(row, text=q_text, font=('Consolas', 11, 'bold'),
                     fg=q_color, bg=bg, width=9, anchor='w').pack(side='left', padx=1)

            tk.Label(row, text=(p.event or '--')[:25], font=('Segoe UI', 9),
                     fg='#88aaff', bg=bg, width=25, anchor='w').pack(side='left', padx=1)

            link_short = ''
            if p.link:
                link_short = p.link.split('?')[0][-30:]
            tk.Label(row, text=link_short or '--', font=('Segoe UI', 8),
                     fg='#666', bg=bg, width=26, anchor='w').pack(side='left', padx=1)

            s_color = '#44dd44' if p.status == 'In Queue' else '#888'
            tk.Label(row, text=p.status, font=('Segoe UI', 8),
                     fg=s_color, bg=bg, width=10, anchor='w').pack(side='left', padx=1)

            close_btn = tk.Button(row, text='X', font=('Segoe UI', 7, 'bold'),
                                   fg='#ff4444', bg=bg, border=0, padx=4,
                                   cursor='hand2',
                                   command=lambda uid=p.uid: self._close_profile(uid))
            close_btn.pack(side='left', padx=1)

    def _refresh_all(self):
        def do_refresh():
            self._log('Refreshing all profile tabs...')
            count = 0
            for key, profile in list(self.profiles.items()):
                port = profile.debug_port
                if not port:
                    continue
                tabs = http_get_json(f'http://127.0.0.1:{port}/json')
                if not tabs:
                    continue
                for tab in tabs:
                    ws_url = tab.get('webSocketDebuggerUrl', '')
                    if not ws_url or tab.get('type', 'page') != 'page':
                        continue
                    cdp_evaluate(ws_url, 'location.reload()')
                    count += 1
                    time.sleep(0.2)
            self.root.after(0, lambda c=count: self._log(f'Refreshed {c} tabs'))
        threading.Thread(target=do_refresh, daemon=True).start()

    def _clear_data(self):
        for p in self.profiles.values():
            p.queue_num = 0
            p.event = ''
            p.link = ''
            p.status = 'Cleared'
        self._render_table()
        self._log('Queue data cleared')

    def _close_profile(self, uid):
        if not uid:
            return
        if not messagebox.askyesno('Close Profile', f'Close profile {uid}?'):
            return

        def do_close():
            resp = api_get(f'/api/v1/browser/stop?user_id={uid}')
            if resp.get('code') == 0:
                self.root.after(0, lambda: self._log(f'Profile {uid} closed'))
            else:
                self.root.after(0, lambda m=resp.get('msg', ''): self._log(f'Close failed: {m}'))
        threading.Thread(target=do_close, daemon=True).start()

    def _send_discord(self):
        name = self.discord_name_entry.get().strip()
        webhook = self.discord_hook_entry.get().strip()
        if not name or name == 'Name':
            self._log('Enter your Discord name first')
            return
        if not webhook or webhook == 'Webhook URL' or 'discord.com/api/webhooks' not in webhook:
            self._log('Enter a valid Discord webhook URL')
            return

        def do_send():
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            lines = [f'**Queue Dashboard** | {name} | {ts}\n']
            lines.append('```')
            lines.append(f'{"Serial":<10} {"Name":<20} {"Queue #":<10} {"Event":<30}')
            lines.append('-' * 72)

            sorted_p = sorted(self.profiles.values(),
                               key=lambda p: (-(p.queue_num or 999999), p.serial or ''))
            for p in sorted_p:
                q = str(p.queue_num) if p.queue_num and p.queue_num > 0 else '--'
                lines.append(f'{(p.serial or "--"):<10} {(p.name or "--")[:20]:<20} {q:<10} {(p.event or "--")[:30]:<30}')
            lines.append('```')

            content = '\n'.join(lines)
            payload = json.dumps({'username': f'{name} | Queue Dashboard', 'content': content})

            try:
                req = urllib.request.Request(webhook, data=payload.encode('utf-8'), method='POST')
                req.add_header('Content-Type', 'application/json')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status < 300:
                        self.root.after(0, lambda: self._log('Discord message sent!'))
                    else:
                        self.root.after(0, lambda: self._log(f'Discord error: {resp.status}'))
            except Exception as e:
                self.root.after(0, lambda: self._log(f'Discord send failed: {e}'))

        threading.Thread(target=do_send, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = QueueDashboardApp()
    app.run()
