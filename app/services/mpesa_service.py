"""
M-Pesa Daraja integration.

Two separate concerns live here:
1. STK Push ("Lipa na M-Pesa Online") — used to actively collect a payment
   (tenant paying rent, landlord paying their RMS subscription) where we
   know exactly which invoice/subscription the payment is for because we
   initiated it. See app/routers/mpesa.py + MpesaSTKRequest.
2. parse_mpesa_sms() — a best-effort parser for a pasted M-Pesa confirmation
   message, used by the Expense module (landlord/caretaker pastes the SMS
   instead of manually typing the code/amount/date) and available for the
   payments flow too if a tenant pastes their confirmation text.

Sandbox vs production is controlled by MPESA_ENV. Nothing here calls out to
Safaricom unless MPESA_CONSUMER_KEY/SECRET are actually configured — with
blank credentials, stk_push() raises a clear config error instead of making
a doomed request.
"""
import re
import base64
from datetime import datetime, timedelta
from typing import Optional

import requests
from fastapi import HTTPException, status

from app.core.config import settings


class MpesaService:
    _token_cache: dict = {"token": None, "expires_at": None}

    # --- Setup -----------------------------------------------------------

    @classmethod
    def _base_url(cls) -> str:
        return "https://api.safaricom.co.ke" if settings.MPESA_ENV == "production" else "https://sandbox.safaricom.co.ke"

    @classmethod
    def _check_configured(cls):
        missing = [
            name for name, val in (
                ("MPESA_CONSUMER_KEY", settings.MPESA_CONSUMER_KEY),
                ("MPESA_CONSUMER_SECRET", settings.MPESA_CONSUMER_SECRET),
                ("MPESA_SHORTCODE", settings.MPESA_SHORTCODE),
                ("MPESA_PASSKEY", settings.MPESA_PASSKEY),
                ("MPESA_CALLBACK_BASE_URL", settings.MPESA_CALLBACK_BASE_URL),
            ) if not val
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"M-Pesa is not configured yet. Missing: {', '.join(missing)}",
            )

    @classmethod
    def get_access_token(cls) -> str:
        cls._check_configured()
        now = datetime.now()
        cached_token = cls._token_cache.get("token")
        cached_expiry = cls._token_cache.get("expires_at")
        if cached_token and cached_expiry and now < cached_expiry:
            return cached_token

        url = f"{cls._base_url()}/oauth/v1/generate?grant_type=client_credentials"
        try:
            resp = requests.get(
                url,
                auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach M-Pesa: {e}")

        data = resp.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 3599))
        cls._token_cache = {"token": token, "expires_at": now + timedelta(seconds=expires_in - 60)}
        return token

    @classmethod
    def _password(cls, timestamp: str) -> str:
        raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        return base64.b64encode(raw.encode()).decode()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        phone = (phone or "").strip().replace(" ", "").replace("+", "").replace("-", "")
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif phone.startswith("7") or phone.startswith("1"):
            phone = "254" + phone
        return phone

    # --- STK Push ----------------------------------------------------------

    @classmethod
    def stk_push(cls, phone_number: str, amount: float, account_reference: str, transaction_desc: str, callback_path: str) -> dict:
        """Initiates an STK push prompt on the payer's phone. Returns the
        raw Safaricom response (contains CheckoutRequestID/MerchantRequestID
        the caller must persist to match the async callback later)."""
        cls._check_configured()
        phone = cls.normalize_phone(phone_number)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = cls._password(timestamp)
        token = cls.get_access_token()

        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(round(amount)),
            "PartyA": phone,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": f"{settings.MPESA_CALLBACK_BASE_URL.rstrip('/')}{callback_path}",
            "AccountReference": (account_reference or "RMS")[:12],
            "TransactionDesc": (transaction_desc or "Payment")[:100],
        }
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = requests.post(
                f"{cls._base_url()}/mpesa/stkpush/v1/processrequest",
                json=payload, headers=headers, timeout=20,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"STK push failed: {e}")

        return resp.json()

    @staticmethod
    def parse_stk_callback(body: dict) -> dict:
        """Flattens Safaricom's nested STK push callback payload."""
        stk = (body or {}).get("Body", {}).get("stkCallback", {})
        result = {
            "checkout_request_id": stk.get("CheckoutRequestID"),
            "merchant_request_id": stk.get("MerchantRequestID"),
            "result_code": stk.get("ResultCode"),
            "result_desc": stk.get("ResultDesc"),
            "amount": None,
            "mpesa_receipt": None,
            "phone_number": None,
            "transaction_date": None,
        }
        items = stk.get("CallbackMetadata", {}).get("Item", [])
        for item in items:
            name = item.get("Name")
            value = item.get("Value")
            if name == "Amount":
                result["amount"] = value
            elif name == "MpesaReceiptNumber":
                result["mpesa_receipt"] = value
            elif name == "PhoneNumber":
                result["phone_number"] = str(value)
            elif name == "TransactionDate":
                result["transaction_date"] = value
        return result

    # --- SMS confirmation parsing -----------------------------------------

    @staticmethod
    def parse_mpesa_sms(text: str) -> dict:
        """
        Best-effort regex parse of a pasted M-Pesa confirmation SMS, e.g.:
        "QAR7XXXXX Confirmed. Ksh1,500.00 sent to JOHN DOE on 12/7/26 at
        2:45 PM. New M-PESA balance is Ksh3,240.00."

        Never raises — returns whatever it could confidently extract and
        leaves the rest None so the caller falls back to what the user
        typed manually.
        """
        text = text or ""
        result: dict = {"mpesa_code": None, "amount": None, "date": None, "recipient": None, "phone": None}

        code_match = re.search(r'\b([A-Z0-9]{10})\b\s+Confirmed', text) or re.search(r'^\s*([A-Z0-9]{10})\b', text.strip())
        if code_match:
            result["mpesa_code"] = code_match.group(1)

        amount_match = re.search(r'Ksh\s?([\d,]+\.?\d*)', text, re.IGNORECASE)
        if amount_match:
            try:
                result["amount"] = float(amount_match.group(1).replace(",", ""))
            except ValueError:
                pass

        date_match = re.search(r'on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s?[AP]M)', text, re.IGNORECASE)
        if date_match:
            for fmt in ("%d/%m/%y %I:%M %p", "%d/%m/%Y %I:%M %p"):
                try:
                    result["date"] = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)}", fmt)
                    break
                except ValueError:
                    continue

        recipient_match = re.search(r'sent to\s+([A-Z ]+?)(?:\s+on\s+\d)', text, re.IGNORECASE)
        if recipient_match:
            result["recipient"] = recipient_match.group(1).strip()

        phone_match = re.search(r'(2547\d{8}|07\d{8}|2541\d{8}|01\d{8})', text)
        if phone_match:
            result["phone"] = phone_match.group(1)

        return result
