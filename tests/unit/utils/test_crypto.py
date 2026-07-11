import hashlib
from pathlib import Path

from adrift.utils.crypto import sha256, sha256_file


def test_sha256_matches_hashlib() -> None:
    assert sha256("hello") == hashlib.sha256(b"hello").hexdigest()


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    file = tmp_path / "data.bin"
    file.write_bytes(b"episode audio bytes" * 1000)

    assert sha256_file(file) == hashlib.sha256(file.read_bytes()).hexdigest()


def test_sha256_file_streams_in_chunks(tmp_path: Path) -> None:
    file = tmp_path / "data.bin"
    file.write_bytes(b"x" * 10)

    assert sha256_file(file, chunk_size=1) == hashlib.sha256(b"x" * 10).hexdigest()
