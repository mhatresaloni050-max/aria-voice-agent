import { useEffect, useRef, useState } from "react";

const LABEL = { idle: "Not in a call", listening: "Listening", thinking: "Thinking",
  speaking: "Speaking", summarizing: "Summarising call…" };
const GREETING = "Hello, this is Aria from Aura Skincare. How can I help you today?";
const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

export default function App() {
  const [state, setState] = useState("idle");
  const [log, setLog] = useState([]);
  const [summary, setSummary] = useState(null);
  const [orders, setOrders] = useState([]);
  const [error, setError] = useState("");
  const [heard, setHeard] = useState("");
  const [dbg, setDbg] = useState("");
  const live = useRef(false), rec = useRef(null), hist = useRef([]), voice = useRef(null), n = useRef(0);

  useEffect(() => {
    fetch("/api/orders").then(r => r.json()).then(setOrders).catch(() => {});
    const pick = () => {
  const v = speechSynthesis.getVoices();
  voice.current = 
    v.find(x => x.name.includes("Neerja")) ||
    v.find(x => x.name.includes("Google") && x.lang.replace('_', '-').toLowerCase().includes("en-in")) ||
    v.find(x => x.name.includes("Prabhat") || x.name.includes("Natural")) ||
    v.find(x => x.lang.replace('_', '-').toLowerCase() === "en-in") ||
    v.find(x => x.default) || 
    v[0] || 
    null;
};
    pick(); speechSynthesis.onvoiceschanged = pick;
  }, []);

  const add = (role, text) => { hist.current.push({ role, text }); setLog(l => [...l, { id: n.current++, role, text }]); };

  const speak = (text, then) => {
  setState("speaking");
  speechSynthesis.cancel(); // Clears stuck speech queues in Chromium

  // Re-verify voice selection in case voices loaded after component mount
  if (!voice.current) {
    const v = speechSynthesis.getVoices();
    voice.current = 
      v.find(x => x.name.includes("Neerja")) ||
      v.find(x => x.name.includes("Google") && x.lang.replace('_', '-').toLowerCase().includes("en-in")) ||
      v.find(x => x.name.includes("Prabhat") || x.name.includes("Natural")) ||
      v.find(x => x.lang.replace('_', '-').toLowerCase() === "en-in") ||
      v.find(x => x.default) || 
      v[0] || 
      null;
  }

  const u = new SpeechSynthesisUtterance(text);
  if (voice.current) u.voice = voice.current;
  u.lang = voice.current?.lang || "en-IN"; 
  u.rate = 1.03;

  u.onstart = () => {
    if (speechSynthesis.paused) {
      speechSynthesis.resume();
    }
  };

  u.onend = u.onerror = () => { 
    if (live.current && then) then(); 
  };

  speechSynthesis.speak(u);
};

  const listen = () => {
    if (!live.current) return;
    setState("listening");
    const r = new SR(); rec.current = r;
    r.lang = "en-IN"; r.interimResults = true; r.continuous = false;
    let got = false;
    r.onstart = () => setDbg("Recognition started, waiting for mic audio…");
    r.onaudiostart = () => setDbg("Mic is active. Speak now.");
    r.onspeechstart = () => setDbg("Speech detected.");
    r.onresult = (e) => {
      let interim = "", final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t; else interim += t;
      }
      if (interim) setHeard(interim);
      if (final.trim()) { got = true; setHeard(""); respond(final.trim()); }
    };
    r.onerror = (e) => {
      setDbg("Recognition event: " + e.error);
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setError("Microphone access was blocked. Allow it and start the call again."); end(false);
      } else if (e.error === "network") {
        setError("Speech recognition can't reach the speech service (network error). Use Chrome or Edge with internet access; Brave and Opera don't support it."); end(false);
      } else if (e.error === "audio-capture") {
        setError("No working microphone found. Check your input device."); end(false);
      }
    };
    r.onend = () => { if (live.current && !got && !r._busy) setTimeout(listen, 200); };
    try { r.start(); } catch {}
  };

  const respond = async (text) => {
    add("user", text); setState("thinking");
    try {
      const d = await (await fetch("/api/chat", json({ messages: hist.current }))).json();
      if (!live.current) return;
      if (d.error) console.warn(d.error);
      add("agent", d.reply); speak(d.reply, listen);
    } catch {
      if (!live.current) return;
      const m = "Sorry, I'm having trouble connecting. Please try again.";
      add("agent", m); speak(m, listen);
    }
  };

  const start = async () => {
    if (!SR) { setError("Speech recognition isn't supported here. Use Chrome or Edge."); return; }
    setError(""); setSummary(null); setLog([]); hist.current = []; n.current = 0;
    try { (await navigator.mediaDevices.getUserMedia({ audio: true })).getTracks().forEach(t => t.stop()); }
    catch { setError("Microphone access was blocked. Allow it and try again."); return; }
    live.current = true; add("agent", GREETING); speak(GREETING, listen);
  };

  const end = async (summarise = true) => {
    live.current = false;
    speechSynthesis.cancel(); try { rec.current?.abort(); } catch {}
    if (!summarise) { setState("idle"); return; }
    setState("summarizing");
    try {
      const transcript = hist.current.map(({ role, text }) => ({ role, text }));
      const d = await (await fetch("/api/summary", json({ transcript }))).json();
      if (d.error) throw new Error(d.error);
      setSummary(d);
    } catch { setError("Could not generate the summary."); }
    setState("idle");
  };

  const inCall = !["idle", "summarizing"].includes(state);

  return (
    <main>
      <header>
        <h1>Aria, Aura Skincare support</h1>
        <p>Start a call and speak to Aria. Try the sample orders below. Works best in Chrome or Edge.</p>
      </header>

      <section className="call">
        <div className={`pill ${state}`}><span className="dot" />{LABEL[state]}</div>
        {!inCall
          ? <button className="go" onClick={start} disabled={state === "summarizing"}>Start call</button>
          : <button className="stop" onClick={() => end()}>End call</button>}
        {state === "listening" && dbg && <p className="muted">{dbg}</p>}
        {state === "listening" && heard && <p className="muted">Hearing: {heard}</p>}
        {error && <p className="err">{error}</p>}
      </section>

      <section>
        <h2>Test orders</h2>
        <div className="orders">
          {orders.map(o => (
            <div className="order" key={o.order_id}>
              <b>{o.order_id}</b> · {o.customer}
              <div>{o.product} · ₹{o.value_inr}</div>
              <div className="st">{o.status}</div>
              <small>{[o.carrier && `${o.carrier} ${o.tracking_id}`, o.notes].filter(Boolean).join(" · ")}</small>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2>Transcript</h2>
        {log.length === 0 && <p className="muted">The conversation will appear here.</p>}
        {log.map(t => (
          <p key={t.id} className={`line ${t.role}`}><b>{t.role === "agent" ? "Aria" : "Customer"}</b>{t.text}</p>
        ))}
      </section>

      {summary && (
        <section>
          <h2>Call outcome</h2>
          <pre>{JSON.stringify(summary, null, 2)}</pre>
        </section>
      )}
    </main>
  );
}
