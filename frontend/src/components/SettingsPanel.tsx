import { useEffect, useState } from "react";
import { getSettings, saveSettings } from "../api/bridge";

export function SettingsPanel() {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    getSettings().then(setS);
  }, []);
  if (!s) return null;
  return (
    <div aria-label="settings">
      <h3>Settings</h3>
      <label>
        Dry-run{" "}
        <input
          type="checkbox"
          checked={s.dry_run}
          onChange={(e) => {
            const next = { ...s, dry_run: e.target.checked };
            setS(next);
            saveSettings(next);
          }}
        />
      </label>
      <div>Allowed roots: {s.allowed_roots.join(", ")}</div>
      <div>Model: {s.model}</div>
    </div>
  );
}
