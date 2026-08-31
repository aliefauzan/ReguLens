import Link from "next/link";
import { getDocument } from "@/lib/api";
import { jurisdictionName } from "../../_ui/status";
import { Suspense } from "react";
import SourceText from "./SourceText";
import Stepper from "./Stepper";

export const dynamic = "force-dynamic";

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // The heading used to read "Reading your document" over a raw id, on a page
  // people also reach long after the reading finished. Naming the document is
  // the difference between a page about *your* BPOM circular and a page about
  // doc_6f69c48bdd59.
  let sourceName: string | null = null;
  let jurisdiction: string | null = null;
  let finished = false;
  let ruleCount = 0;
  // Where the metadata came from. A document whose country nobody typed in was
  // read off the page, and the page should be able to say so.
  let readItself: string | null = null;
  try {
    const { document, clauses } = await getDocument(id);
    sourceName = document.source_name;
    jurisdiction = document.jurisdiction;
    const evidence = document.detection?.jurisdiction?.evidence ?? null;
    if (evidence && !document.declared_fields?.includes("jurisdiction")) {
      readItself = evidence;
    }
    finished = document.status === "extracted" || document.status === "reconciled";
    ruleCount = clauses.length;
  } catch {
    // The stepper polls and shows its own error state; the shell still renders.
  }

  return (
    <main className="page page-narrow" data-testid="document-detail">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← Back</Link>

      <h1 className="t-large-title mt-3">{sourceName ?? "Your document"}</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        {jurisdiction ? `${jurisdictionName(jurisdiction)} · ` : ""}
        {!finished
          ? "This page updates itself. You can leave and come back — the work carries on without you."
          : ruleCount === 0
            ? "We could not find any rules in this one."
            : "Everything we found in this document is listed below."}
      </p>

      {readItself ? (
        <p className="t-footnote t-secondary prose-measure mt-2" data-testid="document-detected">
          You did not have to tell us the country: the document says “{readItself}”.
        </p>
      ) : null}

      <Stepper documentId={id} />

      {/* The reader reads `?cite=` to know which passage to open at, so it
          needs a Suspense boundary of its own. */}
      <Suspense fallback={null}>
        <SourceText documentId={id} />
      </Suspense>

      <p className="t-caption t-secondary mt-6" data-testid="document-id">
        Reference, if you need to quote it to us: <span className="mono">{id}</span>
      </p>
    </main>
  );
}
