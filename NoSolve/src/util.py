import sys, os
from datetime import datetime
from string import digits, ascii_letters
from random import choice, randint, shuffle
from json import load

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

with open("input/proxies.txt", "r", encoding="utf-8") as file:
    proxies = file.readlines()

with open("input/config.json", "r", encoding="utf-8") as file:
    config = load(file)

with open("input/accounts.txt", "r", encoding="utf-8", errors="replace") as file:
    accounts = [line.strip() for line in file if line.strip()]

normalized_accounts = set()
for acc in accounts:
    parts = acc.split(":", 1)
    if len(parts) == 2:
        email, rest = parts
        normalized_accounts.add(f"{email.lower()}:{rest}")
    else:
        normalized_accounts.add(acc.lower())

accounts = sorted(normalized_accounts)

invalid_file = "output/invalid.txt"
locked_file = "output/locked.txt"
valid_file = "output/valid.txt"

invalid = set()
locked = set()
valid_userpass_only = set()

if os.path.exists(invalid_file):
    with open(invalid_file, "r", encoding="utf-8", errors="replace") as file:
        invalid = {line.strip() for line in file if line.strip()}

if os.path.exists(locked_file):
    with open(locked_file, "r", encoding="utf-8", errors="replace") as file:
        locked = {line.strip() for line in file if line.strip()}
    with open(locked_file, "w", encoding="utf-8") as file:
        for line in sorted(locked):
            file.write(line + "\n")

if os.path.exists(valid_file):
    with open(valid_file, "r", encoding="utf-8", errors="replace") as file:
        valid_lines = {line.strip() for line in file if line.strip()}
    with open(valid_file, "w", encoding="utf-8") as file:
        for line in sorted(valid_lines):
            file.write(line + "\n")
    for s in valid_lines:
        parts = s.split(":", 1)
        if len(parts) == 2:
            user = parts[0]
            if user:
                valid_userpass_only.add(s)

filtered_accounts = [
    acc for acc in accounts
    if acc not in invalid
    and acc not in locked
    and (("@" in acc.split(":", 1)[0]) or (acc not in valid_userpass_only))
]

shuffle(filtered_accounts)

with open("input/accounts.txt", "w", encoding="utf-8") as file:
    for acc in filtered_accounts:
        file.write(acc + "\n")

class Util:
    @staticmethod
    def encode_data(data) -> str:
        encoded_data = []
        for c in data:
            if ord(c) > 127 or c in " %$&+,/:;=?@<>%{}":
                encoded_data.append(f'%{ord(c):02X}')
            else:
                encoded_data.append(c)
        return "".join(encoded_data)

    @staticmethod
    def get_random_proxy() -> str:
        return choice(proxies).strip("\n")

    @staticmethod
    def get_config() -> dict:
        return config

    @staticmethod
    def get_accounts() -> list:
        return filtered_accounts

    @staticmethod
    def get_random_string() -> str:
        return "".join([choice(ascii_letters + digits) for _ in range(randint(12, 20))])

    @staticmethod
    def get_date_formatted() -> str:
        return datetime.now().strftime("%m/%d/%Y %H:%M:%S")