// Single typed fetch client. Every call into the API goes through here so the
// base URL, error shape, and trace_id handling live in one place.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

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

export async function createProduct(body: unknown): Promise<Product> {
  const response = await fetch(`${BASE}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(
      Array.isArray(payload?.detail)
        ? payload.detail.map((d: { msg: string }) => d.msg).join("; ")
        : (payload?.detail ?? "Could not create the product."),
    );
  }
  return payload.product as Product;
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
  trace_id: string | null;
  uploaded_at: string | null;
};

export type Clause = {
  id: string;
  document_id: string;
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
  unnormalized_unit: boolean;
  status: string;
};

export async function uploadDocument(form: FormData): Promise<{ document: RegulatoryDocument; cached: boolean }> {
  const response = await fetch(`${BASE}/documents`, { method: "POST", body: form });
  const traceId = response.headers.get("x-trace-id");
  if (!response.ok) {
    let message = `Upload failed (${response.status}).`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") message = payload.detail;
    } catch {
      // keep default message
    }
    throw new Error(message);
  }
  void traceId;
  return (await response.json()) as { document: RegulatoryDocument; cached: boolean };
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
  substance_normalized: string | null;
  limit_value: number | null;
  unit: string | null;
  product_value: number | null;
  evaluation: string;
  severity: string;
  reason: string | null;
};

export type ComplianceView = {
  statuses: Record<string, string>;
  requirements: ComplianceRequirement[];
  issue_counts: { total: number; critical: number };
};

export function getCompliance(id: string): Promise<ComplianceView> {
  return get(`/products/${id}/compliance`);
}

export function getAlerts(): Promise<{ alerts: GraphEvent[] }> {
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

export async function confirmClause(id: string): Promise<void> {
  const response = await fetch(`${BASE}/clauses/${id}/confirm`, { method: "POST" });
  if (!response.ok) throw new Error(`Confirm failed (${response.status}).`);
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

export function listClauses(params: { status?: string }): Promise<{ clauses: Clause[] }> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return get(`/clauses${suffix}`);
}
