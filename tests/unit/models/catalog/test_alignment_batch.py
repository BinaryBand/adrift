import unittest

from adrift.models import AlignmentConfig
from adrift.services.catalog.alignment import prepare_alignment_batch
from adrift.utils.text import normalize_text
from adrift.utils.title_normalization import normalize_title
from tests.unit.models.catalog._fixtures import dt as _dt
from tests.unit.models.catalog._fixtures import ep as _ep


class TestPrepareAlignmentBatch(unittest.TestCase):
    def test_prepares_clean_primitive_rows(self) -> None:
        alignment = AlignmentConfig(extra_stopwords=["morbid", "  Listener  "])
        ref = _ep(
            id="ref-1",
            title="Morbid: A True Crime Podcast | The Bermondsey Horror",
            description="  An   episode   description  ",
            pub_date=_dt(2024, 1, 5),
        )
        dl = _ep(
            id="dl-1",
            title="The Bermondsey Horror | Morbid",
            description="",
            pub_date=None,
        )

        batch = prepare_alignment_batch([ref], [dl], "Morbid", alignment)

        self.assertEqual(
            batch.references[0].normalized_title,
            normalize_text(normalize_title("Morbid", ref.title)),
        )
        self.assertEqual(
            batch.references[0].normalized_description,
            normalize_text(ref.description or ""),
        )
        self.assertEqual(batch.references[0].pub_date_unix_s, 1704412800)
        self.assertEqual(
            batch.downloads[0].normalized_title,
            normalize_text(normalize_title("Morbid", dl.title)),
        )
        self.assertIsNone(batch.downloads[0].pub_date_unix_s)

    def test_flattens_alignment_config_for_rust(self) -> None:
        alignment = AlignmentConfig(
            extra_stopwords=["morbid", "listener"],
            sparse_title_min=0.81,
            match_tolerance=0.77,
        )

        batch = prepare_alignment_batch([], [], "Morbid", alignment)

        self.assertEqual(batch.config.id_weight, alignment.weights.id)
        self.assertEqual(batch.config.date_weight, alignment.weights.date)
        self.assertEqual(batch.config.title_weight, alignment.weights.title)
        self.assertEqual(batch.config.description_weight, alignment.weights.description)
        self.assertEqual(batch.config.date_score_tiers, tuple(alignment.date_score_tiers))
        self.assertEqual(batch.config.sparse_title_min, alignment.sparse_title_min)
        self.assertEqual(batch.config.match_tolerance, alignment.match_tolerance)
        self.assertEqual(batch.config.title_certainty_min, 0.97)
        self.assertEqual(batch.config.metadata_rescue_subset_sim_min, 0.78)
        self.assertEqual(batch.config.containment_bonus, 0.08)
        self.assertEqual(
            set(batch.config.base_anchor_stopwords),
            {
                "the",
                "a",
                "an",
                "and",
                "of",
                "with",
                "from",
                "for",
                "to",
                "in",
                "on",
                "at",
                "by",
                "episode",
                "part",
                "listener",
                "tales",
                "podcast",
                "mini",
                "special",
                "guest",
                "guests",
                "bonus",
                "volume",
                "vol",
            },
        )
        self.assertEqual(batch.config.extra_stopwords, ("morbid", "listener"))
