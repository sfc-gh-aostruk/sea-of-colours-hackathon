#!/usr/bin/env python3
"""Deploy Sea of Colours Snowflake artefacts.

Default behaviour (NON-DESTRUCTIVE):
  1. snowflake/soc_schema.sql       — CREATE TABLE IF NOT EXISTS
  2. snowflake/soc_views.sql        — CREATE OR REPLACE VIEW
  3. snowflake/soc_procedures.sql   — Snowpark Python stored procs (Phase 2)
  4. snowflake/soc_create_agent*.sql — every Cortex agent spec (Phase 5,
                                       including orchestrator-config A/B
                                       variants like _list / _grid).

Tables are NEVER dropped here. Phase 2/5 files are deployed only when
they exist on disk, so this script is safe to run after Phase 1 alone.

Flags:
  --schema-only   Stop after soc_schema.sql + soc_views.sql.
  --procs         Also deploy soc_procedures.sql (default).
  --agent         Also deploy every soc_create_agent*.sql (default).
  --no-procs      Skip soc_procedures.sql.
  --no-agent      Skip every soc_create_agent*.sql file.
  --config FILE   Path to Snowflake config (defaults to ~/.ssh/sf_config or
                  whatever SF_CONFIG_FILE points to).

Reads credentials from a Snowflake config file with these keys (matches
AA4 convention):

  account=<account>
  user=<user>
  private_key_file=<path to PEM>
  warehouse=<warehouse>            # optional, defaults below
  database=UMAN_SIM_DB
  schema=SEA_OF_COLOURS
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List


DEFAULT_WAREHOUSE = "SOC_WH"  # dedicated XSMALL warehouse, AUTO_SUSPEND=60s
DEFAULT_DATABASE = "UMAN_SIM_DB"
DEFAULT_SCHEMA = "SEA_OF_COLOURS"
DEFAULT_ROLE = os.environ.get("SF_ROLE", "ACCOUNTADMIN")

HERE = Path(__file__).resolve().parent.parent
SNOWFLAKE_DIR = HERE / "snowflake"


def _load_sf_props(path: str) -> dict:
    """Parse the same key=value config that AA4 uses."""
    props: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                props[k.lower().strip()] = v.strip()
    return props


def create_snowpark_session(config_file: str):
    """Build a Snowpark session from a sf_config-style file."""
    from snowflake.snowpark import Session
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Snowflake config not found: {config_file}")

    props = _load_sf_props(config_file)
    if "private_key_file" not in props:
        raise KeyError(
            f"{config_file} missing 'private_key_file=' entry"
        )

    key_path = props["private_key_file"]
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Private key file not found: {key_path}")

    with open(key_path, "rb") as kf:
        private_key = serialization.load_pem_private_key(
            kf.read(), password=None, backend=default_backend(),
        )
    private_key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return Session.builder.configs({
        "account": props.get("account"),
        "user": props.get("user"),
        "private_key": private_key_bytes,
        "warehouse": props.get("warehouse", DEFAULT_WAREHOUSE),
        "database": props.get("database", DEFAULT_DATABASE),
        "schema": props.get("schema", DEFAULT_SCHEMA),
    }).create()


def build_engine_zip() -> Path:
    """Zip the ``sea_of_colours`` package for IMPORTS into Snowpark procs.

    Snowflake's IMPORTS clause expects a stage path to a zip / .py file
    whose top-level entries match the import names. We package the entire
    ``sea_of_colours`` package (engine + snowpark layer) under one zip so
    every proc handler can resolve ``import sea_of_colours.snowpark.procs``.
    """
    import zipfile

    out_dir = HERE / "build"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / "sea_of_colours.zip"
    pkg_root = HERE / "sea_of_colours"
    if not pkg_root.is_dir():
        raise FileNotFoundError(f"package not found: {pkg_root}")

    print()
    print("=" * 60)
    print(f"Packaging {pkg_root.name} -> {zip_path}")
    print("=" * 60)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in pkg_root.rglob("*"):
            if path.is_dir():
                continue
            if any(seg.startswith("__pycache__") for seg in path.parts):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            arcname = str(path.relative_to(HERE))
            zf.write(path, arcname)
    print(f"  packaged {zip_path.stat().st_size // 1024} KB")
    return zip_path


def upload_engine_zip(session, zip_path: Path) -> None:
    """PUT the engine zip onto @SOC_PY_STAGE (idempotent)."""
    print()
    print("=" * 60)
    print(f"Uploading {zip_path.name} to @SOC_PY_STAGE...")
    print("=" * 60)
    session.sql(
        "CREATE STAGE IF NOT EXISTS SOC_PY_STAGE "
        "DIRECTORY = (ENABLE = TRUE) "
        "COMMENT = 'Python imports for SOC_* Snowpark procedures.'"
    ).collect()
    abs_path = zip_path.resolve()
    put_sql = (
        f"PUT 'file://{abs_path}' @SOC_PY_STAGE "
        "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
    )
    print(f"  {put_sql}")
    result = session.sql(put_sql).collect()
    if result:
        first = result[0].as_dict() if hasattr(result[0], "as_dict") else dict(result[0])
        print(f"  uploaded: {first}")


def _split_statements(sql_text: str) -> List[str]:
    """Split a SQL file into individual statements.

    Mirrors AA4's splitter so $$-delimited Python procedure / agent bodies
    survive in one statement. Lines outside a body that are blank or pure
    SQL comments are dropped; everything else accumulates until a top-level
    semicolon (``;``) or, inside a body, ``$$;``.
    """
    statements: List[str] = []
    current: List[str] = []
    in_body = False

    for raw_line in sql_text.split("\n"):
        stripped = raw_line.strip()

        if not in_body and (not stripped or stripped.startswith("--")):
            continue

        current.append(raw_line)
        upper = stripped.upper()

        if any(
            kw in upper
            for kw in (
                "CREATE OR REPLACE PROCEDURE",
                "CREATE PROCEDURE",
                "CREATE OR REPLACE AGENT",
                "CREATE AGENT",
            )
        ):
            in_body = True

        if stripped.endswith(";"):
            if in_body and "$$;" in raw_line:
                in_body = False
                statements.append("\n".join(current))
                current = []
            elif not in_body:
                statements.append("\n".join(current))
                current = []

    if current:
        statements.append("\n".join(current))

    return [s.strip() for s in statements if s.strip()]


def deploy_sql_file(session, filepath: Path, *, label: str | None = None) -> None:
    """Execute every statement in ``filepath`` against ``session``."""
    label = label or filepath.name
    print()
    print("=" * 60)
    print(f"Deploying: {label}  ({filepath})")
    print("=" * 60)

    if not filepath.exists():
        print(f"  (skipped — file does not exist)")
        return

    statements = _split_statements(filepath.read_text())
    for i, stmt in enumerate(statements, 1):
        preview = stmt[:200] + ("..." if len(stmt) > 200 else "")
        print(f"\n[{i}/{len(statements)}] {preview}")
        try:
            session.sql(stmt).collect()
            print("  OK")
        except Exception as e:  # pragma: no cover - depends on live SF
            msg = str(e)
            if "already exists" in msg.lower():
                print(f"  OK (already exists)")
                continue
            print(f"  ERROR: {e}")
            raise


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--config",
        default=os.environ.get(
            "SF_CONFIG_FILE",
            os.path.expanduser("~/.ssh/sf_config"),
        ),
        help="Snowflake config file (key=value lines).",
    )
    ap.add_argument(
        "--schema-only",
        action="store_true",
        help="Deploy only soc_schema.sql + soc_views.sql; skip procs / agent.",
    )
    ap.add_argument(
        "--no-procs",
        action="store_true",
        help="Skip soc_procedures.sql (default: include if file exists).",
    )
    ap.add_argument(
        "--no-agent",
        action="store_true",
        help="Skip soc_create_agent.sql (default: include if file exists).",
    )
    ap.add_argument(
        "--agents-only",
        action="store_true",
        help=(
            "Skip schema / views / procedures and deploy ONLY the "
            "soc_create_agent*.sql files. Useful when iterating on a "
            "Cortex agent spec under SF_ROLE=SYSADMIN, which typically "
            "lacks CREATE TABLE on the schema (owned by ACCOUNTADMIN) "
            "but does have CREATE AGENT."
        ),
    )
    ap.add_argument(
        "--agent-name",
        action="append",
        help=(
            "Restrict --agents-only deploys to a specific spec filename "
            "stem (e.g. 'soc_create_agent_grid_v2'). Repeatable. When "
            "omitted, every soc_create_agent*.sql is deployed."
        ),
    )
    args = ap.parse_args()

    print("Creating Snowpark session...")
    session = create_snowpark_session(args.config)

    # Pin role / warehouse / database / schema before anything else fires.
    role = DEFAULT_ROLE
    try:
        session.sql(f"USE ROLE {role}").collect()
    except Exception as e:  # pragma: no cover - depends on live SF
        print(f"  (could not USE ROLE {role}: {e}; continuing with session default)")
    session.sql(f"USE DATABASE {DEFAULT_DATABASE}").collect()

    # ``--agents-only`` skips everything except CREATE OR REPLACE AGENT.
    # The schema is already in place under ACCOUNTADMIN-owned objects;
    # SYSADMIN typically can't re-run it but CAN replace agents. We
    # still need USE SCHEMA so the agent specs (which start with
    # ``USE SCHEMA``) inherit the right context, but skip the
    # CREATE TABLE / CREATE VIEW / proc-zip steps entirely.
    if args.agents_only:
        try:
            session.sql(f"USE SCHEMA {DEFAULT_SCHEMA}").collect()
        except Exception as e:  # pragma: no cover - depends on live SF
            print(f"  (warning: USE SCHEMA {DEFAULT_SCHEMA} failed: {e})")
        agent_specs = sorted(SNOWFLAKE_DIR.glob("soc_create_agent*.sql"))
        if args.agent_name:
            allowed = set(args.agent_name)
            agent_specs = [s for s in agent_specs if s.stem in allowed]
            missing = allowed - {s.stem for s in agent_specs}
            for m in missing:
                print(f"  warning: --agent-name {m!r} matched no file on disk")
        if not agent_specs:
            print("  (no agent specs to deploy — exiting)")
            return 0
        for spec in agent_specs:
            deploy_sql_file(session, spec, label=f"agent · {spec.name}")
        print()
        print("=" * 60)
        print(f"Deployed {len(agent_specs)} agent spec(s).")
        print("=" * 60)
        return 0

    deploy_sql_file(session, SNOWFLAKE_DIR / "soc_schema.sql", label="schema")
    deploy_sql_file(session, SNOWFLAKE_DIR / "soc_views.sql", label="views")

    if not args.schema_only:
        if not args.no_procs:
            zip_path = build_engine_zip()
            upload_engine_zip(session, zip_path)
            deploy_sql_file(
                session,
                SNOWFLAKE_DIR / "soc_procedures.sql",
                label="procedures",
            )
        if not args.no_agent:
            # Deploy every `soc_create_agent*.sql` file we can find.
            # The legacy `soc_create_agent.sql` is the canonical default
            # (kept for back-compat); newer per-variant specs land as
            # `soc_create_agent_<variant>.sql` (e.g. _list, _grid for the
            # Phase 1 orchestrator-config A/B). Stable ordering — alphabetical —
            # so the deploy log is reproducible across runs.
            agent_specs = sorted(SNOWFLAKE_DIR.glob("soc_create_agent*.sql"))
            if not agent_specs:
                print("\n  (no soc_create_agent*.sql files found — skipping agents)")
            for spec in agent_specs:
                deploy_sql_file(session, spec, label=f"agent · {spec.name}")

    print()
    print("=" * 60)
    print("Deployment complete.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
