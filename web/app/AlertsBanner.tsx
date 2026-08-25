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
                  was “{before.label}” · changed by a rule you added, without being asked
                </span>
              </span>
              <span className="flex gap-2">
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
    </section>
  );
}
