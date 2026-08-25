import Link from "next/link";
import UploadForm from "./form";

export default function NewDocumentPage() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12" data-testid="new-document">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← Back</Link>
      <h1 className="t-large-title mt-3">Add rules</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        Give ReguLens a regulation to read — a PDF, or text you paste in. It pulls out the limits and
        compares them with what it already knows. How trustworthy you say the source is decides how
        much ReguLens is allowed to act on it.
      </p>
      <UploadForm />
    </main>
  );
}
