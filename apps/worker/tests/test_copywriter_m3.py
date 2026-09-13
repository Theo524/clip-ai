from services.copywriter import generate_clip_copy_local


def test_m3_generates_description_and_useful_subject_tags():
    generated = generate_clip_copy_local(
        "They told us the walls were built to protect humanity. But the truth is the walls were hiding something from everyone.",
        "auto",
        local_context="The scouts returned from outside the walls. They told us the walls were built to protect humanity. But the truth is the walls were hiding something from everyone.",
        subject_hint="Attack on Titan",
        content_type="anime",
        moment_type="reveal",
    )
    assert generated.description
    assert generated.description.endswith((".", "!", "?", "…"))
    assert "#AttackOnTitan" in generated.hashtags
    assert "#Anime" in generated.hashtags
    assert "#Reveal" in generated.hashtags
    assert "#Eren" not in generated.hashtags
    assert "Eren" not in generated.title


def test_m3_uses_only_trusted_subject_hint_for_show_name():
    generated = generate_clip_copy_local(
        "He finally understood why the plan had failed, and the room went silent.",
        subject_hint="Attack on Titan",
        content_type="anime",
    )
    assert "Attack on Titan" in generated.grounded_terms
    assert any(tag == "#AttackOnTitan" for tag in generated.hashtags)


def test_m3_does_not_invent_unsupplied_character_names():
    generated = generate_clip_copy_local(
        "They reached the gate just before it closed. Nobody knew whether they would make it back.",
        content_type="anime",
        moment_type="action",
    )
    combined = f"{generated.title} {generated.description} {' '.join(generated.hashtags)}"
    for invented in ("Eren", "Mikasa", "Naruto", "Goku"):
        assert invented not in combined


def test_m3_documentary_title_uses_complete_when_clause():
    generated = generate_clip_copy_local(
        "When wolves returned to Yellowstone, elk stopped spending as much time in the valleys. The vegetation recovered, and even the riverbanks began to change.",
        subject_hint="Planet Earth III",
        content_type="documentary",
        moment_type="informative",
    )
    assert "wolves returned to yellowstone" in generated.title.lower()
    assert len(generated.title) <= 78
    assert "#Yellowstone" in generated.hashtags
    assert "#Documentary" in generated.hashtags


def test_m3_social_caption_is_description_plus_tags_for_relay_compatibility():
    generated = generate_clip_copy_local(
        "The biggest mistake I made was hiring too quickly. That's why I now hire slowly and test for values first.",
        content_type="podcast",
        moment_type="informative",
    )
    assert generated.social_caption.startswith(generated.description)
    assert "\n\n#" in generated.social_caption
    assert "#Podcast" in generated.social_caption


def test_m3_hashtag_list_is_short_and_deduplicated():
    generated = generate_clip_copy_local(
        "Wolves changed the valley. Wolves changed the riverbanks. Wolves changed how elk moved through the valley.",
        subject_hint="Wolves",
        content_type="documentary",
        moment_type="informative",
    )
    assert len(generated.hashtags) <= 7
    assert len({tag.lower() for tag in generated.hashtags}) == len(generated.hashtags)


def test_m3_local_context_can_help_choose_topic_without_leaking_into_description():
    generated = generate_clip_copy_local(
        "The riverbanks began to recover after that.",
        local_context="Wolves returned to Yellowstone. Elk moved away from the riverbanks. The riverbanks began to recover after that.",
        content_type="documentary",
    )
    assert "Wolves returned" not in generated.description
    assert "Yellowstone" not in generated.description
