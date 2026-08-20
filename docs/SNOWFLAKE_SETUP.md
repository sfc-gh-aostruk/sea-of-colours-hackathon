# BYO-Snowflake setup

**TL;DR: you don't need any of this to play.** `SOC_BACKEND=memory` (the
default for local dev — see `README.md`) plays a full game against
`RED_HARVEST` / `RED_HARVEST_LITE` with zero external services. This doc
is only for the two things that need a real Snowflake account:

1. **Running / improving V11** — the reference Cortex agent
   (`sea_of_colours/orchestrator_2/harnesses/tabula_v11/`). It calls
   Snowflake Cortex's inference API to think; everything else about it
   is plain Python running on your machine.
2. **Persistent, Snowflake-backed game history** (`SOC_BACKEND=snowflake`)
   — optional, only useful if you want every season durably written to
   real tables instead of living in server memory.

These are independent. You can do (1) without (2).

## 1. Playing against / building V11 — PAT only, no schema deploy

V11 talks to Snowflake over one REST endpoint —
`/api/v2/cortex/v1/chat/completions` (Cortex's inference API, not the
"Agents" feature) — using a Programmatic Access Token. It does **not**
need any table, view, or stored procedure deployed; the harness runs
entirely as local Python and calls `soc_engine.submit_policy(...)`
directly, same as the heuristic agents.

### Steps

1. **Get a Snowflake account.** A
   [30-day free trial](https://signup.snowflake.com/) works — pick any
   cloud/region, the `Standard` edition is enough as long as Cortex is
   available in that region ([regional availability list](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql#region-availability)).
2. **Generate a Programmatic Access Token (PAT).** In Snowsight:
   `Admin → Users & Roles → <your user> → Programmatic access tokens →
   Generate new token`. Give it a role that can call Cortex (see next
   step) and copy the token value — Snowflake only shows it once.
3. **Make sure your role can use Cortex.** Any role with the
   `SNOWFLAKE.CORTEX_USER` database role granted (ACCOUNTADMIN has it by
   default on a fresh trial account) can call the inference endpoint:
   ```sql
   GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;
   ```
4. **Write a config file** at `~/.ssh/sf_config` (or point
   `SF_CONFIG_FILE` at another path) with just your account identifier:
   ```
   account=<your_account_identifier>
   ```
   Find your account identifier in Snowsight's bottom-left account
   selector, or in the URL: `https://<account_identifier>.snowflakecomputing.com`.
5. **Export the PAT** in the shell you'll run the game / scripts from:
   ```bash
   export SNOWFLAKE_PAT=<the token from step 2>
   ```
6. **Smoke-test the credentials** before wiring up a whole game:
   ```bash
   python - <<'PY'
   from sea_of_colours.orchestrator_2.cortex_chat import CortexChatInvoker
   inv = CortexChatInvoker(max_completion_tokens=20)
   print("ready:", inv.is_ready())
   print(inv.invoke("Reply with exactly the word: pong"))
   PY
   ```
   `ready: True` and a response containing `pong` means you're set.
7. **Play a game against V11** (or run it headless — see
   `scripts/run_matchup_v11.py` / `scripts/run_season.py --p2 cortex`).
   `SOC_BACKEND` can stay `memory`; V11 doesn't need it to be
   `snowflake`.

### Cost / rate-limit notes

- Each V11 turn makes a small, bounded number of chat-completions calls
  (see `sea_of_colours/orchestrator_2/harnesses/tabula_v11/harness.py`),
  each capped by `max_completion_tokens` and a wall-clock timeout — so a
  runaway turn can't rack up an unbounded bill.
- Trial-account credits comfortably cover a full hackathon's worth of
  matches; Cortex inference billing is per-token, independent of
  warehouse compute (no warehouse is even required for this path).

## 2. Optional: persistent Snowflake-backed sessions (`SOC_BACKEND=snowflake`)

Only needed if you want every season durably written to real Snowflake
tables (`SOC_SESSION`, `SOC_REPLAY_FRAME`, etc.) instead of living in
server memory for the life of the process. This is a bigger setup step
and pulls in an extra dependency:

```bash
pip install -r requirements-snowflake.txt
```

1. Extend your `sf_config` with key-pair auth (this path uses a Snowpark
   session, not the PAT — different auth mechanism, same file):
   ```
   account=<your_account_identifier>
   user=<your_username>
   private_key_file=/path/to/your/rsa_key.p8
   warehouse=SOC_WH        # optional — the deploy script creates this XSMALL warehouse if absent
   database=UMAN_SIM_DB    # optional — override the default database name
   schema=SEA_OF_COLOURS   # optional — override the default schema name
   ```
   See [Snowflake's key-pair auth docs](https://docs.snowflake.com/en/user-guide/key-pair-auth)
   for generating `rsa_key.p8` and registering the public key on your user.
2. Deploy the schema (non-destructive — safe to re-run):
   ```bash
   python scripts/deploy_soc_schema.py
   # or, to skip the Cortex Agents-API specs (not needed for V11):
   python scripts/deploy_soc_schema.py --no-agent
   ```
3. Run with the Snowflake backend:
   ```bash
   SOC_BACKEND=snowflake python run_web.py
   ```

See `README.md`'s "Web + Snowflake" section for the full flag reference
and cost notes on this path.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `CortexChatInvoker(...).is_ready()` is `False` | `SNOWFLAKE_PAT` unset/empty, or `account=` missing/wrong in `sf_config`. |
| `401`/`403` from the chat-completions call | Role on the PAT doesn't have `SNOWFLAKE.CORTEX_USER` granted, or the PAT expired. |
| Cortex call times out / V11 falls back to a shorter plan | Normal under load — V11's wall-clock cap intentionally truncates and falls back rather than stalling the game; see the harness's timeout constants if you want to tune it. |
| `ModuleNotFoundError: snowflake.snowpark` | You're on the `SOC_BACKEND=snowflake` path without `pip install -r requirements-snowflake.txt`. Not needed for V11 / the PAT path above. |
