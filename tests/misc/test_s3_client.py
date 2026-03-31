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


if __name__ == "__main__":
    unittest.main()
