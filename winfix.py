import subprocess
import sys
import time
import ctypes
import json
import os
import re

COMMANDS_FILE = "custom_commands.json"
CEREBRAS_API_KEY = "csk-j9w88jfd5592524xhhvx3fdm5ph83me9ve28ywyfmnm94p5d"

# Safe AI loading
AI_AVAILABLE = False
client = None
try:
    from cerebras.cloud.sdk import Cerebras
    client = Cerebras(api_key=CEREBRAS_API_KEY)
    AI_AVAILABLE = True
    print("✅ Cerebras AI loaded successfully")
except ImportError:
    print("⚠️  Cerebras SDK not installed. AI disabled.")
except Exception:
    print("⚠️  AI not available (model/key issue) - using classic mode")

def load_custom_commands():
    if os.path.exists(COMMANDS_FILE):
        try:
            with open(COMMANDS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_custom_commands(commands):
    try:
        with open(COMMANDS_FILE, "w") as f:
            json.dump(commands, f, indent=2)
    except:
        pass

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def confirm_action(description):
    while True:
        ans = input(f"\n[CONFIRM] Run '{description}'? (Y/N): ").strip().lower()
        if ans in ['y', 'yes']: return True
        if ans in ['n', 'no']:
            print("Cancelled.")
            return False
        print("Please type Y or N.")

def run_command(cmd, description="Custom command"):
    if not confirm_action(description): return
    print(f"\n[EXECUTING] {description}")
    print(f"Command: {cmd}")
    print("-" * 60)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=900)
        if result.stdout: 
            print(result.stdout.strip())
        if result.stderr and result.returncode != 0:
            print("ERROR:\n" + result.stderr.strip())
        print(f"[{'SUCCESS' if result.returncode == 0 else 'WARNING'}] Code: {result.returncode}")
    except Exception as e:
        print(f"[ERROR] {e}")

# Native Levenshtein Distance for spell-checking and fuzzy matching
def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]

def find_best_match(user_input, possibilities, threshold=3):
    r"""
    Finds the best command match.
    Returns (match_string, exact_or_fuzzy)
    """
    user_input_clean = user_input.lower().replace("#", "").replace("_", "").replace(" ", "")
    best_match = None
    min_distance = float('inf')

    for opt in possibilities:
        opt_clean = opt.lower().replace("#", "").replace("_", "").replace(" ", "")
        
        # Check for direct contains or exact stripped matches
        if user_input_clean == opt_clean:
            return opt, True
            
        distance = levenshtein_distance(user_input_clean, opt_clean)
        if distance < min_distance:
            min_distance = distance
            best_match = opt

    # If it is reasonably close, return the fuzzy match
    if min_distance <= threshold:
        return best_match, False
    return None, False

def sanitize_json_backslashes(raw_json_str):
    r"""
    Scans the JSON string and replaces unescaped backslashes with escaped ones.
    Fixes things like "C:\Windows\Temp" to "C:\\Windows\\Temp" to prevent JSON parsing crashes.
    """
    # Negative lookbehind/lookahead to avoid double escaping already escaped characters like \n, \t, \", or \\
    pattern = r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})'
    return re.sub(pattern, r'\\\\', raw_json_str)

def ai_command_creator():
    if not AI_AVAILABLE or client is None:
        print("\nAI unavailable → Using Classic Creator")
        classic_command_creator()
        return

    print("\n🤖 AI COMMAND CREATOR")
    name = input("\nName for this command: ").strip()
    if not name: return

    intent = input("\nWhat should it do? (e.g. clean my pc and fix internet): ").strip()
    intent_lower = intent.lower()

    # Determine execution complexity based on user input vocabulary
    mode = "balanced"
    if any(keyword in intent_lower for keyword in ["advanced", "deep", "thorough", "complex", "full", "complete", "detailed", "max", "maximum", "expert"]):
        mode = "advanced"
        mode_instruction = (
            "The user explicitly requested an ADVANCED/COMPLETE procedure. "
            "You MUST generate an extensive sequence of at least 8 to 12 highly effective, safe Windows commands "
            "to comprehensively accomplish the task step-by-step."
        )
        max_tokens = 1500
    elif any(keyword in intent_lower for keyword in ["simple", "basic", "quick", "fast", "minimal", "easy", "light", "short"]):
        mode = "simple"
        mode_instruction = (
            "The user explicitly requested a SIMPLE/QUICK procedure. "
            "Provide ONLY 1 to 3 of the most direct, high-impact, and safe commands to complete the task."
        )
        max_tokens = 400
    else:
        mode_instruction = (
            "Provide a standard, balanced list of 3 to 6 essential and safe Windows commands to complete the task."
        )
        max_tokens = 800

    print(f"\n🤖 Generating safe commands [Mode: {mode.upper()}] using Cerebras AI...")
    actions = [["sfc /scannow", "System Repair"], ["ipconfig /flushdns", "Fix DNS"]]

    try:
        response = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Windows CLI automation assistant. Your job is to return helper commands. "
                        "You must ONLY reply with a valid JSON array of arrays: [[\"cmd\", \"desc\"], [\"cmd\", \"desc\"]]. "
                        "Do NOT include conversational text, markdown wrapping (no ```json blocks), or comments. "
                        "Crucial: Every single backslash (\\) in Windows paths MUST be escaped as a double backslash (\\\\) inside the JSON strings. "
                        "Example: \"C:\\\\Windows\\\\Temp\"\n\n"
                        f"{mode_instruction}"
                    )
                },
                {
                    "role": "user",
                    "content": f"Generate safe Windows command line arguments to achieve: {intent}"
                }
            ],
            temperature=0.1,
            max_tokens=max_tokens
        )
        
        text = response.choices[0].message.content.strip()
        
        # Strip markdown code blocks using hex escapes (\x60 = `) to prevent copy-paste corruption
        text = re.sub(r'^\x60\x60\x60(?:json)?\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n\x60\x60\x60$', '', text)
        text = text.strip()
        
        # Apply the fix: sanitize unescaped backslashes first, then extract matching json structure
        text = sanitize_json_backslashes(text)
        
        match = re.search(r'\[\s*\[.*\]\s*\]', text, re.DOTALL)
        if match:
            text = match.group(0)
            
        actions = json.loads(text)
            
    except Exception as e:
        print(f"AI formulation failed ({e}) - using safe default fallbacks")

    print(f"\n=== AI Suggestion ({mode.upper()} mode) ===")
    for cmd, desc in actions:
        print(f"• {desc} -> Command: {cmd}")
    print("====================")

    if input("\nSave this command? (Y/N): ").strip().lower() == 'y':
        commands = load_custom_commands()
        commands[name] = actions
        save_custom_commands(commands)
        print(f"✅ Saved '{name}'! Type the name to run it.")
    else:
        print("Cancelled.")

def classic_command_creator():
    print("\n🛠️ Classic Command Creator")
    name = input("\nCommand name: ").strip()
    if not name: return
    print("\n1. Clean PC\n2. Fix Internet\n3. Repair Windows\n4. Security")
    ch = input("Choose: ").strip()
    if ch == "1":
        actions = [["cleanmgr /sagerun:1", "Disk Cleanup"], ["sfc /scannow", "System Repair"]]
    elif ch == "2":
        actions = [["ipconfig /flushdns", "Flush DNS"], ["netsh winsock reset", "Reset Network"]]
    elif ch == "3":
        actions = [["sfc /scannow", "Repair Files"], ["DISM /Online /Cleanup-Image /RestoreHealth", "Windows Repair"]]
    else:
        actions = [["sfc /scannow", "System Repair"]]
    commands = load_custom_commands()
    commands[name] = actions
    save_custom_commands(commands)
    print(f"✅ Saved '{name}'")

def list_custom_commands():
    commands = load_custom_commands()
    if commands:
        print("\n=== SAVED COMMANDS ===")
        for n in commands:
            print(f" → {n}")
    else:
        print("No saved commands yet.")

def run_custom_command(name):
    commands = load_custom_commands()
    if name in commands:
        print(f"\n=== Running {name} ===")
        for cmd, desc in commands[name]:
            run_command(cmd, desc)
            time.sleep(1.5)
    else:
        print(f"Command '{name}' not found.")

def main():
    print("=== Windows Repair Console ===")
    print("WinRepair# | netsh# | Command_creator | list | help | exit")
    
    # Core command registry
    system_commands = ['exit', 'quit', 'bye', 'help', 'winrepair#', 'netsh#', 'command_creator', 'list', 'sfc']

    while True:
        try:
            user_input = input("\nUSER$: ").strip()
            if not user_input: 
                continue

            # Load any custom saved names dynamically
            custom_cmd_dict = load_custom_commands()
            all_possibilities = system_commands + list(custom_cmd_dict.keys())

            # Perform spelling/fuzzy correction matching
            resolved_command, is_exact = find_best_match(user_input, all_possibilities)

            if not resolved_command:
                # If we have absolutely no clue, execute as a potential custom command attempt
                run_custom_command(user_input)
                continue

            # If it was fuzzy but not exact, confirm with the user first
            if not is_exact:
                confirm_fuzzy = input(f"Did you mean '{resolved_command}'? (Y/N): ").strip().lower()
                if confirm_fuzzy not in ['y', 'yes']:
                    print("Action cancelled.")
                    continue
                cmd_to_run = resolved_command.lower()
            else:
                cmd_to_run = resolved_command.lower()

            # Execute the matching command block
            if cmd_to_run in ['exit', 'quit', 'bye']:
                print("Goodbye!")
                break
            elif cmd_to_run == 'help':
                print("\nCommand_creator → AI / Classic command generator")
                print("list            → Show your saved custom commands")
                print("WinRepair#      → Automated system files & DISM repair")
                print("netsh#          → Automated network stack diagnostic reset")
                print("sfc             → Fast system file verification scan")
            elif cmd_to_run in ['winrepair#', 'winrepair']:
                win_repair_protocol()
            elif cmd_to_run in ['netsh#', 'netsh']:
                netsh_repair_protocol()
            elif cmd_to_run == 'command_creator':
                ai_command_creator()
            elif cmd_to_run == 'list':
                list_custom_commands()
            elif cmd_to_run == 'sfc':
                run_command("sfc /scannow", "System File Checker")
            else:
                # Run the custom command matching the name
                run_custom_command(resolved_command)

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            input("Press Enter to continue...")

def win_repair_protocol():
    print("\n=== WINREPAIR PROTOCOL ===")
    for cmd, desc in [("sfc /scannow", "Repair System Files"), ("DISM /Online /Cleanup-Image /RestoreHealth", "Repair Windows")]:
        run_command(cmd, desc)

def netsh_repair_protocol():
    print("\n=== NETWORK REPAIR ===")
    for cmd, desc in [("ipconfig /flushdns", "Fix DNS"), ("netsh winsock reset", "Reset Network")]:
        run_command(cmd, desc)

if __name__ == "__main__":
    if is_admin():
        print("✅ Administrator mode")
    else:
        print("⚠️  Not Administrator")
    main()