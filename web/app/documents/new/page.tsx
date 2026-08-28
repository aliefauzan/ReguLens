import Link from "next/link";
import Rulebook from "../../_ui/Rulebook";
import UploadForm from "./form";

export default function NewDocumentPage() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12" data-testid="new-document">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← Back</Link>
      <h1 className="t-large-title mt-3">Add rules</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        Give ReguLens a regulation to read — a PDF, or text you paste in. It works out which
        country&apos;s rules it is and how much weight the source carries, pulls out the limits, and
        compares them with what it already knows. You only confirm what it could not read.
      </p>
      {/* The rulebook comes first: most people do not have a regulation PDF,
          and the ones we already hold answer the question without an upload. */}
      <div className="mt-8">
        <Rulebook />
      </div>

      <h2 className="t-title mt-10">Or read your own document</h2>
      <UploadForm />
    </main>
  );
}
