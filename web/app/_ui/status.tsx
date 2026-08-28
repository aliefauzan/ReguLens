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

// Market ids are storage keys. Nobody outside the codebase should see them.
export const MARKET_NAMES: Record<string, string> = {
  market_de: "Germany (European Union)",
  market_id: "Indonesia (BPOM)",
};

export function marketName(id: string): string {
  return MARKET_NAMES[id] ?? id.replace("market_", "").toUpperCase();
}

export const JURISDICTION_NAMES: Record<string, string> = {
  EU: "European Union",
  ID_BPOM: "Indonesia (BPOM)",
};

export function jurisdictionName(code: string | null | undefined): string {
  if (!code) return "—";
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
};

export function plain(value: string | null | undefined): string {
  if (!value) return "—";
  return PLAIN[value] ?? value.replaceAll("_", " ");
}
