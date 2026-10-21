"""Локальное приложение оператора. Использует ту же SQLite, что и сайт."""
import argparse
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from app import connect

class OperatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('RepairLab — заявки мастерской')
        self.geometry('1050x600')
        self.minsize(760, 420)
        ttk.Label(self, text='RepairLab / Рабочее место оператора', font=('Arial', 18, 'bold')).pack(anchor='w', padx=20, pady=20)
        toolbar = ttk.Frame(self); toolbar.pack(fill='x', padx=20)
        ttk.Button(toolbar, text='Обновить', command=self.refresh).pack(side='left')
        self.status = ttk.Combobox(toolbar, values=['Новая', 'В работе', 'Завершена'], state='readonly', width=16)
        self.status.set('В работе'); self.status.pack(side='left', padx=10)
        ttk.Button(toolbar, text='Изменить статус', command=self.update_status).pack(side='left')
        ttk.Button(toolbar, text='Экспорт CSV', command=self.export).pack(side='right')
        frame = ttk.Frame(self); frame.pack(fill='both', expand=True, padx=20, pady=20)
        columns = ('id', 'name', 'phone', 'service', 'visit_date', 'status')
        self.table = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for key, label in zip(columns, ['Номер', 'Имя', 'Телефон', 'Устройство', 'Дата', 'Статус']):
            self.table.heading(key, text=label); self.table.column(key, width=140, minwidth=80)
        self.table.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(frame, command=self.table.yview); scrollbar.pack(side='right', fill='y')
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind('<<TreeviewSelect>>', self.show_detail)
        self.detail = ttk.Label(self, text='Выберите заявку, чтобы прочитать описание.', wraplength=900)
        self.detail.pack(anchor='w', padx=20, pady=(0,20))
        self.refresh()

    def refresh(self):
        with connect() as conn:
            self.rows = [dict(r) for r in conn.execute('SELECT * FROM requests ORDER BY created_at DESC')]
        self.table.delete(*self.table.get_children())
        for row in self.rows:
            self.table.insert('', 'end', iid=row['id'], values=[row[k] for k in self.table['columns']])
        self.detail.config(text=f'Всего заявок: {len(self.rows)}. Выберите заявку для просмотра.')

    def show_detail(self, event=None):
        selected = self.table.selection()
        if selected:
            row = next(r for r in self.rows if r['id'] == selected[0])
            self.detail.config(text='Описание: ' + row['problem'])

    def update_status(self):
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo('Выберите заявку', 'Сначала выделите строку в таблице.'); return
        with connect() as conn:
            conn.execute('UPDATE requests SET status=? WHERE id=?', (self.status.get(), selected[0]))
        self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if path:
            with open(path, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.DictWriter(file, fieldnames=['id','name','phone','service','visit_date','problem','created_at','status'])
                writer.writeheader()
                # Защита от выполнения формул при открытии в таблицах.
                for row in self.rows:
                    writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for k,v in row.items()})
            messagebox.showinfo('Экспорт', 'Заявки сохранены в CSV.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--list', action='store_true', help='Список заявок без графического окна')
    if parser.parse_args().list:
        with connect() as conn:
            for row in conn.execute('SELECT id,service,visit_date,status FROM requests ORDER BY created_at DESC'):
                print(' | '.join(row))
    else:
        OperatorApp().mainloop()
