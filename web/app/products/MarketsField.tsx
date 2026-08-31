"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  discoverCountry,
  discoveryEventsUrl,
  ensureMarket,
  listCountries,
  listMarkets,
  listSources,
  type Country,
  type DiscoveryJob,
  type Market,
} from "@/lib/api";
import { JURISDICTION_SHORT_NAMES, jurisdictionShortName, marketName } from "../_ui/status";

/**
 * Which countries this product is sold into.
 *
 * The form used to name Germany and Indonesia in the source. That was wrong in
 * both directions: a country discovered on the Sources page could never be
 * picked here, and a user selling into a third country was told, by omission,
 * that ReguLens has no opinion about it.
 *
 * So the tiles are the markets that exist — the two we seed plus every country
 * anybody has started watching — and every remaining country is one dropdown
 * away. Picking one does two things, in this order:
 *
 * 1. Creates its market. `impact.evaluate` keeps only target markets that have
 *    a document, so a product pointed at a market that does not exist loses
 *    that country with no verdict and no error.
 * 2. Starts watching it — the same discovery run the Sources page offers, from
 *    here, so a country is not selected before anything is being read for it.
 *    A country is only worth naming as a market if something is looking at its
 *    regulations.
 *
 * Discovery finds a usable catalogue for roughly one country in three, and the
 * tile says which happened. A country whose regulator could not be found stays
 * selectable and reads "not watched yet": the product still records where it is
 * sold, and the verdict for that market says "No rules added yet" rather than
 * implying a check that never ran.
 */
export default function MarketsField({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [markets, setMarkets] = useState<Market[] | null>(null);
  const [countries, setCountries] = useState<Country[]>([]);
  const [discoveryAvailable, setDiscoveryAvailable] = useState(false);
  const [watchedJurisdictions, setWatchedJurisdictions] = useState<Set<string> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  /** The watch attempt for each market, while it runs and after it ends. */
  const [jobs, setJobs] = useState<Record<string, DiscoveryJob>>({});
  const streams = useRef<Record<string, EventSource>>({});

  useEffect(() => {
    listMarkets()
      .then((body) => setMarkets(body.markets))
      .catch(() =>
        setLoadError(
          "We could not load the list of countries. The tiles below are the ones this product already names.",
        ),
      );
    // Additive: without these two the tiles still work, they just cannot say
    // which countries are being watched or offer the rest.
    listCountries()
      .then((body) => {
        setCountries(body.countries);
        setDiscoveryAvailable(body.available);
      })
      .catch(() => undefined);
    refreshWatched();
    const open = streams.current;
    return () => Object.values(open).forEach((stream) => stream.close());
  }, []);

  function refreshWatched() {
    return listSources()
      .then((body) =>
        setWatchedJurisdictions(
          new Set(body.sources.filter((s) => s.enabled).map((s) => s.jurisdiction.toUpperCase())),
        ),
      )
      .catch(() => undefined);
  }

  /**
   * Every tile: the markets that exist, plus any this product already names.
   *
   * The second half matters when editing. A target market whose document is
   * gone would otherwise vanish from the form, and saving would then quietly
   * drop a country the user never unticked.
   */
  const tiles: (Market | { id: string })[] = useMemo(() => {
    const known = markets ?? [];
    const ids = new Set(known.map((m) => m.id));
    return [...known, ...value.filter((id) => !ids.has(id)).map((id) => ({ id }))];
  }, [markets, value]);

  const takenCodes = useMemo(
    () => new Set((markets ?? []).map((m) => m.country_code?.toUpperCase()).filter(Boolean)),
    [markets],
  );

  const addable = useMemo(
    () => countries.filter((country) => !takenCodes.has(country.code.toUpperCase())),
    [countries, takenCodes],
  );

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((m) => m !== id) : [...value, id]);
  }

  async function add(code: string) {
    if (!code) return;
    setAdding(true);
    setAddError(null);
    try {
      const { market } = await ensureMarket(code);
      setMarkets((current) => {
        const rest = (current ?? []).filter((m) => m.id !== market.id);
        return [...rest, market].sort((a, b) => a.id.localeCompare(b.id));
      });
      if (!value.includes(market.id)) onChange([...value, market.id]);
      if (discoveryAvailable) startWatching(market.id, code);
    } catch {
      setAddError("That country could not be added. Nothing changed.");
    } finally {
      setAdding(false);
    }
  }

  /**
   * Go and find where this country publishes its regulations.
   *
   * The same run the Sources page starts, watched through the same stream. The
   * market already exists by the time this is called, so a failure here costs
   * the user nothing they selected — it only means nothing is being read yet,
   * which the tile then says.
   */
  async function startWatching(marketId: string, code: string) {
    try {
      const started = await discoverCountry(code);
      setJobs((current) => ({ ...current, [marketId]: started.job }));
      streams.current[marketId]?.close();
      const stream = new EventSource(discoveryEventsUrl(started.job_id));
      streams.current[marketId] = stream;
      stream.onmessage = (event) => {
        const next = JSON.parse(event.data) as DiscoveryJob;
        setJobs((current) => ({ ...current, [marketId]: next }));
        if (["done", "partial"].includes(next.status)) {
          // A source landed, so this market is watched now. Both lists move.
          refreshWatched();
          listMarkets()
            .then((body) => setMarkets(body.markets))
            .catch(() => undefined);
        }
        if (["done", "partial", "failed"].includes(next.status)) stream.close();
      };
      // The run continues on the worker whether or not this page is listening,
      // so a dropped stream is not a failed search. The tile keeps its last
      // known state instead of claiming the search died.
      stream.onerror = () => stream.close();
    } catch {
      setJobs((current) => ({
        ...current,
        [marketId]: {
          country_code: code,
          country_name: code,
          status: "failed",
          regulator: null,
          root_url: null,
          candidates: [],
          error: "The search could not be started.",
          model: "",
          trace_id: null,
        },
      }));
    }
  }

  return (
    <fieldset className="card p-6" data-testid="field-markets">
      <legend className="t-headline float-left w-full">Where do you want to sell it?</legend>
      <p className="help clear-both">Pick every country you sell into, or plan to.</p>

      {markets === null && !loadError ? (
        <p className="t-footnote t-secondary mt-4" data-testid="markets-loading">
          Loading countries…
        </p>
      ) : null}

      {loadError ? (
        <p className="t-footnote mt-3" style={{ color: "var(--danger)" }} data-testid="markets-error">
          {loadError}
        </p>
      ) : null}

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {tiles.map((tile) => {
          const market = "country" in tile ? (tile as Market) : null;
          const label = market?.country || marketName(tile.id);
          const checked = value.includes(tile.id);
          const watched = isWatched(market, watchedJurisdictions);
          const job = jobs[tile.id];
          const state = tileState(job, watched);
          return (
            <label
              key={tile.id}
              className="inset flex cursor-pointer items-center gap-3 p-4"
              style={checked ? { boxShadow: "inset 0 0 0 2px var(--accent)" } : undefined}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(tile.id)}
                aria-label={`Sell in ${label}`}
                data-testid={`market-${tile.id}`}
                style={{ width: 22, height: 22, accentColor: "var(--accent)" }}
              />
              <span>
                <span className="t-subhead block" style={{ fontWeight: 600 }}>
                  {label}
                </span>
                <span
                  className="t-footnote t-secondary"
                  style={state.tone ? { color: state.tone } : undefined}
                  data-testid={`market-sub-${tile.id}`}
                >
                  {state.line ?? regimeLine(market)}
                </span>
                {job?.error && job.status === "failed" ? (
                  <span
                    className="t-caption block"
                    data-testid={`market-why-${tile.id}`}
                    style={{ color: "var(--secondary)" }}
                  >
                    {job.error}
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
      </div>

      {addable.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="t-footnote">
            <span className="label">Somewhere else?</span>
            <select
              className="field mt-1"
              value=""
              disabled={adding}
              onChange={(event) => add(event.target.value)}
              data-testid="market-add"
            >
              <option value="">{adding ? "Adding…" : "Add another country…"}</option>
              {addable.map((country) => (
                <option key={country.code} value={country.code}>
                  {country.name}
                </option>
              ))}
            </select>
          </label>
          <p className="t-caption t-secondary" style={{ maxWidth: "28rem" }}>
            {discoveryAvailable ? (
              <>
                Picking a country also starts watching it: we look up its food regulator and the
                page where it publishes. That works for roughly one country in three, and a country
                we cannot read says so — you can still sell there, and still add its address by
                hand on{" "}
                <Link href="/sources" className="underline">
                  Watching
                </Link>
                .
              </>
            ) : (
              <>
                Adding a country here does not fetch its rules. Until one of its regulations has
                been read, its verdict says so.{" "}
                <Link href="/sources" className="underline">
                  Watch a country
                </Link>
                .
              </>
            )}
          </p>
        </div>
      ) : null}

      {addError ? (
        <p className="t-footnote mt-3" style={{ color: "var(--danger)" }} data-testid="market-add-error">
          {addError}
        </p>
      ) : null}
    </fieldset>
  );
}

/**
 * Is anything being read for this market?
 *
 * `null` while the source list is still loading or could not be loaded — the
 * tile then says nothing about watching rather than guessing "not watched",
 * which would be a false accusation against a country that is fine.
 */
function isWatched(market: Market | null, watched: Set<string> | null): boolean | null {
  if (market === null || watched === null) return null;
  return (market.jurisdictions ?? []).some((j) => watched.has(String(j).toUpperCase()));
}

/**
 * What the tile says under the country's name, when that is not simply whose
 * rules apply: a search in flight, a search that found nothing, or a country
 * nobody has watched.
 */
function tileState(
  job: DiscoveryJob | undefined,
  watched: boolean | null,
): { line: string | null; tone?: string } {
  switch (job?.status) {
    case "queued":
      return { line: "Starting to watch it…" };
    case "proposing":
      return { line: "Looking up its regulator…" };
    case "reading":
      return { line: "Reading the regulator's site…" };
    case "failed":
      return { line: "Could not find where it publishes", tone: "var(--warn)" };
    default:
      break;
  }
  if (watched === false) return { line: "Not watched yet", tone: "var(--warn)" };
  return { line: null };
}

/**
 * Whose rules are read for this market: "European Union rules", "BPOM rules",
 * "MHLW rules".
 *
 * One market legitimately carries two jurisdictions for the same country, and
 * the tile must not read them out as two regimes. Indonesia ships as
 * `["ID_BPOM"]`, and discovering Indonesia appends the bare country code its
 * watched sources are registered under, giving `["ID_BPOM", "ID"]` — one
 * country, one regulator, two storage keys. Rendering both said "BPOM,
 * National rules", which describes a country with two separate rulebooks.
 * Nothing has two rulebooks here, so a named regime always wins over the bare
 * country code, and the regulator's own name is used before falling back to
 * the word "national".
 */
function regimeLine(market: Market | null): string {
  const named = (market?.jurisdictions ?? []).filter((j) => JURISDICTION_SHORT_NAMES[j]);
  if (named.length > 0) return `${named.map(jurisdictionShortName).join(", ")} rules`;
  if (market?.regulator) return `${market.regulator} rules`;
  return "National rules";
}
