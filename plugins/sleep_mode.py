import ctypes
import time
import threading

PLUGIN = {
    "name": "sleep_mode",
    "description": (
        "Locks the Windows workstation and displays a visual 'sleep' message "
        "when user asks to 'go to sleep mode'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
}

def delayed_display(player):
    """Wait for lock screen to cover, then display text."""
    time.sleep(1)
    if player:
        try:
            player.show_content("Sleep Mode", "System locked.")
            player.write_log("SAM: Performed system lockdown and displayed sleep status.")
        except Exception:
            pass

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Locks Windows and shows content."""
    try:
        # Lock the workstation using Win32 API
        # user32.LockWorkStation() is non-destructive and standard.
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            return "I couldn't lock your computer right now."

        # Display content via player after a short delay on a thread
        threading.Thread(target=delayed_display, args=(player,), daemon=True).start()

        return "Going into sleep mode and locking the system."
    except Exception as e:
        return f"Failed to activate sleep mode: {e}"
