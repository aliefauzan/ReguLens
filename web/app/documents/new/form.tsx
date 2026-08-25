"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { uploadDocument, type SourceType } from "@/lib/api";

// The source-type selector is a product feature, not a form field: it sets the
// authority tier that caps what the system will do with a clause. The copy says
// so in the words a non-specialist would use.
const SOURCES: { value: SourceType; label: string; hint: string; power: string }[] = [
  {
    value: "official_regulation",
    label: "An official regulation",
    hint: "The law itself, or an official gazette.",
    power: "Can change your product's verdict on its own",
  },
  {
    value: "official_guidance",
    label: "Official guidance",
    hint: "A circular or guidance note from the regulator.",
    power: "Trusted, but checked more carefully",
  },
  {
    value: "industry_association",
    label: "An industry association",
    hint: "A bulletin from a trade body.",
    power: "Usually needs your confirmation",
  },
  {
    value: "news_article",
    label: "A news article",
    hint: "Press coverage of a rule change.",
    power: "Flagged for you to check",
  },
  {
    value: "social_chat",
    label: "A message or social post",
    hint: "Something forwarded to you in a group chat.",
    power: "Never changes anything by itself",
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
      else throw new Error("Choose a PDF file, or paste the text of the rule.");

      const { document } = await uploadDocument(form);
      router.push(`/documents/${document.id}${document.status === "extracted" ? "?cached=1" : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The upload did not go through.");
      setSaving(false);
    }
  }

  return (
    <form className="mt-8 space-y-6" onSubmit={submit} data-testid="upload-form">
      <fieldset className="card p-6" data-testid="authority-selector">
        <legend className="t-headline float-left w-full">Where did this come from?</legend>
        <p className="help clear-both">
          Be honest here. A screenshot from a chat group is treated very differently from a gazette,
          and that is the point.
        </p>
        <div className="mt-4 grid gap-2">
          {SOURCES.map((source) => {
            const selected = sourceType === source.value;
            return (
              <label
                key={source.value}
                className="inset flex cursor-pointer items-start gap-3 p-4"
                style={selected ? { boxShadow: "inset 0 0 0 2px var(--accent)" } : undefined}
              >
                <input
                  type="radio"
                  name="source_type"
                  checked={selected}
                  onChange={() => setSourceType(source.value)}
                  aria-label={source.label}
                  className="mt-0.5"
                  style={{ width: 20, height: 20, accentColor: "var(--accent)" }}
                  data-testid={`source-${source.value}`}
                />
                <span>
                  <span className="t-subhead block" style={{ fontWeight: 600 }}>{source.label}</span>
                  <span className="t-footnote t-secondary block">{source.hint}</span>
                  <span className="badge badge-muted mt-2">{source.power}</span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <section className="card p-6">
        <h2 className="t-headline">About the document</h2>
        <div className="mt-4 grid gap-5 sm:grid-cols-3">
          <label className="block">
            <span className="label">Who published it?</span>
            <input
              className="field"
              value={sourceName}
              onChange={(e) => setSourceName(e.target.value)}
              required
              data-testid="field-source-name"
            />
          </label>
          <label className="block">
            <span className="label">Which country's rules?</span>
            <select
              className="field"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              data-testid="field-jurisdiction"
            >
              <option value="EU">European Union</option>
              <option value="ID_BPOM">Indonesia (BPOM)</option>
            </select>
          </label>
          <label className="block">
            <span className="label">When does it take effect?</span>
            <input
              type="date"
              className="field"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              data-testid="field-effective-date"
            />
            <span className="help">Optional.</span>
          </label>
        </div>
      </section>

      <section className="card p-6">
        <h2 className="t-headline">The document itself</h2>
        <p className="help">Do one or the other — a file, or pasted text.</p>

        <label className="mt-4 block">
          <span className="label">Upload a PDF</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="field"
            style={{ paddingTop: 10 }}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            data-testid="field-file"
          />
          <span className="help">
            Up to 100 pages and 20 MB. The PDF must contain real text — a photo or a scan will not work.
          </span>
        </label>

        <label className="mt-5 block">
          <span className="label">Or paste the text</span>
          <textarea
            className="field"
            style={{ fontSize: 15, lineHeight: 1.5 }}
            placeholder={"Paste an announcement, a circular, or a forwarded message here."}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={!!file}
            data-testid="field-text"
          />
          {file ? <span className="help">Clear the file above if you want to paste text instead.</span> : null}
        </label>
      </section>

      {error ? (
        <div className="card p-5" data-testid="upload-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>That did not go through</p>
          <p className="t-subhead t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      <div className="flex items-center gap-3">
        <button type="submit" disabled={saving} className="btn btn-primary" data-testid="submit-upload">
          {saving ? "Sending…" : "Read this document"}
        </button>
        <span className="t-footnote t-secondary">Takes about a minute.</span>
      </div>
    </form>
  );
}
