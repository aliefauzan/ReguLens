"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ensureMarket,
  listCountries,
  listMarkets,
  listSources,
  type Country,
  type Market,
} from "@/lib/api";
import { jurisdictionShortName, marketName } from "../_ui/status";

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
 * away. Picking one from the dropdown creates its market first (`ensureMarket`)
 * and only then ticks it, because `impact.evaluate` keeps only target markets
 * that have a document: a product pointed at a market that does not exist loses
 * that country with no verdict and no error, which is the failure this whole
 * file exists to avoid.
 *
 * A country with no watched source says so on its tile. Its verdict will read
 * "No rules added yet" until somebody watches it, and promising otherwise here
 * would be the same lie as a monitor that reports nothing when it is broken.
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
  const [watchedJurisdictions, setWatchedJurisdictions] = useState<Set<string> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

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
      .then((body) => setCountries(body.countries))
      .catch(() => undefined);
    listSources()
      .then((body) =>
        setWatchedJurisdictions(
          new Set(body.sources.filter((s) => s.enabled).map((s) => s.jurisdiction.toUpperCase())),
        ),
      )
      .catch(() => undefined);
  }, []);

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
    } catch {
      setAddError("That country could not be added. Nothing changed.");
    } finally {
      setAdding(false);
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
                <span className="t-footnote t-secondary" data-testid={`market-sub-${tile.id}`}>
                  {regimeLine(market)}
                  {watched === false ? (
                    <>
                      {" · "}
                      <span style={{ color: "var(--warn)" }}>not watched yet</span>
                    </>
                  ) : null}
                </span>
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
            Adding a country here does not fetch its rules. Until one of its regulations has been
            read, its verdict says so.{" "}
            <Link href="/sources" className="underline">
              Watch a country
            </Link>
            .
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

/** "European Union rules", "BPOM rules", "National rules". */
function regimeLine(market: Market | null): string {
  const regimes = (market?.jurisdictions ?? []).map(jurisdictionShortName).filter(Boolean);
  if (regimes.length === 0) return "National rules";
  return `${regimes.join(", ")} rules`;
}
