import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())


class TestS3ClientSingleton(unittest.TestCase):
    def test_import_does_not_require_s3_env(self):
        with patch.dict(
            os.environ,
            {
                "S3_USERNAME": "",
                "S3_SECRET_KEY": "",
                "S3_ENDPOINT": "",
                "S3_REGION": "",
            },
            clear=False,
        ):
            sys.modules.pop("src.files.s3", None)
            s3 = importlib.import_module("src.files.s3")
            self.assertTrue(hasattr(s3, "get_s3_client"))

    def test_get_s3_client_is_cached(self):
        # Import inside test to ensure we patch before module code runs further
        import src.files.s3 as s3

        # Reset module state for deterministic test
        s3._s3_client = None
        s3._effective_endpoint = None

        with patch.dict(
            os.environ,
            {
                "S3_USERNAME": "u",
                "S3_SECRET_KEY": "k",
                "S3_ENDPOINT": "http://example",
                "S3_REGION": "us-east-1",
            },
            clear=False,
        ):
            with patch("src.files.s3.boto3.session.Session") as mock_session_cls:
                mock_session = mock_session_cls.return_value
                mock_client = object()
                mock_session.client.return_value = mock_client

                c1 = s3.get_s3_client()
                c2 = s3.get_s3_client()

                # Same object reused
                self.assertIs(c1, c2)
                # Only one client created
                mock_session.client.assert_called_once()

    def test_get_s3_client_requires_env_at_runtime(self):
        import src.files.s3 as s3

        s3._s3_client = None
        s3._effective_endpoint = None

        with patch.dict(
            os.environ,
            {
                "S3_USERNAME": "",
                "S3_SECRET_KEY": "",
                "S3_ENDPOINT": "",
                "S3_REGION": "",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                s3.get_s3_client()

        self.assertIn("Missing required S3 environment variables", str(ctx.exception))

    def test_can_swap_secret_provider(self):
        import src.files.s3 as s3

        class _FakeSecretProvider:
            def get(self, key: str, default: str = "") -> str:
                values = {
                    "S3_USERNAME": "provider-user",
                    "S3_SECRET_KEY": "provider-key",
                    "S3_ENDPOINT": "http://provider-endpoint",
                    "S3_REGION": "us-west-1",
                    "LOCAL_S3_ENDPOINT": "",
                }
                return values.get(key, default)

        s3._s3_client = None
        s3._effective_endpoint = None
        s3.set_secret_provider(_FakeSecretProvider())
        try:
            with patch("src.files.s3.boto3.session.Session") as mock_session_cls:
                mock_session = mock_session_cls.return_value
                mock_client = object()
                mock_session.client.return_value = mock_client

                s3.get_s3_client()

                kwargs = mock_session.client.call_args.kwargs
                self.assertEqual(kwargs["aws_access_key_id"], "provider-user")
                self.assertEqual(kwargs["aws_secret_access_key"], "provider-key")
                self.assertEqual(kwargs["region_name"], "us-west-1")
                self.assertEqual(kwargs["endpoint_url"], "http://provider-endpoint")
        finally:
            s3.reset_secret_provider()

    def test_setting_secret_provider_invalidates_cached_state(self):
        import src.files.s3 as s3

        class _StaticProvider:
            def get(self, key: str, default: str = "") -> str:
                values = {
                    "S3_USERNAME": "u",
                    "S3_SECRET_KEY": "k",
                    "S3_ENDPOINT": "http://e",
                    "S3_REGION": "us-east-1",
                    "LOCAL_S3_ENDPOINT": "",
                }
                return values.get(key, default)

        s3._s3_client = object()
        s3._effective_endpoint = "cached"

        s3.set_secret_provider(_StaticProvider())
        try:
            self.assertIsNone(s3._s3_client)
            self.assertIsNone(s3._effective_endpoint)
        finally:
            s3.reset_secret_provider()


class TestRetryDecorator(unittest.TestCase):
    """Test the retry() exponential-backoff decorator."""

    def _make_retry(self):
        from src.files.s3 import retry

        return retry

    def test_succeeds_on_first_attempt_no_sleep(self):
        retry = self._make_retry()

        call_count = 0

        @retry(attempts=3, backoff_base=2)
        def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        with patch("src.files.s3.time.sleep") as mock_sleep:
            result = fn()

        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 1)
        mock_sleep.assert_not_called()

    def test_retries_and_eventually_succeeds(self):
        retry = self._make_retry()

        call_count = 0

        @retry(attempts=3, backoff_base=2)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        with patch("src.files.s3.time.sleep"):
            result = fn()

        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 3)

    def test_exhausted_retries_raises_original_exception(self):
        """B1 fix: must raise the original exception, not AssertionError."""
        retry = self._make_retry()

        class _SentinelError(Exception):
            pass

        @retry(attempts=3, backoff_base=2)
        def fn():
            raise _SentinelError("original")

        with patch("src.files.s3.time.sleep"):
            with self.assertRaises(_SentinelError) as ctx:
                fn()

        self.assertEqual(str(ctx.exception), "original")

    def test_backoff_grows_exponentially(self):
        retry = self._make_retry()

        @retry(attempts=4, backoff_base=2)
        def fn():
            raise RuntimeError("fail")

        with patch("src.files.s3.time.sleep") as mock_sleep:
            with self.assertRaises(RuntimeError):
                fn()

        # Sleeps should use backoff_base**i for i = 1, 2, 3
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertEqual(sleep_args, [2, 4, 8])


if __name__ == "__main__":
    unittest.main()
