from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from .core import connect, initialize, stable_hash, transition_candidate, utc_now
from .observer import observe_repository, persist_snapshot, write_snapshot
from .needs import approve_need_proposal, list_needs, propose_needs
from .report import render_daily_report


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schema"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("--db", type=Path, default=Path("work/radar.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("self-test")
    report = sub.add_parser("report")
    report.add_argument("--date", required=True)
    report.add_argument("--output", type=Path)
    scan = sub.add_parser("scan-github")
    scan.add_argument("--config", type=Path, required=True)
    observe = sub.add_parser("observe")
    observe.add_argument("repository", type=Path)
    observe.add_argument("--output", type=Path)
    observe.add_argument("--repo-key")
    observe.add_argument("--full-name")
    needs = sub.add_parser("needs")
    needs_sub = needs.add_subparsers(dest="needs_command", required=True)
    needs_propose = needs_sub.add_parser("propose")
    needs_propose.add_argument("--repo-key", required=True)
    needs_list = needs_sub.add_parser("list")
    needs_list.add_argument("--repo-key", required=True)
    needs_approve = needs_sub.add_parser("approve")
    needs_approve.add_argument("proposal_id")
    needs_approve.add_argument("--approved-by", required=True)
    return parser


def run_self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        connection = connect(Path(directory) / "test.db")
        try:
            initialize(connection, SCHEMA_PATH)
            now = utc_now()
            with connection:
                connection.execute(
                    "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                    ("src-1", "github", "owner/repo", stable_hash("github", "owner/repo"), now, now),
                )
                connection.execute(
                    "INSERT INTO source_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("sv-1", "src-1", stable_hash("content"), stable_hash("content"), None, now, "{}"),
                )
                connection.execute(
                    "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?)",
                    ("cand-1", "sv-1", "DISCOVERED", None, now, now),
                )
            first = transition_candidate(
                connection,
                candidate_id="cand-1",
                new_status="FETCHED",
                reason="self_test",
                operation_type="fetch",
                input_version="v1",
                worker_version="self-test-v1",
            )
            duplicate = transition_candidate(
                connection,
                candidate_id="cand-1",
                new_status="FETCHED",
                reason="self_test",
                operation_type="fetch",
                input_version="v1",
                worker_version="self-test-v1",
            )
            event_count = connection.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0]
            state = connection.execute(
                "SELECT current_status FROM candidates WHERE id='cand-1'"
            ).fetchone()[0]
            assert first is True and duplicate is False
            assert event_count == 1 and state == "FETCHED"
            try:
                connection.execute("DELETE FROM candidate_events")
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("append-only trigger failed")
        finally:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        run_self_test()
        print("SELF_TEST=PASS")
        return 0
    if args.command == "scan-github":
        print(
            "scan-github henüz etkin değil: doğrulanmış repo adresleri ve GitHub istemcisi gerekli.",
            file=sys.stderr,
        )
        return 2
    if args.command == "observe":
        snapshot = observe_repository(args.repository)
        if args.output:
            write_snapshot(snapshot, args.output)
            print(f"SNAPSHOT_WRITTEN={args.output}")
        connection = connect(args.db)
        initialize(connection, SCHEMA_PATH)
        result = persist_snapshot(
            connection,
            repo_key=args.repo_key or args.repository.resolve().name,
            full_name=args.full_name or args.repository.resolve().name,
            snapshot=snapshot,
        )
        print(f"FILES_OBSERVED={snapshot['file_count']}")
        print(f"SNAPSHOT_HASH={snapshot['snapshot_hash']}")
        print(f"REPO_CHANGED={str(result['changed']).lower()}")
        print(f"CHANGES={len(result['changes'])}")
        print(f"IMPACTED_CONTEXT={len(result['impacted_context'])}")
        return 0

    if args.command == "needs":
        connection = connect(args.db)
        initialize(connection, SCHEMA_PATH)
        if args.needs_command == "propose":
            proposals = propose_needs(connection, args.repo_key)
            print(json.dumps(proposals, ensure_ascii=False, indent=2))
            print(f"PROPOSALS={len(proposals)}")
            return 0
        if args.needs_command == "list":
            needs = list_needs(connection, args.repo_key)
            print(json.dumps(needs, ensure_ascii=False, indent=2))
            print(f"ACTIVE_NEEDS={len(needs)}")
            return 0
        if args.needs_command == "approve":
            need = approve_need_proposal(connection, args.proposal_id, args.approved_by)
            print(json.dumps(need, ensure_ascii=False, indent=2))
            return 0

    connection = connect(args.db)
    if args.command == "init":
        initialize(connection, SCHEMA_PATH)
        print(f"DATABASE_INITIALIZED={args.db}")
        return 0
    if args.command == "report":
        text = render_daily_report(connection, args.date)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(f"REPORT_WRITTEN={args.output}")
        else:
            print(text)
        return 0
    return 1
