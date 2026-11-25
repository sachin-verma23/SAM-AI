import os
import sys

PLUGIN = {
    "name": "restart_confirm",
    "description": (
        "Internal handler for restarting SAM. Use this when the user "
        "says 'restart' or 'restart karo khud ko'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Restarts the application by spawning a new process and exiting current."""
    if player:
        player.write_log("SAM: Initiating self-restart via verbal confirm script.")
        
    try:
        # Get path to current script
        executable = sys.executable
        args = sys.argv
        
        # Log attempting restart
        if player:
            player.write_log(f"SAM: Found executable {executable}, args {args}")

        # Basic protection against accidental execution
        if "python" not in os.path.basename(executable).lower() and not executable.endswith(".exe"):
            return "Cannot restart, executable path seems invalid."

        # Restart logic
        os.execv(executable, [executable] + args)
        
        # os.execv replaces the current process, this shouldn't be reached
        return "Restarting now."
    except Exception as e:
        if player:
            player.write_log(f"SAM: Restart failed: {e}")
        return f"Restart failed: {e}"
