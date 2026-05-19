from dashbox.core.duration import duration_text, existing_duration_text


def test_duration_text_formats_seconds_for_display() -> None:
    cases = (
        (123, "2:03"),
        (3661, "1:01:01"),
    )

    for value, expected in cases:
        assert duration_text(value) == expected


def test_duration_text_rejects_empty_and_non_numeric_values() -> None:
    for value in (0, True, "1:02"):
        assert duration_text(value) == ""


def test_existing_duration_text_accepts_preformatted_duration_only() -> None:
    cases = (
        ("01:02", "01:02"),
        ("1:02:03", "1:02:03"),
        ("2 min", ""),
    )

    for value, expected in cases:
        assert existing_duration_text(value) == expected
