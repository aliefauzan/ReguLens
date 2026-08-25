import Link from "next/link";
import Stepper from "./Stepper";

export const dynamic = "force-dynamic";

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // The stepper polls everything client-side; the server shell only needs to
  // exist so the route resolves. A missing document surfaces as the poll
  // error state.
  return (
    <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12" data-testid="document-detail">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← Back</Link>

      <h1 className="t-large-title mt-3">Reading your document</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        This page updates itself. You can leave and come back — the work carries on without you.
      </p>
      <p className="t-caption t-secondary mono mt-2" data-testid="document-id">{id}</p>

      <Stepper documentId={id} />
    </main>
  );
}
