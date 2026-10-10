from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, BotCommand
from aiogram.filters import Command
from aiogram.enums import ChatType
from aiogram.filters.chat_member_updated import \
    ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
import keyboards as kb


from static import TOKEN
import repository as rep
from connection import create_connection
import models
from states import AddWorkout
from logger import setup_logger


bot = Bot(token=TOKEN)
dp = Dispatcher()
admin_state = {} # user_id -> chat_id
logger = setup_logger()


# --- Logic ---

def is_registration_time(t_day: models.WeeklyPractice):
    now = datetime.now()

    if now.weekday() != t_day.weekday:
        return False

    current = now.strftime("%H:%M")

    return t_day.registration_start <= current < t_day.registration_end


async def notify_start(chat_id):
    await bot.send_message(chat_id, "🔥 Запись на тренировку открыта!")


async def notify_end(chat_id):
    await bot.send_message(chat_id, "❌ Запись закрыта!")


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="schedule", description="Расписание"),
        BotCommand(command="join", description="Записаться"),
        BotCommand(command="leave", description="Отменить запись"),
        BotCommand(command="list", description="Список участников"),
        BotCommand(command="help", description="Помощь"),
    ]

    await bot.set_my_commands(commands)


# ----- Events -----


@dp.errors()
async def errors_handler(event):
    logger.exception(f"Ошибка: {event.exception}")


# 1. Когда бот добавлен (переход из "не участник" в "участник")
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def bot_added(event: ChatMemberUpdated):
    conn = dp["db"]
    chat_id = event.chat.id
    logger.info(f"Бот добавлен в чат {chat_id}")
    await rep.get_or_create_managed_chat(conn, chat_id)

# 2. Когда бот удален (переход из "участник" в "не участник")
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER >> IS_NOT_MEMBER))
async def chat_leave_handler(event: ChatMemberUpdated):
    conn = dp["db"]
    chat_id = event.chat.id
    logger.info(f"Бот удален из чата {chat_id}")
    await rep.remove_managed_chat(conn, chat_id)


# --- Commands ---


@dp.message(Command("help"))
async def help_cmd(message: Message):
    text = (
        "📖 Команды бота:\n\n"
        "/schedule — расписание тренировок\n"
        "/join — записаться\n"
        "/leave — выйти\n"
        "/list — список участников\n"
        "/admin — панель админа\n"
        "/help — помощь\n"
    )

    await message.answer(text)



@dp.message(Command("schedule"))
async def show_schedule(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Команда только для группы 😏")
        return

    conn = dp["db"]
    schedule = await rep.get_training_schedule(conn, message.chat.id)

    if not schedule:
        await message.answer("Расписание пусто 😴")
        return

    text = "📅 Расписание:\n\n"

    days_map = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    for t in schedule:
        text += (
            f"{days_map[t.weekday]}\n"
            f"📝 Регистрация: {t.registration_start} - {t.registration_end}\n"
            f"🏃 Тренировка: {t.train_start} - {t.train_end}\n"
            f"👥 Лимит участников: {t.max_participants}\n\n"
        )

    await message.answer(text)


@dp.message(Command("join"))
async def join_list(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Я не работаю в личке 😏")
        return

    conn = dp["db"]
    schedule = await rep.get_training_schedule(conn, message.chat.id)

    active_training = None

    for t_day in schedule:
        if is_registration_time(t_day):
            active_training = t_day
            break

    if not active_training:
        await message.answer("Запись сейчас закрыта 😴")
        return

    count = await rep.count_participants(conn, message.chat.id)

    if count >= active_training.max_participants:
        await message.answer("Мест больше нет ❌")
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    success = await rep.add_participant(
        conn, message.chat.id, user.id, username, user.full_name
    )

    if not success:
        await message.answer("Ты уже записан 👀")
        return

    await message.answer(
        f"{username} записан! ({count + 1}/{active_training.max_participants})"
    )

    logger.info(f"JOIN | chat={message.chat.id} user={message.from_user.id}")


@dp.message(Command("leave"))
async def leave_list(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Я не работаю в личке 😏")
        return

    conn = dp["db"]

    username = message.from_user.username or message.from_user.full_name

    if not await rep.remove_participant(conn, message.chat.id, message.from_user.id):
        return await message.answer(f"{username} для начала нужно записаться!!!")
    
    await message.answer(f"{username} выписался 😢")
    logger.info(f"LEAVE | chat={message.chat.id} user={message.from_user.id}")


@dp.message(Command("list"))
async def show_list(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Я не работаю в личке 😏")
        return

    conn = dp["db"]

    participants = await rep.get_participants(conn, message.chat.id)

    if not participants:
        await message.answer("Список пуст 😴")
        return

    text = "📋 Список участников:\n\n"
    for i, participant in enumerate(participants, start=1):
        text += f"{i}. {participant.username or participant.full_name}\n"

    await message.answer(text)


# ----- Admin commands -----


@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return await message.answer("Пиши в личку 😏")

    conn = dp["db"]
    user_id = message.from_user.id

    managed_chats = await rep.get_managed_chats(conn)
    admin_chats = []

    for chat_entry in managed_chats:
        try:
            member = await bot.get_chat_member(chat_entry.chat_id, user_id)
            if member.status in ["administrator", "creator"]:
                chat = await bot.get_chat(chat_entry.chat_id)
                chat_entry.title = chat.title
                admin_chats.append(chat_entry)
        except:
            continue

    if not admin_chats:
        return await message.answer("Ты не админ 🤷")

    await message.answer(
        "Выбери группу:",
        reply_markup=kb.admin_groups_kb(admin_chats)
    )


@dp.callback_query(lambda c: c.data.startswith("admin:group:"))
async def select_group(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[2])

    admin_state[callback.from_user.id] = chat_id

    conn = dp["db"]
    workouts = await rep.get_training_schedule(conn, chat_id)
    chat = await bot.get_chat(chat_id)
    title = chat.title or str(chat_id)

    await callback.message.edit_text(
        f"Группа: {title}",
        reply_markup=kb.workouts_kb(workouts)
    )


# --- ADD FLOW ---

@dp.callback_query(lambda c: c.data == "admin:add")
async def add_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.edit_text(
        "Выбери день:",
        reply_markup=kb.days_kb()
    )
    await state.set_state(AddWorkout.weekday)


@dp.callback_query(AddWorkout.weekday, lambda c: c.data.startswith("weekday:"))
async def add_weekday(callback: CallbackQuery, state: FSMContext):
    await state.update_data(weekday=int(callback.data.split(":")[1]))

    await callback.message.edit_text(
        "Начало записи:",
        reply_markup=kb.time_kb("registration_start")
    )
    await state.set_state(AddWorkout.registration_start)


@dp.callback_query(
    AddWorkout.registration_start,
    lambda c: c.data.startswith("registration_start:")
)
async def add_registration_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(
        registration_start=callback.data.split(":")[1]
    )

    await callback.message.edit_text(
        "Конец записи:",
        reply_markup=kb.time_kb("registration_end")
    )
    await state.set_state(AddWorkout.registration_end)


@dp.callback_query(
    AddWorkout.registration_end,
    lambda c: c.data.startswith("registration_end:")
)
async def add_registration_end(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    registration_end = callback.data.split(":")[1]

    if registration_end <= data["registration_start"]:
        return await callback.answer("Конец записи раньше начала", show_alert=True)

    await state.update_data(registration_end=registration_end)

    await callback.message.edit_text(
        "Начало тренировки:",
        reply_markup=kb.time_kb("train_start")
    )
    await state.set_state(AddWorkout.train_start)


@dp.callback_query(AddWorkout.train_start, lambda c: c.data.startswith("train_start:"))
async def add_train_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    train_start = callback.data.split(":")[1]

    if train_start < data["registration_end"]:
        return await callback.answer(
            "Тренировка не может начаться раньше конца записи",
            show_alert=True
        )

    await state.update_data(train_start=train_start)

    await callback.message.edit_text(
        "Конец тренировки:",
        reply_markup=kb.time_kb("train_end")
    )
    await state.set_state(AddWorkout.train_end)


@dp.callback_query(AddWorkout.train_end, lambda c: c.data.startswith("train_end:"))
async def add_train_end(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    end = callback.data.split(":")[1]

    if end <= data["train_start"]:
        return await callback.answer("Конец раньше начала", show_alert=True)

    await state.update_data(train_end=end)

    await callback.message.edit_text(
        "Лимит участников:",
        reply_markup=kb.max_kb()
    )
    await state.set_state(AddWorkout.max_participants)


@dp.callback_query(AddWorkout.max_participants, lambda c: c.data.startswith("max:"))
async def add_finish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    max_p = int(callback.data.split(":")[1])

    conn = dp["db"]
    chat_id = admin_state.get(callback.from_user.id)

    if not chat_id:
        await callback.answer("Сначала выбери группу", show_alert=True)
        return

    has_conflict = await rep.has_time_conflict(
        conn,
        chat_id,
        data["weekday"],
        data["registration_start"],
        data["registration_end"]
    )
    if has_conflict:
        await callback.answer("На это время уже есть запись", show_alert=True)
        return

    created = await rep.create_weekly_practice(
        conn,
        chat_id,
        data["weekday"],
        data["registration_start"],
        data["registration_end"],
        data["train_start"],
        data["train_end"],
        max_p
    )

    if not created:
        await callback.answer("Не удалось сохранить тренировку", show_alert=True)
        return

    await callback.message.edit_text("✅ Добавлено")
    await state.clear()


@dp.callback_query(lambda c: c.data == "admin:delete")
async def delete_start(callback: CallbackQuery):
    conn = dp["db"]
    chat_id = admin_state.get(callback.from_user.id)

    if not chat_id:
        await callback.answer("Сначала выбери группу", show_alert=True)
        return

    workouts = await rep.get_training_schedule(conn, chat_id)

    if not workouts:
        await callback.answer("Нет тренировок", show_alert=True)
        return

    await callback.message.edit_text(
        "Выбери тренировку для удаления:",
        reply_markup=kb.delete_kb(workouts)
    )


@dp.callback_query(lambda c: c.data.startswith("delete:"))
async def delete_workout(callback: CallbackQuery):
    workout_id = int(callback.data.split(":")[1])

    conn = dp["db"]

    await rep.remove_weekly_practice(conn, workout_id)

    await callback.message.edit_text("❌ Удалено")


# --- Scheduler ---


async def bot_main():
    conn = await create_connection()

    logger.info("Бот запускается...")

    dp["db"] = conn
    await rep.init(conn)
    await set_commands(bot)

    logger.info("БД инициализирована")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await conn.close()

