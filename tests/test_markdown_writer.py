from pathlib import Path

from app.markdown_writer import save_markdown_to_activities


def test_save_markdown_to_custom_output_dir(tmp_path: Path):
    draft = {"Activity Title": "Sorting and counting foam snowballs by size using number cards"}
    ordered_fields = ["Activity Title", "Preview content"]
    path, slug = save_markdown_to_activities(draft, ordered_fields, output_dir=tmp_path)
    assert path.exists()
    assert path.parent == tmp_path
    assert slug == "sorting-and-counting-foam-snowballs-by-size-using-number-cards"

