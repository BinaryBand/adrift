from unittest.mock import patch
from pathlib import Path
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())


class TestS3ClientSingleton(unittest.TestCase):
    def test_get_s3_client_is_cached(self):
        # Import inside test to ensure we patch before module code runs further
        import src.files.s3 as s3

        # Reset module state for deterministic test
        s3._S3_CLIENT = None
        s3._EFFECTIVE_ENDPOINT = None

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
