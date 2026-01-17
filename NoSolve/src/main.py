import sys, os, time
from curl_cffi import requests
from output import Output
from thread_lock import lock
from threading import Thread
from counter import counter
from roblox import Roblox
from util import Util
from combocheck import invalid, checked, locked

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    os.mkdir("output")
except:
    pass

try:
    os.mkdir("output/usernames")
except:
    pass

try:
    os.mkdir("output/payment_info")
except:
    pass

try:
    os.mkdir("output/pending")
except:
    pass

try:
    os.mkdir("output/premium")
except:
    pass

try:
    os.mkdir("output/rap")
except:
    pass

try:
    os.mkdir("output/balance")
except:
    pass

try:
    os.mkdir("output/creation_date")
except:
    pass

try:
    os.mkdir("output/rare_items")
except:
    pass

try:
    os.mkdir("output/robux")
except:
    pass

try:
    os.mkdir("output/summary")
except:
    pass

try:
    os.mkdir("output/items")
except:
    pass

try:
    os.mkdir("output/badges")
except:
    pass

if not os.path.isfile("output/failed.txt"):
    open("output/failed.txt", "w").close()

if not os.path.isfile("output/invalid.txt"):
    open("output/invalid.txt", "w").close()

if not os.path.isfile("output/valid.txt"):
    open("output/valid.txt", "w").close()

if not os.path.isfile("output/og_combo.txt"):
    open("output/og_combo.txt", "w").close()

if not os.path.isfile("output/valid_combo.txt"):
    open("output/valid_combo.txt", "w").close()
    
if not os.path.isfile("output/cookies.txt"):
    open("output/cookies.txt", "w").close()

if not os.path.isfile("output/locked.txt"):
    open("output/locked.txt", "w").close()

if not os.path.isfile("output/terminated.txt"):
    open("output/terminated.txt", "w").close()

if not os.path.isfile("output/temp_banned.txt"):
    open("output/temp_banned.txt", "w").close()

threading_lock = lock

invalid.read_file("output/invalid.txt")
checked.read_file("output/og_combo.txt")
locked.read_file("output/locked.txt")

config = Util.get_config()

THREAD_AMOUNT = config["threads"]
ACCOUNTS = Util.get_accounts()

def change_terminal_name(new_name):
    if os.name == "nt":
        os.system(f'title {new_name}')
    elif sys.platform in ["linux", "darwin"]:
        sys.stdout.write(f'\033]0;{new_name}\007')
        sys.stdout.flush()
    else:
        print("Unsupported OS")

def get_solver_balance():
    """Get balance from the configured solver"""
    config = Util.get_config()
    default_solver = config.get("DefaultSolver", "Devious")
    solver_keys = config.get("Solvers_Keys", {})
    
    session = requests.Session()
    
    try:
        if default_solver == "Devious":
            devious_key = solver_keys.get("Devious", "")
            if devious_key:
                response = session.get(f"https://key.devioussolver.com/key/{devious_key}", timeout=10).json()
                remaining = response.get("remaining_solves", 0)
                max_solves = response.get("max_solves", 0)
                used = response.get("solves", 0)
                return {
                    "remaining": remaining,
                    "max": max_solves,
                    "used": used,
                    "solver": "Devious"
                }
        
        elif default_solver == "RoSolve":
            rosolve_key = solver_keys.get("RoSolve", "")
            if rosolve_key:
                response = session.get(f"https://rosolve.pro/getSolves?key={rosolve_key}", timeout=10).json()
                balance = response.get("solves", 0)
                return {
                    "balance": balance,
                    "solver": "RoSolve"
                }
              
        elif default_solver == "CDS":
            cds_key = solver_keys.get("CDS", "")
            if cds_key:
                response = session.post("https://cds-solver.com/getBalance", json={"api_key": cds_key}, timeout=10).json()
                balance = response.get("balance", 0)
                return {
                    "balance": balance,
                    "solver": "CDS"
                }
            
    except Exception as e:
        print(f"Error getting solver balance: {e}")
    
    return None

def title() -> None:
    last_accounts = 0
    last_time = time.time()
    
    while threading_lock.get_lock():
        try:
            balance_info = get_solver_balance()
            counter_value = counter.get_value()
            current_time = time.time()
            elapsed_time = current_time - last_time
            
            if elapsed_time > 0:
                accounts_per_sec = (counter_value - last_accounts) / elapsed_time
            else:
                accounts_per_sec = 0
            
            last_accounts = counter_value
            last_time = current_time
            
            if balance_info:
                if balance_info["solver"] == "Devious":
                    title_text = f"NoSolve - Remaining: {'{:,}'.format(balance_info['remaining'])} / Accounts Checked: {counter_value}/{len(ACCOUNTS)} ({accounts_per_sec:.2f}/s)"
                elif balance_info["solver"] == "RoSolve":
                    balance = balance_info["balance"]
                    title_text = f"NoSolve - Balance: {'{:,}'.format(int(balance*1e3))} (${'{:.2f}'.format(balance)}) / Accounts Checked: {counter_value}/{len(ACCOUNTS)} ({accounts_per_sec:.2f}/s)"
                elif balance_info["solver"] == "CDS":
                    balance = balance_info["balance"]
                    cost = (balance / 1000) * 0.50
                    cost_str = f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}"
                    title_text = f"NoSolve - Balance: {balance:,} ({cost_str}) / Accounts Checked: {counter_value}/{len(ACCOUNTS)} ({accounts_per_sec:.2f}/s)"
            else:
                title_text = f"Roblox Checker - Accounts Checked: {counter_value}/{len(ACCOUNTS)} ({accounts_per_sec:.2f}/s)"
            
            change_terminal_name(title_text)
            
        except Exception as e:
            print(f"Error in title function: {e}")
        
        time.sleep(2.5)

def main() -> None: 
    threads = []

    if len(ACCOUNTS) <= THREAD_AMOUNT:
        for _ in range(len(ACCOUNTS)):
            thread = Thread(target=Roblox(threading_lock, counter, invalid, checked, locked, ACCOUNTS).check)
            thread.start()
            threads.append(thread)
    else:
        for _ in range(THREAD_AMOUNT):
            thread = Thread(target=Roblox(threading_lock, counter, invalid, checked, locked, ACCOUNTS).check)
            thread.start()
            threads.append(thread)

    thread = Thread(target=title)
    thread.start()
    threads.append(thread)

    for thread in threads:
        thread.join()

    Output("SUCCESS").log("Finished checking all accounts")

if __name__ == "__main__":
    main()