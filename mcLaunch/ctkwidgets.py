#import tkinter as tk
import tkinter.ttk as ttk
import tkinter as tk
from PIL import Image, ImageTk
import os



def geticon(icon_name, size=(64, 64)):
    """
    Retrieve an icon image and resize it to the specified size.

    Parameters:
    icon_name (str): The name of the icon file (without extension).
    """
    defaultpath=os.path.join(os.path.dirname(__file__),"images",icon_name+".png")
    if os.path.exists(defaultpath):
        result=ImageTk.PhotoImage(Image.open(defaultpath).resize(size))
    else:
        if os.path.exists(icon_name):
            result=ImageTk.PhotoImage(Image.open(icon_name).resize(size))
        else:
            result=ImageTk.PhotoImage(Image.open(os.path.join(os.path.dirname(__file__),"images","vanilla.png")).resize(size))
    return result


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        """
        Initializes a ScrollableFrame widget with a canvas and a vertical scrollbar.

        Parameters:
        parent : widget
        """
        super().__init__(parent, *args, **kwargs)
        
        self.canvas = tk.Canvas(self, bg="#2E3030")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,style="TScrollbar")
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            self._on_frame_configure
        )

        self.scrollable_frame_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # Bind mouse scroll events
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        self.scrollable_frame.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind_all("<Button-4>", self._on_mousewheel)
        self.scrollable_frame.bind_all("<Button-5>", self._on_mousewheel)

        # Bind canvas configure event
        self.bind("<Configure>", self.update_frame_size)
        self.scrollable_frame.bind("<Configure>", self.update_frame_size)

    def _on_mousewheel(self, event):
        """
        Handle mousewheel events to scroll the canvas.

        Parameters:
        event : tkinter event
        """
        # Get the bounding box of the canvas
        bbox = self.canvas.bbox("all")

        # Check if there is more content to scroll
        if bbox[3] > self.winfo_height():
            # If there is more content to scroll, scroll the canvas
            if event.num == 4 or event.delta > 0:
                # Scroll up
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                # Scroll down
                self.canvas.yview_scroll(1, "units")
        else:
            # If there is no more content to scroll, scroll to the top
            self.canvas.yview_scroll(0,"pages")

    def update_frame_size(self, event):
        # Make the internal frame's width match the canvas' width
        self.update()
        self.bindchilds()
        canvas_width = event.width
        self.canvas.itemconfig(self.scrollable_frame_window, width=canvas_width)
        self._on_frame_configure()
        
    def _on_frame_configure(self, event=None):
        """
        Handle the configure event of the internal frame.

        Parameters:
        event : tkinter event
            The configure event of the internal frame.

        Notes:
        This method is called by the canvas when the internal frame is
        resized. It updates the scrollregion of the canvas and checks if
        there is more content to scroll. If there is more content to scroll,
        it packs the scrollbar. If there is no more content to scroll, it
        hides the scrollbar.
        """
        # Update the scrollregion of the canvas
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        # Get the bounding box of the canvas
        bbox = self.canvas.bbox("all")

        # Update the window
        self.update()

        # Check if there is more content to scroll
        if bbox[3] > self.winfo_height():
            # If there is more content to scroll, show the scrollbar
            self.scrollbar.pack(side="right",fill="y")
        else:
            # If there is no more content to scroll, hide the scrollbar
            self.canvas.yview_scroll(0,"pages")
            self.scrollbar.pack_forget()

    def bindchilds(self, widget=None):
        """
        Bind the mousewheel event to all children of the given widget.

        Parameters:
        widget : widget
            The widget whose children to bind. If None, the internal frame is used.

        Notes:
        This method is called by the constructor and the update_frame_size method.
        """
        widget = widget or self.scrollable_frame
        for child in widget.winfo_children():
            # Unbind the mousewheel event from the child
            child.unbind("<MouseWheel>")
            child.unbind("<Button-4>")
            child.unbind("<Button-5>")

            # Bind the mousewheel event to the child
            if hasattr(child, "bind") and callable(child.bind):
                child.bind("<MouseWheel>", self._on_mousewheel)
                child.bind("<Button-4>", self._on_mousewheel)
                child.bind("<Button-5>", self._on_mousewheel)

                # Bind the mousewheel event to all children of the child
                self.bindchilds(child)
            
if __name__=="__main__":
    root=ttk.Tk()
    scrollzone=ScrollableFrame(root)
    scrollzone.pack(expand=True,fill="both")
    for i in range(30):
        ttk.Label(scrollzone.scrollable_frame,text=str(i)).pack()
    root.mainloop()