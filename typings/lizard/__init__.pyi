from __future__ import annotations

from typing import Iterable, List, NamedTuple

class FunctionInfo(NamedTuple):
    name: str
    start_line: int
    end_line: int
    long_name: str
    cyclomatic_complexity: int

class FileInformation:
    CCN: int
    function_list: List[FunctionInfo]
    file_name: str

def analyze_file(path: str) -> FileInformation: ...
def analyze_files(paths: Iterable[str]) -> List[FileInformation]: ...
def analyze_source_code(filename: str, code: str) -> FileInformation: ...
