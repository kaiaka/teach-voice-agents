


from datetime import datetime

class C:
    RESET  = "\033[0m"
    BLACK  = "\033[30m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    BLUE   = "\033[34m"
    MAGENTA= "\033[35m"
    CYAN   = "\033[36m"
    WHITE  = "\033[37m"
    GRAY   = "\033[90m"
    BOLD    = "\033[1m"


def log_event(event, source="", value="", extra=""):
    row = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "event": event,
        "source": source,
        "value": value.replace("\n", " ").strip(),
        "extra": extra.replace("\n", " ").strip()
    }
    try:
        if event == "user_text" or event == "ai_response":
            role = "User" if event == "user_text" else "Agent"
            print(f'{C.BOLD}[{role}]{C.RESET} {value}')
        else:
            print(f'{C.GRAY}[{event}] {value}{C.RESET}')
    except Exception:
        pass