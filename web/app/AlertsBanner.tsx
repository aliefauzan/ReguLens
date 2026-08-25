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
    <section className="mt-6 space-y-3" data-testid="alerts-banner">
      {alerts.slice(0, 3).map((alert) => {
        const after = statusCopy(alert.after?.status);
        const before = statusCopy(alert.before?.status);
        const market = alert.after?.market ?? alert.before?.market ?? "";
        // An alert is not automatically bad news: a new rule can clear a
        // product as easily as it can block one. Colour follows the outcome.
        const worse = alert.after?.status === "non_compliant";
        const better = alert.after?.status === "compliant";
        const accent = worse ? "var(--danger)" : better ? "var(--good)" : "var(--warn)";
        return (
          <div
            key={alert.id}
            className="card p-5"
            style={{ borderLeft: `4px solid ${accent}` }}
            data-testid="alert-row"
          >
            <div data-testid="impact-chain">
                <p className="t-headline" style={{ color: accent }}>
                  {market ? `${marketName(market)}: ${after.label.toLowerCase()}` : after.label}
                </p>
              <p className="t-footnote t-secondary prose-measure mt-1">
                {after.meaning} This changed on its own, because a rule you added says so.
              </p>
              <p className="t-footnote t-secondary mt-2">
                Was “{before.label}” · now “{after.label}”
              </p>
            </div>

            {/* One action row, same place on every alert. */}
            <div className="mt-4 flex gap-2">
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
            </div>
          </div>
        );
      })}
    </section>
  );
}
