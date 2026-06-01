from src.core.prompts.persona_profiles import PersonaId, get_persona_profile


def test_persona_profile_exposes_structured_layers() -> None:
    persona = get_persona_profile(PersonaId.MARLOWE_NOIR)

    assert persona.role_identity
    assert persona.stable_traits
    assert persona.language_style
    assert persona.value_boundaries
    assert persona.companion_boundaries

    flattened = persona.system_instruction
    assert "Stable traits:" in flattened
    assert "Language style:" in flattened
    assert "Value boundaries:" in flattened
    assert "Companion boundaries:" in flattened
