import type { RowResult, StreamEvent } from "../api/stream";

/** Everything the counter screen shows about one run, built up event by event. */
export interface RunState {
  running: boolean;
  intakeId: string | null;
  redacted: Record<string, number>;
  flags: string[];
  bike: { name: string | null; note: string | null; question: string | null } | null;
  rows: Record<string, RowResult>;
  failedRows: Record<string, string>;
  escalationMessage: string | null;
  questions: Record<string, string>;
  outcome: string | null;
  awaitingConfirmation: boolean;
  workOrderId: number | null;
  draft: { work_order_id: number | null; estimate_total: string | null; unverified_parts: string[]; error: string | null } | null;
  error: string | null;
}

export const emptyRun: RunState = {
  running: false, intakeId: null, redacted: {}, flags: [], bike: null, rows: {}, failedRows: {},
  escalationMessage: null, questions: {}, outcome: null, awaitingConfirmation: false,
  workOrderId: null, draft: null, error: null,
};

export function applyEvent(state: RunState, e: StreamEvent): RunState {
  switch (e.event) {
    case "accepted":
      return { ...state, intakeId: e.data.intake_id, redacted: e.data.pii_redacted, flags: e.data.guardrail_flags };
    case "bike":
      return { ...state, bike: { name: e.data.name, note: e.data.note, question: e.data.question } };
    case "row":
      return { ...state, rows: { ...state.rows, [e.data.row_id]: e.data } };
    case "row_failed":
      return { ...state, failedRows: { ...state.failedRows, [e.data.row_id]: e.data.error } };
    case "route":
      return { ...state, escalationMessage: e.data.escalation_message, questions: e.data.questions, outcome: e.data.outcome };
    case "draft":
      return { ...state, draft: e.data };
    case "done":
      return { ...state, running: false, outcome: e.data.outcome, intakeId: e.data.intake_id,
               awaitingConfirmation: e.data.awaiting_confirmation, workOrderId: e.data.work_order_id };
    case "error":
      return { ...state, running: false, error: e.data.message };
    default:
      return state;
  }
}
