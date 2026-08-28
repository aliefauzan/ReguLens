"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getDocumentText, type DocumentText, type SourceCitation } from "@/lib/api";

/**
 * The document, in its own words, with the cited passages marked in it.
 *
 * "Where this came from" used to end at a document name. That is one step
 * better than an id and one step short of useful: the reader still has to find
 * the sentence in an annex to check the number they were shown. Here the
 * passage is highlighted in place, and arriving from a rule scrolls straight to
 * it.
 *
 * What it will not do is guess. A clause we could not locate in the text is
 * listed as unlocated rather than pointed at the nearest paragraph — the
 * citation is only worth anything if the reader can trust where it points.
 */

type Piece = { text: string; citation: SourceCitation | null };

/** Cut the document into plain runs and cited runs, in order. */
function split(text: string, citations: SourceCitation[]): Piece[] {
  const found = citations
    .filter((citation) => citation.match !== "not_found" && citation.end > citation.start)
    .sort((a, b) => a.start - b.start);

  const pieces: Piece[] = [];
  let cursor = 0;
  for (const citation of found) {
    // Two clauses read from the same row would otherwise nest inside each
    // other; the first one to start owns the passage.
    if (citation.start < cursor) continue;
    if (citation.start > cursor) {
      pieces.push({ text: text.slice(cursor, citation.start), citation: null });
    }
    pieces.push({ text: text.slice(citation.start, citation.end), citation });
    cursor = citation.end;
  }
  if (cursor < text.length) pieces.push({ text: text.slice(cursor), citation: null });
  return pieces;
}

export default function SourceText({ documentId }: { documentId: string }) {
  const params = useSearchParams();
  const focused = params.get("cite");
  const [data, setData] = useState<DocumentText | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const target = useRef<HTMLElement | null>(null);

  useEffect(() => {
    getDocumentText(documentId)
      .then(setData)
      .catch(() => setFailed(true));
  }, [documentId]);

  // Arriving from a rule means the reader asked for one passage. Open the
  // reader for them and put it in front of them; arriving cold leaves the
  // document collapsed, because most visits are not about the raw text.
  useEffect(() => {
    if (focused) setOpen(true);
  }, [focused]);

  useEffect(() => {
    if (!open || !focused || !data) return;
    const timer = setTimeout(() => {
      target.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
    return () => clearTimeout(timer);
  }, [open, focused, data]);

  const pieces = useMemo(
    () => (data?.text ? split(data.text, data.citations) : []),
    [data],
  );

  if (failed) return null;
  if (!data) {
    return (
      <p className="t-footnote t-secondary mt-8" data-testid="source-text-loading">
        Loading the document text…
      </p>
    );
  }

  const located = data.citations.filter((citation) => citation.match !== "not_found");
  const unlocated = data.citations.length - located.length;
  const focusedCitation = focused
    ? data.citations.find((citation) => citation.clause_id === focused)
    : undefined;

  if (!data.available) {
    return (
      <section className="card mt-8 p-6" data-testid="source-text-unavailable">
        <h2 className="t-section">The document itself</h2>
        <p className="t-footnote t-secondary prose-measure mt-2">
          We did not keep the full text of this one — it was read before ReguLens started storing
          it. Add the document again and the passages behind each rule will be shown here.
        </p>
      </section>
    );
  }

  return (
    <section className="card mt-8 p-6" data-testid="source-text">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="t-section">The document itself</h2>
        <button
          type="button"
          className="btn btn-quiet btn-small"
          onClick={() => setOpen((current) => !current)}
          data-testid="toggle-source-text"
        >
          {open ? "Hide the text" : "Show the text"}
        </button>
      </div>

      <p className="t-footnote t-secondary prose-measure mt-2">
        {located.length > 0
          ? `Every rule we found is highlighted where we read it. ${located.length} of ${data.citations.length} ${
              data.citations.length === 1 ? "passage is" : "passages are"
            } marked.`
          : "No passage could be matched back to the text."}
        {unlocated > 0
          ? ` ${unlocated} could not be located in the text, so ${
              unlocated === 1 ? "it is" : "they are"
            } not highlighted — we would rather mark nothing than mark the wrong sentence.`
          : ""}
        {data.truncated ? " This is the first part of a long document." : ""}
      </p>

      {focusedCitation ? (
        <p
          className="t-footnote mt-2"
          style={{ color: focusedCitation.match === "not_found" ? "var(--danger)" : "var(--accent)" }}
          data-testid="source-focus-note"
        >
          {focusedCitation.match === "not_found"
            ? "We could not find this rule's wording in the document text. The rule still links to this document, but we will not point at a passage we are unsure of."
            : focusedCitation.match === "approximate"
              ? "Showing the closest passage — the rule's wording differs slightly from the document's."
              : "The passage this rule was read from is highlighted below."}
        </p>
      ) : null}

      {open ? (
        <div
          className="inset mt-4 p-4"
          style={{ maxHeight: "60vh", overflow: "auto" }}
          data-testid="source-text-body"
        >
          <pre
            className="t-footnote"
            style={{
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "var(--font-mono, ui-monospace, monospace)",
              lineHeight: 1.65,
              margin: 0,
            }}
          >
            {pieces.map((piece, index) =>
              piece.citation ? (
                <mark
                  key={index}
                  ref={piece.citation.clause_id === focused ? target : undefined}
                  id={`cite-${piece.citation.clause_id}`}
                  title={
                    piece.citation.match === "approximate"
                      ? "Closest match to a rule's wording"
                      : "A rule was read from here"
                  }
                  data-testid={`cite-${piece.citation.clause_id}`}
                  style={{
                    background:
                      piece.citation.clause_id === focused
                        ? "color-mix(in srgb, var(--accent) 38%, transparent)"
                        : "color-mix(in srgb, var(--accent) 14%, transparent)",
                    color: "inherit",
                    borderRadius: 4,
                    padding: "1px 2px",
                    boxShadow:
                      piece.citation.clause_id === focused
                        ? "0 0 0 2px var(--accent)"
                        : undefined,
                  }}
                >
                  {piece.text}
                </mark>
              ) : (
                <span key={index}>{piece.text}</span>
              ),
            )}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
