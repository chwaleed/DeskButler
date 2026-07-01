export type AgentEvent = {
  type: "step" | "approval" | "final" | "error";
  turn_id: string;
  text?: string;
  request?: { tool: string; args: Record<string, unknown>; message: string };
};

declare global {
  interface Window {
    pywebview: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
    onAgentEvent?: (e: AgentEvent) => void;
  }
}

export function sendMessage(text: string): Promise<string> {
  return window.pywebview.api.send_message(text) as Promise<string>;
}
export function approve(decision: { decision: "approve" | "reject" }): Promise<void> {
  return window.pywebview.api.approve(decision) as Promise<void>;
}
export function cancel(): Promise<void> {
  return window.pywebview.api.cancel() as Promise<void>;
}
export function getSettings(): Promise<any> {
  return window.pywebview.api.get_settings() as Promise<any>;
}
export function saveSettings(data: any): Promise<void> {
  return window.pywebview.api.save_settings(data) as Promise<void>;
}
export function onAgentEvent(handler: (e: AgentEvent) => void): void {
  window.onAgentEvent = handler;
}
