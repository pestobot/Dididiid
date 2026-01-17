from typing import Union
from session_noproxy import Session as SessionNoProxy
from session import Session as SessionWithProxy
from util import Util
from datetime import datetime
import robloxpy
import time

config = Util.get_config()
rare_items = config["rareItems"]
use_proxies = config.get("account_info", {}).get("UseProxies", False)

Session = SessionWithProxy if use_proxies else SessionNoProxy
SessionType = Union[SessionWithProxy, SessionNoProxy]


def make_str(l):
    if l:
        s = ", ".join(l)
        max_length = 1024
        return s[:max_length - 3] + "..." if len(s) > max_length else s
    else:
        return "None"

def format_number(num):
    if num is None:
        return "_unknown"
    try:
        return "{:,}".format(int(num))
    except (ValueError, TypeError):
        return "_unknown"

def retry(func):
    def wrapper(*func_args, **func_kwargs):
        attempt = 0
        while attempt < 3:
            try:
                return func(*func_args, **func_kwargs)
            except Exception as e:
                if hasattr(e, 'response') and e.response.status_code == 401:
                    return "Unauthorized"
                if hasattr(e, 'response') and getattr(e.response, "status_code", None) == 401:
                    return "_unknown"
                print(f"Error occurred: {e}")
                attempt += 1
                if attempt == 3:
                    raise
    return wrapper

@retry
def get_rap(session: SessionType, UserID: int) -> str:
    ErroredRAP = 0
    TotalValue = 0
    Cursor = ""
    Done = False
    while not Done:
        try:
            response = session.get(f"https://inventory.roblox.com/v1/users/{UserID}/assets/collectibles?sortOrder=Asc&limit=100&cursor={Cursor}")
            if response.status_code == 401:
                return "Unauthorized"
            Items = response.json()
            next_cursor = Items.get('nextPageCursor')
            if next_cursor == "null" or next_cursor is None:
                Done = True
            else:
                Cursor = next_cursor

            for Item in Items["data"]:
                try:
                    RAP = int(Item['recentAveragePrice'])
                    TotalValue += RAP
                except:
                    pass
        except Exception as ex:
            Done = True
            print(f"Error retrieving RAP: {ex}")
    return format_number(TotalValue) if TotalValue > 0 else "0"

@retry
def get_robux(session: SessionType, user_id):
    try:
        response = session.get(f"https://economy.roblox.com/v1/users/{user_id}/currency")
        if response.status_code == 401:
            return "_unknown"
        robux_value = response.json().get("robux")
        if robux_value is None:
            return "_unknown"
        return format_number(robux_value) if robux_value > 0 else "0"
    except Exception as e:
        print(f"Error retrieving Robux: {e}")
        return "_unknown"

@retry
def is_premium(session: SessionType, user_id):
    try:
        response = session.get(f"https://premiumfeatures.roblox.com/v1/users/{user_id}/validate-membership")
        if response.status_code == 401:
            return "_unknown"
        return response.text == "true"
    except Exception as e:
        print(f"Error checking premium status: {e}")
        return "_unknown"

@retry
def get_pending_and_summary(session: SessionType, user_id):
    try:
        response = session.get(f"https://economy.roblox.com/v2/users/{user_id}/transaction-totals?timeFrame=Year&transactionType=summary")
        if response.status_code == 401:
            return ["_unknown", "_unknown"]
        data = response.json()
        pending = data.get("pendingRobuxTotal")
        incoming = data.get("incomingRobuxTotal")
        return [
            format_number(pending) if pending is not None and pending > 0 else "0" if pending is not None else "_unknown",
            format_number(incoming) if incoming is not None and incoming > 0 else "0" if incoming is not None else "_unknown"
        ]
    except Exception as e:
        print(f"Error retrieving pending and summary: {e}")
        return ["_unknown", "_unknown"]

@retry
def has_payment_info(session: SessionType) -> bool | str:
    try:
        response = session.get("https://apis.roblox.com/payments-gateway/v1/payment-profiles")
        if response.status_code == 401:
            return "_unknown"
        if response.status_code == 200 and len(response.json()) != 0:
            return True
        return False
    except Exception as e:
        print(f"Error checking payment info: {e}")
        return "_unknown"

@retry
def get_items(session: SessionType, user_id) -> dict[str, str]:
    items = {
        "rare_items": [],
        "hats": [],
        "faces": [],
        "heads": [],
        "limited_items": []
    }

    urls = {
        "hats": f"https://inventory.roblox.com/v2/users/{user_id}/inventory/8?cursor=&limit=100&sortOrder=Desc",
        "faces": f"https://inventory.roblox.com/v2/users/{user_id}/inventory/18?cursor=&limit=100&sortOrder=Desc",
        "heads": f"https://inventory.roblox.com/v2/users/{user_id}/inventory/17?cursor=&limit=100&sortOrder=Desc"
    }

    max_retries = 3
    retry_delay = 2
    
    rare_items_set = set(int(item_id) for item_id in rare_items)

    try:
        limiteds, limited_ids = robloxpy.User.External.GetLimiteds(user_id)
        items["limited_items"] = limiteds
        for asset_name, asset_id in zip(limiteds, limited_ids):
            if int(asset_id) in rare_items_set: 
                items["rare_items"].append(asset_name)
    except Exception as e:
        print(f"Error retrieving limited items: {e}")

    for key, url in urls.items():
        for attempt in range(max_retries):
            try:
                response = session.get(url)
                if response.status_code == 401:
                    items[key] = ["Unauthorized"]
                    break
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    for item in data:
                        asset_id = item.get("assetId")
                        asset_name = item.get("assetName")
                        items[key].append(asset_name)
                        if int(asset_id) in rare_items_set: 
                            items["rare_items"].append(asset_name)
                    break
                else:
                    print(f"Failed to retrieve {key}, status code: {response.status_code}")
            except Exception as e:
                print(f"Error retrieving {key} (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    return {
        "rare_items": make_str(items["rare_items"]),
        "hats": make_str(items["hats"]),
        "faces": make_str(items["faces"]),
        "heads": make_str(items["heads"]),
        "limited_items": make_str(items["limited_items"]),
        "is_verified": "Sign" if "Verified Sign" in items["hats"] else "Hat" if any(x in items["hats"] for x in ["Verified", "Bonafide", "Plaidafied"]) else False,
        "total_items": len(items["hats"]) + len(items["limited_items"])
    }


@retry
def balance(session: SessionType):
    try:
        response = session.get("https://apis.roblox.com/credit-balance/v1/get-conversion-metadata")
        if response.status_code == 401:
            return "Unauthorized"
        if response.status_code == 200:
            data = response.json()
            credit_balance = data.get("creditBalance")
            if credit_balance is None:
                return "None"
            return format_number(credit_balance) if credit_balance > 0 else "0"
        else:
            return f"Failed to retrieve data: {response.status_code}"
    except Exception as e:
        print(f"Error retrieving balance: {e}")
        return "Failed to retrieve balance"

@retry
def get_creation_date(session: SessionType, user_id: int) -> str:
    try:
        response = session.get(f"https://users.roblox.com/v1/users/{user_id}")
        if response.status_code == 401:
            return "Unauthorized"
        if response.status_code != 200:
            return "_unknown"

        user_data = response.json()
        creation_date = user_data.get("created")
        if not creation_date:
            return "_unknown"

        creation_date = creation_date.replace("Z", "+00:00")

        try:
            parsed_date = datetime.fromisoformat(creation_date)
        except ValueError:

            if '.' in creation_date:
                base, fraction = creation_date.split('.', 1)
                fraction = ''.join(ch for ch in fraction if ch.isdigit())
                fraction = fraction.ljust(6, '0')[:6]
                fixed_date_str = f"{base}.{fraction}+00:00"
                parsed_date = datetime.fromisoformat(fixed_date_str)
            else:
                parsed_date = datetime.fromisoformat(creation_date)

        return str(parsed_date.year)

    except Exception as e:
        print(f"[!] Error retrieving creation date for user {user_id}: {e}")
        return "_unknown"

@retry
def get_thumbnail(session: SessionType, user_id: int) -> str:
    try:
        response = session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false")
        if response.status_code == 401:
            return "Unauthorized"
        if response.status_code == 200:
            data = response.json().get("data")
            if data:
                image_url = data[0].get("imageUrl")
                if image_url != "":
                    return image_url
    except Exception as e:
        print(f"Error retrieving thumbnail for {user_id}: {e}")
        return "_unknown"
    return "_unknown"

@retry
def get_roblox_badges(session: SessionType, user_id: int) -> str:
    try:
        response = session.get(f"https://accountinformation.roblox.com/v1/users/{user_id}/roblox-badges")
        if response.status_code == 401:
            return "Unauthorized"
        if response.status_code == 200:
            data = response.json()
            badge_names = [item['name'] for item in data]
            return make_str(badge_names)
    except Exception as e:
        print(f"Error retrieving badges: {e}")
        return "_unknown"

@retry
def get_follower_count(user_id: int) -> str:
    try:
        followers = robloxpy.User.Friends.External.GetFollowerCount(user_id)
        return format_number(followers) if followers > 0 else "0"
    except Exception as e:
        print(f"Error retrieving follower count: {e}")
        return "_unknown"

@retry
def get_owned_groups(session: SessionType, user_id: int) -> str | None:
    try:
        response = session.get(f"https://groups.roblox.com/v1/users/{user_id}/groups/roles")
        if response.status_code == 401:
            return "_unknown"
            
        groups_data = response.json()
        owned_groups = []
        
        for group in groups_data.get("data", []):
            if group.get("role", {}).get("rank") == 255:
                group_id = group["group"].get("id")
                group_name = group["group"].get("name", "_unknown")
                member_count = group["group"].get("memberCount")

                funds = None
                try:
                    funds_response = session.get(f"https://economy.roblox.com/v1/groups/{group_id}/currency")
                    if funds_response.status_code == 200:
                        funds = funds_response.json().get("robux")
                except Exception:
                    funds = None

                owned_groups.append(
                    f"{group_name} ({format_number(funds) if funds and funds > 0 else '0'} R$, {format_number(member_count) if member_count and member_count > 0 else '0'} members)"
                )
                    
        if owned_groups:
            return ", ".join(owned_groups)
        return None
        
    except Exception as e:
        print(f"Error retrieving owned groups: {e}")
        return "_unknown"


@retry
def get_total_visits(session: SessionType, user_id: int) -> str:
    try:
        total_visits = 0
        cursor = ""
        done = False
        
        while not done:
            url = f"https://games.roblox.com/v2/users/{user_id}/games"
            params = {"limit": 50, "sortOrder": "Asc"}
            if cursor:
                params["cursor"] = cursor
            
            response = session.get(url, params=params)
            if response.status_code == 401:
                return "_unknown"
            
            if response.status_code != 200:
                return "_unknown"
            
            data = response.json()
            for game in data.get("data", []):
                total_visits += game.get("placeVisits", 0)
            
            next_cursor = data.get("nextPageCursor")
            if next_cursor == "null" or next_cursor is None:
                done = True
            else:
                cursor = next_cursor
        
        return format_number(total_visits) if total_visits > 0 else "0"
    
    except Exception as e:
        print(f"Error retrieving total visits: {e}")
        return "_unknown"
    
class AccountInfo:
    @staticmethod
    def get_account_info(session: SessionType, user_id) -> dict:
        try:
            robux = get_robux(session, user_id)
        except Exception as e:
            robux = "_unknown"
            print(f"Error in robux retrieval: {e}")

        try:
            payment_info = has_payment_info(session)
        except Exception as e:
            payment_info = "_unknown"
            print(f"Error in payment info retrieval: {e}")

        try:
            premium = is_premium(session, user_id)
        except Exception as e:
            premium = "_unknown"
            print(f"Error in premium status retrieval: {e}")

        try:
            rap = get_rap(session, user_id)
        except Exception as e:
            rap = "_unknown"
            print(f"Error in RAP retrieval: {e}")

        try:
            pending_and_summary = get_pending_and_summary(session, user_id)
            pending = pending_and_summary[0]
            summary = pending_and_summary[1]
        except Exception as e:
            pending = "_unknown"
            summary = "_unknown"
            print(f"Error in pending and summary retrieval: {e}")

        try:
            creation_date = get_creation_date(session, user_id)
        except Exception as e:
            creation_date = "_unknown"
            print(f"Error in creation date retrieval: {e}")

        try:
            user_balance = balance(session)
        except Exception as e:
            user_balance = "_unknown"
            print(f"Error in balance retrieval: {e}")

        try:
            followers = get_follower_count(user_id)
        except Exception as e:
            followers = "_unknown"
            print(f"Error in follower count retrieval: {e}")

        try:
            items = get_items(session, user_id)
        except Exception as e:
            items = {
                "rare_items": "_unknown",
                "hats": "_unknown",
                "faces": "_unknown",
                "heads": "_unknown",
                "limited_items": "_unknown",
                "is_verified": False,
                "total_items": "_unknown"
            }
            print(f"Error in items retrieval: {e}")

        try:
            image_url = get_thumbnail(session, user_id)
        except Exception as e:
            image_url = "_unknown"
            print(f"Error in thumbnail retrieval: {e}")

        try:
            badges = get_roblox_badges(session, user_id)
        except Exception as e:
            badges = "_unknown"
            print(f"Error in badges retrieval: {e}")

        try:
            owned_groups = get_owned_groups(session, user_id) 
        except Exception as e:
            owned_groups = "_unknown"
            print(f"Error in owned groups retrieval: {e}")

        try:
            total_visits = get_total_visits(session, user_id)
        except Exception as e:
            total_visits = "_unknown"
            print(f"Error in total visits retrieval: {e}")

        return {
            "Robux": robux,
            "Balance": user_balance,
            "Premium": premium,
            "Payment Info": payment_info,
            "RAP": rap,
            "Pending": pending,
            "Summary": summary,
            "Creation Date": creation_date,
            "Hats": items["hats"],
            "Heads": items["heads"],
            "Faces": items["faces"],
            "Rare Items": items["rare_items"],
            "Limited Items": items["limited_items"],
            "Verified": items["is_verified"],
            "Total Items": format_number(items["total_items"]),
            "Badges": badges,
            "Thumbnail": image_url,
            "Followers": followers,
            "Total Visits": total_visits,
            "Owned Groups": owned_groups
        }