import unittest

from freesrt.segmentation import (
    SegmentationConfig,
    display_length,
    grapheme_units,
    segment_cues,
    wrap_text,
)


class SegmentationTestCase(unittest.TestCase):
    def test_thai_without_spaces_is_split_without_placeholder(self):
        source = "ไทยไม่มีช่องว่าง" * 12
        result = segment_cues([{"start_ms": 0, "end_ms": 10_000, "text": source}], language="th")
        self.assertGreater(len(result.cues), 1)
        self.assertEqual("".join("".join(cue["text"].split()) for cue in result.cues), "".join(source.split()))
        self.assertNotIn("...", "".join(cue["text"] for cue in result.cues))
        for cue in result.cues:
            self.assertLessEqual(display_length(cue["text"]), 70)
            self.assertTrue(all(len(grapheme_units(line)) <= 35 for line in cue["text"].splitlines()))

    def test_english_prefers_natural_line_breaks(self):
        source = "This is a very long subtitle paragraph that should be split across multiple readable subtitle events."
        result = segment_cues([{"start_ms": 0, "end_ms": 6_000, "text": source}], language="en")
        self.assertEqual(len(result.cues), 2)
        self.assertEqual(" ".join(" ".join(cue["text"].replace("\n", " ").split()) for cue in result.cues), source)
        self.assertTrue(any(issue["code"] == "SOFT_WORD_LIMIT" for issue in result.issues))

    def test_combining_marks_are_not_split(self):
        source = "กำลังทดสอบสระและวรรณยุกต์" * 5
        result = segment_cues([{"start_ms": 0, "end_ms": 8_000, "text": source}], language="th")
        self.assertGreater(len(result.cues), 1)
        self.assertEqual("".join("".join(cue["text"].split()) for cue in result.cues), "".join(source.split()))
        self.assertTrue(all(cue["end_ms"] > cue["start_ms"] for cue in result.cues))

    def test_short_text_is_only_wrapped(self):
        source = "one two three four five six seven eight"
        result = segment_cues([{"start_ms": 0, "end_ms": 3_000, "text": source}], language="en")
        self.assertEqual(len(result.cues), 1)
        self.assertEqual(result.cues[0]["text"].replace("\n", " "), source)
        self.assertLessEqual(max(len(line) for line in result.cues[0]["text"].splitlines()), 35)

    def test_unresolvable_timing_is_reported_without_empty_cues(self):
        result = segment_cues([{"start_ms": 0, "end_ms": 9_000, "text": "ก"}], language="th")
        self.assertEqual(len(result.cues), 1)
        self.assertTrue(any(issue["code"] == "SEGMENTATION_UNRESOLVED" for issue in result.issues))
        self.assertTrue(result.cues[0]["text"])

    def test_round_trip_is_idempotent(self):
        source = "A long sentence, with punctuation, that should wrap cleanly across subtitle lines."
        first = segment_cues([{"start_ms": 0, "end_ms": 5_000, "text": source}], language="en")
        second = segment_cues(first.cues, language="en")
        self.assertEqual(first.cues, second.cues)

    def test_config_can_use_stricter_line_limit(self):
        config = SegmentationConfig(max_line_chars=10, max_cue_chars=20)
        wrapped = wrap_text("one two three four", config)
        self.assertTrue(all(len(line) <= 10 for line in wrapped.splitlines()))


    def test_spaces_count_toward_the_hard_visual_line_limit(self):
        source = " ".join(["1234567"] * 9)
        result = segment_cues([{"start_ms": 0, "end_ms": 5_000, "text": source}], language="en")
        self.assertGreater(len(result.cues), 1)
        self.assertTrue(all(
            len(grapheme_units(line)) <= 35
            for cue in result.cues
            for line in cue["text"].splitlines()
        ))
        self.assertEqual(
            "".join("".join(cue["text"].split()) for cue in result.cues),
            "".join(source.split()),
        )

    def test_natural_boundary_stays_near_the_balanced_target(self):
        source = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
        result = segment_cues([{"start_ms": 0, "end_ms": 8_000, "text": source}], language="en")
        lengths = [display_length(cue["text"]) for cue in result.cues]
        self.assertGreater(len(lengths), 1)
        self.assertLessEqual(max(lengths) - min(lengths), 20)

    def test_minimum_duration_warning_only_when_actually_unresolved(self):
        source = " ".join(["1234567"] * 9)
        enough_time = segment_cues([{"start_ms": 0, "end_ms": 5_000, "text": source}], language="en")
        self.assertFalse(any(issue["code"] == "MIN_DURATION_UNRESOLVED" for issue in enough_time.issues))
        too_short = segment_cues([{"start_ms": 0, "end_ms": 1_000, "text": source}], language="en")
        self.assertTrue(any(issue["code"] == "MIN_DURATION_UNRESOLVED" for issue in too_short.issues))

    def test_proportional_timing_never_exceeds_hard_duration_when_feasible(self):
        source = "short. " + "longword" * 15
        result = segment_cues([{"start_ms": 0, "end_ms": 20_500, "text": source}], language="en")
        self.assertTrue(all(cue["end_ms"] - cue["start_ms"] <= 7_000 for cue in result.cues))

    def test_wrapped_punctuation_boundary_is_idempotent_at_capacity(self):
        source = "a" * 34 + "." + "b" * 35
        first = segment_cues([{"start_ms": 0, "end_ms": 5_000, "text": source}], language="en")
        second = segment_cues(first.cues, language="en")
        self.assertEqual(first.cues, second.cues)

    def test_reading_speed_violation_is_explicitly_unresolved(self):
        source = "x" * 60
        result = segment_cues([{"start_ms": 0, "end_ms": 2_000, "text": source}], language="en")
        self.assertTrue(any(issue["code"] == "READING_SPEED_UNRESOLVED" for issue in result.issues))

    def test_thai_sara_am_is_one_display_grapheme(self):
        self.assertEqual(grapheme_units("\u0e01\u0e33"), ["\u0e01\u0e33"])
        self.assertEqual(display_length("\u0e01\u0e33"), 1)


if __name__ == "__main__":
    unittest.main()
