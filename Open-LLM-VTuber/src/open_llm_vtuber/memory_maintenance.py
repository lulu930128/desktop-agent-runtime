"""Explicit, resumable maintenance through the existing History, Repository and Index owners."""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from contextlib import closing, nullcontext
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from .character_memory_manager import (
    _MEMORY_REPOSITORY,
    _contains_sensitive_data,
    infer_memory_delete_plan,
    process_character_memory_turn,
    suppressed_sources,
)
from .character_memory_lifecycle import review_digest
from .character_memory_migration import file_digest
from .character_memory_repository import (
    CharacterMemoryRepository,
    store_lock,
    memory_namespaces,
)
from .chat_history_manager import _get_safe_history_path, _write_history
from .conversation_history_index import (
    _CONVERSATION_HISTORY_INDEX,
    ConversationHistoryIndex,
)
from .memory_formation import read_policy
from .memory_semantics import local_encoder


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _prepare(rows, character, uid, project, include_legacy):
    if not isinstance(rows, list) or not all(isinstance(m, dict) for m in rows):
        raise ValueError("invalid_history")
    messages = [m for m in rows if m.get("role") != "metadata"]
    counts = Counter()
    selected = []
    changed = False
    for index, human in enumerate(messages):
        if human.get("role") not in {"human", "user"}:
            continue
        if human.get("project_id", "") != project:
            counts["different_project"] += 1
            continue
        assistant = messages[index + 1] if index + 1 < len(messages) else {}
        if assistant.get("role") not in {"ai", "assistant"}:
            counts["unpaired"] += 1
            continue
        content = human.get("content")
        if not isinstance(content, str) or not isinstance(
            assistant.get("content"), str
        ):
            raise ValueError("invalid_message")
        if _contains_sensitive_data(content) or _contains_sensitive_data(
            assistant["content"]
        ):
            counts["sensitive"] += 1
            continue
        if infer_memory_delete_plan(content).skip_write:
            counts["historical_privacy_request"] += 1
            continue
        turn = human.get("turn_id")
        if not turn:
            if not include_legacy or assistant.get("turn_id"):
                counts["legacy_unselected"] += 1
                continue
            turn = _digest([character, uid, index, human.get("timestamp"), content])
            human.update(turn_id=turn, completion="received")
            assistant.update(turn_id=turn, completion="legacy_unknown")
            changed = True
        if turn != assistant.get("turn_id") or assistant.get("completion") not in {
            "complete",
            "legacy_unknown",
        }:
            counts["incomplete"] += 1
            continue
        selected.append((human, assistant))
    return selected, counts, changed


def backfill(
    character,
    *,
    project="",
    histories=None,
    include_legacy=False,
    facts=False,
    apply=False,
    index=None,
):
    """The caller selects a concrete character, project (empty = unbound) and optional history IDs."""
    index = index or _CONVERSATION_HISTORY_INDEX
    directory = Path(_get_safe_history_path(character, "probe")).parent
    if not directory.is_dir():
        raise FileNotFoundError("History directory unavailable")
    rule = read_policy(_MEMORY_REPOSITORY, character, project) if facts else None
    if facts and not rule:
        raise ValueError("No matching fact formation grant")
    encoder = local_encoder()
    if facts and not encoder:
        raise ValueError("Selected semantic extractor unavailable")
    job = _digest(
        [
            "memory-backfill-v3",
            character,
            project,
            sorted(histories) if histories is not None else None,
            include_legacy,
            facts,
            rule,
            encoder.revision if encoder else "lexical",
        ]
    )
    results = {}
    if apply:
        with closing(index._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS companion_backfill(job TEXT,source TEXT,revision TEXT,"
                "receipt TEXT,PRIMARY KEY(job,source))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS companion_runs(job TEXT PRIMARY KEY, character TEXT, project TEXT, updated TEXT)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO companion_runs VALUES(?,?,?,CURRENT_TIMESTAMP)",
                (job, character, project),
            )
    visited = {}
    while True:
        paths = (
            sorted(directory.glob("*.json"))
            if histories is None
            else [
                Path(_get_safe_history_path(character, h))
                for h in sorted(set(histories))
            ]
        )
        for path in paths:
            uid = path.stem
            try:
                revision = file_digest(path)
                if visited.get(uid) == revision:
                    continue
                visited[uid] = revision
                if apply:
                    with closing(index._connect()) as conn:
                        row = conn.execute(
                            "SELECT receipt FROM companion_backfill WHERE job=? AND source=? AND revision=?",
                            (job, uid, revision),
                        ).fetchone()
                    if row:
                        cached = json.loads(row[0])
                        if cached["status"] != "failed":
                            results[uid] = cached
                            continue
                rows = json.loads(path.read_bytes())
                selected, excluded, changed = _prepare(
                    rows, character, uid, project, include_legacy
                )
                # Unbound historical forget instructions have no auditable target. Preserve the original;
                # local review can later bind the suppressed spans before enabling historical processing.
                if excluded.get("historical_privacy_request") and any(
                    m.get("role") in {"human", "user"}
                    and not m.get("turn_id")
                    and infer_memory_delete_plan(str(m.get("content", ""))).skip_write
                    for m in rows
                ):
                    excluded["unknown_forget_target"] += len(selected)
                    selected, changed = [], False
                suppressed = (
                    suppressed_sources(character, project)
                    if apply
                    else {
                        (history, turn)
                        for ns in memory_namespaces(character, project)
                        for actor, history, turn in _MEMORY_REPOSITORY.load(ns).get(
                            "suppressed_spans", []
                        )
                        if actor == character
                    }
                )
                blocked_turns = {turn for _, turn in suppressed}
                written = eligible = 0
                if apply and changed:
                    with store_lock(path):
                        if file_digest(path) != revision:
                            raise ValueError("source_changed")
                        pending = directory / ".index-pending"
                        pending.mkdir(exist_ok=True)
                        (pending / path.name).touch()
                        _write_history(path, rows)
                        revision = file_digest(path)
                        visited[uid] = revision
                with store_lock(path, wait=True) if apply and facts else nullcontext():
                    if apply and facts and file_digest(path) != revision:
                        raise ValueError("source_changed")
                    for human, assistant in selected:
                        if human["turn_id"] in blocked_turns:
                            excluded["suppressed"] += 1
                            continue
                        eligible += 1
                        if apply and facts:
                            if not human.get("timestamp"):
                                excluded["unknown_source_time"] += 1
                                continue
                            modified, _ = process_character_memory_turn(
                                conf_uid=character,
                                history_uid=uid,
                                turn_id=human["turn_id"],
                                project_id=project,
                                user_text=human["content"],
                                assistant_text="",
                                observed_at=human["timestamp"],
                                backfill=True,
                                policy_digest=review_digest(rule),
                            )
                            written += int(modified)
                if apply:
                    index._refresh(
                        character, path, directory / ".index-pending" / path.name
                    )
                receipt = {
                    "status": "processed" if apply else "dry_run",
                    "eligible_turns": eligible,
                    "excluded": dict(excluded),
                    "fact_writes": written,
                }
            except (
                ValueError,
                OSError,
                KeyError,
                TypeError,
                RuntimeError,
                sqlite3.Error,
            ) as exc:
                reason = (
                    str(exc)
                    if str(exc)
                    in {
                        "source_changed",
                        "invalid_history",
                        "invalid_message",
                        "formation_policy_changed",
                    }
                    else type(exc).__name__
                )
                receipt = {"status": "failed", "reason": reason}
                revision = visited.get(uid, "")
            results[uid] = receipt
            if apply:
                with closing(index._connect()) as conn, conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO companion_backfill VALUES(?,?,?,?)",
                        (job, uid, revision, json.dumps(receipt)),
                    )
        if not apply or all(
            p.stem in results
            and (
                results[p.stem]["status"] == "failed"
                or (p.is_file() and visited.get(p.stem) == file_digest(p))
            )
            for p in (directory.glob("*.json") if histories is None else paths)
        ):
            break
    failed = sum(r["status"] == "failed" for r in results.values())
    return {
        "job_id": job,
        "sources": len(results),
        "failed": failed,
        "remaining": failed,
        "receipts": results,
    }


def processing_status(root, character, project):
    """Inspect completed source receipts without starting a scan or creating an index."""
    directory = (
        Path(root)
        / Path(_get_safe_history_path(character, "probe")).parent
        / ".formation-pending"
    )
    pending = unknown = 0
    for path in directory.glob("*.json"):
        try:
            marker = json.loads(path.read_bytes())
            if "project_id" not in marker:
                unknown += 1
            elif marker["project_id"] == project:
                pending += 1
        except (OSError, ValueError, TypeError):
            unknown += 1
    queue = {"pending_turns": pending, "unresolved_turns": unknown}
    db = Path(root) / "memories/conversation_history.sqlite3"
    if not db.is_file():
        return {**queue, "state": "unbuilt", "processed": 0, "failures": {}}
    try:
        with closing(
            sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        ) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            failures = {}
            if "history_failures" in tables:
                for reason, count in conn.execute(
                    "SELECT reason,count(*) FROM history_failures WHERE conf_uid=? GROUP BY reason",
                    (character,),
                ):
                    failures[reason] = count
            processed = 0
            if {"companion_runs", "companion_backfill"} <= tables:
                latest = conn.execute(
                    "SELECT job FROM companion_runs WHERE character=? AND project=? ORDER BY updated DESC,rowid DESC LIMIT 1",
                    (character, project),
                ).fetchone()
                if latest:
                    for status, reason, count in conn.execute(
                        "SELECT json_extract(receipt,'$.status'),json_extract(receipt,'$.reason'),count(*) FROM companion_backfill WHERE job=? GROUP BY 1,2",
                        latest,
                    ):
                        if status == "failed":
                            failures[reason] = failures.get(reason, 0) + count
                        else:
                            processed += count
            return {
                **queue,
                "state": "degraded" if failures else "available",
                "processed": processed,
                "failures": failures,
            }
    except sqlite3.Error as exc:
        return {
            **queue,
            "state": "degraded",
            "processed": 0,
            "failures": {type(exc).__name__: 1},
        }


def _sources(root):
    patterns = (
        "chat_history/*/*.json",
        "chat_history/*/*.events.jsonl",
        "chat_history/*/.formation-pending/*.json",
        "memories/characters/*/long_term.json",
        "memories/shared/user/long_term.json",
        "memories/shared/project/*/long_term.json",
        "memories/formation-policy.json",
    )
    files = sorted({p for pattern in patterns for p in root.glob(pattern)})
    for path in files:
        if path.resolve() != path or not path.is_file():
            raise ValueError("Snapshot source redirects outside its canonical location")
    return files


def backup(root, archive):
    root, archive = Path(root).resolve(strict=True), Path(archive).absolute()
    if not (root / "chat_history").is_dir() and not (root / "memories").is_dir():
        raise ValueError("Missing source roots")
    files = _sources(root)
    manifest = {p.relative_to(root).as_posix(): file_digest(p) for p in files}
    with tempfile.TemporaryDirectory(dir=archive.parent) as tmp:
        staging = Path(tmp) / "snapshot.zip"
        with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_DEFLATED) as out:
            for path in files:
                out.write(path, path.relative_to(root).as_posix())
            if manifest != {
                p.relative_to(root).as_posix(): file_digest(p) for p in _sources(root)
            }:
                raise ValueError(
                    "Source changed during backup; retry with a consistent source"
                )
            out.writestr(
                "manifest.json",
                json.dumps({"version": 1, "files": manifest}, sort_keys=True),
            )
        _verify_archive(staging)
        if os.name == "nt":
            os.rename(
                staging, archive
            )  # Windows rejects a destination created concurrently.
        else:
            os.link(staging, archive)
    return {"files": len(files), "sha256": file_digest(archive)}


def _verify_archive(archive):
    with zipfile.ZipFile(archive) as src:
        manifest = json.loads(src.read("manifest.json"))
        files = manifest["files"]
        if manifest["version"] != 1 or sorted(src.namelist()) != sorted(
            [*files, "manifest.json"]
        ):
            raise ValueError("Archive inventory mismatch")
        import re

        allowed = re.compile(
            r"(?:chat_history/[^/]+/(?:[^/]+\.(?:json|events\.jsonl)|\.formation-pending/[A-Za-z0-9_-]+\.json)|memories/(?:formation-policy\.json|(?:characters/[^/]+|shared/user|shared/project/[0-9a-f]{64})/long_term\.json))"
        )
        seen = set()
        for name, expected in files.items():
            if (
                not allowed.fullmatch(name)
                or any(c in name for c in "\\:")
                or any(
                    p in {".", ".."} or p.endswith((".", " ")) or Path(p).is_reserved()
                    for p in name.split("/")
                )
                or name.casefold() in seen
            ):
                raise ValueError("Invalid archive member")
            seen.add(name.casefold())
            if hashlib.sha256(src.read(name)).hexdigest() != expected:
                raise ValueError("Archive digest mismatch")
        return files


def restore(archive, destination):
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(
            "Restore requires a new destination; existing updates preserved"
        )
    files = _verify_archive(archive)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        staging = Path(tmp) / "restore"
        staging.mkdir()
        with zipfile.ZipFile(archive) as src:
            for name, expected in files.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as out:
                    out.write(src.read(name))
                if file_digest(target) != expected:
                    raise ValueError("Restore verification failed")
        staging.rename(destination)
    return {"files": len(files), "verified": True}


def rebuild_copy(source, destination, characters, *, projects=()):
    """Restore canonical state in a new root and validate rebuilt projections before publication."""
    from .character_memory_sql_index import SQLiteMemoryIndex

    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError("Repair requires a new destination")
    characters = sorted(set(characters))
    if not characters:
        raise ValueError("Choose the source characters to index")
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        staging = Path(tmp) / "staging"
        archive = Path(tmp) / "source.zip"
        original = backup(source, archive)
        restore(archive, staging)
        repo = CharacterMemoryRepository(root=staging / "memories")
        history = ConversationHistoryIndex(
            db_path=repo.root() / "conversation_history.sqlite3", repository=repo
        )
        l3 = SQLiteMemoryIndex(repository=repo)
        previous = Path.cwd()
        prior_root = os.environ.get("KURO_MEMORY_ROOT")
        # CLI-only offline operation. All History paths resolve inside the restored copy.
        try:
            os.chdir(staging)
            os.environ["KURO_MEMORY_ROOT"] = str(repo.root())
            for actor in characters:
                history.sync(actor)
                for project in ("", *projects):
                    for namespace in memory_namespaces(actor, project):
                        if repo.store_path(namespace).is_file():
                            l3.refresh(namespace)
            with closing(history._connect()) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Rebuilt history index integrity check failed")
                sources = conn.execute(
                    "SELECT count(*) FROM history_sources"
                ).fetchone()[0]
                failures = dict(
                    conn.execute(
                        "SELECT reason,count(*) FROM history_failures GROUP BY reason"
                    )
                )
            if l3.db_path().is_file():
                with closing(l3._connect()) as conn:
                    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Rebuilt fact index integrity check failed")
        finally:
            os.chdir(previous)
            if prior_root is None:
                os.environ.pop("KURO_MEMORY_ROOT", None)
            else:
                os.environ["KURO_MEMORY_ROOT"] = prior_root
        if failures:
            return {
                "published": False,
                "failed": sum(failures.values()),
                "reasons": failures,
            }
        staging.rename(destination)
    return {
        "published": True,
        "failed": 0,
        "indexed_sources": sources,
        "source_archive_sha256": original["sha256"],
    }


def migrate_scopes(source, destination, *, projects=()):
    """Stage a byte-verified canonical snapshot and promote only explicit existing scope IDs."""
    from .character_memory_migration import inventory

    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError("Scope migration requires a new destination")
    counts = Counter()
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        archive = Path(tmp) / "source.zip"
        receipt = backup(source, archive)
        staging = Path(tmp) / "next"
        restore(archive, staging)
        repo = CharacterMemoryRepository(root=staging / "memories")
        for path in sorted((repo.root() / "characters").glob("*/long_term.json")):
            actor = path.parent.name
            store = repo.load(actor)
            inventory(store)
            retained = []
            for entry in store["entries"]:
                level, identity = entry.get("scope_level"), entry.get("scope_id")
                if level == "global_user" and identity == "local-user":
                    target = memory_namespaces(actor)[1]
                elif level == "project" and identity in projects and identity != actor:
                    target = memory_namespaces(actor, identity)[-1]
                else:
                    retained.append(entry)
                    counts[
                        "unresolved"
                        if level in {"global_user", "project"}
                        else "actor_retained"
                    ] += 1
                    continue
                shared = repo.load(target)
                match = next(
                    (e for e in shared["entries"] if e.get("id") == entry["id"]), None
                )
                if match is not None and match != entry:
                    raise ValueError("Conflicting memory ID across namespaces")
                if match is None:
                    shared["entries"].append(entry)
                    repo.save(target, shared)
                counts["moved"] += 1
            if len(retained) != len(store["entries"]):
                store["entries"] = retained
                repo.save(actor, store)
        staging.rename(destination)
    return {
        "source_archive_sha256": receipt["sha256"],
        "counts": dict(counts),
        "verified": True,
    }


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("backup", "restore"):
        cmd = commands.add_parser(action)
        cmd.add_argument("root", type=Path)
        cmd.add_argument("archive", type=Path)
    recovery = commands.add_parser("rebuild-copy")
    recovery.add_argument("root", type=Path)
    recovery.add_argument("destination", type=Path)
    recovery.add_argument("--character", action="append", required=True)
    recovery.add_argument("--project", action="append", default=[])
    scope_cmd = commands.add_parser("migrate-scopes")
    scope_cmd.add_argument("root", type=Path)
    scope_cmd.add_argument("destination", type=Path)
    scope_cmd.add_argument("--project", action="append", default=[])
    cmd = commands.add_parser("backfill")
    cmd.add_argument("root", type=Path)
    cmd.add_argument("character")
    cmd.add_argument("--project", default="")
    cmd.add_argument("--history", action="append")
    cmd.add_argument("--include-legacy", action="store_true")
    cmd.add_argument("--facts", action="store_true")
    cmd.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.action == "backup":
        result = backup(args.root, args.archive)
    elif args.action == "rebuild-copy":
        result = rebuild_copy(
            args.root, args.destination, args.character, projects=args.project
        )
    elif args.action == "migrate-scopes":
        result = migrate_scopes(args.root, args.destination, projects=args.project)
    elif args.action == "restore":
        result = restore(args.archive, args.root)
    else:
        os.chdir(args.root.resolve(strict=True))
        os.environ["KURO_MEMORY_ROOT"] = str(Path.cwd() / "memories")
        result = backfill(
            args.character,
            project=args.project,
            histories=args.history,
            include_legacy=args.include_legacy,
            facts=args.facts,
            apply=args.apply,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result.get("failed")))


if __name__ == "__main__":
    raise SystemExit(main())
