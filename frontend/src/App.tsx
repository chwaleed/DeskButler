import { useEffect, useState } from "react";
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
    <div style={{ display: "flex", gap: 16, padding: 16 }}>
      <div style={{ flex: 2 }}>
        <ChatThread messages={messages} />
        <ApprovalModal request={approval} onApprove={() => decide("approve")} onReject={() => decide("reject")} />
        <div>
          <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} placeholder="Ask me to list or move files…" />
          <button onClick={submit} disabled={busy}>Send</button>
          {busy && <button onClick={() => { cancel(); setBusy(false); }}>Stop</button>}
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <ActionLog steps={steps} />
        <SettingsPanel />
      </div>
    </div>
  );
}
