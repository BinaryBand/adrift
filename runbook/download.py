"""
& .venv/Scripts/python.exe runbook/download.py --skip-install --skip-update config/podcasts.json config/youtube.json
"""

from pathlib import Path
import subprocess
import argparse
import dotenv
import sys

sys.path.insert(0, Path(dotenv.find_dotenv()).parent.as_posix())
from runbook.podcasts.download_podcasts import DF_TARGETS


def main() -> None:
    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(description="Download and update podcasts.")
    parser.add_argument("files", nargs="*", default=DF_TARGETS, help="Included files")
    parser.add_argument("--skip-download", action="store_true", default=False)
    parser.add_argument("--skip-update", action="store_true", default=False)
    args = parser.parse_args()

    if not args.skip_download:
        download = [sys.executable, "runbook/podcasts/download_podcasts.py"]
        download += ["--include"] + args.files
        subprocess.run(download, check=True)

    if not args.skip_update:
        update = [sys.executable, "runbook/podcasts/update_podcasts.py"]
        update += ["--include"] + args.files
        subprocess.run(update, check=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
