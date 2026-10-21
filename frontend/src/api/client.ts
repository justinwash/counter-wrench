import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

// Typed against the API's OpenAPI schema (`make api-types`): a route or model change that the
// UI doesn't follow fails the build instead of failing in the browser.
// Same origin as the page: the Vite dev proxy in development, FastAPI itself in Docker.
// `fetch` is looked up per call, not captured at import, so tests can stub it.
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  fetch: (request) => globalThis.fetch(request),
});

export type ComplaintOption = components["schemas"]["ComplaintOption"];
export type BikeCandidate = components["schemas"]["BikeCandidate"];
export type IntakeForm = components["schemas"]["IntakeForm"];
export type OrderDetail = components["schemas"]["OrderDetail"];
export type Rating = components["schemas"]["Rating"];
export type OrderLine = components["schemas"]["OrderLine"];
export type OrderSummary = components["schemas"]["OrderSummary"];
export type LaborOption = components["schemas"]["LaborOption"];
export type PartFit = components["schemas"]["PartFit"];
