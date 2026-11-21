"""Public payment page backed by Stripe Checkout.

Card details are entered on Stripe's hosted checkout page and never reach this
server. Confirmed payments arrive through the /webhook endpoint.
"""
import logging
import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import stripe
from flask import Flask, abort, jsonify, redirect, render_template, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("payments")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "My Business")
CURRENCY = os.environ.get("CURRENCY", "usd").lower()
MIN_AMOUNT = Decimal(os.environ.get("MIN_AMOUNT", "1.00"))
MAX_AMOUNT = Decimal(os.environ.get("MAX_AMOUNT", "10000.00"))
MAX_NOTE_LENGTH = 200

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # reject oversized request bodies


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "form-action 'self' https://checkout.stripe.com; frame-ancestors 'none'"
    )
    return resp


def parse_amount(raw):
    """Return the amount in cents, or raise ValueError with a user-facing message."""
    try:
        amount = Decimal((raw or "").strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError("Please enter a valid amount, like 25.00.")
    if not amount.is_finite():
        raise ValueError("Please enter a valid amount, like 25.00.")
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
        raise ValueError(f"Amount must be between {MIN_AMOUNT:.2f} and {MAX_AMOUNT:.2f}.")
    return int(amount * 100)


def render_form(error=None, status=200, **values):
    return (
        render_template(
            "index.html",
            business=BUSINESS_NAME,
            currency=CURRENCY.upper(),
            min_amount=MIN_AMOUNT,
            max_amount=MAX_AMOUNT,
            max_note=MAX_NOTE_LENGTH,
            error=error,
            **values,
        ),
        status,
    )


@app.get("/")
def index():
    return render_form()


@app.post("/checkout")
def checkout():
    amount_raw = request.form.get("amount", "")
    note = (request.form.get("note") or "").strip()[:MAX_NOTE_LENGTH]
    try:
        cents = parse_amount(amount_raw)
    except ValueError as exc:
        return render_form(error=str(exc), status=400, amount=amount_raw, note=note)

    product = {"name": f"Payment to {BUSINESS_NAME}"}
    if note:
        product["description"] = note
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "quantity": 1,
                "price_data": {"currency": CURRENCY, "unit_amount": cents, "product_data": product},
            }],
            success_url=f"{BASE_URL}/success",
            cancel_url=f"{BASE_URL}/cancel",
            metadata={"note": note},
        )
    except stripe.StripeError:
        log.exception("Could not create Stripe Checkout session")
        return render_form(
            error="We couldn't start the payment. Please try again in a moment.",
            status=502, amount=amount_raw, note=note,
        )
    return redirect(session.url, code=303)


@app.get("/success")
def success():
    # Showing this page is not proof of payment; the webhook is the source of truth.
    return render_template("message.html", business=BUSINESS_NAME, title="Thank you!",
                           body="Your payment was submitted. A receipt will be emailed to you.")


@app.get("/cancel")
def cancel():
    return render_template("message.html", business=BUSINESS_NAME, title="Payment cancelled",
                           body="No charge was made.", show_back=True)


@app.post("/webhook")
def webhook():
    if not WEBHOOK_SECRET:
        log.error("STRIPE_WEBHOOK_SECRET is not set; rejecting webhook")
        abort(500)
    try:
        event = stripe.Webhook.construct_event(
            request.get_data(), request.headers.get("Stripe-Signature", ""), WEBHOOK_SECRET
        )
    except (ValueError, stripe.SignatureVerificationError):
        abort(400)

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        log.info("Payment completed: session=%s amount=%s %s status=%s",
                 s["id"], s.get("amount_total"), s.get("currency"), s.get("payment_status"))
        # TODO: record the payment in your database / send it to your accounting system here.
    return jsonify(received=True)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
