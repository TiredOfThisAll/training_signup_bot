from dataclasses import dataclass
from typing import Optional


@dataclass
class ManagedChat:
    chat_id: int
    title: Optional[str] = None


@dataclass
class WeeklyPractice:
    id: Optional[int]
    chat_id: int
    weekday: int  # 0-6 (Пн-Вс)
    registration_start: str
    registration_end: str
    train_start: str
    train_end: str
    max_participants: int


@dataclass
class Participant:
    id: Optional[int]
    chat_id: int
    user_id: int
    username: Optional[str]
    full_name: str
