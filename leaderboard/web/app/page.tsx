import { getStandings, getEquitySeries, type Row } from "@/lib/db";
import { Sparkline } from "@/components/Sparkline";

// Always render fresh from Turso (the poller updates every 15 min). No caching.
export const dynamic = "force-dynamic";
export const revalidate = 0;

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

function cls(x: number): string {
  return x >= 0 ? "pos" : "neg";
}

export default async function Page() {
  let rows: Row[] = [];
  let series: number[][] = [];
  let error: string | null = null;

  try {
    rows = await getStandings();
    series = await Promise.all(rows.map((r) => getEquitySeries(r.id)));
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="wrap">
      <header>
        <h1>F405 Options Bot — Live Leaderboard</h1>
        <p>BTC weekly options · Deribit testnet · ranked by risk-adjusted return</p>
      </header>

      <div className="note">
        Ranking metric = <strong>total return ÷ max drawdown</strong> (floored at
        2%). The game rewards <strong>survival</strong>, not gambling: any bot that
        got liquidated or fell below 25% of its starting equity is flagged{" "}
        <span className="skull">💀 BLEW UP</span> and sinks to the bottom,
        regardless of how good it looked beforehand. Updates every ~15 minutes.
      </div>

      {error ? (
        <div className="empty">
          Could not reach the database.
          <br />
          <span className="muted">{error}</span>
          <br />
          <br />
          Set <code>TURSO_DATABASE_URL</code> and <code>TURSO_AUTH_TOKEN</code> in
          your Vercel project, then redeploy.
        </div>
      ) : rows.length === 0 ? (
        <div className="empty">
          No standings yet. Once the poller runs (GitHub Actions, every 15 min)
          and students register read-only keys, rankings appear here.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Student</th>
              <th>Equity</th>
              <th>Return</th>
              <th>Max DD</th>
              <th>Risk-Adj</th>
              <th>Equity (recent)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              // Survivors are ranked 1..N; blown-up bots show "—" (out of the race).
              const rank = r.blew_up ? "—" : `${i + 1}`;
              return (
                <tr key={r.id} className={r.blew_up ? "blewup" : ""}>
                  <td className={`rank ${!r.blew_up && i === 0 ? "top" : ""}`}>
                    {rank}
                  </td>
                  <td>
                    <div className="name">
                      {r.name}
                      {r.blew_up ? <span className="skull">💀 BLEW UP</span> : null}
                    </div>
                    {r.team ? <div className="team">{r.team}</div> : null}
                  </td>
                  <td className="num">
                    ${Math.round(r.equity_usd).toLocaleString()}
                  </td>
                  <td className={`num ${cls(r.total_return)}`}>
                    {pct(r.total_return)}
                  </td>
                  <td className="num neg">{pct(r.max_drawdown)}</td>
                  <td className={`ra ${cls(r.risk_adjusted)}`}>
                    {r.risk_adjusted.toFixed(2)}
                  </td>
                  <td>
                    <Sparkline data={series[i]} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <footer>
        IBA F405 — Derivatives · paper trading on Deribit testnet · no real money.
      </footer>
    </main>
  );
}
