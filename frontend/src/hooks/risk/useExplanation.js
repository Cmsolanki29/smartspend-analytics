/**
 * useExplanation — fetches SHAP explanation for a transaction.
 * Returns { data, loading, error }. Safe to call with txnId=null.
 */

import { useEffect, useState } from "react";
import { getExplanation } from "../../services/riskApi";

export function useExplanation(txnId) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  useEffect(() => {
    if (!txnId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setData(null);
    setLoading(true);
    setError(null);

    getExplanation(txnId)
      .then((res) => { if (!cancelled) { setData(res); setLoading(false); } })
      .catch((err) => { if (!cancelled) { setError(err); setLoading(false); } });

    return () => { cancelled = true; };
  }, [txnId]);

  return { data, loading, error };
}
