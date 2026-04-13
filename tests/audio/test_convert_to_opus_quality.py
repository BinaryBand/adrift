import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files import audio


def _ffprobe_for_kbps(kbps: int | None) -> str:
    if kbps is None:
        return json.dumps({"streams": [{"codec_type": "audio"}], "format": {}})
    bits = str(int(kbps) * 1000)
    return json.dumps({"streams": [{"codec_type": "audio", "bit_rate": bits}], "format": {"bit_rate": bits}})


def _extract_cmd_bitrate_kbps(cmd: list[str]) -> int:
    i = cmd.index("-b:a")
    val = cmd[i + 1]
    assert val.endswith("k")
    return int(val[:-1])


def test_no_upscale_by_default(monkeypatch, tmp_path):
    src = tmp_path / "in.mp3"
    src.write_bytes(b"x")
    monkeypatch.setattr(audio, "_ensure_audio_stream", lambda f: _ffprobe_for_kbps(64))
    captured = {}

    def fake_run(cmd, file, output, ffprobe_out):
        captured["cmd"] = list(cmd)

    monkeypatch.setattr(audio, "_run_ffmpeg_convert", fake_run)

    audio.convert_to_opus(src, target_bitrate_kbps=128, force_bitrate=False)
    assert _extract_cmd_bitrate_kbps(captured["cmd"]) == 64


def test_force_upscale(monkeypatch, tmp_path):
    src = tmp_path / "in.mp3"
    src.write_bytes(b"x")
    monkeypatch.setattr(audio, "_ensure_audio_stream", lambda f: _ffprobe_for_kbps(64))
    captured = {}

    def fake_run(cmd, file, output, ffprobe_out):
        captured["cmd"] = list(cmd)

    monkeypatch.setattr(audio, "_run_ffmpeg_convert", fake_run)

    audio.convert_to_opus(src, target_bitrate_kbps=128, force_bitrate=True)
    assert _extract_cmd_bitrate_kbps(captured["cmd"]) == 128


def test_downscale_to_target(monkeypatch, tmp_path):
    src = tmp_path / "in.mp3"
    src.write_bytes(b"x")
    monkeypatch.setattr(audio, "_ensure_audio_stream", lambda f: _ffprobe_for_kbps(320))
    captured = {}

    def fake_run(cmd, file, output, ffprobe_out):
        captured["cmd"] = list(cmd)

    monkeypatch.setattr(audio, "_run_ffmpeg_convert", fake_run)

    audio.convert_to_opus(src, target_bitrate_kbps=96, force_bitrate=False)
    assert _extract_cmd_bitrate_kbps(captured["cmd"]) == 96
