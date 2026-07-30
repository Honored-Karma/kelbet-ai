from aiogram.fsm.state import State, StatesGroup


class ChatStates(StatesGroup):
    waiting_message = State()
