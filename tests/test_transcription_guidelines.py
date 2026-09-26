from python.transcription_guidelines import (
    COMMON_SPELLINGS,
    FILLER_WORDS,
    NONVERBAL_TAGS,
    SUPPORTED_PUNCTUATION,
    page_rules,
    validate_segments,
    validate_transcript,
)


def codes(text):
    return {issue.code for issue in validate_transcript(text)}


def test_guideline_annotations_are_accepted():
    assert not codes(
        "(Speaker 1) [uh] I was thinking <pause> we should go, ((Tuesday))?"
    )


def test_filler_and_nonverbal_tags_are_checked():
    found = codes("uh, then <giggle> [maybe]")
    assert {"unbracketed-filler", "unknown-tag", "unknown-filler"} <= found


def test_only_supported_punctuation_is_allowed_in_prose():
    assert "unsupported-punctuation" in codes("What: really; yes")
    assert "unsupported-punctuation" not in codes("Are you serious!?")


def test_common_spellings_and_speaker_labels_are_reported():
    issues = validate_transcript("Okay, woah", speaker="Alice")
    found = {issue.code for issue in issues}
    assert {"standard-spelling", "speaker-label"} <= found


def test_segment_summary_is_page_safe():
    result = validate_segments(
        [{"id": 4, "speaker": "Speaker 1", "text": "[uh] <cough> hello."}]
    )
    assert result["standard"] == "Spontaneous Speech Data Annotations"
    assert result["speakerCount"] == 1
    assert result["hasErrors"] is False


def test_page_rules_are_the_validator_vocabularies():
    import json

    rules = json.loads(json.dumps(page_rules()))  # must survive a JSON round-trip
    assert set(rules["fillers"]) == set(FILLER_WORDS)
    assert set(rules["tags"]) == set(NONVERBAL_TAGS)
    assert set(rules["punctuation"]) == set(SUPPORTED_PUNCTUATION)
    assert rules["spellings"] == dict(COMMON_SPELLINGS)
    # Every injected vocabulary entry is accepted by the validator itself,
    # so the page's live checkText can never disagree with validate_transcript.
    for filler in rules["fillers"]:
        assert "unknown-filler" not in codes(f"[{filler}]")
    for tag in rules["tags"]:
        assert "unknown-tag" not in codes(f"<{tag}>")
