import { useEffect, useRef, useState } from "react";
import { Titlebar } from "./components/Titlebar";
import { ChatThread, type Msg } from "./components/ChatThread";
import { ApprovalCard, type Req } from "./components/ApprovalCard";
import { Composer } from "./components/Composer";
import { Rail, type RailView } from "./components/Rail";
import type { Step } from "./components/ActivityLog";
import { ScrollArea } from "./components/ui/scroll-area";
import {
  approve,
  cancel,
  getSettings,
  onAgentEvent,
  saveSettings,
  sendMessage,
  type AgentEvent,
  type Settings,
} from "./api/bridge";

function now() {
  const p = (n: number) => String(n).padStart(2, "0");
  const t = new Date();
  return `${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())}`;
}

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [approval, setApproval] = useState<Req | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastStep, setLastStep] = useState("");
  const [input, setInput] = useState("");
  const [view, setView] = useState<RailView>("activity");
  const [settings, setSettings] = useState<Settings | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getSettings().then(setSettings);
    onAgentEvent((e: AgentEvent) => {
      if (e.type === "step") {
        const text = e.text ?? "";
        setSteps((s) => [...s, { t: now(), text }]);
        setLastStep(text);
      } else if (e.type === "approval") {
        setApproval((e.request as Req) ?? null);
      } else if (e.type === "final") {
        setMessages((m) => [...m, { role: "agent", text: e.text ?? "" }]);
        setBusy(false);
      } else if (e.type === "error") {
        setMessages((m) => [...m, { role: "agent", text: `Error: ${e.text}` }]);
        setBusy(false);
      }
    });
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, approval]);

  async function submit(text?: string) {
    const value = (text ?? input).trim();
    if (!value || busy || approval) return;
    setMessages((m) => [...m, { role: "user", text: value }]);
    setSteps((s) => [...s, { t: now(), text: `you: ${value}` }]);
    setBusy(true);
    setInput("");
    const turnId = await sendMessage(value);
    if (turnId === "busy") setBusy(false);
  }

  function decide(decision: "approve" | "reject") {
    setApproval(null);
    setBusy(true);
    approve({ decision });
  }

  function persist(next: Settings) {
    setSettings(next);
    saveSettings(next);
  }

  function newChat() {
    setMessages([]);
    setApproval(null);
    setBusy(false);
    setView("activity");
  }

  return (
    <div className="h-screen flex flex-col bg-background text-foreground text-sm">
      <Titlebar
        busy={busy}
        dryRun={settings?.dry_run ?? false}
        onChats={() => setView(view === "chats" ? "activity" : "chats")}
        onNewChat={newChat}
        onSettings={() => setView(view === "settings" ? "activity" : "settings")}
      />
      <div className="flex flex-1 min-h-0">
        <div className="flex-1 min-w-0 flex flex-col">
          <ScrollArea className="flex-1">
            <div className="p-6">
              <ChatThread
                messages={messages}
                busy={busy}
                lastStep={lastStep}
                onSuggest={(s) => submit(s)}
              />
              <div ref={chatEndRef} />
            </div>
          </ScrollArea>
          <ApprovalCard
            request={approval}
            onApprove={() => decide("approve")}
            onReject={() => decide("reject")}
          />
          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => submit()}
            onStop={() => {
              cancel();
              setBusy(false);
            }}
            busy={busy}
            disabled={busy || !!approval}
          />
        </div>
        <Rail
          view={view}
          onView={setView}
          steps={steps}
          onClearLog={() => setSteps([])}
          settings={settings}
          onSettingsChange={persist}
        />
      </div>
    </div>
  );
}
