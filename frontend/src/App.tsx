import { useEffect, useRef, useState } from "react";
import { ChatThread, type Msg } from "./components/ChatThread";
import { ActionLog } from "./components/ActionLog";
import { ApprovalModal, type Req } from "./components/ApprovalModal";
import { SettingsPanel } from "./components/SettingsPanel";
import { approve, cancel, onAgentEvent, sendMessage, type AgentEvent } from "./api/bridge";

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [steps, setSteps] = useState<string[]>([]);
  const [approval, setApproval] = useState<Req | null>(null);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onAgentEvent((e: AgentEvent) => {
      if (e.type === "step") setSteps((s) => [...s, e.text ?? ""]);
      else if (e.type === "approval") setApproval(e.request ?? null);
      else if (e.type === "final") {
        setMessages((m) => [...m, { role: "agent", text: e.text ?? "" }]);
        setBusy(false);
      } else if (e.type === "error") {
        setMessages((m) => [...m, { role: "agent", text: `Error: ${e.text}` }]);
        setBusy(false);
      }
    });
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, approval]);

  async function submit() {
    if (!input.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: input }]);
    setBusy(true);
    const turnId = await sendMessage(input);
    setInput("");
    if (turnId === "busy") setBusy(false);
  }

  function decide(decision: "approve" | "reject") {
    setApproval(null);
    approve({ decision });
  }

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      {/* Conversation column */}
      <div style={{ flex: 2, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontWeight: 600 }}>
          DeskButler {busy && <span style={{ color: "var(--muted)", fontWeight: 400 }}>· working…</span>}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {messages.length === 0 && (
            <p style={{ color: "var(--muted)" }}>
              Ask me to list a folder or move a file. Try: “list my Downloads”.
            </p>
          )}
          <ChatThread messages={messages} />
          <ApprovalModal request={approval} onApprove={() => decide("approve")} onReject={() => decide("reject")} />
          <div ref={endRef} />
        </div>
        <div style={{ display: "flex", gap: 8, padding: 16, borderTop: "1px solid var(--border)" }}>
          <input
            style={{ flex: 1 }}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            disabled={busy}
            placeholder="Ask me to list or move files…"
          />
          <button onClick={submit} disabled={busy}>Send</button>
          {busy && (
            <button
              style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)" }}
              onClick={() => { cancel(); setBusy(false); }}
            >
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Activity + settings rail */}
      <div style={{ flex: 1, minWidth: 260, borderLeft: "1px solid var(--border)", padding: 16, overflowY: "auto", background: "var(--surface)" }}>
        <ActionLog steps={steps} />
        <div style={{ height: 24 }} />
        <SettingsPanel />
      </div>
    </div>
  );
}
