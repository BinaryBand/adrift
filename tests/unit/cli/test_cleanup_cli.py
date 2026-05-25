from adrift.cli.cleanup import _duplicate_audio_candidates


def test_duplicate_audio_candidates_prefers_canonical_opus() -> None:
    file_names = [
        "candy-mossler.opus",
        "candy-mossler-morbid-a-true-crime-podcast.opus",
        "candy-mossler-morbid-podcast.opus",
    ]

    result = _duplicate_audio_candidates("Morbid", file_names)

    assert result == [
        "candy-mossler-morbid-a-true-crime-podcast.opus",
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
