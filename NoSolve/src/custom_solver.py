from util import Util
from time import sleep
from curl_cffi import requests
import json

config = Util.get_config()

DEFAULT_SOLVER = config.get("DefaultSolver", "Devious")
SOLVER_KEYS = config.get("Solvers_Keys", {})
ROSOLVE_KEY = SOLVER_KEYS.get("RoSolve", "")
DEVIOUS_KEY = SOLVER_KEYS.get("Devious", "")
FUNBYPASS_KEY = SOLVER_KEYS.get("FunBypass", "")
CDS_KEY = SOLVER_KEYS.get("CDS", "")

PUBLIC_KEY = "476068BF-9607-4799-B53D-966BE98E2B81"

def solve_with_devious(blob, proxy, cookies=None):
    """Solve using Devious solver"""
    try:
        solution = requests.post(
            "https://api.devioussolver.com/solve", 
            json={
                "api_key": DEVIOUS_KEY,
                "proxy": proxy,
                "blob_exchange": blob,
                "public_key": PUBLIC_KEY,
                "cookies": cookies or {}
            }, 
            timeout=120
        ).json()
        
        token = solution.get("token")

        if token:
            return token
    except Exception as e:
        print(f"Devious solver failed: {e}")
    return None

def solve_with_rosolve(roblox_session, blob, proxy):
    """Solve using Rosolve solver"""
    try:
        session = requests.Session()
        
        challengeInfo = {
            "publicKey": PUBLIC_KEY,
            "site": "https://www.roblox.com/",
            "surl": "https://arkoselabs.roblox.com",
            "capiMode": "inline",
            "styleTheme": "default",
            "languageEnabled": False,
            "jsfEnabled": False,
            "extraData": {
                "blob": blob
            },
            "ancestorOrigins": ["https://www.roblox.com"],
            "treeIndex": [1],
            "treeStructure": "[[],[]]",
            "locationHref": "https://www.roblox.com/arkose/iframe",
            "documentReferrer": "https://www.roblox.com/login"
        }

        browserInfo = {
            'Sec-Ch-Ua': roblox_session.headers.get("sec-ch-ua", ""),
            'User-Agent': roblox_session.headers.get("user-agent", ""),
            'Mobile': False
        }

        payload = {
            "key": ROSOLVE_KEY,
            "challengeInfo": challengeInfo,
            "browserInfo": browserInfo,
            "proxy": proxy
        }

        response = session.post("https://rosolve.pro/createTask", json=payload, timeout=120).json()

        task_id = response.get("taskId")

        if task_id == None:
            raise ValueError(f"Failed to get taskId, reason: {response.get('error', 'Unknown error')}")
        
        counter = 0

        while counter < 60:
            sleep(1)

            payload = {
                "key": ROSOLVE_KEY,
                "taskId": task_id
            }

            solution = session.post("https://rosolve.pro/taskResult", json=payload).json()

            if solution["status"] == "completed":
                return solution["result"]["solution"]
            
            elif solution["status"] == "failed":
                return None
            
            counter += 1

        return None
        
    except Exception as e:
        print(f"Rosolve solver failed: {e}")
    return None


def solve_with_cds(roblox_session, blob, proxy, cookies=None):
    try:
        session = requests.Session()
        task = session.post("https://cds-solver.com/createTask", json={
            "api_key": CDS_KEY,
            "site_key": PUBLIC_KEY,
            "browser_version": 142,
            "locale": "en-US",
            "proxy": proxy,
            "blob": blob,
            "cookies": cookies or {}
        }, timeout=120).json()
        task_id = task.get("task_id") or task.get("taskId")
        if not task_id:
            return None
        count = 0
        while count <= 120:
            payload = {
                "api_key": CDS_KEY,
                "task_id": task_id
            }
            token_resp = session.post("https://cds-solver.com/getTask", json=payload, timeout=30).json()
            status = token_resp.get("status")
            if status == "processing":
                count += 1
                sleep(0.3)
                continue
            if status == "success":
                return token_resp.get("token")
            return None
    except Exception:
        return None
    
def solve_with_funbypass(roblox_session, blob, proxy):
    """Solve using FunBypass solver (updated to use configurable API URL and key)"""
    try:
        session = requests.Session()

        task_payload = {
            "clientKey": FUNBYPASS_KEY,
            "task": {
                "type": "FunCaptchaTask",
                "websiteURL": "https://www.roblox.com/",
                "websitePublicKey": PUBLIC_KEY,
                "websiteSubdomain": "roblox.com",
                "data": json.dumps({"blob": blob}),
                "proxy": proxy,
            },
            "headers": {
                "user-agent": roblox_session.headers.get("user-agent", ""),
                "sec-ch-ua": roblox_session.headers.get("sec-ch-ua", ""),
            },
        }

        create_resp = session.post("https://api.funbypass.com/createTask", json=task_payload, timeout=60)
        if create_resp.status_code != 200:
            raise ValueError(f"createTask HTTP {create_resp.status_code}: {create_resp.text}")

        create_data = create_resp.json()
        if create_data.get("errorId") != 0:
            raise ValueError(f"createTask error: {create_data}")

        task_id = create_data.get("taskId")
        if not task_id:
            raise ValueError(f"createTask missing taskId: {create_data}")

        for _ in range(60):
            sleep(1)
            result_resp = session.get(f"https://api.funbypass.com/getTaskResult/{task_id}", timeout=30)
            if result_resp.status_code not in (200, 202):
                continue

            result_data = result_resp.json()
            if result_data.get("errorId") != 0:
                raise ValueError(f"getTaskResult error: {result_data}")

            status = result_data.get("status")
            if status == "processing":
                continue
            elif status == "ready":
                solution = result_data.get("solution")
                if isinstance(solution, dict) and "token" in solution:
                    return solution["token"]
                if isinstance(solution, str):
                    return solution
                return None
            elif status == "failure":
                return None

        return None

    except Exception as e:
        print(f"FunBypass solver failed: {e}")
    return None

def get_token(roblox_session: requests.Session, blob, proxy, cookies=None):
    """Main solver function that uses DefaultSolver preference"""
    
    if DEFAULT_SOLVER == "Devious" and DEVIOUS_KEY and DEVIOUS_KEY.strip():
        return solve_with_devious(blob, proxy, cookies)
        
    elif DEFAULT_SOLVER == "RoSolve" and ROSOLVE_KEY and ROSOLVE_KEY.strip():
        return solve_with_rosolve(roblox_session, blob, proxy)
    
    elif DEFAULT_SOLVER == "FunBypass" and FUNBYPASS_KEY and FUNBYPASS_KEY.strip():
        return solve_with_funbypass(roblox_session, blob, proxy)

    elif DEFAULT_SOLVER == "CDS" and CDS_KEY and CDS_KEY.strip():
        return solve_with_cds(roblox_session, blob, proxy, cookies)

    return None