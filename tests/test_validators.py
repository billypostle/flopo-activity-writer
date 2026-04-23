from app.validators import validate_draft


def _base_draft():
    return {
        "Activity Title": "Exploring winter textures in a small world sensory tray",
        "Themes": "Winter; Small world play",
        "Activity Summary": "This activity invites children to explore winter textures in open-ended play. Adults support language and shared attention without over-directing.",
        "Learning Objectives": "Children may notice texture, temperature and changes as they manipulate materials.",
        "Observation Cues": "Adults notice language, turn-taking and repeated choices.",
        "Linked materials": "",
        "Materials": "Builders tuff tray; Cotton wool; Ice cubes; Small world animals",
        "Step-by-Step Guidance": "Prepare a tray and offer a small set of winter-themed resources. Invite child-led exploration while observing and supporting.",
        "Adult Role": "Stay nearby, model simple language, and scaffold conflict resolution only when needed.",
        "Age Adaptation: 0-12 months (Little Learners)": "",
        "Age Adaptation: 12-24 months (Early Explorers)": "Offer fewer materials and simple language prompts.",
        "Age Adaptation: 2 years (Budding Adventurers)": "Add opportunities for symbolic play and short shared turns.",
        "Age Adaptation: 3 years (Curious Investigators)": "Invite predictions and comparison language during play.",
        "Age Adaptation: 4 years (Confident Discoverers)": "Encourage collaborative planning and reflection.",
        "Space Required": "A clear floor area around a low tray.",
        "Time Required": "20-30 minutes.",
        "Safety Considerations": "Supervise closely. Check loose parts for choking risk. Monitor wet surfaces to reduce slipping hazards.",
        "EYFS (2024) Links with Explanation": "Communication and Language is supported as adults model vocabulary. Physical Development is supported through grasping and scooping. Understanding the World is supported through sensory exploration of winter materials.",
        "Ethos Adaptation: Montessori": "Prepare a calm, ordered tray with limited materials and clear boundaries. The adult offers quiet observation and only models once. The adult notices concentration and responds by preserving uninterrupted work cycles.",
        "Ethos Adaptation: Forest School": "Move the activity outdoors using natural resources. The adult supports risk-managed exploration and adapts to weather changes. The adult observes resilience, problem-solving and collaboration in the outdoor space.",
        "Ethos Adaptation: Reggio Emilia": "Rearrange the environment with an intentional invitation table near natural light and visible documentation space. The adult documents language and collaboration, then responds with follow-up provocations. The adult observes group meaning-making and adjusts materials accordingly.",
        "Ethos Adaptation: Steiner (Waldorf)": "Use natural fibres and muted colours with a gentle rhythm. The adult models calm language and pacing. The adult notices emotional state, responds to fluctuations in engagement, and adapts tempo to support regulation.",
        "Preview content": "Children run their hands through cotton wool and pause when ice cubes slide across the tray. An adult crouches nearby, naming rough, smooth and cold as children compare what they feel.",
    }


def test_validate_draft_passes_for_well_formed_content():
    draft = _base_draft()
    fields = list(draft.keys())
    report = validate_draft(draft, fields)
    assert report.passed is True
    assert report.blocking_issues == []


def test_validate_draft_fails_on_bad_title():
    draft = _base_draft()
    draft["Activity Title"] = "Fun!"
    fields = list(draft.keys())
    report = validate_draft(draft, fields)
    assert report.passed is False
    assert any("title" in issue.lower() for issue in report.blocking_issues)


def test_procedural_leakage_in_summary_and_preview_is_warning_not_blocking():
    draft = _base_draft()
    draft["Activity Summary"] = (
        "Children explore winter textures in sustained play. "
        "Adults prepare prompts, then set up materials and adapt support responsively."
    )
    draft["Preview content"] = (
        "First, set up the tray and then introduce the materials with simple prompts."
    )
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    assert not any("summary may include setup/procedural detail" in i.lower() for i in report.blocking_issues)
    assert any("summary may include setup/procedural detail" in w.lower() for w in report.warnings)
    assert any("preview content may reveal too much setup/procedural detail" in w.lower() for w in report.warnings)


def test_passive_voice_warning_threshold_is_less_sensitive():
    draft = _base_draft()
    passive_sentence = "The activity is guided and is structured and is framed and is supported."
    draft["Learning Objectives"] = " ".join([passive_sentence] * 2)
    draft["Observation Cues"] = "The language is modelled and is scaffolded during play."
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    assert not any("passive voice" in w.lower() for w in report.warnings)


def test_preview_meta_language_is_blocking():
    draft = _base_draft()
    draft["Preview content"] = (
        "A brief excerpt showing children exploring shapes. "
        "The preview hints at open-ended dialogue while withholding the full steps."
    )
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    assert report.passed is False
    assert any("meta-language" in issue.lower() for issue in report.blocking_issues)


def test_preview_must_include_concrete_scene_detail():
    draft = _base_draft()
    draft["Preview content"] = (
        "Learning unfolds in meaningful ways across the experience. "
        "The moment supports broad developmental outcomes."
    )
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    assert report.passed is False
    assert any("too abstract" in issue.lower() for issue in report.blocking_issues)


def test_preview_write_up_language_is_blocking():
    draft = _base_draft()
    draft["Preview content"] = (
        "Winter-themed snowflake making with a folding and cutting approach; includes a counting extension using simple counters. "
        "Preview content hints at the range of adaptations and environment setups without disclosing full instructional steps."
    )
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    assert report.passed is False
    assert any("meta-language" in issue.lower() for issue in report.blocking_issues)
    assert any("scene actors" in issue.lower() for issue in report.blocking_issues)


def test_unknown_themes_are_blocking():
    draft = _base_draft()
    draft["Themes"] = "Winter; Sensory Play; Communication and Language; Water play"
    fields = list(draft.keys())
    report = validate_draft(draft, fields)

    assert report.passed is False
    assert any("webflow cms themes" in issue.lower() for issue in report.blocking_issues)
    assert any("Sensory Play" in issue for issue in report.blocking_issues)
