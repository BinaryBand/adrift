use pyo3::prelude::*;
use strsim::normalized_levenshtein;

fn pair_score(reference: &(String, String), download: &(String, String)) -> f64 {
    let rt = reference.0.to_lowercase();
    let dt = download.0.to_lowercase();
    let rd = reference.1.to_lowercase();
    let dd = download.1.to_lowercase();

    let title = normalized_levenshtein(&rt, &dt);
    let desc = if rd.is_empty() || dd.is_empty() {
        0.0
    } else {
        normalized_levenshtein(&rd, &dd)
    };
    title * 0.85 + desc * 0.15
}

#[pyfunction]
fn align_with_scores(
    references: Vec<(String, String)>,
    downloads: Vec<(String, String)>,
    match_tolerance: f64,
) -> PyResult<(Vec<(usize, usize)>, Vec<(usize, usize, f64)>)> {
    let mut all_scores: Vec<(usize, usize, f64)> = Vec::new();

    for (r_idx, reference) in references.iter().enumerate() {
        for (d_idx, download) in downloads.iter().enumerate() {
            all_scores.push((r_idx, d_idx, pair_score(reference, download)));
        }
    }

    let mut sorted = all_scores.clone();
    sorted.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));

    let mut used_refs = vec![false; references.len()];
    let mut used_dls = vec![false; downloads.len()];
    let mut pairs: Vec<(usize, usize)> = Vec::new();

    for (r_idx, d_idx, score) in sorted {
        if score < match_tolerance {
            continue;
        }
        if used_refs[r_idx] || used_dls[d_idx] {
            continue;
        }
        used_refs[r_idx] = true;
        used_dls[d_idx] = true;
        pairs.push((r_idx, d_idx));
    }

    Ok((pairs, all_scores))
}

#[pymodule]
fn adrift_rust_align(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(align_with_scores, m)?)?;
    Ok(())
}
