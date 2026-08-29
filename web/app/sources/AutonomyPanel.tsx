"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getAutonomy, type Autonomy } from "@/lib/api";

/**
 * The receipts for the one claim the product cannot make in prose.
 *
 * "It watches for changes" is a slogan until a reader can see how many
 * regulations arrived without anybody fetching them. Every number here is a
 * query over the same records the rest of the app reads, so each one is
 * clickable through to the thing it counts.
 *
 * Zeros are shown as zeros. A quiet week is the ordinary case for a monitor,
 * and this is the easiest place in the product to tell a flattering lie.
 */
function ago(iso: string | null): string {
  if (!iso) return "not yet";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "not yet";
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
}

export default function AutonomyPanel() {
  const [stats, setStats] = useState<Autonomy | null>(null);

  useEffect(() => {
    getAutonomy()
      .then(setStats)
      .catch(() => {
        // Additive UI. If it cannot load, the page below still works.
      });
  }, []);

  if (!stats) return null;

  const figures: { value: number; label: string; hint: string }[] = [
    {
      value: stats.regulations_found,
      label: stats.regulations_found === 1 ? "regulation read" : "regulations read",
      hint: "nobody uploaded these",
    },
    {
      value: stats.clauses_read,
      label: stats.clauses_read === 1 ? "rule extracted" : "rules extracted",
      hint: "out of those documents",
    },
    {
      value: stats.verdicts_changed,
      label: stats.verdicts_changed === 1 ? "verdict changed" : "verdicts changed",
      hint: "on a product, unprompted",
    },
    { value: stats.checks_run, label: "checks run", hint: `last ${ago(stats.last_checked_at)}` },
  ];

  return (
    <section className="card mt-6 p-5" data-testid="autonomy-panel">
      <h2 className="t-headline">What ReguLens did on its own</h2>
      <p className="t-footnote t-secondary prose-measure mt-1">
        Counted from the records themselves, not from a tally that could drift. Nobody pressed a
        button for any of it.
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {figures.map((figure) => (
          <div key={figure.label} data-testid={`autonomy-${figure.label.replace(/\s+/g, "-")}`}>
            <dd className="t-large-title" style={{ lineHeight: 1.1 }}>
              {figure.value}
            </dd>
            <dt className="t-footnote mt-1">{figure.label}</dt>
            <dd className="t-caption t-secondary">{figure.hint}</dd>
          </div>
        ))}
      </dl>

      {stats.failing_sources > 0 ? (
        <p className="t-footnote mt-4" style={{ color: "var(--danger)" }} data-testid="autonomy-failing">
          {stats.failing_sources} of {stats.watched_sources} addresses could not be read last time.
          Until that is fixed, nothing is being watched there — the rows below say which.
        </p>
      ) : null}

      {stats.regulations_found === 0 ? (
        <p className="t-footnote t-secondary mt-4">
          Nothing found yet. The addresses below are checked on a schedule; a regulation appears
          here the first time one of them changes or publishes something new.
        </p>
      ) : (
        <p className="t-footnote t-secondary mt-4">
          <Link className="underline" href="/rules">
            See the rules these produced
          </Link>{" "}
          — they went through the same reading, checks and review queue as anything uploaded by
          hand.
        </p>
      )}
    </section>
  );
}
