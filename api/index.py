import json, os, re, time
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
app = Flask(__name__)   # on Vercel the React build is served as static files; this app only serves /api/*

KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
FALLBACKS = [m.strip() for m in os.getenv("GEMINI_FALLBACKS", "gemini-flash-latest,gemini-3.1-flash-lite").split(",") if m.strip()]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

ORDERS = {
    "ORD-101": {"order_id": "ORD-101", "customer": "Priya Sharma", "product": "Vitamin C Serum (30ml)",
                "value_inr": 699, "status": "Out for Delivery", "carrier": "BlueDart",
                "tracking_id": "BD-982103", "notes": "Expected by 6 PM today"},
    "ORD-102": {"order_id": "ORD-102", "customer": "Rahul Verma", "product": "Hydrating Sunscreen SPF 50",
                "value_inr": 499, "status": "Delivered", "carrier": "Delhivery",
                "tracking_id": "DL-441029", "notes": "Delivered 14 days ago", "delivered_days_ago": 14},
    "ORD-103": {"order_id": "ORD-103", "customer": "Ananya Patel", "product": "Green Tea Face Wash + Toner",
                "value_inr": 850, "status": "Processing", "carrier": None,
                "tracking_id": None, "notes": "Ordered 3 hours ago"},
}

SYSTEM_PROMPT = """You are Aria, a friendly, professional, concise Indian customer support specialist for Aura Skincare, a premium organic Indian skincare brand. You are on a live VOICE call.

STYLE
- Speak in warm Indian English. If the customer speaks Hinglish, reply in simple Hinglish.
- Keep replies to 1-2 short sentences. No lists, no markdown. Ask one question at a time.
- Do not repeat what the customer said. Read order/tracking IDs slowly, character by character.
- Your words are spoken by a text-to-speech voice: write "rupees" instead of symbols, no emojis, and say order IDs like "O R D, one zero one".
- The customer's speech is auto-transcribed and may contain errors. "order 101" or "ord 101" means ORD-101; pass it to the tool as ORD-101.

BRAND POLICIES (the only source of truth; never invent others)
- Shipping: free delivery above Rs 499; orders below Rs 499 have a Rs 50 fee. Standard delivery 3-5 business days.
- Returns: within 7 days of delivery, only unopened, unused products in original packaging. Damaged/defective items must be reported within 48 hours of delivery with photos, for a replacement.
- Cancellation: only while status is Processing. Once Shipped or Out for Delivery it cannot be cancelled; the customer may refuse delivery at the doorstep.
- COD: available for orders up to Rs 2,500; pay by cash or UPI at the doorstep.

RULES
- Never promise a refund, replacement, discount or exception outside these policies. If a request falls outside policy, politely explain why and offer the closest allowed option.
- You can only help with Aura Skincare topics. Politely decline anything else (e.g. flights) and steer back.
- For any question about a specific order, ask for the order ID if missing, then call get_order_details. Never guess order details. Use the tool result (including cancellable / return_window_open flags) to apply policy.
- If the tool says the order is not found, say you could not locate it and ask the customer to repeat or verify the ID. Do not make up data.
- If audio is unclear or you are unsure, ask the customer to repeat. If you lack information (medical advice, ingredient details not given, refunds status), say so honestly and offer a human follow-up instead of guessing.
- Do not claim you performed actions (cancellation, refund) you have no tool for; explain the policy and next step instead."""

TOOLS = [{"functionDeclarations": [{
    "name": "get_order_details",
    "description": "Look up an Aura Skincare order by ID (format ORD-###). Call whenever the customer asks about a specific order's status, delivery, cancellation or return.",
    "parameters": {"type": "OBJECT",
                   "properties": {"order_id": {"type": "STRING", "description": "Order ID, e.g. ORD-101"}},
                   "required": ["order_id"]},
}]}]


def normalize_id(raw):
    m = re.search(r"ORD\D{0,3}(\d+)", (raw or "").upper())
    return f"ORD-{m.group(1)}" if m else None


def get_order_details(order_id):
    oid = normalize_id(order_id)
    if not oid:
        return {"found": False, "error": "Missing or malformed order ID. Ask the customer for an ID like ORD-101."}
    order = ORDERS.get(oid)
    if not order:
        return {"found": False, "error": f"No order found for {oid}. Ask the customer to verify the ID."}
    days = order.get("delivered_days_ago")
    return {"found": True, **order,
            "cancellable": order["status"] == "Processing",
            "return_window_open": days is not None and days <= 7}


@app.get("/api/orders")
def orders():
    return jsonify(list(ORDERS.values()))


@app.post("/api/order")
def order():
    return jsonify(get_order_details((request.get_json(silent=True) or {}).get("order_id")))


def gemini(body):
    """Try the main model (one retry on 503), then fall back to other models if it is overloaded or unavailable."""
    last = None
    for model in [MODEL] + FALLBACKS:
        cfg = {k: v for k, v in body.get("generationConfig", {}).items()
               if not (k == "thinkingConfig" and "2.5" not in model)}  # thinkingBudget only valid on 2.5-era models
        payload = {**body, "generationConfig": cfg}
        for _ in range(2):
            last = requests.post(URL.format(model), headers={"x-goog-api-key": KEY or ""}, json=payload, timeout=30)
            if last.ok:
                return last.json()
            if last.status_code != 503:
                break
            time.sleep(0.8)
        print(f"Gemini {model} failed ({last.status_code}), trying next model")
        if last.status_code not in (429, 404, 500, 503):
            break
    last.raise_for_status()


@app.post("/api/chat")
def chat():
    """One conversational turn: LLM decides whether to call get_order_details, we run it, LLM answers."""
    if not KEY:
        return jsonify(reply="The server is missing its Gemini key.", error="GEMINI_API_KEY not set"), 500
    msgs = (request.get_json(silent=True) or {}).get("messages", [])
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["text"]}]} for m in msgs]
    while contents and contents[0]["role"] == "model":
        contents.pop(0)  # Gemini needs the history to start with a user turn
    used_order = None
    try:
        for _ in range(4):
            data = gemini({"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": contents,
                           "tools": TOOLS,
                           "generationConfig": {"temperature": 0.6, "maxOutputTokens": 300,
                                                "thinkingConfig": {"thinkingBudget": 0}}})
            cands = data.get("candidates") or []
            content = (cands[0].get("content") if cands else None) or {}
            parts = content.get("parts", [])
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                text = "".join(p.get("text", "") for p in parts).strip()
                return jsonify(reply=text or "Sorry, could you please say that again?", order_id=used_order)
            contents.append({"role": "model", "parts": parts})
            results = []
            for c in calls:
                res = get_order_details((c.get("args") or {}).get("order_id"))
                if res.get("found"):
                    used_order = res["order_id"]
                results.append({"functionResponse": {"name": c["name"], "response": {"result": res}}})
            contents.append({"role": "user", "parts": results})
        return jsonify(reply="Sorry, I ran into a problem. Could you please repeat that?")
    except requests.HTTPError as e:
        body = e.response.text if e.response is not None else str(e)
        print("GEMINI ERROR:", body)
        busy = e.response is not None and e.response.status_code == 429
        return jsonify(reply="I'm a little busy right now. Please try again in a moment." if busy
                       else "Sorry, I'm having trouble right now. Please try again.", error=body), 200
    except Exception as e:
        print("CHAT ERROR:", repr(e))
        return jsonify(reply="Sorry, I'm having trouble right now. Please try again.", error=repr(e)), 200


@app.post("/api/summary")
def summary():
    transcript = (request.get_json(silent=True) or {}).get("transcript", [])
    text = "\n".join(f"{t['role'].upper()}: {t['text']}" for t in transcript)
    if not text.strip():
        return jsonify({"customer_intent": "NONE", "order_id": None, "resolution_status": "NO_CONVERSATION",
                        "call_summary": "No conversation took place."})
    prompt = ("Summarise this customer support call. Return ONLY JSON with keys: customer_intent "
              "(ORDER_TRACKING | CANCELLATION | RETURN_REFUND | PRODUCT_INFO | SHIPPING | COD | OUT_OF_SCOPE | OTHER), "
              "order_id (string or null), resolution_status (RESOLVED | UNRESOLVED | ESCALATION_NEEDED), "
              "call_summary (1-2 sentences).\n\n" + text)
    try:
        data = gemini({"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json",
                                            "thinkingConfig": {"thinkingBudget": 0}}})
        return jsonify(json.loads(data["candidates"][0]["content"]["parts"][0]["text"]))
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.get("/api/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
