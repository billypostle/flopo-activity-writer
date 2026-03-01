from app.markdown_writer import save_markdown_to_activities
from app.notion_client import create_notion_draft


def test_local_save_still_works_when_notion_not_configured(tmp_path):
    draft = {"Activity Title": "Exploring texture through winter sensory baskets"}
    fields = ["Activity Title", "Preview content"]
    saved, _ = save_markdown_to_activities(draft, fields, output_dir=tmp_path)
    assert saved.exists()

    try:
        create_notion_draft(draft)
    except Exception as exc:
        # In local environments this may fail due to missing credentials,
        # invalid IDs, or permission issues. Any raised error is acceptable
        # for this fallback test; local save is the critical assertion.
        assert str(exc)
