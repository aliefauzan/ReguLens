// Single typed fetch client. Every call into the API goes through here so the
// base URL, error shape, and trace_id handling live in one place.

// Two different hosts can be correct at once. In docker compose the browser
// reaches the API on localhost:8080 while server components inside the web
// container must call the service by its compose name. NEXT_PUBLIC_API_URL is
// the browser's answer; API_INTERNAL_URL, when set, is the server's.
const BASE =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080");

export type Market = {
  id: string;
  jurisdiction: string;
  country: string;
  label: string;
  regulator: string;
};

export type ApiError = { status: number; message: string; traceId: string | null };

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  const traceId = response.headers.get("x-trace-id");
  if (!response.ok) {
    const error: ApiError = {
      status: response.status,
      message: await response.text(),
      traceId,
    };
    throw error;
  }
  return (await response.json()) as T;
}

export function listMarkets(): Promise<{ markets: Market[]; trace_id: string }> {
  return get("/markets");
}

export function health(): Promise<{ status: string; version: string; firestore: string }> {
  return get("/health");
}

export type Ingredient = {
  name: string;
  normalized: string | null;
  unnormalized: boolean;
  amount: number | null;
  unit: string | null;
};

export type Product = {
  id: string;
  name: string;
  product_type: string;
  origin: string;
  packaging: string | null;
  ingredients: Ingredient[];
  target_markets: string[];
  created_at: string | null;
  updated_at: string | null;
};

export type GraphEvent = {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  cause?: Record<string, unknown> | null;
  triggered_by: string;
  trace_id: string | null;
  occurred_at: string | null;
};

export function listProducts(): Promise<{ products: Product[] }> {
  return get("/products");
}

export function getProduct(id: string): Promise<{ product: Product }> {
  return get(`/products/${id}`);
}

export function getProductEvents(id: string): Promise<{ events: GraphEvent[] }> {
  return get(`/products/${id}/events`);
}

type ValidationDetail = {
  msg?: string;
  type?: string;
  loc?: (string | number)[];
  ctx?: Record<string, unknown>;
};

/** Field names as the form asks for them, not as the schema stores them. */
const FIELD_WORDS: Record<string, string> = {
  name: "the product name",
  product_type: "the kind of product",
  origin: "where it is made",
  packaging: "the packaging",
  ingredients: "the ingredient list",
  unit: "the unit",
  amount: "the amount",
  target_markets: "the countries you sell into",
  source_name: "who published it",
  jurisdiction: "which country's rules",
  text: "the pasted text",
};

const UNIT_WORDS: Record<string, string> = {
  percent_w_w: "% of weight",
  mg_per_kg: "mg per kg",
  ppm: "ppm",
};

/**
 * Server validation, in the words the form uses.
 *
 * FastAPI answers a bad field with the schema's own vocabulary — "String should
 * have at least 1 character", "Input should be 'percent_w_w', 'mg_per_kg' or
 * 'ppm'". That is a correct message written for whoever wrote the schema. The
 * person looking at it filled in a form and now has to guess which box was
 * wrong and what `percent_w_w` is.
 */
export function humanizeValidation(detail: unknown, fallback: string): string {
  if (!Array.isArray(detail)) {
    return typeof detail === "string" && detail ? detail : fallback;
  }
  const messages = (detail as ValidationDetail[]).map((item) => {
    const path = (item.loc ?? []).filter((part) => part !== "body");
    const fieldKey = [...path].reverse().find((part) => typeof part === "string") as string | undefined;
    const field = fieldKey ? (FIELD_WORDS[fieldKey] ?? fieldKey.replaceAll("_", " ")) : "one of the fields";
    const row = path.find((part) => typeof part === "number");
    const where = row === undefined ? field : `${field} on row ${(row as number) + 1}`;

    switch (item.type) {
      case "string_too_short":
      case "missing":
        return `Please fill in ${where}.`;
      case "string_too_long":
        return `${where} is too long.`;
      case "enum": {
        const allowed = String(item.ctx?.expected ?? "")
          .split(",")
          .map((raw) => raw.trim().replaceAll("'", ""))
          .map((raw) => UNIT_WORDS[raw] ?? raw.replaceAll("_", " "))
          .filter(Boolean);
        return allowed.length > 0
          ? `Pick one of these for ${where}: ${allowed.join(", ")}.`
          : `That is not a valid choice for ${where}.`;
      }
      case "greater_than":
      case "greater_than_equal":
        return `${where} has to be a positive number.`;
      case "float_parsing":
      case "int_parsing":
        return `${where} has to be a number.`;
      case "too_short":
        return `Add at least one entry to ${where}.`;
      default:
        return item.msg ? `${where}: ${item.msg}` : fallback;
    }
  });
  // Capitalised, de-duplicated, and joined into something readable as prose.
  return [...new Set(messages)].join(" ") || fallback;
}

export async function createProduct(body: unknown): Promise<Product> {
  const response = await fetch(`${BASE}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(humanizeValidation(payload?.detail, "Could not save the product."));
  }
  return payload.product as Product;
}

export type Sample = {
  id: string;
  title: string;
  summary: string;
  source_type: SourceType;
  source_name: string;
  jurisdiction: string;
  citation: string;
  text: string;
};

/** One regulation excerpt that ships with the app, ready to be read. */
export type LibraryEntry = {
  id: string;
  jurisdiction: string;
  source_type: SourceType;
  source_name: string;
  title: string;
  summary: string;
  citation: string;
  product_types: string[];
  truncated: boolean;
  starter: boolean;
};

/** The regulations we already hold. This is why nobody has to find a PDF first. */
export function listLibrary(): Promise<{ entries: LibraryEntry[]; starter_ids: string[] }> {
  return get("/library");
}

export type LibraryLoadResult = {
  id: string;
  found: boolean;
  document_id?: string;
  cached?: boolean;
  status?: string;
};

/**
 * Read the named rules, or the starter set when none are named.
 *
 * Each one goes through the ordinary upload path, so this cannot put anything
 * into the graph that an upload could not.
 */
export async function loadLibrary(
  ids?: string[],
): Promise<{ results: LibraryLoadResult[]; queued: number; already_read: number }> {
  const response = await fetch(`${BASE}/library/load`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  });
  if (!response.ok) {
    throw new Error("We could not load those rules. Check that the service is running.");
  }
  return (await response.json()) as {
    results: LibraryLoadResult[];
    queued: number;
    already_read: number;
  };
}

/** Regulation excerpts bundled with the app, for a user who has no PDF to hand. */
export function listSamples(): Promise<{ samples: Sample[] }> {
  return get("/samples");
}

/** Create the demo product and ingest one real rule for it. Safe to repeat. */
export async function seedDemo(): Promise<{
  product: Product;
  document: RegulatoryDocument;
  cached: boolean;
}> {
  const response = await fetch(`${BASE}/demo/seed`, { method: "POST" });
  if (!response.ok) {
    throw new Error("We could not load the sample data. Check that the service is running.");
  }
  return (await response.json()) as { product: Product; document: RegulatoryDocument; cached: boolean };
}

export async function updateProduct(id: string, body: unknown): Promise<Product> {
  const response = await fetch(`${BASE}/products/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(humanizeValidation(payload?.detail, "Could not save the changes."));
  }
  return payload.product as Product;
}

/** Removes the product and every requirement derived from it. Not undoable. */
export async function deleteProduct(id: string): Promise<void> {
  const response = await fetch(`${BASE}/products/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`Could not delete the product (${response.status}).`);
}

export type Substance = { canonical: string; label: string; synonyms: string[] };

export function listSubstances(): Promise<{ substances: Substance[] }> {
  return get("/substances");
}

export const PRODUCT_TYPES = [
  "food_beverage_powder",
  "food_beverage_liquid",
  "food_solid",
  "supplement",
  "cosmetic",
] as const;

export const UNITS = ["percent_w_w", "mg_per_kg", "ppm"] as const;

// ---- Documents (phase 2) ----

export type SourceType =
  | "official_regulation"
  | "official_guidance"
  | "industry_association"
  | "news_article"
  | "social_chat";

export type StageLogEntry = {
  stage: string;
  ok: boolean;
  at: string | null;
  detail?: Record<string, unknown> | null;
};

export type RegulatoryDocument = {
  id: string;
  filename: string | null;
  source_type: SourceType;
  source_name: string;
  jurisdiction: string;
  declared_effective_date: string | null;
  content_sha256: string;
  page_count: number | null;
  char_count: number;
  parse_quality: number | null;
  status: string;
  stage_log: StageLogEntry[];
  error: string | null;
  failed_stage: string | null;
  // What the document said about itself at upload, and which fields the user
  // typed in rather than letting us read.
  detection: Detection | null;
  declared_fields: string[];
  /** upload | library | demo | watched_source — where the document came from. */
  origin?: string;
  trace_id: string | null;
  uploaded_at: string | null;
};

export type Clause = {
  id: string;
  document_id: string;
  jurisdiction?: string | null;
  text: string;
  clause_type: string;
  substance: string | null;
  substance_normalized: string | null;
  unnormalized_substance: boolean;
  limit_value: number | null;
  unit_raw: string | null;
  product_type: string | null;
  effective_date: string | null;
  confidence: number;
  confidence_breakdown?: Record<string, number>;
  needs_review: boolean;
  review_reasons: string[];
  // The queue writes a single reason; the extractor writes the list. Both are
  // read, because a clause carrying neither tells the reader nothing.
  review_reason?: string | null;
  unnormalized_unit: boolean;
  status: string;
};

/** One answer read off a document, with the phrase it was read from. */
export type Guess<T = string> = {
  value: T | null;
  confidence: number;
  evidence: string | null;
};

/**
 * What the document says about itself.
 *
 * `needs_confirmation` is the only field the form has to branch on: it is true
 * when the country or the kind of source could not be read, and those two
 * decide which market a rule lands in and how much it is allowed to change.
 */
export type Detection = {
  jurisdiction: Guess;
  source_type: Guess<SourceType>;
  source_name: Guess;
  effective_date: Guess;
  needs_confirmation: boolean;
};

/** Read a document without storing it. Nothing is created until the user submits. */
export async function detectDocument(
  form: FormData,
): Promise<{ detection: Detection; page_count: number | null; filename: string | null }> {
  const response = await fetch(`${BASE}/documents/detect`, { method: "POST", body: form });
  if (!response.ok) {
    let message =
      response.status === 413
        ? "That file is too big. Try a shorter excerpt, or paste just the part that matters."
        : "We could not read that document. Check the file, then try again.";
    try {
      const payload = await response.json();
      if (payload?.detail) message = humanizeValidation(payload.detail, message);
    } catch {
      // keep the plain message
    }
    throw new Error(message);
  }
  return (await response.json()) as {
    detection: Detection;
    page_count: number | null;
    filename: string | null;
  };
}

export async function uploadDocument(form: FormData): Promise<{ document: RegulatoryDocument; cached: boolean }> {
  const response = await fetch(`${BASE}/documents`, { method: "POST", body: form });
  const traceId = response.headers.get("x-trace-id");
  if (!response.ok) {
    let message =
      response.status === 413
        ? "That file is too big. Try a shorter excerpt, or paste just the part that matters."
        : "The upload did not go through. Check the file, then try again.";
    try {
      const payload = await response.json();
      if (payload?.detail) message = humanizeValidation(payload.detail, message);
    } catch {
      // keep the plain message
    }
    throw new Error(message);
  }
  void traceId;
  return (await response.json()) as { document: RegulatoryDocument; cached: boolean };
}

/** Where one clause sits inside the document it was read from. */
export type SourceCitation = {
  clause_id: string;
  start: number;
  end: number;
  match: "exact" | "approximate" | "not_found";
};

export type DocumentText = {
  document_id: string;
  text: string;
  source: "pasted" | "extracted";
  truncated: boolean;
  available: boolean;
  citations: SourceCitation[];
};

/** The document's own words, with each clause located inside them. */
export function getDocumentText(id: string): Promise<DocumentText> {
  return get(`/documents/${id}/text`);
}

/** What we think an ingredient name means, and what we will do about it. */
export type SubstanceResolution = {
  query: string;
  recognised: boolean;
  canonical: string | null;
  label: string | null;
  kind: "additive" | "food" | "function" | "unknown";
  message: string;
  suggestions: { canonical: string; label: string; why: string }[];
};

export function resolveSubstance(query: string): Promise<SubstanceResolution> {
  return get(`/substances/resolve?q=${encodeURIComponent(query)}`);
}

export function listDocuments(): Promise<{ documents: RegulatoryDocument[] }> {
  return get("/documents");
}

export function getDocument(
  id: string,
): Promise<{ document: RegulatoryDocument; clauses: Clause[] }> {
  return get(`/documents/${id}`);
}

export async function retryDocument(id: string): Promise<void> {
  const response = await fetch(`${BASE}/documents/${id}/retry`, { method: "POST" });
  if (!response.ok) throw new Error(`Retry failed (${response.status}).`);
}

// ---- Compliance, alerts, query (phases 4-5) ----

export type ComplianceRequirement = {
  id: string;
  market_id: string;
  clause_id: string;
  // The document the clause was read from, so a verdict can be traced back to
  // a source a person recognises rather than to an id.
  document_id?: string | null;
  jurisdiction?: string | null;
  requirement_type?: string | null;
  substance_normalized: string | null;
  limit_value: number | null;
  unit: string | null;
  product_value: number | null;
  product_unit?: string | null;
  // Both sides converted to one unit — the comparison that was actually made.
  comparable_value?: number | null;
  comparable_limit?: number | null;
  comparable_unit?: string | null;
  evaluation: string;
  severity: string;
  reason: string | null;
  // The day this rule starts. Null means it is already in force, which is what
  // every clause read before this field existed looks like.
  effective_date?: string | null;
};

export type ComplianceView = {
  // What is true today. Rules that enter into force later are not counted.
  statuses: Record<string, string>;
  // Per market, the next date that answer changes and what it changes to.
  // Absent for a market whose future rules do not move the verdict.
  upcoming: Record<
    string,
    // `clause_id` / `document_id` name the rule that sets the date, so the page
    // can link to the passage instead of asserting a deadline unsupported.
    { effective_date: string; status: string; clause_id?: string | null; document_id?: string | null }
  >;
  // One recipe, several markets: the lowest limit still in force is the only
  // number a product can actually be built to. Null when the caller narrowed to
  // one market, where the question does not arise.
  binding_limits: BindingLimits | null;
  requirements: ComplianceRequirement[];
  issue_counts: { total: number; critical: number };
};

export type BindingSubstance = {
  substance_normalized: string;
  binding_limit: number;
  unit: string;
  binding_market_id: string;
  binding_market_label: string | null;
  binding_jurisdiction: string | null;
  binding_clause_id: string | null;
  binding_document_id: string | null;
  product_value: number | null;
  verdict: "pass" | "fail" | "unknown";
  limits_by_market: {
    market_id: string;
    market_label: string | null;
    limit: number;
    clause_id: string | null;
  }[];
  markets_without_a_rule: string[];
  uncomparable_rules: number;
};

export type BindingLimits = {
  substances: BindingSubstance[];
  markets: string[];
  skipped: { uncomparable_rules: number; substances_affected: string[] };
};

export type SimulationResult = {
  statuses: Record<string, string>;
  requirements: ComplianceRequirement[];
  binding_limits: BindingLimits;
  simulated: true;
};

/** What-if. Writes nothing — safe to call as often as a form changes. */
export function simulate(body: {
  name: string;
  product_type: string;
  origin: string;
  packaging?: string | null;
  ingredients: { name: string; amount?: number | null; unit?: string | null }[];
  target_markets: string[];
}): Promise<SimulationResult> {
  return post("/simulate", body);
}

/** The pack somebody hands an auditor. */
export function evidenceUrl(productId: string): string {
  return `${BASE}/products/${productId}/evidence`;
}

export function getCompliance(id: string): Promise<ComplianceView> {
  return get(`/products/${id}/compliance`);
}

/** One market's binding limit for a substance, with the words behind it. */
export type RemediationLimit = {
  market_id: string;
  limit: number;
  unit: string;
  clause_id: string;
  document_id: string | null;
  effective_date: string | null;
  quote: string | null;
  citation_href: string | null;
  /** Looser rows for the same substance in the same market. Counted, not hidden. */
  other_limits_in_market: number;
  is_strictest: boolean;
};

export type RemediationTarget = {
  substance: string;
  substance_label: string;
  target_value: number | null;
  target_unit: string | null;
  /** Filled exactly when there is no target. The API refuses to send one without the other. */
  no_target_reason: string | null;
  no_target_reason_text: string;
  coverage: "full" | "partial";
  markets_without_rules: string[];
  strictest_market_id: string | null;
  current_value: number | null;
  current_unit: string | null;
  raw_value: number | null;
  raw_unit: string | null;
  verdict_today: string;
  limits: RemediationLimit[];
};

export type RemediationNotChecked = {
  ingredient: string;
  reason_code: string;
  reason_text: string;
};

/** A draft fix plan. Read-only: asking for it changes nothing. */
export type RemediationPlan = {
  product_id: string;
  product_name: string;
  generated_for_markets: string[];
  targets: RemediationTarget[];
  not_checked: RemediationNotChecked[];
  trace_id: string | null;
};

export function getRemediation(id: string): Promise<RemediationPlan> {
  return get(`/products/${id}/remediation`);
}

/**
 * Why an alert happened, resolved from stored records by the API.
 *
 * `unprompted` is the field the whole feature exists for: true means the
 * regulation reached the graph without anybody uploading it. `cause_available`
 * is false when the causing document has since been deleted — the alert then
 * says the cause is no longer on file rather than showing a plausible guess.
 */
export type AlertContext = {
  product_id?: string;
  product_name?: string | null;
  market_id?: string | null;
  market_label?: string | null;
  market_country?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  document_id?: string | null;
  clause_id?: string | null;
  unprompted: boolean;
  origin?: string | null;
  cause_available: boolean;
  source_name?: string | null;
  jurisdiction?: string | null;
  source_type?: string | null;
  substance?: string | null;
  limit_value?: number | null;
  limit_unit?: string | null;
  clause_text?: string | null;
  // Set on an alert about a verdict that changes on a date nobody has reached
  // yet. `effective_date` is the day it starts.
  scheduled?: boolean;
  effective_date?: string | null;
};

export function getAlerts(): Promise<{ alerts: (GraphEvent & { context: AlertContext })[] }> {
  return get("/alerts");
}

export async function ackAlert(id: string): Promise<void> {
  const response = await fetch(`${BASE}/alerts/${id}/ack`, { method: "POST" });
  if (!response.ok) throw new Error(`Ack failed (${response.status}).`);
}

export type QueryResult = {
  intent: string;
  answer: string;
  cited_clauses: {
    id: string;
    text?: string;
    jurisdiction?: string;
    confidence?: number;
    document_id?: string;
  }[];
  confidence: number | null;
  latency_ms: number;
  refusal: boolean;
};

export function ask(question: string, productId?: string): Promise<QueryResult> {
  return post("/query", { question, product_id: productId ?? null });
}

/**
 * Fired after anything that changes the numbers on the navigation bar.
 *
 * The badges re-read on navigation, but accepting or ignoring a clause happens
 * without leaving the page, and a count that still says 2 after you cleared one
 * is worse than no count.
 */
/**
 * A regulator address ReguLens re-reads on a schedule.
 *
 * `document` is one regulation whose wording can change under us; `feed` is a
 * list where a change means a new entry appeared. `last_status` is rendered
 * rather than hidden, because a source that has been erroring for a week means
 * "we are not watching that", and this is the only place to find that out.
 */
export type WatchedSource = {
  id: string;
  url: string;
  label: string;
  kind: "document" | "feed" | "listing" | "sparql";
  source_type: SourceType;
  jurisdiction: string;
  check_interval_hours: number;
  link_pattern: string | null;
  sparql_query: string | null;
  enabled: boolean;
  last_status: "never_checked" | "unchanged" | "changed" | "baselined" | "busy" | "error";
  last_error: string | null;
  last_checked_at: string | null;
  last_changed_at: string | null;
  document_ids: string[];
  checks: number;
  changes: number;
};

export type SourceCheckResult = {
  source_id: string;
  url?: string;
  label?: string;
  status: string;
  reason?: string;
  error?: string;
  first_read?: boolean;
  new_entries?: number;
  ingested?: { document_id: string; cached: boolean; source_name: string; chars: number }[];
  failed?: { title: string; link: string; error: string }[];
};

/**
 * What ReguLens did without being asked. Every figure is a query over stored
 * records, so a number here can be clicked through to the thing it counts —
 * and a quiet week reports zeros rather than something flattering.
 */
export type Autonomy = {
  watched_sources: number;
  enabled_sources: number;
  failing_sources: number;
  checks_run: number;
  last_checked_at: string | null;
  regulations_found: number;
  clauses_read: number;
  verdicts_changed: number;
  documents: string[];
};

export function getAutonomy(): Promise<Autonomy> {
  return get("/stats/autonomy");
}

export function listSources(): Promise<{
  sources: WatchedSource[];
  default_interval_hours: number;
}> {
  return get("/sources");
}

export async function addSource(body: {
  url: string;
  label: string;
  kind: "document" | "feed" | "listing" | "sparql";
  source_type: SourceType;
  jurisdiction: string;
  link_pattern?: string | null;
  sparql_query?: string | null;
}): Promise<{ source: WatchedSource; created: boolean }> {
  const response = await fetch(`${BASE}/sources`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      humanizeValidation(payload?.detail, "We could not start watching that address."),
    );
  }
  return payload as { source: WatchedSource; created: boolean };
}

export async function seedSources(): Promise<{ sources: { id: string; created: boolean }[] }> {
  const response = await fetch(`${BASE}/sources/seed`, { method: "POST" });
  if (!response.ok) throw new Error("We could not install the built-in watch list.");
  return (await response.json()) as { sources: { id: string; created: boolean }[] };
}

export async function setSourceEnabled(id: string, enabled: boolean): Promise<WatchedSource> {
  const response = await fetch(`${BASE}/sources/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) throw new Error("We could not change that source.");
  return ((await response.json()) as { source: WatchedSource }).source;
}

export async function deleteSource(id: string): Promise<void> {
  const response = await fetch(`${BASE}/sources/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("We could not stop watching that address.");
}

/**
 * Read one source now, ignoring its interval.
 *
 * Synchronous: one HTTP fetch and a hash comparison. Anything slow that follows
 * — extraction, reconciliation, impact — is already behind Pub/Sub, exactly as
 * it is for an upload.
 */
export async function checkSource(id: string): Promise<SourceCheckResult> {
  const response = await fetch(`${BASE}/sources/${id}/check`, { method: "POST" });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? "We could not read that address just now.");
  }
  return payload as SourceCheckResult;
}

export const COUNTS_CHANGED = "regulens:counts-changed";

function announceCountsChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(COUNTS_CHANGED));
}

/** Reject a clause in the review queue. It is parked, not deleted. */
export async function dismissClause(id: string): Promise<void> {
  const response = await fetch(`${BASE}/clauses/${id}/dismiss`, { method: "POST" });
  if (!response.ok) throw new Error(`Dismiss failed (${response.status}).`);
  announceCountsChanged();
}

export async function confirmClause(id: string): Promise<void> {
  const response = await fetch(`${BASE}/clauses/${id}/confirm`, { method: "POST" });
  if (!response.ok) throw new Error(`Confirm failed (${response.status}).`);
  announceCountsChanged();
}

async function post(path: string, body: unknown): Promise<any> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as any;
}

export type Conflict = {
  id: string;
  clause_a: string;
  clause_b: string;
  type: string;
  detail: Record<string, number | string | null>;
  severity: string;
  status: string;
};

export function listConflicts(): Promise<{ conflicts: Conflict[] }> {
  return get("/conflicts");
}

/**
 * `relevantOnly` narrows the list to rules that could bear on something this
 * workspace actually makes. It never deletes and never downgrades — relevance
 * is recomputed on every read, so a rule held back today applies to a product
 * added tomorrow. `hidden` and `hidden_reasons` always come back, because a
 * list that quietly drops a hundred and forty rules is worse than a long one.
 */
export function listClauses(params: {
  status?: string;
  relevantOnly?: boolean;
}): Promise<{ clauses: Clause[]; hidden: number; hidden_reasons: Record<string, number> }> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.relevantOnly) search.set("relevant_only", "true");
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return get(`/clauses${suffix}`);
}

// ---------------------------------------------------------------------------
// Country discovery
// ---------------------------------------------------------------------------

export type Country = { code: string; name: string };

export type DiscoveryCandidate = {
  url: string;
  label: string;
  reason: string;
  status: "validating" | "committed" | "rejected";
  source_id: string | null;
  link_pattern: string | null;
  match_count: number;
  error: string | null;
};

export type DiscoveryJob = {
  id?: string;
  country_code: string;
  country_name: string;
  status: "queued" | "proposing" | "reading" | "done" | "partial" | "failed";
  regulator: string | null;
  root_url: string | null;
  candidates: DiscoveryCandidate[];
  committed?: number;
  error: string | null;
  model: string;
  trace_id: string | null;
};

export function listCountries(): Promise<{
  countries: Country[];
  available: boolean;
  model: string;
}> {
  return get("/countries");
}

export function discoverCountry(
  code: string,
): Promise<{ job_id: string; job: DiscoveryJob; joined: boolean }> {
  return post("/countries/discover", { country_code: code });
}

export function getDiscoveryJob(jobId: string): Promise<{ job: DiscoveryJob }> {
  return get(`/discovery/${jobId}`);
}

/** The URL an `EventSource` opens. Not fetched here — the browser owns the stream. */
export function discoveryEventsUrl(jobId: string): string {
  return `${BASE}/discovery/${jobId}/events`;
}
