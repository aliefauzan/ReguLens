"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ackAlert, getAlerts, type AlertContext, type GraphEvent } from "@/lib/api";
import { marketName, statusCopy } from "./_ui/status";

type Alert = GraphEvent & {
  before?: { status?: string; market?: string } | null;
  after?: { status?: string; market?: string } | null;
  cause?: { clause_id?: string; document_id?: string } | null;
  acknowledged?: boolean;
  context?: AlertContext;
};

/**
 * The sentence under an alert, assembled only from facts the API resolved.
 *
 * Nothing is guessed. This used to read "changed by a rule you added, without
 * being asked" for every alert, which was wrong twice over: it was wrong when
 * the user had just uploaded the document, and it was wrong in the other
 * direction for a regulation that arrived overnight from a watched address,
 * which nobody added at all. Now each case says what actually happened, and a
 * cause that has been deleted says so instead of borrowing another one's story.
 */
function why(context: AlertContext | undefined): string {
  if (!context || !context.cause_available) {
    return "The rule behind this has since been removed, so the verdict above is the last one we calculated.";
  }
  const source = context.source_name ?? "a rule we read";
  const limit =
    context.substance && context.limit_value != null
      ? ` It sets ${context.substance.replace(/_/g, " ")} at ${context.limit_value}${
          context.limit_unit === "mg_per_kg" ? " mg/kg" : ""
        }.`
      : "";
  if (context.unprompted) {
    // The one sentence this whole feature exists to be able to say.
    return `Nobody uploaded this. ${source} was published at an address ReguLens watches, and we read it on our own.${limit}`;
  }
  if (context.origin === "library") {
    return `Caused by ${source}, one of the rules bundled with ReguLens.${limit}`;
  }
  return `Caused by ${source}, which you added.${limit}`;
}

export default function AlertsBanner() {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getAlerts();
        if (!cancelled) setAlerts(data.alerts as Alert[]);
      } catch {
        // Alerts are additive UI; a failed poll stays quiet.
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => {
      clearInterval(timer);
      cancelled = true;
    };
  }, []);

  if (alerts.length === 0) return null;

  return (
    // The next-step card above carries the detail and the action. These are the
    // receipts: what changed, and when, one line each. Repeating a paragraph
    // per alert next to it just made the page harder to read.
    <section className="mt-6" data-testid="alerts-banner">
      <h2 className="t-section">What changed on its own</h2>
      {alerts.some((a) => a.context?.unprompted) ? (
        <p className="t-footnote t-secondary mt-1" data-testid="alerts-unprompted-note">
          At least one of these came from a regulation ReguLens found by itself, on its
          schedule — no upload, no prompt.{" "}
          <Link className="underline" href="/sources">
            See what it watches
          </Link>
          .
        </p>
      ) : null}
      <ul className="card mt-3 overflow-hidden">
        {alerts.slice(0, 5).map((alert) => {
          const after = statusCopy(alert.after?.status);
          const before = statusCopy(alert.before?.status);
          const market = alert.after?.market ?? alert.before?.market ?? "";
          const worse = alert.after?.status === "non_compliant";
          const better = alert.after?.status === "compliant";
          const accent = worse ? "var(--danger)" : better ? "var(--good)" : "var(--warn)";
          return (
            <li
              key={alert.id}
              className="row flex flex-wrap items-center justify-between gap-3 px-5 py-4"
              data-testid="alert-row"
            >
              <span data-testid="impact-chain">
                <span className="t-body" style={{ color: accent, fontWeight: 600 }}>
                  {market ? marketName(market) : "This product"}: {after.label.toLowerCase()}
                </span>
                <span className="t-footnote t-secondary block">
                  was “{before.label}” · {why(alert.context)}
                </span>
              </span>
              <span className="flex gap-2">
                <Link
                  href={
                    // Straight to the passage that caused it where we know it,
                    // rather than to a page the reader has to search.
                    alert.context?.document_id
                      ? `/documents/${alert.context.document_id}${
                          alert.context.clause_id ? `?cite=${alert.context.clause_id}` : ""
                        }`
                      : "/conflicts"
                  }
                  className="btn btn-secondary btn-small"
                  data-testid="alert-see-why"
                >
                  See why
                </Link>
                <button
                  className="btn btn-quiet btn-small"
                  onClick={() => ackAlert(alert.id)}
                  data-testid="alert-ack"
                >
                  Got it
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
