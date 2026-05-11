#!/usr/bin/env python3
"""Manual S3 connectivity & shape check.

Run via 'make check-s3'. Checks:
 - S3 credentials usable (list_buckets)
 - target bucket exists (from config paths, e.g., 'media')
 - 'podcasts/' root under that bucket is either empty or matches configured shows.

Exit codes:
 0 OK
 1 check failures (bucket missing or shape mismatch)
 2 missing S3 env vars
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, cast

from botocore.exceptions import ClientError

from src.app_common import load_podcasts_config
from src.application.context import AppContext
from src.orchestration.download_client import s3_prefix
from src.ports import require_secrets

_REQUIRED_S3_KEYS = ("S3_USERNAME", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_REGION")
_S3_CHECK_ERRORS = (OSError, RuntimeError, TypeError, ValueError)


def load_configs() -> List:
    return load_podcasts_config(include=["config/*.toml"], skip_schedule_filter=True)


def expected_slugs_by_bucket(configs: List) -> Dict[str, Dict[str, Set[str]]]:
    """Return mapping bucket -> root -> set(slugs).

    Example: { 'media': { 'podcasts': {'last-week-tonight', 'coffeezilla'} } }
    """
    d: Dict[str, Dict[str, Set[str]]] = {}
    for cfg in configs:
        bucket, prefix = s3_prefix(cfg)
        parts = Path(prefix).parts
        if not parts:
            continue
        root = parts[0]
        slug = parts[1] if len(parts) > 1 else None
        d.setdefault(bucket, {}).setdefault(root, set())
        if slug:
            d[bucket][root].add(slug)
    return d


def head_bucket_exists(client, bucket: str) -> Tuple[bool, bool, str]:
    """Return (exists, accessible, message)."""
    try:
        client.head_bucket(Bucket=bucket)
        return True, True, ""
    except ClientError as exc:
        err = exc.response.get("Error", {})
        code = err.get("Code", "")
        # AccessDenied likely means bucket exists but not accessible
        if code in ("403", "AccessDenied") or "AccessDenied" in str(exc):
            return True, False, "AccessDenied"
        if code in ("404", "NoSuchBucket") or "404" in str(exc) or "Not Found" in str(exc):
            return False, False, "NotFound"
        return False, False, str(exc)
    except _S3_CHECK_ERRORS as exc:
        return False, False, str(exc)


def list_child_names(client, bucket: str, root: str) -> Tuple[Set[str], bool]:
    """Return (child_names, contents_found).

    child_names are the immediate child directory or file names under root/.
    """
    prefix = root.rstrip("/") + "/"
    paginator = client.get_paginator("list_objects_v2")
    params = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/"}
    child_names: Set[str] = set()
    contents_found = False
    try:
        for page in paginator.paginate(**params):
            for cp in page.get("CommonPrefixes", []):
                p = cp.get("Prefix", "")
                rel = p[len(prefix) :].strip("/")
                if rel:
                    child_names.add(rel.split("/")[0])
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if key == prefix:
                    continue
                contents_found = True
                rel = key[len(prefix) :].strip("/")
                if rel:
                    child_names.add(rel.split("/")[0])
        return child_names, contents_found
    except ClientError:
        raise


def main() -> int:
    ctx = AppContext.from_env()
    s3_service = cast(Any, ctx.s3)

    try:
        require_secrets(ctx.secrets, _REQUIRED_S3_KEYS)
    except _S3_CHECK_ERRORS as exc:
        print(f"S3 environment not configured: {exc}", file=sys.stderr)
        return 2

    client = s3_service.get_client()
    try:
        client.list_buckets()
    except _S3_CHECK_ERRORS as exc:
        print(f"Credential check failed: {exc}", file=sys.stderr)
        return 1
    print("S3 credentials appear valid (list_buckets succeeded).")

    configs = load_configs()
    expected = expected_slugs_by_bucket(configs)

    buckets_to_check = set(expected.keys())
    # ensure common bucket 'media' is checked too
    buckets_to_check.add("media")

    overall_ok = True
    for bucket in sorted(buckets_to_check):
        print(f"\nChecking bucket: {bucket}")
        exists_flag, accessible, msg = head_bucket_exists(client, bucket)
        if not exists_flag:
            print(f"  ERROR: bucket '{bucket}' not found ({msg})", file=sys.stderr)
            overall_ok = False
            continue
        if not accessible:
            print(f"  ERROR: cannot access bucket '{bucket}' ({msg})", file=sys.stderr)
            overall_ok = False
            continue
        print("  Bucket exists and is reachable.")

        bucket_expected = expected.get(bucket, {})
        roots = set(bucket_expected.keys()) or {"podcasts"}
        for root in sorted(roots):
            print(f"  Inspecting prefix: {root}/")
            try:
                actual_children, contents_found = list_child_names(client, bucket, root)
            except _S3_CHECK_ERRORS as exc:
                print(f"    ERROR listing '{root}/': {exc}", file=sys.stderr)
                overall_ok = False
                continue

            if not actual_children:
                print(f"    OK: '{root}/' appears empty.")
                continue

            expected_children = bucket_expected.get(root, set())
            if not expected_children:
                print(
                    f"    NOTE: found {len(actual_children)} entries under '{root}/'"
                    " but no configured podcasts to compare against."
                )
                print(f"    Entries: {sorted(actual_children)[:20]}")
                # do not mark as failure
                continue

            missing = expected_children - actual_children
            extra = actual_children - expected_children
            if missing or extra:
                expected_length = len(expected_children)
                actual_length = len(actual_children)
                print(
                    f"    MISMATCH: expected {expected_length} entries, found {actual_length}.",
                    file=sys.stderr,
                )
                if missing:
                    print(f"      Missing: {sorted(missing)}", file=sys.stderr)
                if extra:
                    print(f"      Extra: {sorted(extra)}", file=sys.stderr)
                overall_ok = False
            else:
                length = len(actual_children)
                print(f"    OK: '{root}/' children match configured podcasts ({length}).")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
