# Aria: AI Voice Support Agent for Aura Skincare

Browser voice agent. React (Vite) frontend, Flask API on Vercel, Gemini for the LLM,
Chrome/Edge speech recognition (STT) and the browser's speech synthesis (TTS).

## Architecture
```
Browser (Chrome / Edge)
  mic ─▶ SpeechRecognition (en-IN) ─▶ text ─▶ POST /api/chat ─▶ Gemini (+ get_order_details tool) ─▶ reply ─▶ speechSynthesis
API (api/index.py): /api/chat  /api/orders  /api/order  /api/summary  /api/health
```
- The API key stays server-side. Gemini decides when to call `get_order_details`; the API runs it and feeds the result back.
  Policy flags (`cancellable`, `return_window_open`) are computed in the tool, not left to the LLM.
- Indian voice with fallbacks (in the browser): Microsoft Neerja (en-IN neural) → Google en-IN voice → Prabhat / any "Natural" voice →
  any en-IN voice → browser default voice → first available voice, so Aria always speaks.
- On End call, the transcript goes to `/api/summary` for the structured JSON outcome.
- Gemini model fallbacks with retries handle busy or unavailable models.

## Run locally
```bash
cp .env.example .env            # add GEMINI_API_KEY
pip install -r requirements.txt
python api/index.py             # API on http://localhost:5000
cd frontend && npm install && npm run dev   # open http://localhost:5173 in Chrome or Edge
```

## Deploy on Vercel
1. Push the repo to GitHub. In Vercel: Add New → Project → import the repo (Framework preset: Other, root directory: repo root).
2. `vercel.json` already sets the build and routes `/api/*` to the Flask function.
3. Settings → Environment Variables: add `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACKS`, then redeploy.
4. Open the production URL in a private window while logged out. If Vercel asks for a login, turn off Deployment Protection.

## Test scripts
- "Where is ORD-101?" / "Check ORD-999" (not found)
- "I bought ORD-102 and opened it, can I return it?" (outside the 7-day window)
- "Cancel ORD-103" (allowed) / "Cancel ORD-101" (not allowed)
- "Book me a flight to Goa" (out of scope)

## How I think
1. **Architecture and stack:** _write your own answer_
2. **Hardest part:** _write your own answer_
3. **One more week:** _write your own answer_
4. **1,000 calls a day:** _write your own answer_
