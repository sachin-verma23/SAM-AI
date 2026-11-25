import sys
import os
import subprocess
import threading

PLUGIN = {
    "name": "self_restart",
    "description": (
        "Initiates a self-restart sequence when the user says 'restart'. "
        "The actual execution only happens after a subsequent 'confirm' command."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "description": "Either 'restart' to initiate, or 'confirm' to execute.",
                "enum": ["restart", "confirm"]
            },
        },
        "required": ["command"],
    },
}

MEMORY_KEY = "self_restart_pending"

def run(parameters: dict, player=None, session_memory=None) -> str:
    command = parameters.get("command", "")
    
    if session_memory is None:
        return "Cannot proceed: session memory is unavailable."

    if command == "restart":
        session_memory[MEMORY_KEY] = True
        return "I am prepared to restart. Please say 'confirm' to execute."

    if command == "confirm":
        if session_memory.get(MEMORY_KEY):
            # Clear state immediately
            session_memory[MEMORY_KEY] = False
            
            if player:
                player.write_log("SAM: Initiating self-restart...")

            # Spawn a detached process to execute the restart after a very brief delay
            # to allow this execution to complete and return the string to be spoken.
            try:
                python_executable = sys.executable
                script_path = sys.argv[0]
                
                # Standard Python way to restart: run current script in new process, then exit this one.
                # Creates a new process that isn't connected to the current one.
                subprocess.Popen([python_executable, script_path], creationflags=subprocess.DETACHED_PROCESS)
                
                # Schedule current process exit
                threading.Timer(0.5, lambda: os._exit(0)).start()
                
                return "Restarting now."
            except Exception as e:
                return f"Failed to restart: {e}"
        else:
            return "Restart not initiated. Please say 'restart' first."

    return "Unknown command for self_restart."
