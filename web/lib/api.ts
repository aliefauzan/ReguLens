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
