"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { listLibrary, loadLibrary, type LibraryEntry } from "@/lib/api";
import { jurisdictionName, plain } from "./status";

/**
 * The regulations that ship with the app.
 *
 * The honest answer to "why do I have to add a regulation?" was: because we
 * shipped an empty rulebook and made the user go and find one. We already hold
 * two real regulations, so this offers them — as excerpts, read through the
 * same pipeline as an upload, with the citation visible before anyone presses
 * anything.
 */

export function LoadStarterRules({
  label = "Load the starter rules",
  onDone,
}: {
  label?: string;
  onDone?: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function load() {
    setError(null);
    setBusy(true);
    try {
      const { queued, already_read: already } = await loadLibrary();
      setDone(
        queued > 0
          ? `Reading ${queued} regulation${queued === 1 ? "" : "s"} now. This page updates itself.`
          : already > 0
            ? "Those rules were already read — nothing to do."
            : "Nothing to load.",
      );
      router.refresh();
      onDone?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-3">
      <button
        type="button"
        className="btn btn-primary btn-small"
        onClick={load}
        disabled={busy}
        data-testid="load-starter-rules"
      >
        {busy ? "Loading…" : label}
      </button>
      {done ? (
        <span className="t-footnote t-secondary" data-testid="load-starter-done">{done}</span>
      ) : null}
      {error ? (
        <span className="t-footnote" style={{ color: "var(--danger)" }} data-testid="load-starter-error">
          {error}
        </span>
      ) : null}
    </span>
  );
}

/**
 * The citation in one line.
 *
 * The full one names the consolidation date and the CELEX id, which is what a
 * reader needs when checking a number — and unreadable repeated twenty-eight
 * times down a list. The long form stays on hover and on the document page.
 */
function shortCitation(entry: LibraryEntry): string {
  const category = entry.citation.match(/food category ([\d.]+)/);
  if (category) return `EU additive list, category ${category[1]}`;
  const page = entry.citation.match(/page (\d+)/);
  if (page) return `BPOM 11/2019, page ${page[1]}`;
  return entry.citation;
}

/** The whole library, grouped by country, one button per rule. */
export default function Rulebook() {
  const router = useRouter();
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    listLibrary()
      .then(({ entries: found }) => setEntries(found))
      // The page still works with a file or pasted text, so a failure here is
      // reported quietly rather than blocking the upload form above it.
      .catch(() => setFailed(true));
  }, []);

  async function add(entry: LibraryEntry) {
    setError(null);
    setBusy(entry.id);
    try {
      const { results } = await loadLibrary([entry.id]);
      const result = results[0];
      setLoaded((current) => ({
        ...current,
        [entry.id]: result?.cached ? "Already read" : "Reading it now",
      }));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That rule did not load.");
    } finally {
      setBusy(null);
    }
  }

  if (failed || entries.length === 0) return null;

  const byCountry = entries.reduce<Record<string, LibraryEntry[]>>((groups, entry) => {
    (groups[entry.jurisdiction] ??= []).push(entry);
    return groups;
  }, {});
  const starters = entries.filter((entry) => entry.starter);

  return (
    <section className="card p-6" data-testid="rulebook">
      <h2 className="t-headline">Rules we already have</h2>
      <p className="help">
        {entries.length} excerpts from the two regulations that ship with ReguLens — the EU additive
        list and the Indonesian BPOM additive annex. Each one is read exactly like a document you
        upload, and every number stays traceable to the page it came from.
      </p>

      <div className="inset mt-4 p-5">
        <p className="t-subhead" style={{ fontWeight: 600 }}>
          Not sure which you need?
        </p>
        <p className="t-footnote t-secondary prose-measure mt-1">
          The starter set is {starters.length} rules covering drinks, powders and supplements in both
          countries. Start there and add more later.
        </p>
        <div className="mt-3">
          <LoadStarterRules />
        </div>
      </div>

      <button
        type="button"
        className="btn btn-quiet btn-small mt-4"
        onClick={() => setShowAll((current) => !current)}
        data-testid="toggle-rulebook"
      >
        {showAll ? "Hide the full list" : `Pick from all ${entries.length} instead`}
      </button>

      {showAll ? (
        <div className="mt-4 grid gap-6">
          {Object.entries(byCountry).map(([jurisdiction, group]) => (
            <div key={jurisdiction}>
              <h3 className="t-subhead" style={{ fontWeight: 600 }}>
                {jurisdictionName(jurisdiction)}
              </h3>
              <div className="mt-2 grid gap-2">
                {group.map((entry) => (
                  <div
                    key={entry.id}
                    className="inset flex flex-wrap items-center justify-between gap-3 p-4"
                    data-testid={`rulebook-${entry.id}`}
                  >
                    <span className="min-w-0">
                      <span className="t-subhead block" style={{ fontWeight: 600 }}>
                        {entry.title}
                      </span>
                      <span className="t-footnote t-secondary block">{entry.summary}</span>
                      <span className="t-caption t-secondary block mt-1" title={entry.citation}>
                        For {entry.product_types.map((type) => plain(type)).join(", ")} ·{" "}
                        {shortCitation(entry)}
                        {entry.truncated ? " · first part of a long table" : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-small"
                      onClick={() => add(entry)}
                      disabled={busy === entry.id || !!loaded[entry.id]}
                      data-testid={`add-rule-${entry.id}`}
                    >
                      {loaded[entry.id] ?? (busy === entry.id ? "Adding…" : "Add this one")}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {error ? (
        <p className="t-footnote mt-3" style={{ color: "var(--danger)" }} data-testid="rulebook-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}
