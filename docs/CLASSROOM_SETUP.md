# Instructor Setup — GitHub Classroom for F405 Options Bot

This is the step-by-step for **the instructor** to stand up the assignment on GitHub
Classroom using this repo as the template. Students fork it into private per-student repos,
push code, and get autograded on every push. You only do this once per term.

> **Already configured for this repo:** it is marked a **template repository** on GitHub
> (Settings → General → *Template repository*), and the Turso DB + GitHub Actions secrets for
> the leaderboard are provisioned and live — so you can skip those. If the template
> checkbox is not set, Classroom cannot use it as the starter and the *Use this template*
> path will be missing.

---

## 1. Create (or reuse) a GitHub organization

GitHub Classroom hangs off a GitHub **organization**, not a personal account.

1. If you do not already have a teaching org, create one: https://github.com/organizations/plan
   (the **Free** plan is enough; it gives unlimited private repos).
2. Note the org name (e.g. `iba-f405`). All student repos will live under it.

## 2. Create the Classroom and link the org

1. Go to https://classroom.github.com and sign in with the GitHub account that owns/admins the org.
2. **New classroom** → pick the organization from step 1 → authorize the GitHub Classroom app
   when prompted (it needs admin on the org to create student repos).
3. Name the classroom something like `IBA F405 — Derivatives`.

## 3. Create the assignment from THIS repo as the template

In the classroom, **New assignment** → *Individual assignment*, then:

| Field | Value |
|---|---|
| **Assignment title** | `BTC Weekly-Options Bot` |
| **Deadline** | end of the live window (the second Friday expiry); allow late pushes |
| **Repository visibility** | **Private** (students must not see each other's alpha) |
| **Repository permission** | students get **write** to their own repo only |
| **Template repository** | search for and select **`kalam360/f405-options-bot`** |
| **Repository prefix** | `f405-bot` (each student repo becomes `f405-bot-<github-handle>`) |

Use the **starter code = this template repo** option so each student gets a full copy of
`botkit/`, the baselines, notebooks, tests, and CI. Paste the text from
[`ASSIGNMENT_BLURB.md`](ASSIGNMENT_BLURB.md) into the assignment **description** field.

> If the template repo does not appear in the picker, it is almost certainly because the
> *Template repository* checkbox is not set yet (see the prerequisite note above), or the
> Classroom app was not granted access to the org.

## 4. Enable autograding (the tests already exist)

This repo ships `.github/classroom/autograding.json`, so Classroom can import the tests
automatically. On the assignment's **Grading and feedback** step:

1. Choose **Add test** → if Classroom offers to import from the repo's `autograding.json`,
   accept it. Otherwise add the two tests below by hand (they mirror the JSON exactly).
2. Pick the **Ubuntu** runner (the tests install `uv` and Python 3.11).

The two autograding tests (10 points total — same split the autograder uses):

| # | Test name | What it runs | Pass condition | Points |
|---|---|---|---|---:|
| 1 | **Unit tests (pytest)** | `uv sync --python 3.11` then `uv run pytest -q` | all tests green (pricing sanity, sim smoke, scorer-on-fixture) | **6** |
| 2 | **Bot runs in sim and produces a valid score.json** | runs the `delta_hedged_vol_seller` baseline through the sim runner, then `score.py`, then asserts the JSON has the required keys and `0 ≤ score_0_3 ≤ 3` | output contains **`SMOKE_OK`** | **4** |

What each test proves:
- **Test 1** is the engineering gate — the student did not break `botkit/`, the journal
  schema, or the provided tests, and their own tests still pass.
- **Test 2** is the end-to-end gate — the bot actually runs offline in `sim` mode and emits a
  scorable journal. It runs against a **baseline** (not the student's strategy) so it stays
  green even before they have written `MyStrategy`; it checks the *plumbing*, not their alpha.

> These autograding points are a **CI health check**, not the course grade. The real `/10`
> (performance, survival, engineering, quant rationale, AI workflow) is graded by hand against
> [`RUBRIC.md`](RUBRIC.md) using [`INSTRUCTOR_GRADING.md`](INSTRUCTOR_GRADING.md). Tell students
> this so they don't mistake "10/10 autograder" for "10/10 in the course."

## 5. Import the roster

1. On the assignment page → **Students** / **Roster** → **Update students**.
2. Upload a class roster (CSV of student identifiers, e.g. university IDs) or paste the list.
   Classroom uses this to map each accepted repo to a named student.
3. Share the **assignment invitation link** (top of the assignment page) with the class.
   When a student clicks it and accepts, Classroom creates their private repo from this
   template and (if rostered) links it to their roster entry.

The same read-only Deribit testnet key each student registers for the **live leaderboard**
(see [`../leaderboard/README.md`](../leaderboard/README.md)) should use an `id` that matches
their roster entry, so the leaderboard rank and the Classroom grade line up.

## 6. How grades and feedback flow back

- **Every push** to a student repo triggers `.github/workflows/autograde.yml` *and* the
  Classroom autograding run. Students see pass/fail + points on their repo's **Actions** tab
  and on the Classroom assignment page.
- You see a **per-student grading table** in Classroom (Download grades as CSV) with the
  autograding score for each accepted repo.
- For written feedback, use Classroom's **feedback pull request** (a `feedback` branch PR
  opened in each student repo) to leave inline comments on their `MyStrategy`/`MyRisk`,
  post-mortem, and journal.
- The autograding number is the CI gate; you enter the final `/10` yourself after the live
  window, following [`INSTRUCTOR_GRADING.md`](INSTRUCTOR_GRADING.md).

## 7. Sanity checklist before you invite students

- [x] Repo is marked a **template** (already done).
- [x] Turso DB + GH Actions secrets provisioned for the leaderboard (already done).
- [ ] Assignment created from `kalam360/f405-options-bot`, **private**, individual.
- [ ] [`ASSIGNMENT_BLURB.md`](ASSIGNMENT_BLURB.md) pasted into the description.
- [ ] Both autograding tests imported (6 + 4 = 10) and the Ubuntu runner selected.
- [ ] Roster uploaded; invitation link tested with a throwaway account (repo is created,
      `uv run pytest` is green, the sim smoke test prints `SMOKE_OK`).
- [x] Leaderboard is **live**: https://f405-leaderboard-abul-kalam-faruks-projects.vercel.app (see `leaderboard/README.md`).
