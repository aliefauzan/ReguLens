import Link from "next/link";
import Stepper from "./Stepper";
import { getDocument } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // The stepper polls everything client-side; the server shell only needs to
  // exist so the route resolves. A missing document surfaces as the poll
  // error state, which is honest enough for a debug-grade page.
  return (
    <main className="mx-auto max-w-3xl p-10" data-testid="document-detail">
      <div className="flex items-baseline justify-between">
        <Link href="/" className="text-sm underline opacity-70">
          ← All products
        </Link>
        <span className="font-mono text-xs opacity-40" data-testid="document-id">
          {id}
        </span>
      </div>

      <h1 className="mt-4 text-2xl font-semibold">Document pipeline</h1>

      <Stepper documentId={id} />
    </main>
  );
}
