import React from "react";
import InsightsTab from "./InsightsTab";

/**
 * Legacy route shim: the standalone Simulator tab was removed from the sidebar
 * (simulator lives under Insights). If an old App.jsx still lazy-loads this file,
 * render Insights so nothing breaks.
 */
export default function SimulatorTab(props) {
  return <InsightsTab {...props} />;
}
