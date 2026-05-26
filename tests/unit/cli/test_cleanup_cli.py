from types import SimpleNamespace
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from adrift.cli.cleanup import _duplicate_audio_candidates, _matched_download_slugs


def test_duplicate_audio_candidates_prefers_canonical_opus() -> None:
    file_names = [
        "candy-mossler.opus",
        "candy-mossler-morbid-a-true-crime-podcast.opus",
        "candy-mossler-morbid-podcast.opus",
        "candy-mossler-morbid-podcast-video.opus",
    ]

    result = _duplicate_audio_candidates("Morbid", file_names)

    assert result == [
        "candy-mossler-morbid-a-true-crime-podcast.opus",
        "candy-mossler-morbid-podcast-video.opus",
        "candy-mossler-morbid-podcast.opus",
    ]


def test_duplicate_audio_candidates_prunes_mp3_when_canonical_opus_exists() -> None:
    file_names = [
        "the-tragic-death-of-gloria-ramirez.opus",
        "episode-707-the-tragic-death-of-gloria-ramirez.mp3",
    ]

    result = _duplicate_audio_candidates("Morbid", file_names)

    assert result == ["episode-707-the-tragic-death-of-gloria-ramirez.mp3"]


def test_duplicate_audio_candidates_skips_ambiguous_group_without_canonical() -> None:
    file_names = [
        "arthurs-seat-coffins-morbid.opus",
        "burke-hare-part-1-morbid.opus",
    ]

    result = _duplicate_audio_candidates("Morbid", file_names)

    assert result == []


def test_matched_download_slugs_deduplicates_colliding_titles() -> None:
    result = SimpleNamespace(
        config=SimpleNamespace(name="Morbid"),
        downloads=[
            SimpleNamespace(title="Episode 707: The Tragic Death of Gloria Ramirez"),
            SimpleNamespace(title="The Tragic Death of Gloria Ramirez | Morbid | Podcast"),
        ],
        pairs=[(0, 0)],
    )

    slugs = _matched_download_slugs(result)

    assert slugs == {"the-tragic-death-of-gloria-ramirez"}


def test_matched_download_slugs_includes_all_matched_download_entries() -> None:
    result = SimpleNamespace(
        config=SimpleNamespace(name="Morbid"),
        downloads=[
            SimpleNamespace(title="Episode 706: The Candy Mossler Case"),
            SimpleNamespace(title="The Tragic Death of Gloria Ramirez | Morbid | Podcast"),
        ],
        pairs=[(0, 0), (1, 1)],
    )

    slugs = _matched_download_slugs(result)

    assert slugs == {
        "the-candy-mossler-case",
        "the-tragic-death-of-gloria-ramirez",
    }


@given(
    titles=st.lists(
        st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            min_size=1,
            max_size=24,
        ),
        min_size=1,
        max_size=24,
    ),
    matched_indices=st.data(),
)
def test_process_unmatched_skips_slug_collisions_with_matched_downloads(
    titles: list[str], matched_indices: st.DataObject
) -> None:
    from adrift.cli import cleanup as cleanup_mod

    size = len(titles)
    matched = matched_indices.draw(st.sets(st.integers(min_value=0, max_value=size - 1)))
    pairs = [(idx, idx) for idx in sorted(matched)]
    result = SimpleNamespace(
        config=SimpleNamespace(name="test-show", path="/media/podcasts/test-show"),
        downloads=[SimpleNamespace(title=title) for title in titles],
        pairs=pairs,
    )

    class _S3Stub:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def exists(self, bucket: str, key_prefix: str) -> str | None:
            _ = bucket
            return f"{key_prefix.split('/')[-1]}.opus"

        def get_client(self) -> SimpleNamespace:
            return SimpleNamespace(delete_object=self._delete_object)

        def _delete_object(self, *, Bucket: str, Key: str) -> None:
            _ = Bucket
            self.deleted.append(Key)

        def invalidate_file_map_cache(self, bucket: str, key: str) -> None:
            _ = (bucket, key)

    s3 = _S3Stub()
    with (
        patch.object(
            cleanup_mod,
            "_resolve_s3_key",
            lambda s3, bucket, prefix, slug: f"{prefix}/{slug}.opus",
        ),
        patch("adrift.services.download_client.s3_prefix", return_value=("bucket", "prefix")),
    ):
        found, missing = cleanup_mod._process_unmatched(result, s3, dry_run=False)

    matched_slugs = _matched_download_slugs(result)
    expected_deleted = [
        f"prefix/{title}.opus"
        for idx, title in enumerate(titles)
        if idx not in matched and title not in matched_slugs
    ]

    assert missing == 0
    assert found == len(expected_deleted)
    assert s3.deleted == expected_deleted
