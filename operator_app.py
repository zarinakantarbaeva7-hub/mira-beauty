"""Локальное приложение оператора: заявки, поиск, детали и CSV.

Работает с той же локальной базой, что и Flask-сайт. Для серверной
базы используйте веб-админку; автоматической синхронизации здесь нет.
"""
import csv
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import DB, MASTER_MAP, SERVICE_MAP, database
from data import STATUS_LABELS


class BookingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Mira Beauty — рабочее место оператора')
        self.geometry('1200x650')
        self.minsize(850, 470)
        self.rows = []
        style = ttk.Style(self)
        style.configure('Treeview', rowheight=30)
        ttk.Label(self, text='Mira Beauty / Заявки клиентов',
                  font=('Arial', 20, 'bold')).pack(anchor='w', padx=24, pady=24)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', padx=24)
        ttk.Label(toolbar, text='Имя, телефон или номер:').pack(side='left')
        self.search = tk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=self.search, width=30)
        entry.pack(side='left', padx=10)
        entry.bind('<Return>', lambda event: self.refresh())
        ttk.Button(toolbar, text='Найти / обновить', command=self.refresh).pack(side='left')
        ttk.Button(toolbar, text='Экспорт CSV', command=self.export).pack(side='right')
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=24, pady=20)
        self.columns = ('id', 'name', 'phone', 'service', 'master', 'date', 'time', 'status')
        self.headings = ('Номер', 'Имя', 'Телефон', 'Услуга', 'Мастер', 'Дата', 'Время', 'Статус')
        self.table = ttk.Treeview(frame, columns=self.columns, show='headings', selectmode='browse')
        for key, title in zip(self.columns, self.headings):
            self.table.heading(key, text=title)
            self.table.column(key, width=135, minwidth=85)
        self.table.column('service', width=190)
        self.table.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.table.bind('<<TreeviewSelect>>', self.detail)
        self.note = ttk.Label(self, text='', wraplength=1000)
        self.note.pack(anchor='w', padx=24, pady=(0, 10))
        ttk.Label(self, text='Статусы меняются в защищённой веб-админке сайта. '
                  'Здесь отображается локальная база.', foreground='#687267').pack(anchor='w', padx=24, pady=(0, 20))
        self.refresh()

    def values(self, row):
        return (row['id'], row['name'], row['phone'],
                SERVICE_MAP.get(row['service'], {'name': row['service']})['name'],
                MASTER_MAP.get(row['master'], {'name': 'Уточнить'})['name'],
                row['visit_date'], row['visit_time'] or 'Уточнить',
                STATUS_LABELS.get(row['status'], row['status']))

    def refresh(self):
        query = '%' + self.search.get().strip() + '%'
        try:
            with database(DB) as connection:
                self.rows = [dict(row) for row in connection.execute(
                    '''SELECT * FROM bookings WHERE name LIKE ? OR phone LIKE ? OR id LIKE ?
                       ORDER BY visit_date DESC, visit_time DESC''', (query, query, query))]
        except sqlite3.Error:
            messagebox.showerror('База данных', 'Не удалось прочитать заявки.')
            return
        self.table.delete(*self.table.get_children())
        for row in self.rows:
            self.table.insert('', 'end', iid=row['id'], values=self.values(row))
        self.note.config(text=f'Найдено заявок: {len(self.rows)}. Выберите строку для просмотра комментария.')

    def detail(self, event=None):
        selected = self.table.selection()
        if selected:
            row = next(row for row in self.rows if row['id'] == selected[0])
            self.note.config(text=f"Комментарий: {row['comment'] or 'Не указан'}. Создана: {row['created_at']}")

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(self.headings)
                for row in self.rows:
                    values = self.values(row)
                    writer.writerow(["'" + str(value) if str(value).lstrip().startswith(('=', '+', '-', '@'))
                                     else value for value in values])
            messagebox.showinfo('Экспорт', 'Текущий список заявок сохранён.')
        except OSError:
            messagebox.showerror('Экспорт', 'Не удалось записать файл. Выберите другую папку.')


if __name__ == '__main__':
    BookingApp().mainloop()
