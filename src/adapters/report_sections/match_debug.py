from src.app_common import MATCH_TOLERANCE
from src.models.pipeline import MatchCandidateTrace, MergeResult, ReferenceMatchTrace

from ._helpers import md_table


def _episode_label(index: int, title: str) -> str:
    cleaned = title.replace("|", "/").replace("\n", " ").strip()
    if len(cleaned) > 80:
        cleaned = cleaned[:77] + "..."
    return f"{index + 1}. {cleaned}"


def _download_label(result: MergeResult, candidate: MatchCandidateTrace | None) -> str:
    if candidate is None:
        return "—"
    return _episode_label(
        candidate.download_index,
        result.downloads[candidate.download_index].title,
    )


def _score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _candidate_reason(candidate: MatchCandidateTrace) -> str:
    labels = {
        "matched": "Accepted",
        "below_threshold": "Below threshold",
        "download_matched_elsewhere": "Candidate download matched elsewhere",
        "reference_matched_elsewhere": "Reference matched to another candidate",
        "not_selected": "Not selected",
    }
    return labels[candidate.reason]


def _best_candidate(trace: ReferenceMatchTrace) -> MatchCandidateTrace | None:
    return trace.candidates[0] if trace.candidates else None


def _matched_candidate(trace: ReferenceMatchTrace) -> MatchCandidateTrace | None:
    for candidate in trace.candidates:
        if candidate.reason == "matched":
            return candidate
    return None


def _greedy_candidate(trace: ReferenceMatchTrace) -> MatchCandidateTrace | None:
    return _matched_candidate(trace) or _best_candidate(trace)


def _greedy_score(
    trace: ReferenceMatchTrace,
    candidate: MatchCandidateTrace | None,
) -> float | None:
    if _matched_candidate(trace) is not None:
        return trace.matched_score
    return None if candidate is None else candidate.score


def _greedy_match_row(result: MergeResult, trace: ReferenceMatchTrace) -> list[str]:
    reference = result.references[trace.reference_index]
    candidate = _greedy_candidate(trace)
    outcome = "No candidate" if candidate is None else _candidate_reason(candidate)
    return [
        _episode_label(trace.reference_index, reference.title),
        _download_label(result, candidate),
        _score(_greedy_score(trace, candidate)),
        outcome,
    ]


def _greedy_match_rows(result: MergeResult) -> list[list[str]]:
    return [_greedy_match_row(result, trace) for trace in result.match_traces or []]


def _match_rows(result: MergeResult) -> list[list[str]]:
    rows: list[list[str]] = []
    for trace in result.match_traces or []:
        reference = result.references[trace.reference_index]
        matched_candidate = _matched_candidate(trace)
        status = "Matched" if matched_candidate is not None else "Unmatched"
        rows.append(
            [
                _episode_label(trace.reference_index, reference.title),
                status,
                _download_label(result, matched_candidate),
                _score(trace.matched_score),
            ]
        )
    return rows


def _candidate_rows(result: MergeResult) -> list[list[str]]:
    rows: list[list[str]] = []
    for trace in result.match_traces or []:
        if trace.matched_download_index is not None:
            continue
        reference = result.references[trace.reference_index]
        for candidate in trace.candidates:
            rows.append(
                [
                    _episode_label(trace.reference_index, reference.title),
                    _download_label(result, candidate),
                    _score(candidate.score),
                    f"{MATCH_TOLERANCE:.2f}",
                    _candidate_reason(candidate),
                ]
            )
    return rows


def _greedy_match_section(result: MergeResult) -> str:
    greedy_rows = _greedy_match_rows(result)
    return f"# Greedy Matches: {result.config.name}\n\n" + md_table(
        ["Reference Episode", "Greedy Candidate", "Score", "Outcome"],
        greedy_rows,
    )


def _unmatched_candidates_section(result: MergeResult) -> str:
    candidate_rows = _candidate_rows(result)
    if not candidate_rows:
        return ""
    return (
        "## Unmatched Reference Candidates\n\n"
        "Top candidates are shown even when their score is below the "
        f"{MATCH_TOLERANCE:.2f} threshold.\n\n"
        + md_table(
            [
                "Reference Episode",
                "Download Candidate",
                "Score",
                "Threshold",
                "Reason",
            ],
            candidate_rows,
        )
    )


def render_matches(result: MergeResult) -> str:
    if not result.references:
        return ""

    rows = _match_rows(result)
    return f"# Matches: {result.config.name}\n\n" + md_table(
        ["Reference Episode", "Status", "Download Match", "Score"], rows
    )


def render_greedy_matches(result: MergeResult) -> str:
    if not result.references:
        return ""

    sections = [_greedy_match_section(result), _unmatched_candidates_section(result)]
    return "\n\n---\n\n".join(section for section in sections if section)


def render_match_debug(result: MergeResult) -> str:
    sections = [render_matches(result), render_greedy_matches(result)]
    return "\n\n---\n\n".join(section for section in sections if section)
