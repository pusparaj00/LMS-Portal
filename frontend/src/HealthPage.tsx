import { useEffect, useState } from "react";

type Health = { status: string; database: string; redis: string };

export function HealthPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/health")
      .then(async (res) => setHealth((await res.json()) as Health))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", margin: "2rem" }}>
      <h1>System health</h1>
      {error && <p role="alert">API unreachable: {error}</p>}
      {!health && !error && <p>Checking…</p>}
      {health && (
        <ul>
          <li>API: {health.status}</li>
          <li>Database: {health.database}</li>
          <li>Redis: {health.redis}</li>
        </ul>
      )}
    </main>
  );
}
