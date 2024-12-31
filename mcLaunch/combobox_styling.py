import tkinter as tk
import tkinter.ttk as ttk

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.title('Default Demo')
        self.geometry('420x200')

        style = ttk.Style()
        style.configure('my.TCombobox', arrowsize=30)
        style.configure('my.TCombobox.Vertical.TScrollbar', arrowsize=28)

        values = []
        for idx in range(1, 2000):
            values.append(f'Testing-{idx}')

        cbo = ttk.Combobox(self, values=values, style='my.TCombobox')
        cbo.grid(ipady=5)
        # ttk styling hack
        self.tk.eval('set popdown [ttk::combobox::PopdownWindow %s]' % cbo)
        self.tk.eval(f'$popdown.f.sb configure -style my.TCombobox.Vertical.TScrollbar')
        ttk.Scrollbar(self, orient='vertical').grid(row=0, column=1, sticky='ns')
if __name__ == '__main__':
    app = App()
    app.mainloop()