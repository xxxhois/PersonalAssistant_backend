from src.services.mental_state import MentalState, MentalStateMachine


def test_mental_state_detects_low_energy_chinese_input() -> None:
    snapshot = MentalStateMachine().evaluate("今天真的好累，不想动")

    assert snapshot.state == MentalState.LOW_ENERGY
    assert snapshot.confidence > 0.5
    assert any("smallest useful action" in item for item in snapshot.prompt_constraints)
