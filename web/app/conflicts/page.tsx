import { listConflicts, type Conflict } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ConflictsPage() {
  let conflicts: Conflict[] = [];
  let error: string | null = null;
  try {
    conflicts = (await listConflicts()).conflicts;
  } catch {
    error = "Could not reach the API.";
  }

  return (
    <main className="mx-auto max-w-5xl p-10" data-testid="conflicts-page">
      <h1 className="text-2xl font-semibold tracking-tight">Open conflicts</h1>
      <p className="mt-1 text-sm opacity-70">
        Cross-jurisdiction mismatches. Both clauses stay active; the stricter one binds the export.
      </p>

      {error ? (
        <p className="mt-8 text-sm" style={{ color: "var(--danger)" }} data-testid="conflicts-error">
          {error}
        </p>
      ) : null}

      {conflicts.length === 0 && !error ? (
        <div className="card mt-8 p-8 text-center text-sm opacity-70" data-testid="conflicts-empty">
          No open conflicts. Nothing in the ingested corpus contradicts across jurisdictions.
        </div>
      ) : null}

      <ul className="mt-8 space-y-4">
        {conflicts.map((conflict) => (
          <li key={conflict.id} className="card p-5" data-testid={`conflict-${conflict.id}`}>
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-xs opacity-60">{conflict.id}</span>
              <span
                className="rounded-full px-2.5 py-0.5 text-xs font-medium"
                style={{ background: "var(--danger-soft)", color: "var(--danger)" }}
              >
                {conflict.severity}
              </span>
            </div>
            <p className="mt-2 text-sm font-medium">{conflict.type.replaceAll("_", " ")}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[8px] border p-3 text-sm" data-testid={`conflict-a-${conflict.id}`}>
                <div className="font-mono text-xs opacity-60">{conflict.clause_a}</div>
                <div className="mt-1">
                  limit {String(conflict.detail?.a_limit)} {String(conflict.detail?.a_unit ?? "")}
                </div>
              </div>
              <div className="rounded-[8px] border p-3 text-sm" data-testid={`conflict-b-${conflict.id}`}>
                <div className="font-mono text-xs opacity-60">{conflict.clause_b}</div>
                <div className="mt-1">
                  limit {String(conflict.detail?.b_limit)} {String(conflict.detail?.b_unit ?? "")}
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
