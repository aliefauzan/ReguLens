"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  addSource,
  checkSource,
  deleteSource,
  listSources,
  seedSources,
  setSourceEnabled,
  type SourceCheckResult,
  type SourceType,
  type WatchedSource,
} from "@/lib/api";
import { jurisdictionName, plain } from "../_ui/status";
import AutonomyPanel from "./AutonomyPanel";

/**
 * The addresses ReguLens re-reads on its own.
 *
 * This page is what makes "we watch for changes" a checkable claim rather than
 * a slogan. Every row says when the address was last read, what came back, and
 * what broke — including the boring answer, "nothing changed", which is the one
 * a monitor gives almost every day. A source erroring quietly for a week would
 * mean nobody is watching it, and this is the only place that would show.
 */
const STATUS_COPY: Record<
  string,
  {
    label: string;
    tone: string;
    meaning: string;
    feedMeaning?: string;
    listingMeaning?: string;
    sparqlMeaning?: string;
  }
> = {
  never_checked: {
    label: "Not read yet",
    tone: "var(--secondary)",
    meaning: "Registered, but the first read has not happened. Press Check now, or wait for tonight.",
  },
  unchanged: {
    label: "No change",
    tone: "var(--good)",
    meaning: "We read it and the wording was the same as last time.",
    // A feed does not have "wording" that stays the same; it has nothing new in
    // it. Saying the wrong one is a small lie about what was actually checked.
    feedMeaning: "We read it and nothing new had been published.",
    listingMeaning: "We read the index and no regulation had been added since last time.",
    sparqlMeaning: "We asked the catalogue and it named nothing we had not already read.",
  },
  changed: {
    label: "Changed — read in",
    tone: "var(--accent)",
    meaning: "The wording moved. The new version went through the ordinary pipeline.",
  },
  baselined: {
    label: "Watching from now",
    tone: "var(--secondary)",
    meaning:
      "We noted what this feed already carried and read none of it. Only things published from now on are read.",
  },
  busy: {
    label: "Being read",
    tone: "var(--secondary)",
    meaning: "Another check of this address is running.",
  },
  error: {
    label: "Could not read",
    tone: "var(--danger)",
    meaning: "The last attempt failed. Until it succeeds, this address is not being watched.",
  },
};

function ago(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never";
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** What one "Check now" actually did, in a sentence. */
function outcome(result: SourceCheckResult): string {
  const ingested = result.ingested?.length ?? 0;
  switch (result.status) {
    case "changed":
      return result.first_read
        ? `Read for the first time — ${ingested} document${ingested === 1 ? "" : "s"} added.`
        : `The wording changed. ${ingested} new version${ingested === 1 ? "" : "s"} read in.`;
    case "unchanged":
      if (result.reason === "not_modified") return "No change — the server said so without sending the page.";
      if (result.reason === "no_new_entries") return "No change — nothing new published.";
      if ((result.failed?.length ?? 0) > 0) return `Nothing readable. ${result.failed?.[0]?.error ?? ""}`;
      return "No change — the wording is the same as last time.";
    case "baselined":
      return `Noted ${result.new_entries ?? result.ingested?.length ?? ""} existing entries. Watching from now on.`;
    case "busy":
      return "Another check of this address is already running.";
    case "error":
      return result.error ?? "The address could not be read.";
    default:
      return plain(result.status);
  }
}

type NewSource = {
  url: string;
  label: string;
  kind: "document" | "feed" | "listing" | "sparql";
  source_type: SourceType;
  jurisdiction: string;
  link_pattern: string;
  sparql_query: string;
};

const BLANK: NewSource = {
  url: "",
  label: "",
  kind: "document",
  source_type: "official_regulation",
  jurisdiction: "EU",
  link_pattern: "",
  sparql_query: "",
};

// What each kind can and cannot tell you. Said out loud on the form, because
// picking "one regulation" for an index page is the mistake that leaves someone
// believing they are watching a regulator when they are watching one PDF.
const KIND_HELP: Record<NewSource["kind"], string> = {
  document:
    "One rule at a fixed address. Tells you when its wording changes — not when a different rule is published somewhere else.",
  feed: "An RSS or Atom feed. Each new entry is read as a new document.",
  listing:
    "A page listing published regulations. New links on it are new rules — one of the two kinds that can find a regulation you did not already know about.",
  sparql:
    "A publisher's catalogue, asked directly. Same job as an index page, but the publisher decides what counts as a match rather than a pattern over a layout — which is what the EU offers, since its web pages refuse automated readers.",
};

export default function SourcesPage() {
  const [sources, setSources] = useState<WatchedSource[]>([]);
  const [intervalHours, setIntervalHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, SourceCheckResult>>({});
  const [form, setForm] = useState<NewSource>(BLANK);
  const [formError, setFormError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  async function load() {
    try {
      const result = await listSources();
      setSources(result.sources);
      setIntervalHours(result.default_interval_hours);
      setError(null);
    } catch {
      setError("We could not reach the ReguLens service. Check that it is running, then reload this page.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function run(id: string) {
    setBusy(id);
    try {
      const result = await checkSource(id);
      setResults((prior) => ({ ...prior, [id]: result }));
      await load();
    } catch (exc) {
      setResults((prior) => ({
        ...prior,
        [id]: { source_id: id, status: "error", error: (exc as Error).message },
      }));
    } finally {
      setBusy(null);
    }
  }

  async function toggle(source: WatchedSource) {
    setBusy(source.id);
    try {
      await setSourceEnabled(source.id, !source.enabled);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function stopWatching(id: string) {
    setBusy(id);
    try {
      await deleteSource(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function install() {
    setBusy("seed");
    try {
      await seedSources();
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setAdding(true);
    setFormError(null);
    try {
      await addSource({
        ...form,
        link_pattern: form.kind === "listing" ? form.link_pattern : null,
        sparql_query: form.kind === "sparql" ? form.sparql_query : null,
      });
      setForm(BLANK);
      await load();
    } catch (exc) {
      setFormError((exc as Error).message);
    } finally {
      setAdding(false);
    }
  }

  return (
    <main className="page" data-testid="sources-page">
      <h1 className="t-large-title">Addresses we re-read</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        Every {intervalHours} hours ReguLens re-reads each address below. When the wording of a
        regulation has changed, the new version goes through the same reading, the same checks and
        the same review queue as a document you upload yourself — nothing here can put a rule
        straight into your verdicts. When nothing has changed, the check costs nothing and this page
        says so.
      </p>

      <AutonomyPanel />

      {loading ? <p className="t-body t-secondary mt-6">Loading…</p> : null}

      {error ? (
        <div className="card mt-6 p-5" data-testid="sources-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>
            Service unavailable
          </p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {!loading && !error && sources.length === 0 ? (
        <div className="card mt-6 p-8 text-center" data-testid="sources-empty">
          <p className="t-headline">Nothing is being watched yet</p>
          <p className="t-footnote t-secondary prose-measure mx-auto mt-1">
            Until an address is registered here, ReguLens only knows what somebody has uploaded.
            Start with the ones we ship: an EU amendment to the food additives annex, the European
            Commission&rsquo;s food safety feed, and BPOM&rsquo;s legal portal — which is the one
            that spots a regulation published somewhere nobody has looked yet.
          </p>
          <button
            className="btn btn-primary mt-5"
            onClick={install}
            disabled={busy === "seed"}
            data-testid="seed-sources"
          >
            {busy === "seed" ? "Working…" : "Watch the addresses we ship"}
          </button>
        </div>
      ) : null}

      <ul className="mt-6 space-y-4">
        {sources.map((source) => {
          const copy = STATUS_COPY[source.last_status] ?? {
            label: plain(source.last_status),
            tone: "var(--secondary)",
            meaning: "",
          };
          const meaning =
            (source.kind === "sparql" && copy.sparqlMeaning) ||
            (source.kind === "listing" && copy.listingMeaning) ||
            (source.kind === "feed" && copy.feedMeaning) ||
            copy.meaning;
          const result = results[source.id];
          return (
            <li key={source.id} className="card p-5" data-testid={`source-${source.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="t-headline">{source.label}</p>
                  <p className="t-footnote t-secondary mt-1 break-all">{source.url}</p>
                </div>
                <span
                  className="t-caption shrink-0 rounded-[8px] px-2 py-1"
                  style={{ background: "var(--fill)", color: copy.tone, fontWeight: 600 }}
                  data-testid={`source-status-${source.id}`}
                >
                  {copy.label}
                </span>
              </div>

              <p className="t-footnote t-secondary mt-3">
                {source.kind === "feed"
                  ? "A list of new publications"
                  : source.kind === "listing"
                    ? "An index of published regulations"
                    : source.kind === "sparql"
                      ? "A catalogue we query"
                      : "One regulation"}{" "}
                ·{" "}
                {jurisdictionName(source.jurisdiction)} · {plain(source.source_type)} · read every{" "}
                {source.check_interval_hours} h
              </p>

              <p className="t-footnote t-secondary mt-1">
                Last read {ago(source.last_checked_at)} · last change{" "}
                {source.last_changed_at ? ago(source.last_changed_at) : "none seen"} ·{" "}
                {source.checks} check{source.checks === 1 ? "" : "s"}, {source.changes} change
                {source.changes === 1 ? "" : "s"}
                {source.document_ids.length > 0 ? (
                  <>
                    {" · "}
                    <Link className="underline" href={`/documents/${source.document_ids[0]}`}>
                      newest document
                    </Link>
                  </>
                ) : null}
              </p>

              {meaning ? <p className="t-footnote t-secondary mt-1">{meaning}</p> : null}

              {source.last_error ? (
                <p className="t-footnote mt-2" style={{ color: "var(--danger)" }} data-testid={`source-error-${source.id}`}>
                  {source.last_error}
                </p>
              ) : null}

              {result ? (
                <p
                  className="t-footnote mt-3 rounded-[8px] p-3"
                  style={{ background: "var(--fill)" }}
                  data-testid={`source-result-${source.id}`}
                >
                  {outcome(result)}
                </p>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  className="btn btn-primary btn-small"
                  onClick={() => run(source.id)}
                  disabled={busy === source.id}
                  data-testid={`check-${source.id}`}
                >
                  {busy === source.id ? "Reading…" : "Check now"}
                </button>
                <button
                  className="btn btn-secondary btn-small"
                  onClick={() => toggle(source)}
                  disabled={busy === source.id}
                  data-testid={`toggle-${source.id}`}
                >
                  {source.enabled ? "Pause" : "Resume"}
                </button>
                <button
                  className="btn btn-secondary btn-small"
                  onClick={() => stopWatching(source.id)}
                  disabled={busy === source.id}
                  data-testid={`remove-${source.id}`}
                >
                  Stop watching
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      {!loading && !error ? (
        <section className="card mt-6 p-5" data-testid="add-source">
          <h2 className="t-headline">Watch another address</h2>
          <p className="t-footnote t-secondary prose-measure mt-1">
            Paste the page a regulator publishes on. A PDF, an HTML page, an RSS feed, or the index
            a regulator lists new rules on — all work. Watching one rule tells you when that rule
            changes; watching an index is how a rule published somewhere new gets found at all. We
            refuse anything we cannot read in one piece rather than reading half of it — a confident
            answer from half a regulation is worse than no answer.
          </p>

          <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={submit}>
            <label className="t-footnote sm:col-span-2">
              Address
              <input
                className="field mt-1 w-full"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://…"
                required
                data-testid="source-url"
              />
            </label>
            <label className="t-footnote sm:col-span-2">
              What to call it
              <input
                className="field mt-1 w-full"
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                placeholder="BPOM additive annex"
                required
                data-testid="source-label"
              />
            </label>
            <label className="t-footnote">
              What is at that address
              <select
                className="field mt-1 w-full"
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value as NewSource["kind"] })}
                data-testid="source-kind"
              >
                <option value="document">One regulation</option>
                <option value="feed">A feed of new publications</option>
                <option value="listing">A page listing published regulations</option>
                <option value="sparql">A catalogue to query (SPARQL)</option>
              </select>
              <span className="t-caption t-secondary mt-1 block">{KIND_HELP[form.kind]}</span>
            </label>
            {form.kind === "listing" ? (
              <label className="t-footnote sm:col-span-2">
                Which links on it are regulations
                <input
                  className="field mt-1 w-full"
                  value={form.link_pattern}
                  onChange={(e) => setForm({ ...form, link_pattern: e.target.value })}
                  placeholder="/download/rule/"
                  required
                  data-testid="source-link-pattern"
                />
                <span className="t-caption t-secondary mt-1 block">
                  Part of the link address, or a regular expression. An index page also links to
                  news, social media and a language switcher; without this we would read the whole
                  website.
                </span>
              </label>
            ) : null}
            {form.kind === "sparql" ? (
              <label className="t-footnote sm:col-span-2">
                The query to ask
                <textarea
                  className="field mt-1 w-full"
                  rows={5}
                  value={form.sparql_query}
                  onChange={(e) => setForm({ ...form, sparql_query: e.target.value })}
                  placeholder="SELECT DISTINCT ?celex ?date WHERE { ... FILTER(?date > &quot;{since}&quot;^^xsd:date) }"
                  required
                  data-testid="source-sparql-query"
                />
                <span className="t-caption t-secondary mt-1 block">
                  Must select a <code>?celex</code>, <code>?work</code> or <code>?uri</code> column
                  naming each document. Write <code>{"{since}"}</code> where the date goes — we
                  substitute a moving window, so the query never grows without limit.
                </span>
              </label>
            ) : null}
            <label className="t-footnote">
              How authoritative is it
              <select
                className="field mt-1 w-full"
                value={form.source_type}
                onChange={(e) =>
                  setForm({ ...form, source_type: e.target.value as SourceType })
                }
                data-testid="source-type"
              >
                <option value="official_regulation">The regulation itself</option>
                <option value="official_guidance">Official guidance</option>
                <option value="industry_association">An industry body</option>
                <option value="news_article">News about a rule</option>
              </select>
            </label>
            <label className="t-footnote">
              Whose rules
              <select
                className="field mt-1 w-full"
                value={form.jurisdiction}
                onChange={(e) => setForm({ ...form, jurisdiction: e.target.value })}
                data-testid="source-jurisdiction"
              >
                <option value="EU">European Union</option>
                <option value="ID_BPOM">Indonesia (BPOM)</option>
              </select>
            </label>
            <div className="flex items-end">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={adding}
                data-testid="add-source-submit"
              >
                {adding ? "Adding…" : "Start watching"}
              </button>
            </div>
          </form>

          {formError ? (
            <p className="t-footnote mt-3" style={{ color: "var(--danger)" }} data-testid="add-source-error">
              {formError}
            </p>
          ) : null}

          {sources.length > 0 ? (
            <button
              className="btn btn-secondary btn-small mt-4"
              onClick={install}
              disabled={busy === "seed"}
              data-testid="seed-sources"
            >
              {busy === "seed" ? "Working…" : "Add the addresses we ship"}
            </button>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
