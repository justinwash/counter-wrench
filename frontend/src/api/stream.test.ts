import { describe, expect, it } from "vitest";
import { parseEvents } from "./stream";

const block = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

describe("parseEvents", () => {
  it("returns complete events and keeps a partial one for the next chunk", () => {
    const text = block("bike", { bike_id: "x" }) + "event: row\ndata: {\"row_";
    const { events, rest } = parseEvents(text);
    expect(events.map((e) => e.event)).toEqual(["bike"]);
    const next = parseEvents(rest + 'id": "r1"}\n\n');
    expect(next.events).toEqual([{ event: "row", data: { row_id: "r1" } }]);
    expect(next.rest).toBe("");
  });

  it("handles rows arriving out of order and CRLF line endings", () => {
    const text = (block("row", { row_id: "r2" }) + block("row", { row_id: "r1" })).replace(/\n/g, "\r\n");
    const ids = parseEvents(text).events.map((e) => (e.data as { row_id: string }).row_id);
    expect(ids).toEqual(["r2", "r1"]);
  });

  it("passes an error event through", () => {
    const { events } = parseEvents(block("error", { message: "model unavailable" }));
    expect(events).toEqual([{ event: "error", data: { message: "model unavailable" } }]);
  });
});
