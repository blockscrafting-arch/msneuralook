"""FSM states for edit flow."""

from aiogram.fsm.state import State, StatesGroup


class EditSummaryStates(StatesGroup):
    """Waiting for editor to send new summary text."""

    waiting_for_text = State()
