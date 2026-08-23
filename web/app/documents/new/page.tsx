import UploadForm from "./form";

export default function NewDocumentPage() {
  return (
    <main className="mx-auto max-w-3xl p-10" data-testid="new-document">
      <h1 className="text-2xl font-semibold">Ingest a regulatory source</h1>
      <p className="mt-1 text-sm opacity-70">
        The document becomes structured, sourced, confidence-scored clauses. How
        authoritative you declare the source decides what the system may do with
        them.
      </p>
      <UploadForm />
    </main>
  );
}
