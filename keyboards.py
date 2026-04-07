from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

days_map = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


# --- выбор дня ---
def days_kb():
    buttons = [
        InlineKeyboardButton(text=day, callback_data=f"weekday:{i}")
        for i, day in enumerate(days_map)
    ]

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# --- универсальная клавиатура времени ---
def time_kb(prefix: str):
    """
    prefix:
        registration_start
        registration_end
        train_start
        train_end
    """
    times = [f"{h:02d}:00" for h in range(6, 24)]

    buttons = [
        [InlineKeyboardButton(text=t, callback_data=f"{prefix}:{t}")]
        for t in times
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- лимит участников ---
def max_kb():
    buttons = [
        [InlineKeyboardButton(text=str(i), callback_data=f"max:{i}")]
        for i in [8, 10, 12, 15, 18, 20, 25, 30]
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- выбор групп ---
def admin_groups_kb(groups):
    buttons = [
        [InlineKeyboardButton(
            text=f"{g.title}",
            callback_data=f"admin:group:{g.chat_id}"
        )]
        for g in groups
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- список тренировок ---
def workouts_kb(workouts):
    buttons = []

    for w in workouts:
        text = (
            f"{days_map[w.weekday]}\n"
            f"📝 {w.registration_start}-{w.registration_end}\n"
            f"🏋 {w.train_start}-{w.train_end}\n"
            f"👥 {w.max_participants}"
        )

        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"admin:workout:{w.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Добавить тренировку", callback_data="admin:add"),
        InlineKeyboardButton(text="❌ Удалить тренировку", callback_data="admin:delete"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- удаление ---
def delete_kb(workouts):
    buttons = [
        [
            InlineKeyboardButton(
                text=f"❌ {days_map[w.weekday]} {w.train_start}-{w.train_end}",
                callback_data=f"delete:{w.id}"
            )
        ]
        for w in workouts
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)

