from adrift.cli.download import _build_pipeline_options


def test_build_pipeline_options_dry_run_overrides_mutating_stages() -> None:
    options = _build_pipeline_options(
        dry_run=True,
        skip_download=False,
        skip_update=False,
        max_downloads=10,
        refresh_sources=False,
    )

    assert options.skip_download is True
    assert options.skip_update is True
    assert options.show_download_plan is True


def test_build_pipeline_options_respects_explicit_flags_without_dry_run() -> None:
    options = _build_pipeline_options(
        dry_run=False,
        skip_download=True,
        skip_update=False,
        max_downloads=5,
        refresh_sources=True,
    )

    assert options.skip_download is True
    assert options.skip_update is False
    assert options.max_downloads == 5
    assert options.refresh_sources is True
    assert options.show_download_plan is False
