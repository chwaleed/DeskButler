export type AgentEvent = {
  type: "step" | "approval" | "final" | "error";
  turn_id: string;
  text?: string;
  request?: { tool: string; args: Record<string, unknown>; message: string };
};

export type Settings = {
  allowed_roots: string[];
  model: string;
  dry_run: boolean;
};

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
    onAgentEvent?: (e: AgentEvent) => void;
  }
}

// pywebview injects window.pywebview.api asynchronously — it is NOT present at
// first render. Resolve once it's available (event, with a poll fallback in case
// the event fired before this listener attached).
let readyPromise: Promise<void> | null = null;
function ready(): Promise<void> {
  if (window.pywebview?.api) return Promise.resolve();
  if (!readyPromise) {
    readyPromise = new Promise<void>((resolve) => {
      const done = () => resolve();
      window.addEventListener("pywebviewready", done, { once: true });
      const poll = setInterval(() => {
        if (window.pywebview?.api) {
          clearInterval(poll);
          resolve();
        }
      }, 50);
    });
  }
  return readyPromise;
}

export async function sendMessage(text: string): Promise<string> {
  await ready();
  return window.pywebview!.api.send_message(text) as Promise<string>;
}
export async function approve(decision: { decision: "approve" | "reject" }): Promise<void> {
  await ready();
  await window.pywebview!.api.approve(decision);
}
export async function cancel(): Promise<void> {
  await ready();
  await window.pywebview!.api.cancel();
}
export async function newChat(): Promise<void> {
  await ready();
  await window.pywebview!.api.new_chat();
}
export async function getSettings(): Promise<Settings> {
  await ready();
  return window.pywebview!.api.get_settings() as Promise<Settings>;
}
export async function saveSettings(data: Settings): Promise<void> {
  await ready();
  await window.pywebview!.api.save_settings(data);
}
export function onAgentEvent(handler: (e: AgentEvent) => void): void {
  window.onAgentEvent = handler;
}
