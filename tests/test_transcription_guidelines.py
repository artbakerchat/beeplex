from beeplex.transcription_guidelines import validate_segments, validate_transcript


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
