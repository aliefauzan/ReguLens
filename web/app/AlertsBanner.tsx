"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ackAlert, getAlerts, type GraphEvent } from "@/lib/api";
import { marketName, statusCopy } from "./_ui/status";

type Alert = GraphEvent & {
  before?: { status?: string; market?: string } | null;
  after?: { status?: string; market?: string } | null;
  cause?: { clause_id?: string; document_id?: string } | null;
  acknowledged?: boolean;
};

/**
 * The activity feed: verdicts that moved without anybody asking.
 *
 * It sits in the dashboard's right-hand column, so each entry is one line of
 * change plus its actions — the detail and the reasoning live on the pages the
 * buttons lead to. A paragraph per alert here just pushed the next alert off
 * the screen.
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
            When a rule you add changes an answer, the change is listed here with what caused it.
          </p>
        </div>
      ) : (
        <ul>
          {alerts.slice(0, 5).map((alert, index) => {
            const after = statusCopy(alert.after?.status);
            const before = statusCopy(alert.before?.status);
            const market = alert.after?.market ?? alert.before?.market ?? "";
            const worse = alert.after?.status === "non_compliant";
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
                    {market ? marketName(market) : "This product"}: {after.label.toLowerCase()}
                  </span>
                  <span className="t-caption block">
                    was “{before.label}” · changed by a rule you added, without being asked
                  </span>
                </p>
                <span className="mt-3 flex flex-wrap gap-1.5">
                  {/* "Breaks a rule" is the only status with a number to hit, so
                      it is the only one that gets the button. Offering a fix plan
                      for a product that passes leads to an empty page. */}
                  {worse && alert.entity_id ? (
                    <Link
                      href={`/products/${alert.entity_id}/remediation`}
                      className="btn btn-secondary btn-small"
                      data-testid="alert-prepare-fix"
                    >
                      Prepare a fix plan
                    </Link>
                  ) : null}
                  <Link href="/conflicts" className="btn btn-secondary btn-small">
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
      )}
    </section>
  );
}
