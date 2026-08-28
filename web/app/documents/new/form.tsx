"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  detectDocument,
  uploadDocument,
  type Detection,
  type SourceType,
} from "@/lib/api";
import { jurisdictionName } from "../../_ui/status";

// The source type is a product feature, not a form field: it sets the authority
// tier that caps what the system will do with a clause. It is now read from the
// document, but the words below are still what we show — both when we say what
// we read, and when we have to ask.
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

// The same line the API draws. Below it we ask; at or above it we state what we
// read and let the user correct it.
const CERTAIN = 0.6;

function sourceCopy(value: string | null) {
  return SOURCES.find((source) => source.value === value) ?? null;
}

function readableDate(iso: string | null): string | null {
  if (!iso) return null;
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

/** What the document itself said, quoted, so no claim here has to be taken on trust. */
function Because({ evidence }: { evidence: string | null }) {
  if (!evidence) return null;
  return (
    <span className="t-caption t-secondary block mt-1">
      because it says “{evidence.length > 90 ? `${evidence.slice(0, 90)}…` : evidence}”
    </span>
  );
}

export default function UploadForm() {
  const router = useRouter();

  // The document comes first now; everything else is read from it.
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");

  const [detection, setDetection] = useState<Detection | null>(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);

  // Only what the user actually changed. Anything left null is whatever the
  // document said, and is sent as nothing at all so the API records it as read
  // rather than declared.
  const [sourceType, setSourceType] = useState<SourceType | null>(null);
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [jurisdiction, setJurisdiction] = useState<string | null>(null);
  const [effectiveDate, setEffectiveDate] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Every read is numbered: a slow read of an abandoned draft must never land
  // on top of a newer one and describe the wrong document.
  const readId = useRef(0);

  async function read(next: { file?: File | null; text?: string }) {
    const chosenFile = next.file ?? null;
    const chosenText = (next.text ?? "").trim();
    if (!chosenFile && chosenText.length < 20) {
      setDetection(null);
      setReadError(null);
      return;
    }
    const ticket = ++readId.current;
    setReading(true);
    setReadError(null);
    try {
      const form = new FormData();
      if (chosenFile) form.set("file", chosenFile);
      else form.set("text", chosenText);
      const { detection: found } = await detectDocument(form);
      if (ticket !== readId.current) return;
      setDetection(found);
      // A fresh document invalidates corrections made to the previous one.
      setSourceType(null);
      setSourceName(null);
      setJurisdiction(null);
      setEffectiveDate(null);
      setEditing(false);
    } catch (err) {
      if (ticket !== readId.current) return;
      setDetection(null);
      setReadError(err instanceof Error ? err.message : "We could not read that document.");
    } finally {
      if (ticket === readId.current) setReading(false);
    }
  }

  function chooseFile(next: File | null) {
    setFile(next);
    if (next) setText("");
    void read({ file: next, text: "" });
  }

  // Typing is read on a pause, not on every keystroke: one request per pasted
  // document, not one per character.
  useEffect(() => {
    if (file || !text.trim()) return;
    const timer = setTimeout(() => void read({ text }), 700);
    return () => clearTimeout(timer);
    // `read` is deliberately not a dependency: it is rebuilt every render, and
    // depending on it would restart the timer on every keystroke it debounces.
  }, [text, file]);

  // What will actually be submitted: the user's correction if they made one,
  // otherwise what the document said — but only if the document said it clearly.
  const readJurisdiction =
    detection && detection.jurisdiction.confidence >= CERTAIN ? detection.jurisdiction.value : null;
  const readSourceType =
    detection && detection.source_type.confidence >= CERTAIN ? detection.source_type.value : null;
  const finalJurisdiction = jurisdiction ?? readJurisdiction;
  const finalSourceType = sourceType ?? readSourceType;
  const finalName = sourceName ?? detection?.source_name.value ?? null;
  const finalDate = effectiveDate ?? detection?.effective_date.value ?? null;

  const hasDocument = !!file || text.trim().length > 0;
  const unread = detection ? [!readJurisdiction, !readSourceType].filter(Boolean).length : 0;
  const mustAsk = unread > 0;
  const showFields = editing || mustAsk;
  const ready = hasDocument && !!finalJurisdiction && !!finalSourceType;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const form = new FormData();
      if (file) form.set("file", file);
      else if (text.trim()) form.set("text", text);
      else throw new Error("Choose a PDF file, or paste the text of the rule.");

      // Only corrections are sent. What we read, the API reads again itself —
      // that way the document records which fields a human actually stood behind.
      if (sourceType) form.set("source_type", sourceType);
      if (sourceName) form.set("source_name", sourceName);
      if (jurisdiction) form.set("jurisdiction", jurisdiction);
      if (effectiveDate) form.set("declared_effective_date", effectiveDate);

      const { document } = await uploadDocument(form);
      router.push(`/documents/${document.id}${document.status === "extracted" ? "?cached=1" : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The upload did not go through.");
      setSaving(false);
    }
  }

  return (
    <form className="mt-8 space-y-6" onSubmit={submit} data-testid="upload-form">
      <section className="card p-6">
        <h2 className="t-headline">The document</h2>
        <p className="help">
          A file, or text you paste. We read it and work out the rest — which country&apos;s rules
          it is, what kind of source it is, and when it takes effect.
        </p>

        <label className="mt-4 block">
          <span className="label">Upload a PDF</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="field"
            style={{ paddingTop: 10 }}
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
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

      {reading ? (
        <p className="t-footnote t-secondary" data-testid="reading">
          Reading the document…
        </p>
      ) : null}

      {readError ? (
        <div className="card p-5" data-testid="detect-error">
          <p className="t-headline">We could not read that one</p>
          <p className="t-subhead t-secondary mt-1">{readError}</p>
          <p className="t-footnote t-secondary mt-2">
            You can still send it — fill in the two questions below and we will read what we can.
          </p>
          <button
            type="button"
            className="btn btn-secondary btn-small mt-3"
            onClick={() => setEditing(true)}
            data-testid="answer-manually"
          >
            Fill it in myself
          </button>
        </div>
      ) : null}

      {detection && !reading ? (
        <section
          className="card p-6"
          style={{ borderLeft: `4px solid ${mustAsk ? "var(--accent)" : "var(--good)"}` }}
          data-testid="detection"
        >
          <h2 className="t-headline">
            {mustAsk
              ? `${unread === 1 ? "One thing" : "Two things"} we could not work out`
              : "Here is what we read"}
          </h2>
          <p className="help">
            {mustAsk
              ? unread === 1
                ? "The document does not say it clearly enough for us to decide on your behalf, and it decides how the rule gets used. Answer it below."
                : "The document does not say either of them clearly enough for us to decide on your behalf, and they decide how the rule gets used. Answer them below."
              : "Read from the document itself. Change anything that is wrong before you send it."}
          </p>

          <dl className="mt-4 grid gap-4">
            <div data-testid="detected-jurisdiction">
              <dt className="t-caption t-secondary">Whose rules these are</dt>
              <dd className="t-subhead" style={{ fontWeight: 600 }}>
                {finalJurisdiction ? jurisdictionName(finalJurisdiction) : "Not stated — please pick"}
              </dd>
              {!jurisdiction ? <Because evidence={detection.jurisdiction.evidence} /> : null}
            </div>

            <div data-testid="detected-source-type">
              <dt className="t-caption t-secondary">What kind of source it is</dt>
              <dd className="t-subhead" style={{ fontWeight: 600 }}>
                {sourceCopy(finalSourceType)?.label ?? "Not stated — please pick"}
              </dd>
              {finalSourceType ? (
                <span className="badge badge-muted mt-2">{sourceCopy(finalSourceType)?.power}</span>
              ) : null}
              {!sourceType ? <Because evidence={detection.source_type.evidence} /> : null}
            </div>

            <div data-testid="detected-name">
              <dt className="t-caption t-secondary">What it is called</dt>
              <dd className="t-subhead">{finalName ?? (file ? "We will name it after the file" : "We will give it a name")}</dd>
            </div>

            <div data-testid="detected-date">
              <dt className="t-caption t-secondary">When it takes effect</dt>
              <dd className="t-subhead">
                {readableDate(finalDate) ?? "The document does not say"}
              </dd>
              {!effectiveDate ? <Because evidence={detection.effective_date.evidence} /> : null}
            </div>
          </dl>

          {!showFields ? (
            <button
              type="button"
              className="btn btn-quiet btn-small mt-4"
              onClick={() => setEditing(true)}
              data-testid="correct-detection"
            >
              Something is wrong — let me change it
            </button>
          ) : null}
        </section>
      ) : null}

      {showFields ? (
        <>
          <fieldset className="card p-6" data-testid="authority-selector">
            <legend className="t-headline float-left w-full">Where did this come from?</legend>
            <p className="help clear-both">
              Be honest here. A screenshot from a chat group is treated very differently from a
              gazette, and that is the point.
            </p>
            <div className="mt-4 grid gap-2">
              {SOURCES.map((source) => {
                const selected = finalSourceType === source.value;
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
                <span className="label">What is it called?</span>
                <input
                  className="field"
                  value={finalName ?? ""}
                  onChange={(e) => setSourceName(e.target.value)}
                  data-testid="field-source-name"
                />
              </label>
              <label className="block">
                <span className="label">Which country&apos;s rules?</span>
                <select
                  className="field"
                  value={finalJurisdiction ?? ""}
                  onChange={(e) => setJurisdiction(e.target.value || null)}
                  data-testid="field-jurisdiction"
                >
                  <option value="">Pick one…</option>
                  <option value="EU">European Union</option>
                  <option value="ID_BPOM">Indonesia (BPOM)</option>
                </select>
              </label>
              <label className="block">
                <span className="label">When does it take effect?</span>
                <input
                  type="date"
                  className="field"
                  value={finalDate ?? ""}
                  onChange={(e) => setEffectiveDate(e.target.value || null)}
                  data-testid="field-effective-date"
                />
                <span className="help">Optional.</span>
              </label>
            </div>
          </section>
        </>
      ) : null}

      {error ? (
        <div className="card p-5" data-testid="upload-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>That did not go through</p>
          <p className="t-subhead t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={saving || reading || !ready}
          className="btn btn-primary"
          data-testid="submit-upload"
        >
          {saving ? "Sending…" : "Read this document"}
        </button>
        <span className="t-footnote t-secondary">
          {!hasDocument
            ? "Add a file or paste some text to start."
            : !ready
              ? `Answer the ${unread === 1 ? "question" : "questions"} above and this button turns on.`
              : "Reading takes about three minutes. You do not have to wait on the page."}
        </span>
      </div>
    </form>
  );
}
