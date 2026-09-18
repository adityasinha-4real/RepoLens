"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnalysisError, streamAnalysis } from "@/lib/analyze-stream";
import type { AnalysisReport, ProgressStage } from "@/lib/api/types";
import { Dashboard } from "../dashboard/dashboard";
import { ErrorPanel } from "./error-panel";
import { ProgressPanel } from "./progress-panel";

type State =
  | { status: "loading"; stage: ProgressStage | null; message: string | null }
  | { status: "success"; report: AnalysisReport }
  | { status: "error"; error: AnalysisError };

export function AnalysisView({
  owner,
  name,
  run = streamAnalysis,
}: {
  owner: string;
  name: string;
  run?: typeof streamAnalysis;
}) {
  const [state, setState] = useState<State>({ status: "loading", stage: null, message: null });
  const [attempt, setAttempt] = useState(0);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    controller.current = ctrl;
    run(`https://github.com/${owner}/${name}`, {
      signal: ctrl.signal,
      onProgress: (stage, message) => {
        if (!ctrl.signal.aborted) setState({ status: "loading", stage, message });
      },
    })
      .then((report) => {
        if (!ctrl.signal.aborted) setState({ status: "success", report });
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        const error =
          err instanceof AnalysisError
            ? err
            : new AnalysisError({ code: "internal_error", message: "An unexpected error occurred." });
        setState({ status: "error", error });
      });
    return () => ctrl.abort();
  }, [owner, name, attempt, run]);

  const retry = useCallback(() => {
    setState({ status: "loading", stage: null, message: null });
    setAttempt((a) => a + 1);
  }, []);

  if (state.status === "loading") {
    return <ProgressPanel repo={`${owner}/${name}`} stage={state.stage} message={state.message} />;
  }
  if (state.status === "error") return <ErrorPanel error={state.error} onRetry={retry} />;
  return <Dashboard report={state.report} />;
}
