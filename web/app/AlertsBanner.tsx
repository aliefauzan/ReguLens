"use client";

import { useEffect, useState } from "react";
import { ackAlert, getAlerts, type GraphEvent } from "@/lib/api";

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
    <section className="mt-6 space-y-2" data-testid="alerts-banner">
      {alerts.slice(0, 3).map((alert) => (
        <div
          key={alert.id}
          className="flex items-center justify-between rounded-[10px] border p-3 text-sm"
          style={{ borderColor: "var(--danger)", background: "var(--danger-soft)" }}
          data-testid="alert-row"
        >
          <span>
            <strong>{alert.after?.status === "non_compliant" ? "Non-compliant" : "Status changed"}</strong>
            {" — "}
            product {alert.entity_id} in {(alert.before || {}).market ?? (alert.after || {}).market}
            {alert.cause?.clause_id ? (
              <span className="opacity-70"> · caused by clause {alert.cause.clause_id}</span>
            ) : null}
          </span>
          <button
            className="rounded-full border px-3 py-1 text-xs"
            onClick={() => ackAlert(alert.id)}
            data-testid="alert-ack"
          >
            Acknowledge
          </button>
        </div>
      ))}
    </section>
  );
}
