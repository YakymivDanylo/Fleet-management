"""Lab 12: PostgreSQL backup, restore and restore drill for the compose stack (runbook RB-001).

    python scripts/db_backup.py backup  [--project fleet_sandbox --env-file .env.sandbox]
    python scripts/db_backup.py restore --dump backups/<file>.dump  # stop app, restore, start
    python scripts/db_backup.py drill   [--dump backups/<file>.dump]  # into a throwaway container
    python scripts/db_backup.py prune   [--keep-daily 7 --keep-weekly 4]
    python scripts/db_backup.py check   [--max-age-hours 26]  # alert ALR-03 FleetBackupStale

Automation level 1 ("scripted"): each RB-001 step is one command; a human decides when to run it.

``drill`` proves that a backup can actually be restored: it starts a disposable ``postgres:16``
container, restores the dump there with ``pg_restore``, and compares every table with the source
database. Tables that only receive inserts while the drill runs (telemetry) must have a restored row
count between the source counts measured just before and just after the dump; all other tables must
match exactly. The elapsed restore time is the measured RTO component of the database. Exit code 1
on any mismatch. Dumps are written to ``backups/`` (git-ignored) with a ``.sha256`` next to them.
"""

import argparse
import hashlib
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "backups"
DRILL_CONTAINER = "fleet-restore-drill"
DRILL_IMAGE = "postgres:16-alpine"
APPEND_ONLY = {"telemetry_readings", "audit_events", "user_activity", "analytics_events"}
COUNT_TABLES_SQL = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


class Stack:
    def __init__(self, project: str, env_file: str) -> None:
        self.base = ["docker", "compose", "-p", project, "--env-file", env_file]

    def compose(self, *args: str, **kwargs) -> subprocess.CompletedProcess:
        return run([*self.base, *args], **kwargs)

    def db_sh(self, script: str, **kwargs) -> subprocess.CompletedProcess:
        return self.compose("exec", "-T", "db", "sh", "-c", script, **kwargs)

    def psql(self, sql: str) -> str:
        script = f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "{sql}"'
        return self.db_sh(script, capture_output=True, text=True).stdout.strip()

    def counts(self) -> dict[str, int]:
        return table_counts(self.psql)


def table_counts(psql) -> dict[str, int]:
    tables = psql(COUNT_TABLES_SQL).split()
    if not tables:
        return {}
    # Table names come from pg_tables (lowercase identifiers), so no quoting is needed — and the
    # same SQL works both through `sh -c "psql -c ..."` and a direct `docker exec psql -c ...`.
    union = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM {t}" for t in tables)
    rows = psql(union).splitlines()
    return {name: int(count) for name, count in (row.split("|") for row in rows)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(stack: Stack) -> tuple[Path, dict[str, int], dict[str, int]]:
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUPS / f"fleet_{stamp}.dump"
    before = stack.counts()
    log(f"backup: pg_dump -Fc -> {target.relative_to(ROOT)}")
    started = time.monotonic()
    with target.open("wb") as out:
        stack.db_sh('pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', stdout=out)
    after = stack.counts()
    digest = sha256(target)
    target.with_suffix(".dump.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    size_kib = target.stat().st_size / 1024
    log(f"backup: done in {time.monotonic() - started:.1f} s, {size_kib:.1f} KiB, sha256 {digest}")
    return target, before, after


def latest_dump() -> Path:
    dumps = sorted(BACKUPS.glob("fleet_*.dump"))
    if not dumps:
        raise SystemExit("no dumps in backups/ — run `backup` first")
    return dumps[-1]


def verify_checksum(dump: Path) -> None:
    expected = dump.with_suffix(".dump.sha256").read_text(encoding="utf-8").split()[0]
    if sha256(dump) != expected:
        raise SystemExit(f"checksum mismatch for {dump.name}: backup is corrupted")
    log(f"checksum OK ({expected[:16]}…)")


def restore(stack: Stack, dump: Path) -> None:
    verify_checksum(dump)
    log("restore: stopping writers (api1..3, worker) — dependency order: DB first, then app")
    stack.compose("stop", "api1", "api2", "api3", "worker")
    with dump.open("rb") as src:
        stack.db_sh(
            'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner',
            stdin=src,
        )
    log("restore: starting app tier")
    stack.compose("up", "-d", "api1", "api2", "api3", "worker", "nginx")
    log("restore: done — verify with RB-001 step 'Верифікація'")


def _drill_psql(sql: str) -> str:
    cmd = [
        "docker",
        "exec",
        DRILL_CONTAINER,
        "psql",
        "-U",
        "drill",
        "-d",
        "drill",
        "-At",
        "-c",
        sql,
    ]
    return run(cmd, capture_output=True, text=True).stdout.strip()


def _start_drill_db() -> None:
    subprocess.run(["docker", "rm", "-f", DRILL_CONTAINER], capture_output=True)
    env = ["-e", "POSTGRES_USER=drill", "-e", "POSTGRES_PASSWORD=drill", "-e", "POSTGRES_DB=drill"]
    run(["docker", "run", "-d", "--name", DRILL_CONTAINER, *env, DRILL_IMAGE], capture_output=True)
    for _ in range(60):
        ready = subprocess.run(
            ["docker", "exec", DRILL_CONTAINER, "pg_isready", "-U", "drill", "-d", "drill"],
            capture_output=True,
        )
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise SystemExit("drill database did not become ready")


def compare(restored: dict[str, int], before: dict[str, int], after: dict[str, int]) -> list[str]:
    problems = []
    for table in sorted(set(before) | set(restored)):
        got, low, high = restored.get(table), before.get(table), after.get(table, before.get(table))
        if got is None or low is None:
            problems.append(f"{table}: missing on one side (restored={got}, source={low})")
        elif table in APPEND_ONLY and not low <= got <= high:
            problems.append(f"{table}: restored {got} not within source [{low}, {high}]")
        elif table not in APPEND_ONLY and got != low:
            problems.append(f"{table}: restored {got} != source {low}")
    return problems


def drill(stack: Stack, dump: Path | None) -> int:
    if dump is None:
        dump, before, after = backup(stack)
    else:
        before = after = stack.counts()
    verify_checksum(dump)
    log(f"drill: throwaway {DRILL_IMAGE} container '{DRILL_CONTAINER}'")
    _start_drill_db()
    try:
        started = time.monotonic()
        with dump.open("rb") as src:
            run(
                [
                    "docker",
                    "exec",
                    "-i",
                    DRILL_CONTAINER,
                    "pg_restore",
                    "-U",
                    "drill",
                    "-d",
                    "drill",
                    "--no-owner",
                    "--exit-on-error",
                ],
                stdin=src,
            )
        elapsed = time.monotonic() - started
        restored = table_counts(_drill_psql)
        version = _drill_psql("SELECT version_num FROM alembic_version")
    finally:
        subprocess.run(["docker", "rm", "-f", DRILL_CONTAINER], capture_output=True)
    print(f"{'table':<22} {'source(before)':>15} {'source(after)':>14} {'restored':>9}")
    for table in sorted(restored):
        low, high = before.get(table, "-"), after.get(table, "-")
        print(f"{table:<22} {low:>15} {high:>14} {restored[table]:>9}")
    problems = compare(restored, before, after)
    log(f"drill: pg_restore {elapsed:.1f} s, alembic head {version}, tables {len(restored)}")
    for problem in problems:
        log(f"drill: MISMATCH {problem}")
    log(f"restore drill: {'FAIL' if problems else 'PASS'}")
    return 1 if problems else 0


def prune(keep_daily: int, keep_weekly: int) -> None:
    """Retention: newest dump per day for `keep_daily` days, per ISO week for `keep_weekly`."""
    dumps = sorted(BACKUPS.glob("fleet_*.dump"), reverse=True)
    now = datetime.now(UTC)
    keep: set[Path] = set()
    seen_days, seen_weeks = set(), set()
    for dump in dumps:
        taken = datetime.strptime(dump.stem.split("_")[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        day, week = taken.date(), taken.isocalendar()[:2]
        if now - taken <= timedelta(days=keep_daily) and day not in seen_days:
            seen_days.add(day)
            keep.add(dump)
        if now - taken <= timedelta(weeks=keep_weekly) and week not in seen_weeks:
            seen_weeks.add(week)
            keep.add(dump)
    for dump in dumps:
        if dump not in keep:
            log(f"prune: removing {dump.name}")
            dump.unlink()
            dump.with_suffix(".dump.sha256").unlink(missing_ok=True)
    log(f"prune: kept {len(keep)} of {len(dumps)} dumps")


def check(max_age_hours: float) -> int:
    """Exit 1 when the newest dump is missing, corrupted or older than max_age_hours."""
    dumps = sorted(BACKUPS.glob("fleet_*.dump"))
    if not dumps:
        log("check: FAIL no backups at all")
        return 1
    newest = dumps[-1]
    taken = datetime.strptime(newest.stem.split("_")[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    age_h = (datetime.now(UTC) - taken).total_seconds() / 3600
    intact = sha256(newest) == newest.with_suffix(".dump.sha256").read_text().split()[0]
    ok = intact and age_h <= max_age_hours
    log(f"check: newest {newest.name}, age {age_h:.1f} h, sha256 {'OK' if intact else 'BAD'}")
    log(f"backup freshness: {'PASS' if ok else 'FAIL'} (limit {max_age_hours} h)")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["backup", "restore", "drill", "prune", "check"])
    parser.add_argument("--project", default="fleet_sandbox")
    parser.add_argument("--env-file", default=".env.sandbox")
    parser.add_argument("--dump", type=Path)
    parser.add_argument("--keep-daily", type=int, default=7)
    parser.add_argument("--keep-weekly", type=int, default=4)
    parser.add_argument("--max-age-hours", type=float, default=26.0)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    stack = Stack(args.project, args.env_file)
    if args.command == "backup":
        backup(stack)
    elif args.command == "restore":
        restore(stack, args.dump or latest_dump())
    elif args.command == "drill":
        return drill(stack, args.dump)
    elif args.command == "check":
        return check(args.max_age_hours)
    else:
        prune(args.keep_daily, args.keep_weekly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
