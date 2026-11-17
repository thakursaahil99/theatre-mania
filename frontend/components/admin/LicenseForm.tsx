"use client";

import { Label, LICENSE_TYPES } from "@/components/admin/ui";
import type { LicenseType } from "@/lib/types";

export interface LicenseDraft {
  license_type: LicenseType;
  licensor: string;
  source_url: string;
  territories: string;
  starts_at: string;
  expires_at: string;
  notes: string;
}

export const emptyLicense = (): LicenseDraft => ({
  license_type: "public_domain",
  licensor: "",
  source_url: "",
  territories: "US",
  starts_at: "",
  expires_at: "",
  notes: "",
});

/** Draft → API payload (dates become UTC midnight ISO strings). */
export function licensePayload(d: LicenseDraft) {
  return {
    license_type: d.license_type,
    licensor: d.licensor || null,
    source_url: d.source_url || null,
    territories: d.territories.split(",").map((t) => t.trim()).filter(Boolean),
    starts_at: d.starts_at ? new Date(`${d.starts_at}T00:00:00Z`).toISOString() : null,
    expires_at: d.expires_at ? new Date(`${d.expires_at}T00:00:00Z`).toISOString() : null,
    notes: d.notes || null,
  };
}

export function LicenseForm({ value, onChange }: { value: LicenseDraft; onChange: (v: LicenseDraft) => void }) {
  const set = <K extends keyof LicenseDraft>(k: K, v: LicenseDraft[K]) => onChange({ ...value, [k]: v });
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <label>
        <Label>License type</Label>
        <select className="field" value={value.license_type} onChange={(e) => set("license_type", e.target.value as LicenseType)}>
          {LICENSE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </label>
      <label>
        <Label hint={value.license_type === "licensed" ? "required" : "optional"}>Licensor</Label>
        <input className="field" value={value.licensor} onChange={(e) => set("licensor", e.target.value)} placeholder="e.g. Janus Films" />
      </label>
      <label>
        <Label hint="proof of rights">Source URL</Label>
        <input className="field" type="url" value={value.source_url} onChange={(e) => set("source_url", e.target.value)}
          placeholder="https://archive.org/details/…" />
      </label>
      <label>
        <Label hint="ISO codes, comma separated, WW = worldwide">Territories</Label>
        <input className="field" value={value.territories} onChange={(e) => set("territories", e.target.value.toUpperCase())} />
      </label>
      <label>
        <Label hint="optional">Starts</Label>
        <input className="field" type="date" value={value.starts_at} onChange={(e) => set("starts_at", e.target.value)} />
      </label>
      <label>
        <Label hint="blank = perpetual">Expires</Label>
        <input className="field" type="date" value={value.expires_at} onChange={(e) => set("expires_at", e.target.value)} />
      </label>
      <label className="md:col-span-2">
        <Label>Notes</Label>
        <textarea className="field min-h-20" value={value.notes} onChange={(e) => set("notes", e.target.value)}
          placeholder="Basis for public-domain status, contract reference, restrictions…" />
      </label>
    </div>
  );
}
