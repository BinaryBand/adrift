def mermaid_block(lines: list[str]) -> str:
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    sep = " | "
    header_line = "| " + sep.join(headers) + " |"
    divider_line = "| " + " | ".join("---" for _ in headers) + " |"
    data_lines = ["| " + sep.join(row) + " |" for row in rows]
    return "\n".join([header_line, divider_line, *data_lines])


def pct(n: int, d: int) -> str:
    return "—" if d == 0 else f"{100 * n / d:.1f}%"
