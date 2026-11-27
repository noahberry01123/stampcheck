# Set up StampCheck in a project: instructions for AI coding agents

You are helping a user set up StampCheck in their project. StampCheck reads a log of human approval decisions, where a person approves or rejects what an automated system or AI recommended. For each reviewer and each approval step, it reports whether the review still checks anything or has turned into a rubber stamp. It is a read-only command-line tool for Python 3.10 or newer.

Plain-text copy of these instructions: <https://stampcheck.io/agent.txt>. Full documentation: <https://github.com/noahberry01123/stampcheck#readme>

If you are working on StampCheck's own source code, this file does not apply to you.

## Rules: follow these at every step

1. **Never send approval data anywhere outside the user's machine.** Don't put rows, reviewer names or results into web searches, issues, pastebins or other services. Look at structure, not contents: read schemas and column names, count rows, and list the distinct values of status columns. Look at no more than 5 sample rows.
2. **Never change application code, database schemas or production config without explicit approval.** Show the exact change first, then wait for a yes. New files that only StampCheck reads, such as the mapping file or a saved query, are fine.
3. **Run read-only queries only.** Use `SELECT` only. Never use `INSERT`, `UPDATE`, `DELETE`, `ALTER` or migrations. StampCheck opens SQLite files read-only by itself. For Postgres, use a read-only database user.
4. **Never present results as proof that a specific person did something wrong.** A verdict is a pattern worth looking into. It usually points to a system problem: queues that are too long, a model that is nearly always right, or a timeout that approves by default. Say "matches the rubber-stamp pattern", not "sam is rubber-stamping".

## Steps

Stop and wait for the user where a step says so. Otherwise carry on to the next step.

### 1. Install StampCheck and run the demo

Install StampCheck in its own virtual environment so the project's dependencies don't change:

```bash
python3 -m venv ~/.stampcheck-venv
~/.stampcheck-venv/bin/pip install stampcheck     # Windows: ~\.stampcheck-venv\Scripts\pip
~/.stampcheck-venv/bin/stampcheck --version
```

`pipx install stampcheck` or `uv tool install stampcheck` also work. For a Postgres source, install `"stampcheck[postgres]"` instead. Below, `stampcheck` means the installed command, for example `~/.stampcheck-venv/bin/stampcheck`.

Run the demo in a scratch folder outside the project to confirm it works:

```bash
stampcheck demo --no-open --out /tmp/stampcheck-demo
```

The demo builds synthetic data, checks it, and prints verdicts for five fictional reviewers: sam RED, taylor RED, jordan AMBER, alex GREEN and kim GREY. **It exits with code 1 on purpose.** Exit code 1 means "something is RED", not that the command failed. Exit code 2 means a real error.

### 2. Find where the project records approval decisions

Look for one record per human decision on a case. Each record should say who decided, what they decided and when. Ideally it also says what the system recommended. Places to look:

- database schemas, migrations and ORM models: tables or columns named like `approval`, `review`, `decision`, `moderation`, `queue`, `audit`, `approved_by`, `reviewed_at` or `status`
- the code that handles a reviewer's approve or reject action (an admin page, a review queue, a Slack button, or a human-in-the-loop step in an agent): what it writes, and where
- log files or event streams (StampCheck reads JSON lines as they are)
- exports the team already makes, such as CSV files

For SQLite, run `sqlite3 path/to.db ".tables"` and `sqlite3 path/to.db ".schema <table>"`, or use Python's `sqlite3` module if the command-line tool is missing. Rule 1 applies.

List every candidate for the user. For each one, say:

- where it is
- what one row means
- which of the fields in step 3 it seems to have
- roughly how many rows it has, and what date range they cover

Then recommend one. **Stop and ask the user which one to use. Don't go further until they answer.**

StampCheck reads CSV and TSV files, JSON lines, SQLite and Postgres. Data in any other database (MySQL, BigQuery and so on) needs a CSV export from a read-only query, which the user runs or approves. If the data is in production, ask the user for a read-only connection or an export.

### 3. Map the fields and write a mapping file

StampCheck needs one row per reviewed case, with these fields:

| StampCheck field | Needed for | Meaning |
|---|---|---|
| `case_id` | required | ID of the case or approval request |
| `decision` | required | What the human did. Must end up as `approve`, `reject`, `escalate`, `timeout_approve` or `timeout_reject` |
| `decided_at` | required | When the decision was made. For timeouts: when the deadline passed |
| `reviewer` | per-reviewer verdicts, queue load, estimated timing | Who decided |
| `recommended` | the agreement checks | What the system proposed. Must end up as `approve` or `reject` |
| `opened_at` | exact timing | When the reviewer opened the case |
| `notified_at` | estimated timing | When the case entered the reviewer's queue |
| `category` | a separate verdict per approval step | The approval step, for example a refund size band |
| `executed` | the duplicate check | How many times the approved action actually ran |

Write the mapping to `stampcheck.yaml` in the project root. `stampcheck init` writes a template that explains every option. This example uses made-up column names:

```yaml
columns:                  # StampCheck field: column name in the user's data
  case_id: request_ref
  decision: final_status
  decided_at: closed_on
  reviewer: agent_email
  recommended: model_suggestion
  opened_at: null         # null: the data doesn't have this field
  notified_at: queue_entered
  category: refund_band
  executed: payout_count
values:                   # the user's values -> StampCheck's values (not case-sensitive)
  recommended:
    REFUND: approve
    NO_REFUND: reject
  decision:
    AUTO_APPROVED_SLA: timeout_approve   # nobody reviewed it in time, so it was approved by default
timezone: Europe/Berlin   # applied to timestamps that have no UTC offset
```

Getting it right:

- **Values.** These are recognised without mapping, and case doesn't matter: approve, approved, accept, accepted, reject, rejected, deny, denied, decline, declined, escalate, escalated, timeout_approve, timeout_reject.
    - Map every other value of the decision and recommendation columns. List them with `SELECT col, COUNT(*) FROM t GROUP BY col`.
    - StampCheck never guesses values: rows with an unmapped value are skipped and listed in the output.
- **Defaults.** Look for a value that means "nobody reviewed it before the deadline, so the system decided". Map it to `timeout_approve` or `timeout_reject`; the silent-timeout check looks for these.
- **Case IDs.** `case_id` is the ID the approved action ran for, such as a ticket or request reference, rather than an auto-increment row ID. Rows with the same `case_id` are added together by the duplicate check.
- **Timestamps.** StampCheck reads ISO 8601 strings, database datetimes, and epoch seconds or milliseconds. If timestamps have no offset, set `timezone` to the zone the app writes them in; check the app's settings.
- **Fields in several tables.** If the fields are spread over several tables, or rows are status changes rather than decisions, write a read-only `SELECT` for `--query` (SQLite and Postgres). It can join, filter, and rename columns, for example `SELECT r.ref AS case_id, ...`.

**Show the mapping file to the user.** For each missing field, say in one plain sentence which check won't run. For example: "There's no recommendation field, so only the speed checks run." What a missing field means:

| Missing | Effect |
|---|---|
| `recommended` | Agreement with the system can't be checked, so only the speed checks run. No reviewer can be RED for rubber-stamping, and fast reviewers get AMBER at most |
| `opened_at` | Time per case is estimated from `notified_at` or from the gaps between a reviewer's decisions. An estimate is an upper bound: it can show that someone is fast, but never that they were careful |
| `opened_at`, `notified_at` and `reviewer` | Speed can't be measured, so only the agreement checks run |
| `reviewer` | No per-reviewer verdicts and no queue-load check, only results per approval step |
| `category` | All rows are treated as one approval step |
| `executed` | No duplicate-execution check |
| no timeout values | The silent-timeout check has nothing to look at |

Then continue to step 4. The check is read-only.

### 4. Run the check and explain the results

```bash
stampcheck check --source path/to/app.db --query "SELECT * FROM approvals" --mapping stampcheck.yaml --out ~/stampcheck-out
```

- `--source`: a CSV, TSV or JSON lines file, a SQLite file, or a `postgresql://` URL. For SQLite, `--query` defaults to `SELECT * FROM reviews`. For Postgres, `--query` is required.
- `--out`: a folder outside the repository. The report names reviewers, so it shouldn't be committed.
- Exit codes:
    - 0: nothing is RED.
    - 1: something is RED. The check itself worked.
    - 2: an input error. The message says what's wrong, usually a column name or unmapped values. Fix the mapping and run it again.

The terminal output shows:

- the column mapping it used
- how many rows it read, used and skipped, with the reasons and any unmapped values
- `Not possible:` lines for checks that couldn't run
- a verdict and a one-sentence reason for each approval step and each reviewer
- `Timing from ...`, which says where each reviewer's times came from

The output folder holds the same information in `result.json` and `report.html`. If many rows were skipped, go back to step 3 and fix the mapping before you summarise.

Summarise the results for the user in plain language:

- **Verdicts:** each approval step's and each reviewer's verdict, with its reason.
    - RED: both warning signs, or a serious problem.
    - AMBER: one warning sign.
    - GREEN: the review looks engaged.
    - GREY: not enough data, which is never a pass.
- **Timing source:** exact (from `opened_at`) or an upper-bound estimate, and what that means for the speed verdicts.
- **Data quality:** skipped rows, unmapped values, "suspicious logging" (a column that looks hard-coded) and checks that couldn't run.
- **The report:** where it is, and the command to open it.
- **What the results mean:** a pattern is evidence to look into, not proof that anyone did anything wrong (rule 4).

### 5. Optional: log opened_at exactly

Without `opened_at`, speed is only estimated. Offer to add StampCheck's logging helper where reviewers decide, so that future data has exact timings:

```python
import stampcheck

stampcheck.record_review(
    case_id=case.ref,
    recommended="approve",         # what the system proposed: "approve" or "reject"
    decision="reject",             # "approve", "reject", "escalate", "timeout_approve" or "timeout_reject"
    reviewer=user.email,
    opened_at=opened_at,           # when the reviewer opened the case
    decided_at=decided_at,
    notified_at=case.queued_at,    # optional: when the case entered the queue
    category="refund_under_50",    # optional
    executed=1,                    # optional: how many times the approved action ran
)
```

- **Where it writes:** to `./stampcheck.db` (SQLite) by default. Pass `path=` or set `STAMPCHECK_PATH` to change it, and use a path ending in `.jsonl` for JSON lines. `stampcheck check --source stampcheck.db` then reads it with no mapping.
- **Safety:** it never raises. Problems are logged as warnings on the `stampcheck` logger, so it can't break the approval flow.
- **Capturing `opened_at`:** record it when the case is shown to the reviewer, then pass it to the code that handles the decision.
- **Dependency:** the app needs `stampcheck` as a dependency.

If the whole review happens inside one function call, the context manager records both timestamps:

```python
with stampcheck.review(case_id, recommended="approve", reviewer=user_id) as r:
    r.decision = ...
```

Show the user the full diff, including the dependency change, and **apply it only after they approve.**

### 6. Optional: run the check on a schedule with a Slack alert

`--alert "slack:$SLACK_WEBHOOK_URL"` posts to Slack only when something is RED or newly drifting. "Newly" means compared with the previous `result.json` in the `--out` folder, so keep that folder between runs.

Alerts are team-level by default, for example "1 of 2 reviewers matches the rubber-stamp pattern". Keep that default. Add `--per-reviewer` only if the user asks, and tell them that in some countries, monitoring individual employees needs agreement first. In Germany, for example, the works council has to agree.

**cron:**

```
0 7 * * 1  cd /path/to/project && ~/.stampcheck-venv/bin/stampcheck check --source data/app.db --query "SELECT ..." --mapping stampcheck.yaml --out ~/stampcheck-out --alert "slack:$SLACK_WEBHOOK_URL"
```

cron doesn't load the user's shell profile, so define the webhook variable in the crontab or in a wrapper script.

**GitHub Actions**, for a database that GitHub's runners can reach: start from <https://github.com/noahberry01123/stampcheck/blob/main/examples/github-actions/stampcheck.yml>. It runs weekly and takes a read-only database URL and the Slack webhook from repository secrets. It also caches the previous `result.json`.

Never write the webhook URL or database credentials into a file that is committed. Both options change the project or production config: show the exact change, and set it up only after the user approves (rule 2).

### When you're done

Tell the user:

- which source and mapping file you used
- the command that runs the check again
- the summary of the results from step 4
- which optional steps you didn't do
