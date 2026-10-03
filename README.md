
A browser-based voice customer support agent. Open the page, click **Start call**, and talk to Aria.
She answers brand and policy questions and looks up live order details with a tool call.

**Live demo:** aria-voice-agent-beta.vercel.app (use Chrome or Edge and allow the microphone)

## Architecture

```
Browser (Chrome / Edge)
  mic -> SpeechRecognition (en-IN) -> text -> POST /api/chat -> Gemini (+ get_order_details tool) -> reply -> speechSynthesis
Flask API (api/index.py): /api/chat  /api/orders  /api/order  /api/summary  /api/health
```

- **Frontend:** React (Vite). Handles the mic, the Listening / Thinking / Speaking indicator, the test orders panel, the transcript and the post-call summary.
- **Backend:** Python (Flask) on Vercel as a serverless function. The API key stays on the server.
- **LLM:** Gemini with function calling. The model decides when to call `get_order_details`; the API runs it and gives the result back to the model.
- **Guardrails:** Brand policies are in the system prompt. Eligibility flags (`cancellable`, `return_window_open`) are calculated in the tool, not by the LLM.
- **Voice:** The browser picks the best Indian voice available: Neerja, then a Google en-IN voice, then Prabhat or any "Natural" voice, then any en-IN voice, then the default voice.
- **Reliability:** Gemini model fallbacks with one retry, so a busy or retired model does not end the call.
- **Post-call:** On End call, the transcript goes to `/api/summary`, which returns the structured JSON outcome.

## Run locally

Needs Python 3.10+ and Node 18+.

1. Copy `.env.example` to `.env` and fill it in:

   | Variable | Meaning |
   |---|---|
   | `GEMINI_API_KEY` | Free key from https://aistudio.google.com |
   | `GEMINI_MODEL` | Main Gemini model |
   | `GEMINI_FALLBACKS` | Comma-separated backup models |

2. Start the backend from the project root:
   ```bash
   pip install -r requirements.txt
   python api/index.py
   ```
3. In a second terminal, start the frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:5173 in Chrome or Edge, allow the microphone, and click **Start call**.

## Try these

- "Where is my order ORD-101?" (order lookup)
- "I bought ORD-102 and opened it, can I return it?" (outside the 7-day return window)
- "Cancel ORD-103" works, "Cancel ORD-101" does not (only while Processing)
- "Can you book me a flight to Goa?" (out of scope)
- "Check order ORD-999" (order not found)

## Known limitations

- Voice calls work only in Chrome and Edge, and need an internet connection.
- The voice comes from the browser, so it sounds different on different devices.
- No barge-in: Aria cannot be interrupted while she speaks.
- A network error ends the call, and the transcript is not saved after a page reload.

## Deploy

Push to GitHub, import the repo in Vercel (framework preset: Other), and add the three environment variables above. `vercel.json` handles the build and routes `/api/*` to the Flask function.

## Tell Us How You Think

### 1. Why did you choose this architecture and stack?

I wanted a voice agent that works well and is easy to deploy and explain. The frontend is React (Vite) and the backend is Flask, because I could build and debug them fastest. The browser handles speech, using Chrome/Edge speech recognition to listen and speech synthesis to talk. Flask sends the conversation to Gemini, which decides when to call `get_order_details`. Both parts run on Vercel, so evaluators get one link and no sleeping server. Rules like `cancellable` are calculated in the tool, not by the LLM, and the brand policies are in the system prompt, so Aria does not just agree with the customer.

### 2. What was the most difficult part, and how did you solve it?

Making the voice loop reliable. Browser speech recognition sometimes gives half sentences or mishears things like "order 101", and some Gemini models were retired (404) or busy (503). I added model fallbacks with one retry, so one bad model does not end the call. I also tuned the prompt so Aria reads order IDs slowly, asks the customer to repeat when audio is unclear, and asks them to verify the ID if an order is not found. In my testing, listening one sentence at a time was the most stable and ignored background noise best.

### 3. If you had one more week, what would you improve first?

Reliability, because that decides whether a call feels broken. Right now a network error ends the call and the transcript is lost on reload. I would keep the call alive with a "Reconnecting…" message, save the transcript in the browser, add request timeouts, and add a timer so a single unclear word gets a polite "please repeat". After that, I would add a better speech service like Deepgram, then barge-in and Hinglish.

### 4. What would change at 1,000 conversations a day?

- **Capacity and cost:** move to a paid LLM plan with rate limits and cost tracking, and add authentication and rate limiting to the API, which is open to anyone with the link right now.
- **Data:** replace the mock orders with a real order system, verify the customer's identity, and handle customer data privately.
- **Quality:** log every call with its outcome, review failures, and run automated policy tests so a prompt change cannot break the return or cancellation rules.
- **Speech:** use a dedicated speech service with monitoring instead of the browser's engine.
- **Support flow:** add a way to hand off to a human, plus real actions like cancelling an order. Today Aria only explains the cancellation policy.
