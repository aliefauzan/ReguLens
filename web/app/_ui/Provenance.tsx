import Link from "next/link";
import { jurisdictionName } from "./status";

/**
 * Where a rule came from, in words.
 *
 * Every page used to answer "Where this came from" with a bare
 * `clause_2da66be9e735`. That is the one thing a reader cannot use: it names
 * nothing, it cannot be looked up, and it appears at exactly the moment
 * somebody is deciding whether to trust the number above it. The document it
 * was read from, and a way back to it, is the actual answer. The id stays for
 * anyone quoting a problem to us, one line down and labelled.
 */
export default function Provenance({
  clauseId,
  documentId,
  sourceName,
  jurisdiction,
  testId,
}: {
  clauseId: string;
  documentId?: string | null;
  sourceName?: string | null;
  jurisdiction?: string | null;
  testId?: string;
}) {
  return (
    <details className="mt-3" data-testid={testId}>
      <summary className="t-footnote cursor-pointer">Where this came from</summary>
      <div className="inset mt-2 p-4">
        <p className="t-body" style={{ fontWeight: 600 }}>
          {sourceName ?? "A document you added"}
        </p>
        {jurisdiction ? (
          <p className="t-footnote t-secondary mt-1">{jurisdictionName(jurisdiction)}</p>
        ) : null}
        {documentId ? (
          <Link
            href={`/documents/${documentId}`}
            className="btn btn-secondary btn-small mt-3"
            data-testid={`open-source-${clauseId}`}
          >
            Open this document
          </Link>
        ) : null}
        <p className="t-caption t-secondary mt-3">
          Reference, if you need to quote it to us: <span className="mono">{clauseId}</span>
        </p>
      </div>
    </details>
  );
}
