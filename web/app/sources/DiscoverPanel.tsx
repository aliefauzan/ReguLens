"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  discoverCountry,
  discoveryEventsUrl,
  listCountries,
  type Country,
  type DiscoveryJob,
} from "@/lib/api";

/**
 * Watching a country nobody seeded.
 *
 * The honest framing matters more here than anywhere else in the app, because
 * this is the one place that asks a model where to look. Two things are true at
 * once and both are shown:
 *
 * - When it works, what lands is an ordinary watched source. The same nightly
 *   check reads it, the same extraction reads what it finds.
 * - It often does not work. Government sites refuse automated reads, publish
 *   through a JavaScript application, or file their acts somewhere no index
 *   links to. Every one of those endings is rendered with its reason, because a
 *   panel that quietly found nothing would make the monitoring claim a lie.
 */
export default function DiscoverPanel({ onCommitted }: { onCommitted?: () => void }) {
  const [countries, setCountries] = useState<Country[]>([]);
  const [available, setAvailable] = useState(false);
  const [model, setModel] = useState("");
  const [typed, setTyped] = useState("");
  const [picked, setPicked] = useState<Country | null>(null);
  const [job, setJob] = useState<DiscoveryJob | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const stream = useRef<EventSource | null>(null);

  useEffect(() => {
    listCountries()
      .then((body) => {
        setCountries(body.countries);
        setAvailable(body.available);
        setModel(body.model);
      })
      .catch(() => {
        // Additive UI: the source list below still works without this.
      });
    return () => stream.current?.close();
  }, []);

  const matches = useMemo(() => {
    const needle = typed.trim().toLowerCase();
    if (!needle) return [];
    return countries
      .filter((c) => c.name.toLowerCase().includes(needle) || c.code.toLowerCase() === needle)
      .slice(0, 8);
  }, [countries, typed]);

  const running =
    job !== null && !["done", "partial", "failed"].includes(job.status);

  function watch(jobId: string) {
    stream.current?.close();
    const source = new EventSource(discoveryEventsUrl(jobId));
    stream.current = source;
    source.onmessage = (event) => {
      const next = JSON.parse(event.data) as DiscoveryJob;
      setJob(next);
      if (["done", "partial"].includes(next.status)) onCommitted?.();
      if (["done", "partial", "failed"].includes(next.status)) source.close();
    };
    source.addEventListener("timeout", () => {
      // Say so rather than leaving a spinner turning forever.
      setFailure("This is taking longer than expected. Reload to see where it got to.");
      source.close();
    });
    source.onerror = () => {
      source.close();
      // The stream dropping is not the job failing — the job runs on the
      // worker either way, so the row is left as it stands.
    };
  }

  async function start() {
    if (!picked) return;
    setFailure(null);
    setJob(null);
    try {
      const started = await discoverCountry(picked.code);
      setJob(started.job);
      watch(started.job_id);
    } catch {
      setFailure("Could not start the search. The API may be unreachable.");
    }
  }

  if (!available) return null;

  return (
    <section className="card mt-6 p-5" data-testid="discover-panel">
      <h2 className="t-headline">Watch another country</h2>
      <p className="t-footnote t-secondary prose-measure mt-1">
        Names the country&apos;s food regulator with {model || "Gemma"}, then reads its site to
        find where regulations are published. What it finds is registered as an ordinary watched
        address — checked nightly, read through the same pipeline as anything uploaded by hand.
      </p>

      <div className="mt-4 flex flex-wrap items-start gap-3">
        <div style={{ position: "relative", minWidth: "16rem" }}>
          <input
            className="field"
            style={{ width: "100%" }}
            placeholder="Country name"
            value={picked ? picked.name : typed}
            data-testid="discover-search"
            disabled={running}
            onChange={(event) => {
              setPicked(null);
              setTyped(event.target.value);
            }}
          />
          {!picked && matches.length > 0 ? (
            <ul className="card" data-testid="discover-matches" style={listStyle}>
              {matches.map((country) => (
                <li key={country.code}>
                  <button
                    type="button"
                    className="t-footnote"
                    style={optionStyle}
                    data-testid={`discover-option-${country.code}`}
                    onClick={() => {
                      setPicked(country);
                      setTyped("");
                    }}
                  >
                    {country.name} <span className="t-secondary">{country.code}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <button
          type="button"
          className="btn btn-primary"
          data-testid="discover-start"
          disabled={!picked || running}
          onClick={start}
        >
          {running ? "Searching…" : "Find regulations"}
        </button>
      </div>

      {failure ? (
        <p className="t-footnote mt-3" style={{ color: "var(--danger)" }} data-testid="discover-failure">
          {failure}
        </p>
      ) : null}

      {job ? <JobView job={job} /> : null}
    </section>
  );
}

function JobView({ job }: { job: DiscoveryJob }) {
  const committed = job.candidates.filter((c) => c.status === "committed").length;
  return (
    <div className="mt-4" data-testid="discover-job">
      <p className="t-footnote">
        <strong>{job.country_name}</strong>
        {job.regulator ? <> · {job.regulator}</> : null}
        {job.root_url ? <> · {job.root_url.replace(/^https?:\/\//, "")}</> : null}
        {" · "}
        <span data-testid="discover-status">{describe(job, committed)}</span>
      </p>

      {job.error ? (
        <p
          className="t-footnote mt-2"
          style={{ color: "var(--danger)" }}
          data-testid="discover-error"
        >
          {job.error}
        </p>
      ) : null}

      {job.candidates.length > 0 ? (
        <ul className="mt-3" style={{ display: "grid", gap: "0.5rem" }}>
          {job.candidates.map((candidate) => (
            <li
              key={candidate.url}
              className="t-footnote"
              data-testid={`discover-row-${candidate.status}`}
              style={{ display: "grid", gap: "0.15rem" }}
            >
              <span>
                <span
                  style={{
                    color:
                      candidate.status === "committed"
                        ? "var(--good)"
                        : candidate.status === "rejected"
                          ? "var(--danger)"
                          : "inherit",
                  }}
                >
                  {candidate.status === "committed"
                    ? "watching"
                    : candidate.status === "rejected"
                      ? "not usable"
                      : "checking"}
                </span>{" "}
                <span className="t-secondary">{candidate.url}</span>
              </span>
              {candidate.status === "committed" ? (
                <span className="t-caption t-secondary">
                  {candidate.match_count} regulation links follow the pattern{" "}
                  <code>{candidate.link_pattern}</code>
                </span>
              ) : null}
              {candidate.error ? (
                <span className="t-caption" style={{ color: "var(--danger)" }}>
                  {candidate.error}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Plain words for the state, including the states that found nothing. */
function describe(job: DiscoveryJob, committed: number): string {
  switch (job.status) {
    case "queued":
      return "queued";
    case "proposing":
      return "looking up the regulator";
    case "reading":
      return "reading the regulator's site";
    case "done":
      return `${committed} address${committed === 1 ? "" : "es"} now watched`;
    case "partial":
      return `${committed} of ${job.candidates.length} usable`;
    case "failed":
      return "nothing usable found";
    default:
      return job.status;
  }
}

const listStyle: React.CSSProperties = {
  position: "absolute",
  zIndex: 20,
  insetInlineStart: 0,
  insetBlockStart: "calc(100% + 0.25rem)",
  width: "100%",
  padding: "0.25rem",
  display: "grid",
  gap: "0.1rem",
  maxHeight: "14rem",
  overflowY: "auto",
};

const optionStyle: React.CSSProperties = {
  width: "100%",
  textAlign: "start",
  padding: "0.35rem 0.5rem",
  background: "none",
  border: "none",
  cursor: "pointer",
  borderRadius: "0.375rem",
};
