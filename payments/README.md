# Payments site

A small public payment page. Visitors enter an amount and are sent to **Stripe Checkout**
to pay; card details never touch this server. Stripe notifies the app of completed
payments through a signed webhook.

## 1. Stripe setup
1. Create a Stripe account and get your **secret key** (Dashboard → Developers → API keys).
   Use the `sk_test_...` key while testing.
2. Add a webhook endpoint (Dashboard → Developers → Webhooks):
   - URL: `https://pay.example.com/webhook`
   - Event: `checkout.session.completed`
   - Copy the **signing secret** (`whsec_...`).

## 2. Run locally
```bash
pip install -r requirements.txt
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...      # from `stripe listen` when testing locally
python3 app.py                                # http://localhost:8080
```
Test card: `4242 4242 4242 4242`, any future date, any CVC.

## 3. Build and push the image
```bash
docker build -t ghcr.io/YOUR_USER/payments:1.0.0 .
docker push ghcr.io/YOUR_USER/payments:1.0.0
```

## 4. Deploy to Kubernetes
Edit the lines marked `CHANGE` in `k8s/configmap.yaml`, `k8s/deployment.yaml` and
`k8s/ingress.yaml`, then:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl -n payments create secret generic payments-secrets \
  --from-literal=STRIPE_SECRET_KEY=sk_live_... \
  --from-literal=STRIPE_WEBHOOK_SECRET=whsec_...
kubectl apply -k k8s/
kubectl -n payments get pods,ingress
```
Never commit your Stripe keys to git.

## Configuration
| Variable | Purpose |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe API key (secret) |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret (secret) |
| `BASE_URL` | Public URL, used for Stripe success/cancel redirects |
| `BUSINESS_NAME` | Name shown to payers |
| `CURRENCY` | ISO currency code, default `usd` |
| `MIN_AMOUNT` / `MAX_AMOUNT` | Allowed payment range |

## Recording payments
`/webhook` logs each completed payment. Add your own code at the `TODO` in `app.py`
to save payments to a database or notify you. The `/success` page alone is not proof
of payment.
