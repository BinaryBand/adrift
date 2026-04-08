import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())

import src.youtube.downloader as yt_downloader
from src.app_common import PodcastConfig
from src.orchestration.download_service import run_download_pipeline
from src.orchestration.models import DownloadRunRequest


class TestDownloadService(unittest.TestCase):
    def test_run_download_pipeline_aggregates_downloads_and_failures(self):
        configs = [PodcastConfig(name="Alpha"), PodcastConfig(name="Beta")]
        calls: list[tuple[str, str, int | None]] = []

        def fake_download(config: PodcastConfig, budget: int | None = None) -> int:
            calls.append(("download", config.name, budget))
            if config.name == "Beta":
                raise RuntimeError("boom")
            return 2

        def fake_update(config: PodcastConfig) -> None:
            calls.append(("update", config.name, None))

        with patch("src.orchestration.download_service.load_podcasts_config", return_value=configs):
            result = run_download_pipeline(
                DownloadRunRequest(include=["config/podcasts.toml"], max_downloads=3),
                download_series=fake_download,
                update_series=fake_update,
            )

        self.assertEqual(result.total_series, 2)
        self.assertEqual(result.total_episodes_downloaded, 2)
        self.assertEqual(len(result.failed_series), 1)
        self.assertEqual(result.failed_series[0].name, "Beta")
        self.assertEqual(
            calls,
            [
                ("download", "Alpha", 3),
                ("update", "Alpha", None),
                ("download", "Beta", 1),
                ("update", "Beta", None),
            ],
        )

    def test_run_download_pipeline_restores_runtime_context(self):
        original_flag = yt_downloader.PROPAGATE_BOT_DETECTION
        original_cwd = Path.cwd()

        def fake_download(config: PodcastConfig, budget: int | None = None) -> int:
            self.assertTrue(yt_downloader.PROPAGATE_BOT_DETECTION)
            self.assertEqual(Path.cwd(), workdir)
            return 0

        def fake_update(config: PodcastConfig) -> None:
            self.assertEqual(Path.cwd(), workdir)

        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            with patch(
                "src.orchestration.download_service.load_podcasts_config",
                return_value=[PodcastConfig(name="Gamma")],
            ):
                run_download_pipeline(
                    DownloadRunRequest(include=["config/podcasts.toml"], workdir=workdir),
                    download_series=fake_download,
                    update_series=fake_update,
                )

        self.assertEqual(Path.cwd(), original_cwd)
        self.assertEqual(yt_downloader.PROPAGATE_BOT_DETECTION, original_flag)


if __name__ == "__main__":
    unittest.main()
