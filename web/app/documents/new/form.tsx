"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { uploadDocument, type SourceType } from "@/lib/api";

// The source-type selector is a product feature, not a form field: it sets the
// authority tier that caps what the system will do with a clause. Label and
// copy say so.
const SOURCES: { value: SourceType; label: string; tier: string; hint: string }[] = [
  {
    value: "official_regulation",
    label: "Official regulation",
    tier: "Tier 1.0 — full authority",
    hint: "Law, regulation, official gazette. Can rewrite compliance state.",
  },
  {
    value: "official_guidance",
    label: "Official guidance",
    tier: "Tier 0.8",
    hint: "Regulator circulars, guidance notes.",
  },
  {
    value: "industry_association",
    label: "Industry association",
    tier: "Tier 0.5",
    hint: "Association bulletins and updates.",
  },
  {
    value: "news_article",
    label: "News article",
    tier: "Tier 0.35",
    hint: "Press coverage of regulatory change.",
  },
  {
    value: "social_chat",
    label: "Social / chat",
    tier: "Tier 0.2 — review only",
    hint: "Forwarded messages, posts. Surfaced for review, never applied.",
  },
];

export default function UploadForm() {
  const router = useRouter();
  const [sourceType, setSourceType] = useState<SourceType>("official_regulation");
  const [sourceName, setSourceName] = useState("European Commission");
  const [jurisdiction, setJurisdiction] = useState("EU");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const form = new FormData();
      form.set("source_type", sourceType);
      form.set("source_name", sourceName);
      form.set("jurisdiction", jurisdiction);
      if (effectiveDate) form.set("declared_effective_date", effectiveDate);
      if (file) form.set("file", file);
      else if (text.trim()) form.set("text", text);
      else throw new Error("Attach a PDF or paste the source text.");

      const { document } = await uploadDocument(form);
      router.push(`/documents/${document.id}${document.status === "extracted" ? "?cached=1" : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setSaving(false);
    }
  }

  return (
    <form className="mt-8 space-y-6" onSubmit={submit} data-testid="upload-form">
      <fieldset data-testid="authority-selector">
        <legend className="text-sm font-medium">How authoritative is this source?</legend>
        <div className="mt-2 grid gap-2">
          {SOURCES.map((source) => (
            <label
              key={source.value}
              className={`flex cursor-pointer items-start gap-3 rounded border p-3 text-sm ${
                sourceType === source.value ? "border-black dark:border-white" : ""
              }`}
            >
              <input
                type="radio"
                name="source_type"
                checked={sourceType === source.value}
                onChange={() => setSourceType(source.value)}
                className="mt-1"
                data-testid={`source-${source.value}`}
              />
              <span>
                <span className="font-medium">{source.label}</span>
                <span className="ml-2 opacity-60">{source.tier}</span>
                <span className="block opacity-60">{source.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-3">
        <label className="block">
          <span className="text-sm">Source name</span>
          <input
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            required
            data-testid="field-source-name"
          />
        </label>
        <label className="block">
          <span className="text-sm">Jurisdiction</span>
          <select
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            data-testid="field-jurisdiction"
          >
            <option value="EU">EU</option>
            <option value="ID_BPOM">Indonesia (BPOM)</option>
          </select>
        </label>
        <label className="block">
          <span className="text-sm">Declared effective date</span>
          <input
            type="date"
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
            data-testid="field-effective-date"
          />
        </label>
      </div>

      <div className="space-y-3">
        <label className="block">
          <span className="text-sm">Document (PDF with text layer, max 100 pages / 20 MB)</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="mt-1 block w-full text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            data-testid="field-file"
          />
        </label>
        <label className="block">
          <span className="text-sm">…or paste the source text (announcements, chat exports)</span>
          <textarea
            className="mt-1 min-h-28 w-full rounded border bg-transparent p-2 font-mono text-xs"
            placeholder={"Kementerian update:\n\nUntuk produk minuman yang akan masuk EU,\nbatas penggunaan sodium benzoate sekarang lebih rendah…"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={!!file}
            data-testid="field-text"
          />
        </label>
      </div>

      {error ? (
        <p className="text-sm text-red-600" data-testid="upload-error">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={saving}
        className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-black"
        data-testid="submit-upload"
      >
        {saving ? "Uploading…" : "Upload document"}
      </button>
    </form>
  );
}
