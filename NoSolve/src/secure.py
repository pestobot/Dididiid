from util import Util
from output import Output
from json import dumps
from datetime import datetime, timedelta
from base64 import b64encode, b64decode
import json
import time
import hashlib
import ecdsa
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
import os

config = Util.get_config()
DEBUG = config.get("debug", False)

def retry(func):
    def wrapper(*func_args, **func_kwargs):
        attempt = 0
        while attempt < 3:
            try:
                return func(*func_args, **func_kwargs)
            except Exception as e:
                print(f"Error occurred: {e}")
                attempt += 1
                if attempt == 3:
                    raise
    return wrapper

@retry
def change_birthdate_request(session, birthdate_payload):
    DEBUG and Output("INFO").log("Change_Birthdate_Request")
    response = session.post("https://users.roblox.com/v1/birthdate", json=birthdate_payload)
    if response.status_code != 200 and response.status_code != 403:
        raise Exception(f"Failed to change birthdate {response.status_code}")
    return response

@retry
def continue_challenge(session, challenge_id, token):
    DEBUG and Output("INFO").log("Change_Birthdate_Continue_Challenge")
    payload = {
        "challengeId": challenge_id,
        "challengeType": "reauthentication",
        "challengeMetadata": dumps({"reauthenticationToken": token}, separators=(",", ":"))
    }

    response = session.post("https://apis.roblox.com/challenge/v1/continue", json=payload)

    if response.status_code != 200:
        raise Exception(f"Reauthentication challenge continue failed {response.status_code}, {response.text}")
    return response

@retry
def change_password_request(session, new_password, old_password, sec_auth_intent):
    payload = {
        "currentPassword": old_password,
        "newPassword": new_password,
        "secureAuthenticationIntent": sec_auth_intent
    }

    response = session.post("https://auth.roblox.com/v2/user/passwords/change", json=payload)

    if response.status_code != 200 or not ".ROBLOSECURITY" in response.cookies:
        raise Exception(f"Failed to change password {response.status_code}, {response.text}")
    return True, response.cookies.get('.ROBLOSECURITY')

def json_stringify(data) -> str:
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False)

class Secure:
    @staticmethod
    def _get_actual_session(session_data):
        """Extract the actual session object from session data"""
        if isinstance(session_data, tuple):
            return session_data[0]  
        return session_data  

    @staticmethod
    def _get_birthdate_headers(session):
        """Get headers for birthdate requests"""
        actual_session = Secure._get_actual_session(session)
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://www.roblox.com",
            "referer": "https://www.roblox.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site"
        }

        return {**actual_session.headers, **headers}

    # credits to valerimyprincess for leaking!
    @staticmethod
    def _handle_chef_challenge(session, challenge_info, account_password):
        DEBUG and Output("INFO").log("Handling Chef Challenge")

        actual_session = Secure._get_actual_session(session)

        cid = challenge_info["id"]
        meta = challenge_info["metadata"]
        uid = meta.get("userId")
        browserTrackerId = meta.get("browserTrackerId")
        script_identifiers = meta.get("scriptIdentifiers", [])

        headers = Secure._get_birthdate_headers(session)

        prelude_resp = actual_session.get("https://apis.roblox.com/rotating-client-service/v1/prelude/latest", headers=headers)
        if prelude_resp.status_code != 200:
            return False, None
        nonce = prelude_resp.text.split('ChefScript.prelude.nonce="', 1)[-1].split('"', 1)[0]

        signing_key = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p, hashfunc=hashlib.sha256)
        exported_verifying_key = b64encode(signing_key.get_verifying_key().to_der()).decode()

        register_payload = {
            'identifier': nonce,
            'key': exported_verifying_key
        }
        actual_session.post("https://apis.roblox.com/rotating-client-service/v1/register", headers=headers, json=register_payload)
        actual_session.get("https://apis.roblox.com/rotating-client-service/v1/defer/raven?pathname=%2Fes%2Fhome", headers=headers)

        expected_symbols = []
        for identifier in script_identifiers:
            resp = actual_session.get(
                f'https://apis.roblox.com/rotating-client-service/v1/fetch?challengeId={cid}&identifier={identifier}',
                headers=headers
            )

            if resp.status_code != 200:
                continue

            try:
                decoded_js = b64decode(resp.text).decode()
                expected_symbol = decoded_js.split('const expectedSymbol="', 1)[-1].split('"', 1)[0]
                rsa_key = decoded_js.split('produceProtectedPayload("', 1)[-1].split('"', 1)[0]
                expected_symbols.append([expected_symbol, rsa_key])
            except:
                continue

        if len(expected_symbols) < 2:
            return False, None

        for expected_symbol, rsa_key in expected_symbols:
            payload_data = {
                "symbolEntry": expected_symbol,
                "events": [
                    "{\"audio\":{\"sampleHash\":1168.9068228197468,\"oscillator\":\"sine\",\"maxChannels\":1,\"channelCountMode\":\"max\"},\"canvas\":{\"commonImageDataHash\":\"178638c684842f30cc1fbaa1bfa16c0f\"},\"fonts\":\"{\\\"Arial Black\\\":531.9140625,\\\"Calibri\\\":420.046875,\\\"Candara\\\":435.4453125,\\\"Comic Sans MS\\\":462.4453125,\\\"Constantia\\\":469.86328125,\\\"Courier\\\":432.0703125,\\\"Courier New\\\":432.0703125,\\\"Franklin Gothic Medium\\\":431.82421875,\\\"Georgia\\\":475.2421875,\\\"Impact\\\":395.54296875,\\\"Lucida Console\\\":433.828125,\\\"Lucida Sans Unicode\\\":472.0078125,\\\"Segoe Print\\\":514.30078125,\\\"Segoe Script\\\":525.234375,\\\"Segoe UI\\\":450,\\\"Tahoma\\\":432.45703125,\\\"Trebuchet MS\\\":428.90625,\\\"Verdana\\\":486.5625}\",\"hardware\":{\"videocard\":{\"vendor\":\"WebKit\",\"renderer\":\"WebKit WebGL\",\"version\":\"WebGL 1.0 (OpenGL ES 2.0 Chromium)\",\"shadingLanguageVersion\":\"WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)\"},\"architecture\":255,\"deviceMemory\":\"8\",\"jsHeapSizeLimit\":4294705152},\"locales\":{\"languages\":\"en-US\",\"timezone\":\"Asia/Yekaterinburg\"},\"permissions\":{\"accelerometer\":\"granted\",\"backgroundFetch\":\"granted\",\"backgroundSync\":\"granted\",\"camera\":\"prompt\",\"clipboardRead\":\"prompt\",\"clipboardWrite\":\"granted\",\"displayCapture\":\"prompt\",\"gyroscope\":\"granted\",\"geolocation\":\"prompt\",\"localFonts\":\"prompt\",\"magnetometer\":\"granted\",\"microphone\":\"prompt\",\"midi\":\"prompt\",\"notifications\":\"prompt\",\"paymentHandler\":\"granted\",\"persistentStorage\":\"prompt\",\"storageAccess\":\"granted\",\"windowManagement\":\"prompt\"},\"plugins\":{\"plugins\":\"[\\\"PDF Viewer|internal-pdf-viewer|Portable Document Format\\\",\\\"Chrome PDF Viewer|internal-pdf-viewer|Portable Document Format\\\",\\\"Chromium PDF Viewer|internal-pdf-viewer|Portable Document Format\\\",\\\"Microsoft Edge PDF Viewer|internal-pdf-viewer|Portable Document Format\\\",\\\"WebKit built-in PDF|internal-pdf-viewer|Portable Document Format\\\"]\"},\"screen\":{\"is_touchscreen\":false,\"maxTouchPoints\":0,\"colorDepth\":24,\"mediaMatches\":[\"prefers-contrast: no-preference\",\"any-hover: hover\",\"any-pointer: fine\",\"pointer: fine\",\"hover: hover\",\"update: fast\",\"prefers-reduced-motion: no-preference\",\"prefers-reduced-transparency: no-preference\",\"scripting: enabled\",\"forced-colors: none\"]},\"system\":{\"platform\":\"Win32\",\"cookieEnabled\":true,\"productSub\":\"20030107\",\"product\":\"Gecko\",\"useragent\":\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36\",\"hardwareConcurrency\":16,\"browser\":{\"name\":\"Chrome\",\"version\":\"141.0\"},\"applePayVersion\":0},\"webgl\":{\"commonImageHash\":\"3a4ed1c6378f68583893dd719f84f6c9\"},\"math\":{\"acos\":1.0471975511965979,\"asin\":-9.614302481290016e-17,\"atan\":4.578239276804769e-17,\"cos\":-4.854249971455313e-16,\"cosh\":1.9468519159297506,\"e\":2.718281828459045,\"largeCos\":0.7639704044417283,\"largeSin\":-0.6452512852657808,\"largeTan\":-0.8446024630198843,\"log\":6.907755278982137,\"pi\":3.141592653589793,\"sin\":-1.9461946644816207e-16,\"sinh\":-0.6288121810679035,\"sqrt\":1.4142135623730951,\"tan\":6.980860926542689e-14,\"tanh\":-0.39008295789884684},\"data_latency_ms\":229.5,\"extension_id\":\"\"}"
                ],
                "metrics": [],
                "nonce": nonce
            }

            payload_data["signature"] = b64encode(
                signing_key.sign(f'{expected_symbol}|{nonce}'.encode())
            ).decode()
            payload_data["preludeTamperedWith"] = False

            aes_key = os.urandom(32)
            iv = os.urandom(12)
            cipher = AES.new(aes_key, AES.MODE_GCM, iv)
            ciphertext, mac_tag = cipher.encrypt_and_digest(json_stringify(payload_data).encode())

            key_cipher = PKCS1_OAEP.new(RSA.import_key(b64decode(rsa_key)))

            submit_payload = {
                'userId': uid,
                'challengeId': cid,
                'payloadV2': b64encode(ciphertext + mac_tag).decode(),
                'params': {
                    'key': b64encode(key_cipher.encrypt(aes_key)).decode(),
                    'iv': b64encode(iv).decode()
                },
                'btid': browserTrackerId
            }

            actual_session.post(
                'https://apis.roblox.com/rotating-client-service/v1/submit',
                headers=headers,
                json=json_stringify(submit_payload)
            )

        continue_payload = {
            "challengeID": cid,
            "challengeMetadata": json.dumps({
                "userId": uid,
                "challengeId": cid,
                "browserTrackerId": browserTrackerId
            }, separators=(",", ":")),
            "challengeType": "chef"
        }

        continue_resp = actual_session.post(
            'https://apis.roblox.com/challenge/v1/continue',
            headers=headers,
            json=continue_payload
        )

        success = continue_resp.status_code == 200
        result = continue_resp.json() if success else None

        return success, result

    @staticmethod
    def _handle_2sv_challenge(session, challenge_info, account_password):
        DEBUG and Output("INFO").log("Handling 2SV Challenge")

        actual_session = Secure._get_actual_session(session)

        cid = challenge_info["id"]
        meta = challenge_info["metadata"]
        inner_id = meta.get("challengeId")
        action = meta.get("actionType", "Generic")
        remember = meta.get("rememberDevice", False)
        uid = meta.get("userId")

        URL_2SV_VERIFY_BASE = "https://twostepverification.roblox.com/v1/users/{userId}/challenges/password/verify"
        URL_CONTINUE = "https://apis.roblox.com/challenge/v1/continue"

        url = URL_2SV_VERIFY_BASE.format(userId=uid)
        payload = {
            "challengeId": inner_id,
            "actionType": action,
            "code": account_password
        }

        verify_headers = {
            **actual_session.headers,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8"
        }

        response = actual_session.post(url, json=payload, headers=verify_headers)

        if response.status_code != 200:
            return False, None

        token = response.json().get("verificationToken")
        if not token:
            return False, None

        cont_payload = {
            "challengeID": cid,
            "challengeType": "twostepverification",
            "challengeMetadata": json.dumps({
                "verificationToken": token,
                "rememberDevice": remember,
                "challengeId": inner_id,
                "actionType": action,
            }),
        }

        continue_headers = {
            **actual_session.headers,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8"
        }

        response = actual_session.post(URL_CONTINUE, json=cont_payload, headers=continue_headers)

        success = response.status_code == 200
        challenge_state = {
            "verification_token": token,
            "inner_2sv_challenge_id": inner_id,
            "action_type": action,
            "remember_device": remember
        } if success else None

        return success, challenge_state

    @staticmethod
    def _process_challenge(session, response, account_password):
        DEBUG and Output("INFO").log("Processing Challenge")

        if response.status_code != 403 or "rblx-challenge-id" not in response.headers:
            return False, None

        initial_challenge_id = response.headers["rblx-challenge-id"]
        initial_challenge_type = response.headers["rblx-challenge-type"]

        challenge_metadata = b64decode(response.headers["rblx-challenge-metadata"]).decode()
        challenge_json = json.loads(challenge_metadata)

        challenge_info = {
            "id": initial_challenge_id,
            "type": initial_challenge_type,
            "metadata": challenge_json,
        }

        challenge_state = {
            "initial_challenge_id": initial_challenge_id,
            "initial_challenge_type": initial_challenge_type
        }

        success = False
        next_challenge = None

        if initial_challenge_type == "chef":
            success, next_challenge = Secure._handle_chef_challenge(session, challenge_info, account_password)
        elif initial_challenge_type == "twostepverification":
            success, state = Secure._handle_2sv_challenge(session, challenge_info, account_password)
            if success and state:
                challenge_state.update(state)
        else:
            return False, None

        if not success:
            return False, None

        if next_challenge and next_challenge.get("challengeType") == "twostepverification":
            metadata_str = next_challenge["challengeMetadata"]
            if metadata_str.strip().startswith("{"):
                parsed_metadata = json.loads(metadata_str)
            else:
                decoded_metadata = b64decode(metadata_str).decode()
                parsed_metadata = json.loads(decoded_metadata)

            success, state = Secure._handle_2sv_challenge(session, {
                "id": next_challenge["challengeId"],
                "metadata": parsed_metadata
            }, account_password)

            if not success or not state:
                return False, None

            challenge_state.update(state)

        return True, challenge_state

    @staticmethod
    def _make_final_birthdate_request(session, birthdate_payload, challenge_state):
        DEBUG and Output("INFO").log("Making Final Birthdate Request")

        actual_session = Secure._get_actual_session(session)

        meta_final = json.dumps({
            "verificationToken": challenge_state["verification_token"],
            "rememberDevice": challenge_state["remember_device"],
            "challengeId": challenge_state["inner_2sv_challenge_id"],
            "actionType": challenge_state["action_type"],
        })

        headers_final = Secure._get_birthdate_headers(session)
        headers_final.update({
            "rblx-challenge-id": challenge_state["initial_challenge_id"],
            "rblx-challenge-metadata": b64encode(meta_final.encode()).decode(),
            "rblx-challenge-type": challenge_state["initial_challenge_type"],
            "x-retry-attempt": "1",
        })

        response = actual_session.post(
            "https://users.roblox.com/v1/birthdate",
            json=birthdate_payload,
            headers=headers_final
        )

        return response.status_code == 200

    @staticmethod
    def change_birthdate(session_data, account):
        DEBUG and Output("INFO").log("Change_Birthdate")
        try:
            actual_session = Secure._get_actual_session(session_data)

            today = datetime.today()
            tomorrow = today + timedelta(days=2)
            adjusted_date = tomorrow.replace(year=tomorrow.year - 13)

            birthdate_payload = {
                "birthDay": adjusted_date.day,
                "birthMonth": adjusted_date.month,
                "birthYear": adjusted_date.year
            }
            headers = Secure._get_birthdate_headers(session_data)

            response = actual_session.post(
                "https://users.roblox.com/v1/birthdate",
                json=birthdate_payload,
                headers=headers
            )

            if response.status_code == 200:
                return True

            if response.status_code == 403:
                success, challenge_state = Secure._process_challenge(session_data, response, account[1])

                if success and challenge_state:
                    return Secure._make_final_birthdate_request(session_data, birthdate_payload, challenge_state)
                else:
                    return False
            else:
                return False

        except Exception as e:
            print(f"Error in change_birthdate: {e}")
            return False

    @staticmethod
    def change_password(session_data, new_password, old_password, sec_auth_intent):
        DEBUG and Output("INFO").log("Change_Password")
        actual_session = Secure._get_actual_session(session_data)
        return change_password_request(actual_session, new_password, old_password, sec_auth_intent)