/**
 * Demo-mode live transaction ticker — rotates recent DB transactions every 3.5s.
 */
import { useEffect, useRef, useState } from "react";
import { getTransactions, waitForBackendReady } from "../services/api";

export type TickerTransaction = {
  id: string | number;
  amount: number;
  merchant: string;
  type: "CREDIT" | "DEBIT";
};

type UseTickerDemoResult = {
  transaction: TickerTransaction | null;
  loading: boolean;
  error: boolean;
};

function mapRows(data: unknown): TickerTransaction[] {
  const rows: Record<string, unknown>[] = Array.isArray(data)
    ? (data as Record<string, unknown>[])
    : ((data as Record<string, unknown[]>)?.transactions as Record<string, unknown>[] | undefined) ??
      ((data as Record<string, unknown[]>)?.data as Record<string, unknown>[] | undefined) ??
      [];

  return rows
    .filter((r) => r && r.amount != null && r.merchant)
    .slice(0, 20)
    .map((r, i) => ({
      id: (r.id ?? r.transaction_id ?? i) as string | number,
      amount: Number(r.amount),
      merchant: String(r.merchant),
      type: String(r.type ?? "")
        .toUpperCase()
        .startsWith("C")
        ? "CREDIT"
        : "DEBIT",
    }));
}

export function useTickerDemo(
  userId: number | string | null | undefined
): UseTickerDemoResult {
  const [queue, setQueue] = useState<TickerTransaction[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!userId) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);

    (async () => {
      await waitForBackendReady(15000);
      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (cancelled) return;
        try {
          const data = await (getTransactions as (id: number | string, p: { limit: number }) => Promise<unknown>)(
            userId,
            { limit: 20 }
          );
          if (cancelled) return;
          const mapped = mapRows(data);
          setQueue(mapped);
          setIndex(0);
          setLoading(false);
          setError(false);
          return;
        } catch {
          if (attempt < 2) {
            await new Promise((r) => setTimeout(r, 1200 * (attempt + 1)));
          }
        }
      }
      if (!cancelled) {
        setError(true);
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (!queue.length) return;

    timerRef.current = setInterval(() => {
      setIndex((i) => (i + 1) % queue.length);
    }, 3500);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [queue]);

  return {
    transaction: queue.length > 0 ? queue[index] : null,
    loading,
    error,
  };
}

export default useTickerDemo;
