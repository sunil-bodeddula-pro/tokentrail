"""Unit tests. Standard library only: python3 -m unittest discover -s tests (pytest also runs them).

Fixtures are written to a temporary directory; nothing touches the network or your real agent logs.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tokentrail.adapters import ClaudeCodeAdapter, GenericJsonlAdapter
from tokentrail.analytics import kpis, roi
from tokentrail.git_collector import parse_log
from tokentrail.models import Health, TaskRun
from tokentrail.pricing import Pricing
from tokentrail.segment import build_runs, classify


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def claude_transcript(session="s1", model="claude-opus-5-5"):
    """Two prompts. The first response is logged as two lines sharing one message id (as Claude Code does)."""
    usage = {
        "input_tokens": 10,
        "output_tokens": 100,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 90,
        "output_tokens_details": {"thinking_tokens": 40},
    }
    base = {"sessionId": session, "cwd": "/tmp/proj", "isSidechain": False}
    return [
        {**base, "type": "ai-title", "aiTitle": "Fix the parser"},
        {
            **base,
            "type": "user",
            "timestamp": "2026-11-01T10:00:00Z",
            "message": {"role": "user", "content": "Fix the parser bug"},
        },
        {
            **base,
            "type": "assistant",
            "timestamp": "2026-11-01T10:00:05Z",
            "message": {"id": "m1", "model": model, "usage": usage, "content": [{"type": "thinking", "thinking": ""}]},
        },
        {
            **base,
            "type": "assistant",
            "timestamp": "2026-11-01T10:00:05Z",
            "message": {
                "id": "m1",
                "model": model,
                "usage": usage,
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/tmp/proj/parser.py"}}
                ],
            },
        },
        {
            **base,
            "type": "user",
            "timestamp": "2026-11-01T10:00:06Z",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 400, "is_error": False}],
            },
        },
        {
            **base,
            "type": "assistant",
            "timestamp": "2026-11-01T10:00:10Z",
            "message": {
                "id": "m2",
                "model": model,
                "usage": usage,
                "content": [
                    {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "/tmp/proj/parser.py"}}
                ],
            },
        },
        {
            **base,
            "type": "user",
            "timestamp": "2026-11-01T10:00:11Z",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "failed", "is_error": True}],
            },
        },
        {
            **base,
            "type": "user",
            "timestamp": "2026-11-01T10:00:12Z",
            "isMeta": True,
            "message": {"role": "user", "content": "injected"},
        },
        {
            **base,
            "type": "user",
            "timestamp": "2026-11-01T10:05:00Z",
            "message": {"role": "user", "content": "Now add a test"},
        },
        {
            **base,
            "type": "assistant",
            "timestamp": "2026-11-01T10:05:04Z",
            "message": {
                "id": "m3",
                "model": model,
                "usage": usage,
                "content": [{"type": "tool_use", "id": "t3", "name": "Skill", "input": {"skill": "unit-tests"}}],
            },
        },
    ]


class ClaudeAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_jsonl(os.path.join(self.tmp.name, "proj", "s1.jsonl"), claude_transcript())
        self.runs = build_runs(
            ClaudeCodeAdapter(self.tmp.name).events(os.path.join(self.tmp.name, "proj", "s1.jsonl")), Pricing()
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_splits_at_prompts_and_skips_meta(self):
        self.assertEqual([r.run_id for r in self.runs], ["s1#1", "s1#2"])
        self.assertEqual(self.runs[0].prompt, "Fix the parser bug")
        self.assertEqual(self.runs[0].title, "Fix the parser")

    def test_usage_counted_once_per_message(self):
        r = self.runs[0]
        self.assertEqual(r.steps, 2)  # m1 (two lines) and m2
        self.assertEqual(r.output_tokens, 200)
        self.assertEqual(r.cache_read_tokens, 1800)
        self.assertEqual(r.thinking_tokens, 80)

    def test_tools_errors_writes_skills(self):
        r1, r2 = self.runs
        self.assertEqual(r1.tools, {"Read": 1, "Edit": 1})
        self.assertEqual((r1.tool_errors, r1.file_writes, r1.tool_output_chars), (1, 1, 406))
        self.assertEqual(r2.skills, ["unit-tests"])

    def test_cost_uses_model_price(self):
        # opus 5.5: 4 in, 20 out, 0.20 cache read, 5.00 cache write per million
        per_msg = (10 * 4 + 100 * 20 + 900 * 0.20 + 90 * 5.00) / 1e6
        self.assertAlmostEqual(self.runs[0].cost_usd, 2 * per_msg, places=6)
        self.assertTrue(self.runs[0].priced)


class GenericAdapterTest(unittest.TestCase):
    def test_reads_generic_events(self):
        with tempfile.TemporaryDirectory() as d:
            write_jsonl(
                os.path.join(d, "a.jsonl"),
                [
                    {
                        "event": "prompt",
                        "session_id": "g1",
                        "agent": "My Agent",
                        "ts": "2026-11-01T09:00:00Z",
                        "text": "do it",
                        "chars": 5,
                    },
                    {
                        "event": "response",
                        "session_id": "g1",
                        "ts": "2026-11-01T09:00:02Z",
                        "model": "local-llama",
                        "message_id": "r1",
                        "usage": {"input": 50, "output": 20},
                    },
                    {
                        "event": "tool_call",
                        "session_id": "g1",
                        "ts": "2026-11-01T09:00:03Z",
                        "tool": "write_file",
                        "target": "a.py",
                    },
                    {
                        "event": "tool_result",
                        "session_id": "g1",
                        "ts": "2026-11-01T09:00:04Z",
                        "error": False,
                        "chars": 10,
                    },
                    {"event": "bogus", "session_id": "g1"},
                ],
            )
            runs = build_runs(GenericJsonlAdapter(d).events(os.path.join(d, "a.jsonl")), Pricing())
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual(
            (r.agent, r.model, r.steps, r.file_writes, r.input_tokens), ("My Agent", "local-llama", 1, 1, 50)
        )
        self.assertFalse(r.priced)  # unknown model: unpriced, not guessed


class EmitTest(unittest.TestCase):
    def test_emit_round_trip(self):
        from tokentrail.emit import EventLog

        with tempfile.TemporaryDirectory() as d:
            log = EventLog(agent="Bot One", session_id="e1", workspace="/w", root=d)
            log.prompt("ship it")
            log.response(model="claude-haiku-5-5", input=100, output=10)
            log.tool_call("apply_patch", target="a.py")
            log.tool_result(error=True, chars=3)
            runs = build_runs(GenericJsonlAdapter(d).events(log.path), Pricing())
        r = runs[0]
        self.assertEqual((r.agent, r.prompt, r.steps, r.file_writes, r.tool_errors), ("Bot One", "ship it", 1, 1, 1))
        self.assertTrue(r.priced)


class HealthTest(unittest.TestCase):
    def run_(self, **kw):
        base = dict(
            run_id="x",
            conversation_id="x",
            agent="a",
            steps=10,
            tool_calls=10,
            tool_errors=0,
            file_writes=1,
            max_repeat=1,
        )
        base.update(kw)
        return TaskRun(**base)

    def test_outcomes(self):
        self.assertEqual(classify(self.run_()), Health.HIGH_VELOCITY.value)
        self.assertEqual(classify(self.run_(steps=40)), Health.POSITIVE.value)
        self.assertEqual(classify(self.run_(max_repeat=4)), Health.TOOL_LOOPS.value)
        self.assertEqual(classify(self.run_(steps=50, file_writes=0)), Health.WANDERING.value)
        self.assertEqual(classify(self.run_(steps=50, file_writes=0, skills=["s"])), Health.POSITIVE.value)
        self.assertEqual(classify(self.run_(tool_errors=4)), Health.HIGH_ERRORS.value)
        self.assertEqual(classify(self.run_(steps=6, tool_calls=5, tool_errors=2)), Health.HIGH_ERRORS.value)

    def test_loop_detection(self):
        from tokentrail.models import Event, Kind

        evs = [Event(Kind.PROMPT, "2026-11-01T00:00:00Z", "c", text="go")]
        for i in range(5):
            evs.append(Event(Kind.RESPONSE, f"2026-11-01T00:00:0{i + 1}Z", "c", message_id=f"m{i}", model="m"))
            evs.append(Event(Kind.TOOL_CALL, f"2026-11-01T00:00:0{i + 1}Z", "c", tool="Bash", target="make test"))
        self.assertEqual(build_runs(evs, Pricing())[0].max_repeat, 5)


class KpiTest(unittest.TestCase):
    def test_definitions(self):
        a = TaskRun(
            "a",
            "c1",
            "x",
            steps=10,
            input_tokens=100,
            cache_write_tokens=0,
            output_tokens=50,
            cache_read_tokens=900,
            tool_calls=10,
            tool_errors=1,
            health=Health.HIGH_VELOCITY.value,
            cost_usd=1.0,
        )
        b = TaskRun(
            "b",
            "c1",
            "x",
            steps=30,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
            tool_calls=30,
            health=Health.TOOL_LOOPS.value,
            cost_usd=2.0,
        )
        k = kpis([a, b])
        self.assertEqual(k["sessions"], 2)
        self.assertEqual(k["conversations"], 1)
        self.assertEqual(k["tokens"], 300)
        self.assertEqual(k["cache_hit_pct"], round(100 * 900 / 1100, 1))
        self.assertEqual(k["avg_steps"], 20.0)
        self.assertEqual(k["healthy_pct"], 50.0)
        self.assertEqual(k["tool_error_pct"], 2.5)
        self.assertEqual(k["cost_usd"], 3.0)


class GitTest(unittest.TestCase):
    def test_parse_log(self):
        sep, end = "\x1f", "\x1e"
        text = (
            sep.join(
                [
                    "a1",
                    "Me",
                    "me@x.com",
                    "2026-11-01T00:00:00Z",
                    "feat(api): add #12 support",
                    "Co-Authored-By: Claude <c@a.com>",
                ]
            )
            + end
            + sep.join(["b2", "Other", "o@x.com", "2026-11-02T00:00:00Z", "tidy up PROJ-7", ""])
            + end
        )
        a, b = parse_log(text, "repo", {"me@x.com"}, None)
        self.assertEqual((a.type, a.scope, a.issues, a.ai_tagged, a.mine), ("feat", "api", ["#12"], True, True))
        self.assertEqual((b.type, b.issues, b.ai_tagged, b.mine), ("", ["PROJ-7"], False, False))
        r = roi([], [a, b])
        self.assertEqual((r["my_commits"], r["ai_tagged"], r["issues_linked"]), (1, 1, 1))


class StoreSyncTest(unittest.TestCase):
    def test_store_keeps_data_after_history_is_deleted_and_mirrors(self):
        from tokentrail.mirror import Mirror
        from tokentrail.store import Store
        from tokentrail.sync import Syncer

        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "claude", "proj", "s1.jsonl")
            write_jsonl(src, claude_transcript())
            store = Store(os.path.join(d, "store"), "m1")
            mirror = Mirror(store, os.path.join(d, "bucket"), redact_prompts=True)
            syncer = Syncer(store, [ClaudeCodeAdapter(os.path.join(d, "claude"))], Pricing(), git=False, mirror=mirror)
            first = syncer.run()
            self.assertEqual((first["parsed"], first["conversations_changed"]), (1, 1))
            self.assertGreaterEqual(first["pushed"], 1)
            self.assertEqual(syncer.run()["parsed"], 0)  # unchanged file is skipped
            os.remove(src)  # agent history cleared
            syncer.run()
            runs, _, machines = store.read_all()
            self.assertEqual((len(runs), machines), (2, ["m1"]))
            # another machine pulls: sees the runs, with prompts redacted
            other = Store(os.path.join(d, "other"), "m2")
            self.assertGreaterEqual(Mirror(other, os.path.join(d, "bucket")).pull(), 1)
            pulled, _, _ = other.read_all()
            self.assertEqual(len(pulled), 2)
            self.assertEqual(pulled[0]["prompt"], "")


class FakeGCS:
    """Just enough of google.cloud.storage.Client: bucket(), list_blobs(), blob().download/upload."""

    def __init__(self):
        self.objects = {}

    def bucket(self, name):
        client = self

        class Blob:
            def __init__(self, key):
                self.name, self.key = key, key

            @property
            def md5_hash(self):
                import base64
                import hashlib

                return base64.b64encode(hashlib.md5(client.objects[self.key]).digest()).decode()

            def download_as_bytes(self):
                return client.objects[self.key]

            def upload_from_string(self, data, content_type=None):
                client.objects[self.key] = data

        class Bucket:
            def blob(self, key):
                return Blob(key)

        return Bucket()

    def list_blobs(self, bucket, prefix=""):
        return [bucket.blob(k) for k in sorted(self.objects) if k.startswith(prefix)]


class FakeS3:
    """Just enough of a boto3 S3 client: put_object, get_object, list_objects_v2 paginator."""

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        import io

        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def get_paginator(self, name):
        import hashlib

        fake = self

        class Pager:
            def paginate(self, Bucket, Prefix):
                keys = [k for b, k in sorted(fake.objects) if b == Bucket and k.startswith(Prefix)]
                for i in range(0, len(keys), 2):  # two per page, to exercise paging
                    yield {
                        "Contents": [
                            {"Key": k, "ETag": f'"{hashlib.md5(fake.objects[(Bucket, k)]).hexdigest()}"'}
                            for k in keys[i : i + 2]
                        ]
                    }

        return Pager()


class CloudBackendTest(unittest.TestCase):
    def round_trip(self, make_backend):
        from tokentrail.mirror import Mirror
        from tokentrail.store import Store
        from tokentrail.sync import Syncer

        with tempfile.TemporaryDirectory() as d:
            write_jsonl(os.path.join(d, "claude", "proj", "s1.jsonl"), claude_transcript())
            store = Store(os.path.join(d, "store"), "m1")
            mirror = Mirror(store, "x://", backend=make_backend())
            syncer = Syncer(store, [ClaudeCodeAdapter(os.path.join(d, "claude"))], Pricing(), git=False, mirror=mirror)
            self.assertGreaterEqual(syncer.run()["pushed"], 1)
            self.assertEqual(mirror.push(), 0)  # nothing changed, nothing re-sent
            other = Store(os.path.join(d, "other"), "m2")
            backend = mirror.backend
            self.assertGreaterEqual(Mirror(other, "x://", backend=backend).pull(), 1)
            self.assertEqual(Mirror(other, "x://", backend=backend).pull(), 0)  # unchanged on the second pull
            pulled, _, machines = other.read_all()
            self.assertEqual((len(pulled), machines), (2, ["m1"]))
            self.assertTrue(all(r["prompt"] == "" and r["redacted"] for r in pulled))

    def test_gcs_with_prefix(self):
        from tokentrail.mirror import GCSBackend

        fake = FakeGCS()
        self.round_trip(lambda: GCSBackend("b", "team/tt/", client=fake))
        self.assertTrue(all(k.startswith("team/tt/v1/m1/") for k in fake.objects))

    def test_s3_without_prefix(self):
        from tokentrail.mirror import S3Backend

        fake = FakeS3()
        self.round_trip(lambda: S3Backend("b", "", client=fake))
        self.assertTrue(all(k.startswith("v1/m1/") for _, k in fake.objects))

    def test_missing_addon_message(self):
        import importlib.util

        from tokentrail.mirror import backend_for

        if importlib.util.find_spec("boto3"):
            self.skipTest("boto3 installed")
        with self.assertRaises(SystemExit) as ctx:
            backend_for("s3://bucket/x")
        self.assertIn("tokentrail[s3]", str(ctx.exception))


class CliTest(unittest.TestCase):
    def test_sync_summary_export(self):
        with tempfile.TemporaryDirectory() as d:
            write_jsonl(os.path.join(d, "claude", "proj", "s1.jsonl"), claude_transcript())
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "store": os.path.join(d, "store"),
                        "claude_dir": os.path.join(d, "claude"),
                        "events_dir": os.path.join(d, "none"),
                    },
                    fh,
                )
            env = {**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..", "src")}

            def run(*a: str) -> str:
                return subprocess.run(
                    [sys.executable, "-m", "tokentrail", *a, "--config", cfg, "--no-git"],
                    capture_output=True,
                    text=True,
                    env=env,
                    check=True,
                ).stdout

            self.assertIn("2 task runs in 1 conversations", run("summary"))
            run("export", "--json", os.path.join(d, "o.json"), "--csv", os.path.join(d, "o.csv"))
            with open(os.path.join(d, "o.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["kpis"]["sessions"], 2)
            self.assertIn("2 task runs", run("status"))


if __name__ == "__main__":
    unittest.main()


class SyncIntervalTest(unittest.TestCase):
    def interval(self, *argv: str, saved: int | None = None) -> int:
        from tokentrail import cli
        from tokentrail import config as cfgmod

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            if saved is not None:
                cfgmod.Config(sync_interval=saved).save(path)
            args = cli.build_parser().parse_args(["dashboard", "--config", path, *argv])
            return cli.settings(args).sync_interval

    def test_default_is_30(self):
        self.assertEqual(self.interval(), 30)

    def test_flag_wins_over_config(self):
        self.assertEqual(self.interval("--sync-interval", "45", saved=120), 45)
        self.assertEqual(self.interval("--interval", "10"), 10)

    def test_config_used_when_no_flag(self):
        self.assertEqual(self.interval(saved=120), 120)

    def test_negative_rejected(self):
        with self.assertRaises(SystemExit), open(os.devnull, "w") as null:
            stderr, sys.stderr = sys.stderr, null
            try:
                self.interval("--sync-interval", "-1")
            finally:
                sys.stderr = stderr
