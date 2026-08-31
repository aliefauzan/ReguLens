"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ackAlert, getAlerts, type AlertContext, type GraphEvent } from "@/lib/api";
import { marketName, readableDate, statusCopy } from "./_ui/status";

type Alert = GraphEvent & {
  before?: { status?: string; market?: string } | null;
  after?: { status?: string; market?: string; effective_date?: string | null } | null;
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
    return context?.scheduled
      ? "The rule setting this date is no longer on file, so we cannot show you which one it was."
      : "The rule behind this has since been removed, so the verdict above is the last one we calculated.";
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
  if (context.scheduled) {
    // Not "your product is wrong". Nothing is wrong yet — which is the whole
    // reason this alert is worth reading while there is still time to act.
    const when = context.effective_date ? readableDate(context.effective_date) : null;
    return `Nothing is wrong today. ${source} changes the answer${
      when ? ` on ${when}` : " on a date it states"
    }, which is the window you have to do something about it.${limit}`;
  }
  if (context.origin === "library") {
    return `Caused by ${source}, one of the rules bundled with ReguLens.${limit}`;
  }
  return `Caused by ${source}, which you added.${limit}`;
}

/**
 * The activity feed: verdicts that moved without anybody asking.
 *
 * It sits in the dashboard's right-hand column, so each entry is one line of
 * change, the sentence explaining it, and its actions — the passage itself
 * lives on the page "See why" leads to.
 */
export default function AlertsBanner() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getAlerts();
        if (!cancelled) setAlerts(data.alerts as Alert[]);
      } catch {
        // Alerts are additive UI; a failed poll stays quiet.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => {
      clearInterval(timer);
      cancelled = true;
    };
  }, []);

  // First paint, before the first poll answers: hold the shape rather than
  // letting the column jump when the data lands.
  if (loading) {
    return (
      <section className="panel p-5" aria-hidden="true">
        <div className="skeleton h-3 w-28" />
        <div className="skeleton mt-4 h-4 w-full" />
        <div className="skeleton mt-2 h-3 w-3/5" />
      </section>
    );
  }

  return (
    <section className="panel overflow-hidden" data-testid="alerts-banner">
      <div className="panel-head">
        <h2 className="t-section">Changed on its own</h2>
        {alerts.length > 0 ? (
          <span className="flex items-center gap-1.5" style={{ color: "var(--good)" }}>
            <span className="dot dot-live" />
            <span className="t-caption mono">{alerts.length}</span>
          </span>
        ) : null}
      </div>

      {alerts.length === 0 ? (
        // An empty feed is a real answer here — the pipeline is watching and
        // has nothing to report — so it says that instead of showing nothing.
        <div className="px-5 py-6 text-center" data-testid="alerts-empty">
          <p className="t-subhead">No verdict has moved</p>
          <p className="t-caption prose-measure mx-auto mt-1">
            When a rule changes an answer, the change is listed here with what caused it.
          </p>
        </div>
      ) : (
        <>
          {alerts.some((a) => a.context?.unprompted) ? (
            <p className="t-caption px-5 pt-3" data-testid="alerts-unprompted-note">
              At least one of these came from a regulation ReguLens found by itself, on its
              schedule — no upload, no prompt.{" "}
              <Link className="underline" href="/sources">
                See what it watches
              </Link>
              .
            </p>
          ) : null}
          <ul>
            {alerts.slice(0, 5).map((alert, index) => {
              const after = statusCopy(alert.after?.status);
              const before = statusCopy(alert.before?.status);
              const market = alert.after?.market ?? alert.before?.market ?? "";
              const scheduled = alert.context?.scheduled === true;
              const worse = alert.after?.status === "non_compliant" && !scheduled;
              const better = alert.after?.status === "compliant";
              const accent = worse ? "var(--danger)" : better ? "var(--good)" : "var(--warn)";
              return (
                <li
                  key={alert.id}
                  className="row rise px-5 py-4"
                  style={{ "--i": index } as React.CSSProperties}
                  data-testid="alert-row"
                >
                  <p data-testid="impact-chain">
                    <span className="t-subhead" style={{ color: accent, fontWeight: 600 }}>
                      {market ? marketName(market) : "This product"}:{" "}
                      {scheduled
                        ? `${after.label.toLowerCase()} from ${readableDate(
                            alert.context?.effective_date,
                          )}`
                        : after.label.toLowerCase()}
                    </span>
                    <span className="t-caption block">
                      {scheduled ? "today “" : "was “"}
                      {before.label}” · {why(alert.context)}
                    </span>
                  </p>
                  <span className="mt-3 flex flex-wrap gap-1.5">
                    {/* "Breaks a rule" is the only status with a number to hit, so
                        it is the only one that gets the button. Offering a fix plan
                        for a product that passes leads to an empty page, and one
                        for a verdict that only starts in March is premature. */}
                    {worse && alert.entity_id ? (
                      <Link
                        href={`/products/${alert.entity_id}/remediation`}
                        className="btn btn-secondary btn-small"
                        data-testid="alert-prepare-fix"
                      >
                        Prepare a fix plan
                      </Link>
                    ) : null}
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
        </>
      )}
    </section>
  );
}
