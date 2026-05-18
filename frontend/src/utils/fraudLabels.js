/** Global FraudShield display labels — ML statistical flags are not "fraud". */

export function fraudAlertDisplayLabel(alertType, riskScore) {
  const t = String(alertType || "").toUpperCase();
  if (t === "ML_ANOMALY") return "Unusual Spend";
  if (Number(riskScore) >= 70) return "Fraud Alert";
  if (Number(riskScore) >= 50) return "Unusual Spend";
  return "Review";
}

export function fraudSeverityFromScore(score) {
  const s = Number(score) || 0;
  if (s >= 70) return "CRITICAL";
  if (s >= 50) return "HIGH";
  return "LOW";
}
