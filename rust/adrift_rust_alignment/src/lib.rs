use std::collections::HashSet;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use rapidfuzz::fuzz;
use rayon::prelude::*;
use regex::Regex;

// Month names that are not discriminating anchor tokens.
const TEMPORAL_TOKENS: &[&str] = &[
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
];

// ---------------------------------------------------------------------------
// Data containers (extracted from Python before releasing the GIL)
// ---------------------------------------------------------------------------

struct EpisodeData {
    episode_id: String,
    normalized_title: String,
    normalized_description: String,
    pub_date_unix_s: Option<i64>,
}

struct BatchConfig {
    date_weight: f64,
    title_weight: f64,
    description_weight: f64,
    date_score_tiers: Vec<(i64, f64)>,
    sparse_title_min: f64,
    match_tolerance: f64,
    title_certainty_min: f64,
    metadata_rescue_subset_sim_min: f64,
    containment_bonus: f64,
    stopwords: HashSet<String>,
    patterns: Vec<Regex>,
}

// ---------------------------------------------------------------------------
// Python extraction helpers
// ---------------------------------------------------------------------------

fn extract_episode(ep: &Bound<'_, PyAny>) -> PyResult<EpisodeData> {
    Ok(EpisodeData {
        episode_id: ep.getattr("episode_id")?.extract()?,
        normalized_title: ep.getattr("normalized_title")?.extract()?,
        normalized_description: ep.getattr("normalized_description")?.extract()?,
        pub_date_unix_s: ep.getattr("pub_date_unix_s")?.extract()?,
    })
}

fn extract_stopwords(config: &Bound<'_, PyAny>) -> PyResult<HashSet<String>> {
    let base: Vec<String> = config.getattr("base_anchor_stopwords")?.extract()?;
    let extra: Vec<String> = config.getattr("extra_stopwords")?.extract()?;
    Ok(base.into_iter().chain(extra).collect())
}

fn extract_patterns(config: &Bound<'_, PyAny>) -> PyResult<Vec<Regex>> {
    let raw: Vec<String> = config.getattr("numbered_marker_patterns")?.extract()?;
    raw.iter()
        .map(|p| {
            Regex::new(p).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string())
            })
        })
        .collect()
}

fn extract_config(config: &Bound<'_, PyAny>) -> PyResult<BatchConfig> {
    Ok(BatchConfig {
        date_weight: config.getattr("date_weight")?.extract()?,
        title_weight: config.getattr("title_weight")?.extract()?,
        description_weight: config.getattr("description_weight")?.extract()?,
        date_score_tiers: config.getattr("date_score_tiers")?.extract()?,
        sparse_title_min: config.getattr("sparse_title_min")?.extract()?,
        match_tolerance: config.getattr("match_tolerance")?.extract()?,
        title_certainty_min: config.getattr("title_certainty_min")?.extract()?,
        metadata_rescue_subset_sim_min: config
            .getattr("metadata_rescue_subset_sim_min")?
            .extract()?,
        containment_bonus: config.getattr("containment_bonus")?.extract()?,
        stopwords: extract_stopwords(config)?,
        patterns: extract_patterns(config)?,
    })
}

// ---------------------------------------------------------------------------
// Fuzzy similarity (mirrors Python _similarity_clean)
// ---------------------------------------------------------------------------

fn token_sort_ratio(a: &str, b: &str) -> f64 {
    let mut ta: Vec<&str> = a.split_whitespace().collect();
    let mut tb: Vec<&str> = b.split_whitespace().collect();
    ta.sort_unstable();
    tb.sort_unstable();
    fuzz::ratio(ta.join(" ").chars(), tb.join(" ").chars())
}

fn token_set_ratio(a: &str, b: &str) -> f64 {
    let sa: HashSet<&str> = a.split_whitespace().collect();
    let sb: HashSet<&str> = b.split_whitespace().collect();
    let mut inter: Vec<&str> = sa.intersection(&sb).copied().collect();
    inter.sort_unstable();
    let mut da: Vec<&str> = sa.difference(&sb).copied().collect();
    da.sort_unstable();
    let mut db: Vec<&str> = sb.difference(&sa).copied().collect();
    db.sort_unstable();
    let si = inter.join(" ");
    let sua = if da.is_empty() { si.clone() } else { format!("{si} {}", da.join(" ")) };
    let sub_ = if db.is_empty() { si.clone() } else { format!("{si} {}", db.join(" ")) };
    let r1 = fuzz::ratio(si.chars(), sua.chars());
    let r2 = fuzz::ratio(si.chars(), sub_.chars());
    let r3 = fuzz::ratio(sua.chars(), sub_.chars());
    r1.max(r2).max(r3)
}

/// Weighted combo matching Python `_similarity_clean`:
/// ratio×0.4 + token_sort_ratio×0.3 + token_set_ratio×0.3.
fn fuzzy_sim(a: &str, b: &str) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let r = fuzz::ratio(a.chars(), b.chars());
    let ts = token_sort_ratio(a, b);
    let tset = token_set_ratio(a, b);
    r * 0.4 + ts * 0.3 + tset * 0.3
}

// ---------------------------------------------------------------------------
// Date similarity (mirrors sim_date)
// ---------------------------------------------------------------------------

fn date_sim(ref_ts: Option<i64>, dl_ts: Option<i64>, tiers: &[(i64, f64)]) -> f64 {
    match (ref_ts, dl_ts) {
        (Some(r), Some(d)) => {
            let delta = (r - d).unsigned_abs() as i64 / 86_400;
            tiers
                .iter()
                .find(|(max_days, _)| delta <= *max_days)
                .map(|(_, score)| *score)
                .unwrap_or(0.0)
        }
        _ => 0.0,
    }
}

// ---------------------------------------------------------------------------
// Anchor token logic (mirrors AnchorTokens)
// ---------------------------------------------------------------------------

fn anchor_set<'a>(title: &'a str, stopwords: &HashSet<String>) -> HashSet<&'a str> {
    title
        .split_whitespace()
        .filter(|t| !stopwords.contains(*t))
        .collect()
}

fn has_containment(a: &HashSet<&str>, b: &HashSet<&str>) -> bool {
    if a.is_empty() || b.is_empty() {
        return false;
    }
    if a.len() <= b.len() {
        a.len() >= 2 && a.iter().all(|t| b.contains(*t))
    } else {
        b.len() >= 2 && b.iter().all(|t| a.contains(*t))
    }
}

/// Returns the extra tokens when one anchor set is a strict subset of the other.
fn subset_extras<'a>(a: &HashSet<&'a str>, b: &HashSet<&'a str>) -> Option<Vec<&'a str>> {
    if a.is_empty() || b.is_empty() {
        return None;
    }
    if a.iter().all(|t| b.contains(*t)) {
        return Some(b.iter().filter(|t| !a.contains(*t)).copied().collect());
    }
    if b.iter().all(|t| a.contains(*t)) {
        return Some(a.iter().filter(|t| !b.contains(*t)).copied().collect());
    }
    None
}

fn is_discriminating(tokens: &[&str]) -> bool {
    tokens
        .iter()
        .any(|t| t.chars().any(|c| c.is_alphabetic()) && !TEMPORAL_TOKENS.contains(t))
}

// ---------------------------------------------------------------------------
// Rejection predicates
// ---------------------------------------------------------------------------

fn has_number_mismatch(ref_title: &str, dl_title: &str, patterns: &[Regex]) -> bool {
    patterns.iter().any(|p| {
        let rv = p
            .captures(ref_title)
            .and_then(|c| c.get(1))
            .and_then(|m| m.as_str().parse::<i64>().ok());
        let dv = p
            .captures(dl_title)
            .and_then(|c| c.get(1))
            .and_then(|m| m.as_str().parse::<i64>().ok());
        rv.is_some() && dv.is_some() && rv != dv
    })
}

fn has_weak_anchor(
    ref_title: &str,
    dl_title: &str,
    title_sim: f64,
    sw: &HashSet<String>,
) -> bool {
    let ra = anchor_set(ref_title, sw);
    let da = anchor_set(dl_title, sw);
    ra.intersection(&da).count() == 0 && title_sim < 0.75
}

/// Mirrors `_should_reject_metadata_subset_rescue`.
fn reject_subset_rescue(
    ref_title: &str,
    dl_title: &str,
    title_sim: f64,
    has_desc: bool,
    has_date: bool,
    stopwords: &HashSet<String>,
    certainty_min: f64,
    rescue_min: f64,
) -> bool {
    if !has_desc || !has_date || title_sim < rescue_min || title_sim >= certainty_min {
        return false;
    }
    let ra = anchor_set(ref_title, stopwords);
    let da = anchor_set(dl_title, stopwords);
    match subset_extras(&ra, &da) {
        Some(ref tokens) if tokens.len() == 1 => is_discriminating(tokens),
        _ => false,
    }
}

/// First-pass rejection: number mismatch and weak anchor.
/// Mirrors `_should_reject_alignment`.
fn should_reject(ref_ep: &EpisodeData, dl_ep: &EpisodeData, title_sim: f64, cfg: &BatchConfig) -> bool {
    has_number_mismatch(&ref_ep.normalized_title, &dl_ep.normalized_title, &cfg.patterns)
        || has_weak_anchor(
            &ref_ep.normalized_title,
            &dl_ep.normalized_title,
            title_sim,
            &cfg.stopwords,
        )
}

// ---------------------------------------------------------------------------
// Weighted scoring
// ---------------------------------------------------------------------------

fn weighted_base(
    title_sim: f64,
    desc_sim: f64,
    ds: f64,
    cfg: &BatchConfig,
    has_desc: bool,
    has_date: bool,
    include_date: bool,
) -> f64 {
    let mut weighted = cfg.title_weight * title_sim;
    let mut total = cfg.title_weight;
    if has_desc {
        weighted += cfg.description_weight * desc_sim;
        total += cfg.description_weight;
    }
    if include_date && has_date {
        weighted += cfg.date_weight * ds;
        total += cfg.date_weight;
    }
    weighted / total
}

fn score_pair_sims(
    ref_ep: &EpisodeData,
    dl_ep: &EpisodeData,
    title_sim: f64,
    has_desc: bool,
    has_date: bool,
    include_date: bool,
    cfg: &BatchConfig,
) -> f64 {
    let desc_sim = if has_desc {
        fuzzy_sim(&ref_ep.normalized_description, &dl_ep.normalized_description)
    } else {
        0.0
    };
    let ds = if include_date && has_date {
        date_sim(ref_ep.pub_date_unix_s, dl_ep.pub_date_unix_s, &cfg.date_score_tiers)
    } else {
        0.0
    };
    let base = weighted_base(title_sim, desc_sim, ds, cfg, has_desc, has_date, include_date);
    let ra = anchor_set(&ref_ep.normalized_title, &cfg.stopwords);
    let da = anchor_set(&dl_ep.normalized_title, &cfg.stopwords);
    let bonus = if include_date && has_containment(&ra, &da) { cfg.containment_bonus } else { 0.0 };
    (base + bonus).min(1.0)
}

/// Full scoring pipeline for one (reference, download) pair.
/// Mirrors `_alignment_score` → `_score_high_certainty` / `_score_low_certainty`.
fn score_pair(ref_ep: &EpisodeData, dl_ep: &EpisodeData, cfg: &BatchConfig) -> f64 {
    if !ref_ep.episode_id.is_empty() && ref_ep.episode_id == dl_ep.episode_id {
        return 1.0;
    }
    let title_sim = fuzzy_sim(&ref_ep.normalized_title, &dl_ep.normalized_title);
    let has_desc = !ref_ep.normalized_description.is_empty()
        && !dl_ep.normalized_description.is_empty();
    let has_date = ref_ep.pub_date_unix_s.is_some() && dl_ep.pub_date_unix_s.is_some();

    if should_reject(ref_ep, dl_ep, title_sim, cfg) {
        return 0.0;
    }
    // High-certainty path (title_sim >= certainty_min): exclude date signal.
    let include_date = title_sim < cfg.title_certainty_min;
    if include_date {
        // Sparse title: no id, no description, weak title → skip.
        if !has_desc && title_sim < cfg.sparse_title_min {
            return 0.0;
        }
        // Subset rescue rejection.
        if reject_subset_rescue(
            &ref_ep.normalized_title,
            &dl_ep.normalized_title,
            title_sim,
            has_desc,
            has_date,
            &cfg.stopwords,
            cfg.title_certainty_min,
            cfg.metadata_rescue_subset_sim_min,
        ) {
            return 0.0;
        }
    }
    score_pair_sims(ref_ep, dl_ep, title_sim, has_desc, has_date, include_date, cfg)
}

// ---------------------------------------------------------------------------
// Greedy pair selection
// ---------------------------------------------------------------------------

fn select_pairs(mut scored: Vec<((usize, usize), f64)>, tolerance: f64) -> Vec<(usize, usize)> {
    scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let mut used_refs: HashSet<usize> = HashSet::new();
    let mut used_dls: HashSet<usize> = HashSet::new();
    let mut pairs: Vec<(usize, usize)> = Vec::new();
    for ((r_idx, d_idx), score) in scored {
        if score < tolerance {
            break; // sorted descending — nothing below this will qualify
        }
        if used_refs.contains(&r_idx) || used_dls.contains(&d_idx) {
            continue;
        }
        used_refs.insert(r_idx);
        used_dls.insert(d_idx);
        pairs.push((r_idx, d_idx));
    }
    pairs
}

// ---------------------------------------------------------------------------
// Public PyO3 entry point
// ---------------------------------------------------------------------------

#[pyfunction]
fn align_batch(py: Python<'_>, batch: &Bound<'_, PyAny>) -> PyResult<(Py<PyList>, Py<PyDict>)> {
    let config_obj = batch.getattr("config")?;
    let cfg = extract_config(&config_obj)?;

    let ref_list: Vec<Bound<'_, PyAny>> = batch.getattr("references")?.extract()?;
    let dl_list: Vec<Bound<'_, PyAny>> = batch.getattr("downloads")?.extract()?;

    let references: Vec<EpisodeData> =
        ref_list.iter().map(extract_episode).collect::<PyResult<_>>()?;
    let downloads: Vec<EpisodeData> =
        dl_list.iter().map(extract_episode).collect::<PyResult<_>>()?;

    let n_refs = references.len();
    let n_dls = downloads.len();

    // Release the GIL while computing the N×M score matrix in parallel.
    let scored: Vec<((usize, usize), f64)> = py.allow_threads(|| {
        (0..n_refs * n_dls)
            .into_par_iter()
            .map(|idx| {
                let r_idx = idx / n_dls;
                let d_idx = idx % n_dls;
                ((r_idx, d_idx), score_pair(&references[r_idx], &downloads[d_idx], &cfg))
            })
            .collect()
    });

    let scores = PyDict::new_bound(py);
    for ((r_idx, d_idx), score) in &scored {
        let key = PyTuple::new_bound(py, [r_idx.into_py(py), d_idx.into_py(py)]);
        scores.set_item(key, *score)?;
    }

    let selected = select_pairs(scored, cfg.match_tolerance);
    let pairs = PyList::empty_bound(py);
    for (r_idx, d_idx) in selected {
        pairs.append(PyTuple::new_bound(py, [r_idx.into_py(py), d_idx.into_py(py)]))?;
    }

    Ok((pairs.unbind(), scores.unbind()))
}

#[pymodule]
fn adrift_rust_alignment(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(align_batch, module)?)?;
    Ok(())
}
