// One place decides what a machine status means in plain words. A first-time
// user should never have to learn the vocabulary of the data model, and two
// pages must never describe the same status differently.

export type StatusTone = "good" | "warn" | "danger" | "muted";

export type StatusCopy = {
  label: string;   // what it is, in words a non-specialist reads correctly
  meaning: string; // one sentence: what it means for them
  tone: StatusTone;
  glyph: string;
};

export const PRODUCT_STATUS: Record<string, StatusCopy> = {
  compliant: {
    label: "Meets the rules",
    meaning: "Everything we have checked for this market passes.",
    tone: "good",
    glyph: "✓",
  },
  non_compliant: {
    label: "Breaks a rule",
    meaning: "At least one ingredient is over a legal limit in this market.",
    tone: "danger",
    glyph: "!",
  },
  attention_required: {
    label: "Needs a look",
    meaning: "Something could not be checked automatically. A person should read it.",
    tone: "warn",
    glyph: "?",
  },
  unknown: {
    label: "No rules added yet",
    meaning: "We have not read any regulation for this market, so we cannot say.",
    tone: "muted",
    glyph: "–",
  },
};

export function statusCopy(status: string | undefined): StatusCopy {
  return PRODUCT_STATUS[status ?? "unknown"] ?? PRODUCT_STATUS.unknown;
}

export function StatusBadge({ status, testId }: { status: string; testId?: string }) {
  const copy = statusCopy(status);
  return (
    <span
      className={`badge badge-${copy.tone}`}
      title={copy.meaning}
      data-testid={testId ?? `status-${status}`}
    >
      <span aria-hidden="true">{copy.glyph}</span>
      {copy.label}
    </span>
  );
}

// A date somebody reads out loud, not an ISO string. Rendered in UTC on
// purpose: an effective date is a legal fact about a calendar day, and shifting
// it into the reader's timezone can move it by one.
export function readableDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const parsed = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

// Market ids are storage keys. Nobody outside the codebase should see them.
export const MARKET_NAMES: Record<string, string> = {
  market_de: "Germany (European Union)",
  market_id: "Indonesia (BPOM)",
};

// A market id is `market_<iso country code>`. Seeded markets name their
// regulator too; a market added from the product form or found by discovery
// has no entry here, and "FR" is not a country a reader recognises at a
// glance. Intl knows every code the country list can produce.
function countryFromMarketId(id: string): string | null {
  const code = id.replace("market_", "").toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return null;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export function marketName(id: string): string {
  return MARKET_NAMES[id] ?? countryFromMarketId(id) ?? id.replace("market_", "").toUpperCase();
}

// The country on its own, for tables where the regulator's name costs a column
// and adds nothing: two markets are told apart by country, not by regulator.
// The full name stays one hover — and one click — away.
export const MARKET_SHORT_NAMES: Record<string, string> = {
  market_de: "Germany",
  market_id: "Indonesia",
};

export function marketShortName(id: string): string {
  return MARKET_SHORT_NAMES[id] ?? countryFromMarketId(id) ?? marketName(id);
}

export const JURISDICTION_NAMES: Record<string, string> = {
  EU: "European Union",
  ID_BPOM: "Indonesia (BPOM)",
};

export function jurisdictionName(code: string | null | undefined): string {
  if (!code) return "—";
  return JURISDICTION_NAMES[code] ?? code;
}

// The regime, said next to the country's own name, where repeating the country
// would be noise: "Indonesia — Indonesia (BPOM) rules". Discovery registers a
// source under the plain country code, and there is nothing to name in that
// case beyond "national".
export const JURISDICTION_SHORT_NAMES: Record<string, string> = {
  EU: "European Union",
  ID_BPOM: "BPOM",
};

export function jurisdictionShortName(code: string): string {
  if (JURISDICTION_SHORT_NAMES[code]) return JURISDICTION_SHORT_NAMES[code];
  if (/^[A-Z]{2}$/.test(code)) return "National";
  return JURISDICTION_NAMES[code] ?? code;
}

// ISO country codes are correct and unreadable. Show the name.
export const COUNTRY_NAMES: Record<string, string> = {
  ID: "Indonesia",
  DE: "Germany",
  MY: "Malaysia",
  SG: "Singapore",
  TH: "Thailand",
  VN: "Vietnam",
  FR: "France",
  NL: "Netherlands",
};

export function countryName(code: string | null | undefined): string {
  if (!code) return "—";
  return COUNTRY_NAMES[code] ?? code;
}

// Machine words that leak into the UI, translated once.
export const PLAIN: Record<string, string> = {
  food_beverage_powder: "Drink powder",
  food_beverage_liquid: "Drink (liquid)",
  food_solid: "Solid food",
  supplement: "Supplement",
  cosmetic: "Cosmetic",
  cross_jurisdiction_limit_mismatch: "Two countries allow different amounts",
  same_jurisdiction_limit_mismatch: "Two rules in one country disagree",
  numeric_limit: "Maximum allowed amount",
  labeling: "Labelling requirement",
  prohibition: "Banned substance",
  percent_w_w: "% of weight",
  mg_per_kg: "mg per kg",
  ppm: "ppm",
  uploaded: "Received",
  extracting: "Reading the document",
  extracted: "Rules found",
  reconciling: "Comparing with what we know",
  reconciled: "Done",
  failed: "Could not be read",
  needs_review: "Waiting for a person",
  active: "In use",
  superseded: "Replaced by a newer rule",
  conflicted: "Disagrees with another rule",
  dismissed: "Ignored by you",
  pending_reconciliation: "Still being sorted",
  product_amount_unknown: "We do not know how much your product contains",
  unit_unconvertible: "The units do not convert",
  non_numeric_clause: "This rule has no number in it",
  clause_unit_unreadable: "We could not read the unit this limit is written in",
  no_maximum: "This rule sets no upper limit",
  prohibited: "This rule forbids the ingredient outright",
  conditional_permission: "This rule only applies in a case we cannot check for you",
  clause_confidence_below_0_5: "We are not sure we read this rule correctly",
};

export function plain(value: string | null | undefined): string {
  if (!value) return "—";
  return PLAIN[value] ?? value.replaceAll("_", " ");
}
