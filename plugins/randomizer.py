import random

PLUGIN = {
    "name": "randomizer",
    "description": "Rolls a die with a specified number of sides (defaulting to 6) or flips a coin.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "type": {
                "type": "STRING",
                "description": "Whether to perform a 'dice' roll or a 'coin' flip.",
            },
            "sides": {
                "type": "INTEGER",
                "description": "The number of sides for the die roll. Defaults to 6 if not specified.",
            },
        },
        "required": ["type"],
    },
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    action_type = parameters.get("type", "").lower()
    sides = parameters.get("sides", 6)

    try:
        if action_type == "coin":
            result = random.choice(["heads", "tails"])
            result_text = f"It's {result}."
        elif action_type == "dice":
            if not isinstance(sides, int) or sides < 1:
                sides = 6
            roll = random.randint(1, sides)
            result_text = f"Rolled a {sides}-sided die and got {roll}."
        else:
            result_text = "I can only flip a coin or roll a die."
    except Exception as e:
        result_text = f"Sorry, I encountered an error trying to do that."

    if player:
        try:
            player.write_log(f"SAM: {result_text}")
        except Exception:
            pass

    return result_text
