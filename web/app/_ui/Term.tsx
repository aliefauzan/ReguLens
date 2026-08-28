"use client";

import { useState } from "react";

/**
 * A word the app cannot avoid using, with its meaning one tap away.
 *
 * Some pages explained "jurisdiction" or "clause" in a sentence underneath;
 * most did not, and a reader who met the word on the wrong page had nowhere to
 * go. A title attribute is not enough — it never appears on a touch screen.
 */
const GLOSSARY: Record<string, string> = {
  jurisdiction:
    "The place whose rules apply — a country, or a bloc like the EU. Two jurisdictions can allow different amounts of the same ingredient.",
  clause:
    "One rule read out of a document: usually a substance, a maximum amount, and the kind of product it applies to.",
  rule: "One rule read out of a document: usually a substance, a maximum amount, and the kind of product it applies to.",
  authority:
    "How much a source is trusted. An official regulation can change a verdict on its own; a forwarded message never can, no matter what it says.",
  "needs review":
    "ReguLens read this but refused to act on it alone — either it was not confident enough, or the source was not official enough. It waits for a person.",
  confidence:
    "How sure ReguLens is that it read a rule correctly. Built from three things: how clean the text was, whether two independent reads agreed, and how authoritative the source is.",
  supersede:
    "A newer rule from the same country replacing an older one. The old rule is kept and marked replaced, never deleted.",
  conflict:
    "Two rules from different countries giving different numbers for the same thing. Neither is wrong; following the stricter one satisfies both.",
  requirement:
    "One check of your product against one rule: your amount, the allowed amount, and the verdict.",
};

export default function Term({ word, children }: { word: string; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const definition = GLOSSARY[word.toLowerCase()];
  if (!definition) return <>{children ?? word}</>;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="t-inherit"
        style={{
          borderBottom: "1px dashed var(--secondary)",
          color: "inherit",
          font: "inherit",
          cursor: "help",
        }}
        data-testid={`term-${word.toLowerCase().replaceAll(" ", "-")}`}
      >
        {children ?? word}
      </button>
      {open ? (
        <span
          role="note"
          className="card absolute left-0 z-40 mt-1 block p-4 t-footnote"
          style={{ width: "min(20rem, 80vw)", top: "100%" }}
        >
          {definition}
        </span>
      ) : null}
    </span>
  );
}
