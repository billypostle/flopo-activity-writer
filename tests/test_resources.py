from app.resources import content_fields_from_csv, normalize_theme_list, parse_theme_values, parse_themes


def test_content_fields_from_csv_has_expected_columns():
    fields = content_fields_from_csv()
    assert "Activity Title" in fields
    assert "Preview content" in fields
    assert "Step-by-Step Guidance" in fields
    assert "Collection ID" not in fields


def test_parse_themes_preserves_webflow_theme_names_with_commas():
    themes = parse_themes()

    assert "Physical education (yoga, dance, football etc)" in themes


def test_parse_theme_values_accepts_comma_lists_and_outputs_semicolons():
    allowed = [
        "Winter",
        "Nature/rainbows and weather",
        "Creative arts and design",
        "Outdoor exploration",
    ]

    value = "Winter, Nature/rainbows and weather, Creative arts and design, Outdoor exploration"

    assert parse_theme_values(value, allowed) == allowed
    assert normalize_theme_list(value, allowed) == (
        "Winter; Nature/rainbows and weather; Creative arts and design; Outdoor exploration"
    )


def test_parse_theme_values_preserves_approved_names_with_internal_commas():
    allowed = ["Personal, Social and Emotional Development", "Winter"]

    assert parse_theme_values(
        "Winter, Personal, Social and Emotional Development",
        allowed,
    ) == ["Winter", "Personal, Social and Emotional Development"]


def test_parse_theme_values_allows_spaces_before_delimiters():
    allowed = ["Winter", "Outdoor exploration"]

    assert normalize_theme_list("Winter , Outdoor exploration", allowed) == (
        "Winter; Outdoor exploration"
    )
