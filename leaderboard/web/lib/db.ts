// Turso / libSQL client + the two queries the leaderboard needs.
//
// Reads are done server-side (in a React Server Component), so the auth token
// never reaches the browser. Configure with two env vars on Vercel:
//   TURSO_DATABASE_URL   e.g. libsql://f405-leaderboard-yourname.turso.io
//   TURSO_AUTH_TOKEN     a read-only-ish token from `turso db tokens create`

import { createClient, type Client } from "@libsql/client";

export type Row = {
  id: string;
  name: string;
  github: string | null;
  team: string | null;
  equity_usd: number;
  start_equity_usd: number;
  total_return: number;
  max_drawdown: number;
  risk_adjusted: number;
  blew_up: number; // 0 / 1
  n_snapshots: number;
  updated_at: number;
};

let _client: Client | null = null;

function client(): Client {
  if (_client) return _client;
  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;
  if (!url) throw new Error("TURSO_DATABASE_URL is not set");
  _client = createClient({ url, authToken });
  return _client;
}

/**
 * The standings, in the canonical order: survivors first (blew_up ASC), then by
 * the risk-adjusted metric (DESC). This is the same ORDER BY the poller indexes.
 */
export async function getStandings(): Promise<Row[]> {
  const rs = await client().execute(
    `SELECT s.student_id AS id, st.name, st.github, st.team,
            s.equity_usd, s.start_equity_usd, s.total_return,
            s.max_drawdown, s.risk_adjusted, s.blew_up,
            s.n_snapshots, s.updated_at
       FROM scores s
       JOIN students st ON st.id = s.student_id
      ORDER BY s.blew_up ASC, s.risk_adjusted DESC`
  );
  return rs.rows as unknown as Row[];
}

/**
 * The recent equity tail for a student (oldest -> newest), used to draw the
 * sparkline. `limit` caps how many points we pull.
 */
export async function getEquitySeries(
  studentId: string,
  limit = 96
): Promise<number[]> {
  const rs = await client().execute({
    sql: `SELECT equity_usd FROM (
             SELECT equity_usd, ts FROM equity_snapshots
              WHERE student_id = ?
              ORDER BY ts DESC LIMIT ?
           ) ORDER BY ts ASC`,
    args: [studentId, limit],
  });
  return rs.rows.map((r) => Number(r.equity_usd));
}
