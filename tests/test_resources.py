from app.resources import content_fields_from_csv


def test_content_fields_from_csv_has_expected_columns():
    fields = content_fields_from_csv()
    assert "Activity Title" in fields
    assert "Preview content" in fields
    assert "Step-by-Step Guidance" in fields
    assert "Collection ID" not in fields

