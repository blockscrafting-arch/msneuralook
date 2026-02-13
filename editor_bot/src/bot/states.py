"""FSM states for edit and schedule flows."""

from aiogram.fsm.state import State, StatesGroup


class EditSummaryStates(StatesGroup):
    """Waiting for editor to send new summary text."""

    waiting_for_text = State()


class ScheduleStates(StatesGroup):
    """Waiting for editor to send schedule datetime."""

    waiting_for_datetime = State()
