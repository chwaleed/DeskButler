import { ChevronLeft, Folder, X, Plus } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Label } from "@/components/ui/label";
import type { Settings } from "@/api/bridge";

const MODELS = [
  { id: "qwen3.5:2b", name: "qwen3.5 · 2B", note: "Fast. Fine for everyday file tasks." },
  { id: "qwen3.5:4b", name: "qwen3.5 · 4B", note: "Slower, better judgment on ambiguous requests." },
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[11px] tracking-[1.4px] uppercase text-muted-foreground/60">
      {children}
    </div>
  );
}

export function SettingsPanel({
  settings,
  onClose,
  onChange,
}: {
  settings: Settings;
  onClose: () => void;
  onChange: (s: Settings) => void;
}) {
  const [newRoot, setNewRoot] = useState("");

  const addRoot = () => {
    const r = newRoot.trim();
    if (!r || settings.allowed_roots.includes(r)) return;
    onChange({ ...settings, allowed_roots: [...settings.allowed_roots, r] });
    setNewRoot("");
  };

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b shrink-0">
        <Button variant="ghost" size="sm" className="font-mono px-1.5" onClick={onClose}>
          <ChevronLeft /> activity
        </Button>
        <div className="flex-1" />
        <SectionLabel>Settings</SectionLabel>
      </div>
      <ScrollArea className="flex-1">
        <div className="px-4 py-4.5 flex flex-col gap-6">
          {/* Dry-run — wired to backend */}
          <label className="flex gap-3 items-start cursor-pointer">
            <Checkbox
              checked={settings.dry_run}
              onCheckedChange={(c) => onChange({ ...settings, dry_run: c === true })}
              className="mt-0.5"
            />
            <div className="flex flex-col gap-0.5">
              <div className="font-semibold">Dry-run mode</div>
              <div className="text-muted-foreground text-[12.5px] text-pretty">
                The agent only shows what it would do. No file is created, moved, or
                deleted.
              </div>
            </div>
          </label>

          {/* Model — wired to backend */}
          <div className="flex flex-col gap-2.5">
            <SectionLabel>Model</SectionLabel>
            <RadioGroup
              value={settings.model}
              onValueChange={(m) => onChange({ ...settings, model: m })}
              className="gap-2.5"
            >
              {MODELS.map((m) => (
                <label key={m.id} className="flex gap-3 items-start cursor-pointer">
                  <RadioGroupItem value={m.id} id={m.id} className="mt-0.5" />
                  <Label htmlFor={m.id} className="flex flex-col gap-0.5 cursor-pointer font-normal">
                    <span className="font-mono text-[12.5px]">{m.name}</span>
                    <span className="text-muted-foreground text-xs">{m.note}</span>
                  </Label>
                </label>
              ))}
            </RadioGroup>
          </div>

          {/* Allowed folders — wired to backend */}
          <div className="flex flex-col gap-2.5">
            <SectionLabel>Allowed folders</SectionLabel>
            <div className="text-muted-foreground text-[12.5px] text-pretty">
              The agent can only see and change files inside these folders.
            </div>
            <div className="flex flex-col gap-1.5">
              {settings.allowed_roots.map((r) => (
                <div
                  key={r}
                  className="flex items-center gap-2 bg-background border rounded-md px-2.5 py-1.5"
                >
                  <Folder className="size-3.5 text-muted-foreground/60 shrink-0" />
                  <span className="flex-1 font-mono text-xs break-all">{r}</span>
                  <button
                    onClick={() =>
                      onChange({
                        ...settings,
                        allowed_roots: settings.allowed_roots.filter((x) => x !== r),
                      })
                    }
                    title="Remove folder"
                    className="text-muted-foreground/60 hover:text-destructive cursor-pointer"
                  >
                    <X className="size-3" />
                  </button>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={newRoot}
                onChange={(e) => setNewRoot(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addRoot()}
                placeholder="C:\Users\you\…"
                className="font-mono text-xs h-8"
              />
              <Button variant="outline" size="sm" className="font-mono" onClick={addRoot}>
                <Plus /> add
              </Button>
            </div>
          </div>

          <div className="font-mono text-[11px] text-muted-foreground/60 border-t pt-3.5 leading-[1.8]">
            runs locally · no network access
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
