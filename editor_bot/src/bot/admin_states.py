"""FSM states for admin panel input."""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """States for admin panel data entry."""

    adding_source_channel = State()
    changing_target_channel = State()
    adding_target_channel = State()
    adding_keyword = State()
    adding_editor = State()
    adding_admin = State()
    editing_openai_prompt = State()
    # Keyword groups
    adding_keyword_group = State()
    adding_keyword_group_choose_channel = State()
    adding_keyword_to_group = State()
    # Bulk keywords
    adding_keywords_bulk = State()
    adding_keywords_bulk_choose_group = State()
    # Edit scheduled post time
    editing_scheduled_time = State()
