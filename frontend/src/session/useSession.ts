import { useCallback, useReducer } from "react";
import {
  ApiError,
  completeSession,
  createSession,
  fetchNextStep,
  runStep,
} from "../api/client";
import type { CreateSessionRequest } from "../api/types";
import { initialSessionState } from "./types";
import { sessionReducer } from "./reducer";

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    return err.status === 0
      ? err.message
      : `${err.message} (HTTP ${err.status})`;
  }
  return err instanceof Error ? err.message : String(err);
}

/**
 * Drives one Agent Inspector session end to end: create -> alternating
 * get_next_step()/run_step() -> complete(). All state transitions are
 * derived from the backend's `need` field, mirroring the two-operation
 * loop the prototype demonstrates.
 */
export function useSession() {
  const [state, dispatch] = useReducer(sessionReducer, initialSessionState);

  const start = useCallback(async (task: CreateSessionRequest) => {
    dispatch({ type: "session/start" });
    try {
      const payload = await createSession(task);
      dispatch({ type: "session/success", payload });
    } catch (err) {
      dispatch({ type: "session/error", error: describeError(err) });
    }
  }, []);

  const getNextStep = useCallback(async () => {
    if (!state.sessionId || state.need !== "next" || state.loading) return;
    dispatch({ type: "next/start" });
    try {
      const payload = await fetchNextStep(state.sessionId);
      dispatch({ type: "next/success", payload });
    } catch (err) {
      dispatch({ type: "next/error", error: describeError(err) });
    }
  }, [state.sessionId, state.need, state.loading]);

  const runNextStep = useCallback(async () => {
    if (!state.sessionId || state.need !== "run" || state.loading) return;
    dispatch({ type: "run/start" });
    try {
      const payload = await runStep(state.sessionId);
      dispatch({ type: "run/success", payload });
    } catch (err) {
      dispatch({ type: "run/error", error: describeError(err) });
    }
  }, [state.sessionId, state.need, state.loading]);

  const approve = useCallback(async () => {
    if (!state.sessionId || state.need !== "approve" || state.loading)
      return;
    dispatch({ type: "complete/start" });
    try {
      const payload = await completeSession(state.sessionId);
      dispatch({ type: "complete/success", payload });
    } catch (err) {
      dispatch({ type: "complete/error", error: describeError(err) });
    }
  }, [state.sessionId, state.need, state.loading]);

  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  return { state, start, getNextStep, runNextStep, approve, reset };
}
