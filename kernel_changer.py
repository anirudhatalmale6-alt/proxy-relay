"""
Bulk Kernel Changer for AdsPower
Pick a folder/group, pick kernel version, change all at once.
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
        self.root.geometry('550x520')
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')
        self.running = False
        self.groups = {}

        self._build_ui()
        self.root.after(500, self._load_groups)

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
                 fg='#e94560', bg='#1a1a2e').pack(pady=(15, 3))

        tk.Label(self.root, text='Pick a folder, pick a kernel, change all at once',
                 font=('Segoe UI', 9), fg='#8888aa', bg='#1a1a2e').pack(pady=(0, 10))

        gf = tk.Frame(self.root, bg='#1a1a2e')
        gf.pack(fill='x', padx=20, pady=5)

        tk.Label(gf, text='Folder:', font=('Segoe UI', 11, 'bold'),
                 fg='#FFD700', bg='#1a1a2e').pack(side='left')

        self.group_var = tk.StringVar(value='-- Loading groups --')
        self.group_menu = tk.OptionMenu(gf, self.group_var, '-- Loading --')
        self.group_menu.configure(font=('Segoe UI', 10), fg='#fff',
                                   bg='#0f3460', activebackground='#16213e',
                                   highlightthickness=0, width=35, anchor='w')
        self.group_menu.pack(side='left', padx=(8, 0), fill='x', expand=True)

        tk.Button(gf, text='Reload', font=('Segoe UI', 8),
                  fg='#fff', bg='#0f3460', border=0, padx=8, pady=2,
                  cursor='hand2', command=self._load_groups).pack(side='right', padx=(8, 0))

        kf = tk.Frame(self.root, bg='#1a1a2e')
        kf.pack(fill='x', padx=20, pady=5)

        tk.Label(kf, text='Kernel:', font=('Segoe UI', 11, 'bold'),
                 fg='#FFD700', bg='#1a1a2e').pack(side='left')

        self.kernel_var = tk.StringVar(value='141')
        versions = ['146', '145', '144', '143', '142', '141', '140', '139']
        kernel_menu = tk.OptionMenu(kf, self.kernel_var, *versions)
        kernel_menu.configure(font=('Consolas', 13, 'bold'), fg='#FFD700',
                               bg='#0f3460', activebackground='#16213e',
                               highlightthickness=0, width=6)
        kernel_menu.pack(side='left', padx=(8, 0))

        bf = tk.Frame(self.root, bg='#1a1a2e')
        bf.pack(pady=12)

        self.start_btn = tk.Button(bf, text='CHANGE KERNEL FOR FOLDER',
                  font=('Segoe UI', 12, 'bold'),
                  fg='#fff', bg='#e94560', activebackground='#ff6b8a',
                  border=0, padx=20, pady=8,
                  cursor='hand2', command=self._start_change)
        self.start_btn.pack()

        self.progress_label = tk.Label(self.root, text='',
                 font=('Segoe UI', 11, 'bold'),
                 fg='#44dd44', bg='#1a1a2e')
        self.progress_label.pack(pady=3)

        lf = tk.Frame(self.root, bg='#1a1a2e')
        lf.pack(fill='both', expand=True, padx=15, pady=(5, 15))
        tk.Label(lf, text='Log', font=('Segoe UI', 8), fg='#8888aa', bg='#1a1a2e').pack(anchor='w')
        self.log_text = tk.Text(lf, font=('Consolas', 8), bg='#0a0a1a', fg='#44dd44',
                                insertbackground='#44dd44', border=0, wrap='word', state='disabled')
        self.log_text.pack(fill='both', expand=True, pady=2)

        self._log('Loading groups from AdsPower...')

    def _load_groups(self):
        def do_load():
            self.groups = {}

            page = 1
            while True:
                resp = None
                for attempt in range(3):
                    resp = api_get(f'/api/v1/group/list?page={page}&page_size=100')
                    if resp.get('code') == 0:
                        break
                    if 'Too many request' in resp.get('msg', ''):
                        time.sleep(1.5)
                    else:
                        break

                if resp.get('code') != 0:
                    break
                grp_list = resp.get('data', {}).get('list', [])
                if isinstance(resp.get('data'), list):
                    grp_list = resp['data']
                if not grp_list:
                    break
                for g in grp_list:
                    gid = str(g.get('group_id', ''))
                    gname = g.get('group_name', f'Group {gid}')
                    if gid:
                        self.groups[gname] = gid
                self.root.after(0, lambda c=len(self.groups): self._log(
                    f'Loading folders... {c} so far'))
                page += 1
                time.sleep(0.5)

            if self.groups:
                self.root.after(0, lambda: self._log(
                    f'Loaded {len(self.groups)} group(s) from API'))
            else:
                self.root.after(0, lambda: self._log(
                    'Group API empty. Scanning profiles for groups...'))

            page = 1
            while True:
                r = None
                for attempt in range(3):
                    r = api_get(f'/api/v1/user/list?page={page}&page_size=100')
                    if r.get('code') == 0:
                        break
                    if 'Too many request' in r.get('msg', ''):
                        time.sleep(1.5)
                    else:
                        break

                if r.get('code') != 0:
                    break
                lst = r.get('data', {}).get('list', [])
                if not lst:
                    break
                for p in lst:
                    gid = str(p.get('group_id', '0'))
                    gname = p.get('group_name', '')
                    if gname and gid and gname not in self.groups:
                        self.groups[gname] = gid
                page += 1
                time.sleep(0.5)

            self.root.after(0, lambda: self._log(
                f'Total: {len(self.groups)} folder(s) found'))

            self.root.after(0, self._update_group_menu)

        threading.Thread(target=do_load, daemon=True).start()

    def _update_group_menu(self):
        menu = self.group_menu['menu']
        menu.delete(0, 'end')

        menu.add_command(label='--- ALL PROFILES ---',
                         command=lambda: self.group_var.set('--- ALL PROFILES ---'))

        for name in sorted(self.groups.keys()):
            menu.add_command(label=name,
                             command=lambda n=name: self.group_var.set(n))

        if self.groups:
            self.group_var.set(sorted(self.groups.keys())[0])
        else:
            self.group_var.set('--- ALL PROFILES ---')

    def _start_change(self):
        if self.running:
            return

        target = self.kernel_var.get()
        selected = self.group_var.get()
        group_id = self.groups.get(selected)
        scope = selected if group_id else 'ALL PROFILES'

        if not messagebox.askyesno('Confirm',
                f'Change kernel to Chrome {target}\n'
                f'for: {scope}?\n\n'
                f'Open profiles need to be closed & reopened\n'
                f'to use the new kernel.'):
            return

        self.running = True
        self.start_btn.configure(state='disabled', text='Working...')

        def do_change():
            page = 1
            success = 0
            failed = 0
            total = 0
            skipped = 0

            while True:
                url = f'/api/v1/user/list?page={page}&page_size=100'
                if group_id:
                    url += f'&group_id={group_id}'

                resp = api_get(url)
                if resp.get('code') != 0:
                    self.root.after(0, lambda: self._log(
                        f'API error on page {page}: {resp.get("msg", "")}'))
                    break

                profiles = resp.get('data', {}).get('list', [])
                if not profiles:
                    break

                for p in profiles:
                    uid = p.get('user_id', '')
                    sn = p.get('serial_number', '')
                    total += 1

                    update_resp = None
                    for attempt in range(3):
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
                            break
                        if 'Too many request' in update_resp.get('msg', ''):
                            time.sleep(1.5)
                        else:
                            break

                    if update_resp.get('code') == 0:
                        success += 1
                    else:
                        failed += 1
                        msg = update_resp.get('msg', '')
                        self.root.after(0, lambda s=sn, m=msg:
                            self._log(f'#{s}: FAILED - {m}'))

                    if total % 10 == 0:
                        self.root.after(0, lambda t=total, s=success, f=failed:
                            self.progress_label.configure(
                                text=f'Progress: {t} done, {s} ok, {f} failed'))

                    time.sleep(0.5)

                page += 1

            self.root.after(0, lambda: self._log(
                f'DONE! {scope}: {success} changed to Chrome {target}. '
                f'Failed: {failed}. Total: {total}.'))
            self.root.after(0, lambda: self.progress_label.configure(
                text=f'DONE: {success}/{total} changed to Chrome {target}'))
            self.root.after(0, lambda: self.start_btn.configure(
                state='normal', text='CHANGE KERNEL FOR FOLDER'))
            self.running = False

        threading.Thread(target=do_change, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = KernelChangerApp()
    app.run()
