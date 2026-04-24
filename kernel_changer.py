"""
Bulk Kernel Changer for AdsPower
Changes browser kernel version for all profiles at once.
"""

import tkinter as tk
from tkinter import messagebox
import threading
import json
import time

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

API_BASE = "http://127.0.0.1:50325"


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


class KernelChangerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('AdsPower Bulk Kernel Changer')
        self.root.geometry('500x450')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')
        self.running = False

        self._build_ui()

    def _log(self, msg):
        ts = time.strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        print(line)
        self.log_text.configure(state='normal')
        self.log_text.insert('end', line + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _build_ui(self):
        tk.Label(self.root, text='BULK KERNEL CHANGER',
                 font=('Segoe UI', 16, 'bold'),
                 fg='#e94560', bg='#1a1a2e').pack(pady=(15, 5))

        tk.Label(self.root, text='Change browser kernel for ALL profiles at once',
                 font=('Segoe UI', 9), fg='#8888aa', bg='#1a1a2e').pack()

        sf = tk.Frame(self.root, bg='#1a1a2e')
        sf.pack(pady=15)

        tk.Label(sf, text='Target Kernel:', font=('Segoe UI', 12, 'bold'),
                 fg='#FFD700', bg='#1a1a2e').pack(side='left', padx=(0, 10))

        self.kernel_var = tk.StringVar(value='141')
        versions = ['146', '145', '144', '143', '142', '141', '140', '139']
        kernel_menu = tk.OptionMenu(sf, self.kernel_var, *versions)
        kernel_menu.configure(font=('Consolas', 14, 'bold'), fg='#FFD700',
                               bg='#0f3460', activebackground='#16213e',
                               highlightthickness=0, width=6)
        kernel_menu.pack(side='left')

        bf = tk.Frame(self.root, bg='#1a1a2e')
        bf.pack(pady=10)

        self.start_btn = tk.Button(bf, text='CHANGE ALL PROFILES',
                  font=('Segoe UI', 12, 'bold'),
                  fg='#fff', bg='#e94560', activebackground='#ff6b8a',
                  border=0, padx=20, pady=8,
                  cursor='hand2', command=self._start_change)
        self.start_btn.pack(side='left', padx=5)

        self.count_btn = tk.Button(bf, text='COUNT PROFILES',
                  font=('Segoe UI', 10),
                  fg='#fff', bg='#0f3460', border=0, padx=12, pady=6,
                  cursor='hand2', command=self._count_profiles)
        self.count_btn.pack(side='left', padx=5)

        self.progress_label = tk.Label(self.root, text='',
                 font=('Segoe UI', 11, 'bold'),
                 fg='#44dd44', bg='#1a1a2e')
        self.progress_label.pack(pady=5)

        lf = tk.Frame(self.root, bg='#1a1a2e')
        lf.pack(fill='both', expand=True, padx=15, pady=(5, 15))
        tk.Label(lf, text='Log', font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack(anchor='w')
        self.log_text = tk.Text(lf, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                insertbackground='#44dd44', border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='both', expand=True, pady=2)

        self._log('Ready. Select target kernel version and click CHANGE ALL PROFILES.')
        self._log('Make sure AdsPower is running with Local API enabled.')

    def _count_profiles(self):
        def do_count():
            self._log('Counting profiles...')
            total = 0
            page = 1
            while True:
                resp = api_get(f'/api/v1/user/list?page={page}&page_size=100')
                if resp.get('code') != 0:
                    self._log(f'API error: {resp.get("msg", "")}')
                    break
                lst = resp.get('data', {}).get('list', [])
                if not lst:
                    break
                total += len(lst)
                page += 1

            self.root.after(0, lambda: self.progress_label.configure(
                text=f'Total profiles: {total}'))
            self._log(f'Found {total} profiles')

        threading.Thread(target=do_count, daemon=True).start()

    def _start_change(self):
        if self.running:
            return

        target = self.kernel_var.get()
        if not messagebox.askyesno('Confirm',
                f'Change ALL profiles to Chrome kernel {target}?\n\n'
                f'This will update every profile in AdsPower.\n'
                f'Profiles that are currently open will need to be\n'
                f'closed and reopened to use the new kernel.'):
            return

        self.running = True
        self.start_btn.configure(state='disabled', text='Working...')

        def do_change():
            page = 1
            success = 0
            failed = 0
            total = 0

            while True:
                resp = api_get(f'/api/v1/user/list?page={page}&page_size=100')
                if resp.get('code') != 0:
                    self.root.after(0, lambda: self._log(f'API error on page {page}: {resp.get("msg", "")}'))
                    break

                profiles = resp.get('data', {}).get('list', [])
                if not profiles:
                    break

                for p in profiles:
                    uid = p.get('user_id', '')
                    sn = p.get('serial_number', '')
                    total += 1

                    update_resp = api_post('/api/v1/user/update', {
                        'user_id': uid,
                        'fingerprint_config': {
                            'browser_kernel_config': {
                                'version': target,
                                'type': 'chrome'
                            }
                        }
                    })

                    if update_resp.get('code') == 0:
                        success += 1
                    else:
                        failed += 1
                        self.root.after(0, lambda s=sn, m=update_resp.get('msg', ''):
                            self._log(f'#{s}: FAILED - {m}'))

                    if total % 10 == 0:
                        self.root.after(0, lambda t=total, s=success, f=failed:
                            self.progress_label.configure(
                                text=f'Progress: {t} checked, {s} ok, {f} failed'))

                page += 1

            self.root.after(0, lambda: self._log(
                f'DONE! Changed {success} profiles to Chrome {target}. Failed: {failed}. Total: {total}.'))
            self.root.after(0, lambda: self.progress_label.configure(
                text=f'DONE: {success}/{total} changed to Chrome {target}'))
            self.root.after(0, lambda: self.start_btn.configure(
                state='normal', text='CHANGE ALL PROFILES'))
            self.running = False

        threading.Thread(target=do_change, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = KernelChangerApp()
    app.run()
