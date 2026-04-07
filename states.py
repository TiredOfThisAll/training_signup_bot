from aiogram.fsm.state import State, StatesGroup


class AddWorkout(StatesGroup):
    weekday = State()
    registration_start = State()
    registration_end = State()
    train_start = State()
    train_end = State()
    max_participants = State()
