from pathlib import Path


def _remove_file_extensions(file_names: list[str]) -> list[str]:
    return [Path(file_name).with_suffix("").as_posix() for file_name in file_names]


def _identifier_matches(name: str, identifier: str, extension_agnostic: bool) -> bool:
    if extension_agnostic:
        return Path(name).with_suffix("").as_posix() == identifier
    return name == identifier


__all__ = ["_remove_file_extensions", "_identifier_matches"]
