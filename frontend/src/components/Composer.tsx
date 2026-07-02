import { Send, Square } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  busy: boolean;
  disabled: boolean;
}) {
  return (
    <div className="flex-none border-t bg-card px-6 py-3.5">
      <div className="max-w-[720px] mx-auto flex gap-2.5">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSubmit()}
          disabled={disabled}
          placeholder="Ask me to list or move files…"
        />
        <Button onClick={onSubmit} disabled={disabled || !value.trim()}>
          <Send /> Send
        </Button>
        {busy && (
          <Button variant="destructive" onClick={onStop}>
            <Square className="fill-current" /> Stop
          </Button>
        )}
      </div>
    </div>
  );
}
