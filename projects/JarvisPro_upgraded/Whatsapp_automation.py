import tkinter as tk
from tkinter import messagebox
try:
    import pyautogui
except ImportError:
    pyautogui = None
try:
    import pyperclip
except ImportError:
    pyperclip = None
import threading
import time
from datetime import datetime


class WhatsAppScheduler:

    def __init__(self, root):

        self.root = root

        self.root.title("WhatsApp Desktop Scheduler")
        self.root.geometry("650x650")
        self.root.resizable(False, False)

        self.create_gui()

    # =========================================================
    # GUI
    # =========================================================

    def create_gui(self):

        title = tk.Label(
            self.root,
            text="WhatsApp Message Scheduler",
            font=("Arial", 22, "bold")
        )

        title.pack(pady=20)

        # -----------------------------------------------------
        # NAME
        # -----------------------------------------------------

        tk.Label(
            self.root,
            text="Receiver Name",
            font=("Arial", 12)
        ).pack()

        self.name_entry = tk.Entry(
            self.root,
            width=45,
            font=("Arial", 12)
        )

        self.name_entry.pack(pady=5)

        # -----------------------------------------------------
        # NUMBER
        # -----------------------------------------------------

        tk.Label(
            self.root,
            text="WhatsApp Number",
            font=("Arial", 12)
        ).pack()

        self.number_entry = tk.Entry(
            self.root,
            width=45,
            font=("Arial", 12)
        )

        self.number_entry.pack(pady=5)

        # -----------------------------------------------------
        # DATE
        # -----------------------------------------------------

        tk.Label(
            self.root,
            text="Date (DD-MM-YYYY)",
            font=("Arial", 12)
        ).pack()

        self.date_entry = tk.Entry(
            self.root,
            width=45,
            font=("Arial", 12)
        )

        self.date_entry.pack(pady=5)

        # -----------------------------------------------------
        # TIME
        # -----------------------------------------------------

        tk.Label(
            self.root,
            text="Time (HH:MM - 24 Hour)",
            font=("Arial", 12)
        ).pack()

        self.time_entry = tk.Entry(
            self.root,
            width=45,
            font=("Arial", 12)
        )

        self.time_entry.pack(pady=5)

        # -----------------------------------------------------
        # MESSAGE
        # -----------------------------------------------------

        tk.Label(
            self.root,
            text="Message",
            font=("Arial", 12)
        ).pack()

        self.message_entry = tk.Text(
            self.root,
            width=45,
            height=7,
            font=("Arial", 12)
        )

        self.message_entry.pack(pady=5)

        # -----------------------------------------------------
        # BUTTON
        # -----------------------------------------------------

        tk.Button(
            self.root,
            text="Schedule Message",
            font=("Arial", 13, "bold"),
            width=25,
            command=self.schedule_message
        ).pack(pady=15)

        # -----------------------------------------------------
        # STATUS
        # -----------------------------------------------------

        tk.Label(
            self.root,
            text="Status",
            font=("Arial", 12, "bold")
        ).pack()

        self.status_label = tk.Label(
            self.root,
            text="Waiting...",
            font=("Arial", 11)
        )

        self.status_label.pack(pady=10)

    # =========================================================
    # SCHEDULE MESSAGE
    # =========================================================

    def schedule_message(self):

        name = self.name_entry.get().strip()

        number = self.number_entry.get().strip()

        date_text = self.date_entry.get().strip()

        time_text = self.time_entry.get().strip()

        message = self.message_entry.get(
            "1.0",
            tk.END
        ).strip()

        # -----------------------------------------------------
        # CHECK INPUT
        # -----------------------------------------------------

        if not name:

            messagebox.showwarning(
                "Missing Information",
                "Please enter receiver name."
            )

            return

        if not number:

            messagebox.showwarning(
                "Missing Information",
                "Please enter WhatsApp number."
            )

            return

        if not message:

            messagebox.showwarning(
                "Missing Information",
                "Please enter message."
            )

            return

        # -----------------------------------------------------
        # CLEAN NUMBER
        # -----------------------------------------------------

        number = number.replace(
            " ",
            ""
        )

        number = number.replace(
            "-",
            ""
        )

        # India number handling
        if number.startswith("0"):

            number = number[1:]

        if not number.startswith("+"):

            number = "+91" + number

        # -----------------------------------------------------
        # DATE + TIME
        # -----------------------------------------------------

        try:

            scheduled_time = datetime.strptime(
                date_text + " " + time_text,
                "%d-%m-%Y %H:%M"
            )

        except ValueError:

            messagebox.showerror(
                "Invalid Date/Time",
                "Use this format:\n\n"
                "Date: 10-08-2026\n"
                "Time: 18:30"
            )

            return

        # -----------------------------------------------------
        # CHECK FUTURE
        # -----------------------------------------------------

        if scheduled_time <= datetime.now():

            messagebox.showerror(
                "Invalid Time",
                "The scheduled time must be in the future."
            )

            return

        # -----------------------------------------------------
        # CREATE MESSAGE DATA
        # -----------------------------------------------------

        data = {

            "name": name,

            "number": number,

            "time": scheduled_time,

            "message": message
        }

        # -----------------------------------------------------
        # START BACKGROUND THREAD
        # -----------------------------------------------------

        threading.Thread(
            target=self.wait_for_time,
            args=(data,),
            daemon=True
        ).start()

        self.status_label.config(
            text="Message scheduled successfully!"
        )

        messagebox.showinfo(
            "Scheduled",
            f"Message scheduled!\n\n"
            f"Receiver: {name}\n"
            f"Number: {number}\n"
            f"Date: {date_text}\n"
            f"Time: {time_text}\n\n"
            f"Message:\n{message}"
        )

    # =========================================================
    # WAIT FOR SCHEDULED TIME
    # =========================================================

    def wait_for_time(self, data):

        target_time = data["time"]

        while True:

            current_time = datetime.now()

            remaining = (
                target_time - current_time
            ).total_seconds()

            if remaining <= 0:

                break

            # Update countdown
            self.root.after(
                0,
                self.update_countdown,
                remaining
            )

            time.sleep(1)

        # -----------------------------------------------------
        # TIME REACHED
        # -----------------------------------------------------

        self.root.after(
            0,
            lambda: self.status_label.config(
                text="Sending WhatsApp message..."
            )
        )

        self.send_whatsapp_message(data)

    # =========================================================
    # COUNTDOWN
    # =========================================================

    def update_countdown(self, seconds):

        seconds = int(seconds)

        hours = seconds // 3600

        minutes = (
            seconds % 3600
        ) // 60

        secs = seconds % 60

        self.status_label.config(
            text=(
                f"Waiting... "
                f"{hours:02d}:{minutes:02d}:{secs:02d}"
            )
        )

    # =========================================================
    # SEND WHATSAPP MESSAGE
    # =========================================================

    def send_whatsapp_message(self, data):

        try:

            # -------------------------------------------------
            # Open WhatsApp Desktop
            # -------------------------------------------------

            pyautogui.hotkey(
                "win",
                "s"
            )

            time.sleep(2)

            pyautogui.write(
                "WhatsApp",
                interval=0.05
            )

            time.sleep(2)

            pyautogui.press(
                "enter"
            )

            time.sleep(5)

            # -------------------------------------------------
            # Open New Chat
            # -------------------------------------------------

            pyautogui.hotkey(
                "ctrl",
                "n"
            )

            time.sleep(2)

            # -------------------------------------------------
            # Search Number
            # -------------------------------------------------

            pyperclip.copy(
                data["number"]
            )

            pyautogui.hotkey(
                "ctrl",
                "v"
            )

            time.sleep(3)

            # -------------------------------------------------
            # Select Search Result
            # -------------------------------------------------

            pyautogui.press(
                "enter"
            )

            time.sleep(3)

            # -------------------------------------------------
            # Type Message
            # -------------------------------------------------

            pyperclip.copy(
                data["message"]
            )

            pyautogui.hotkey(
                "ctrl",
                "v"
            )

            time.sleep(1)

            # -------------------------------------------------
            # SEND
            # -------------------------------------------------

            pyautogui.press(
                "enter"
            )

            time.sleep(2)

            self.root.after(
                0,
                lambda: self.message_sent(data)
            )

        except Exception as e:

            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Error",
                    f"Could not send message.\n\n{e}"
                )
            )

    # =========================================================
    # SUCCESS
    # =========================================================

    def message_sent(self, data):

        self.status_label.config(
            text=f"Message sent to {data['name']}!"
        )

        messagebox.showinfo(
            "Message Sent",
            f"WhatsApp message sent successfully!\n\n"
            f"Receiver: {data['name']}\n"
            f"Number: {data['number']}"
        )


# =============================================================
# START APPLICATION
# =============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = WhatsAppScheduler(root)

    root.mainloop()