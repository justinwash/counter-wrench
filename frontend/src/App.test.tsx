import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("the New intake link in the header starts the intake over, even from the intake page", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json([])));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><App /></MemoryRouter></QueryClientProvider>);

  const notes = screen.getByLabelText("General notes") as HTMLInputElement;
  fireEvent.change(notes, { target: { value: "customer is in a hurry" } });
  expect((screen.getByLabelText("General notes") as HTMLInputElement).value).toBe("customer is in a hurry");

  fireEvent.click(screen.getByText("New intake"));
  expect((screen.getByLabelText("General notes") as HTMLInputElement).value).toBe("");
});
