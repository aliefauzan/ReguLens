import Link from "next/link";
import { getDocument } from "@/lib/api";
import { jurisdictionName } from "../../_ui/status";
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
  try {
    const { document, clauses } = await getDocument(id);
    sourceName = document.source_name;
    jurisdiction = document.jurisdiction;
    finished = document.status === "extracted" || document.status === "reconciled";
    ruleCount = clauses.length;
  } catch {
    // The stepper polls and shows its own error state; the shell still renders.
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12" data-testid="document-detail">
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

      <Stepper documentId={id} />

      <p className="t-caption t-secondary mt-8" data-testid="document-id">
        Reference, if you need to quote it to us: <span className="mono">{id}</span>
      </p>
    </main>
  );
}
