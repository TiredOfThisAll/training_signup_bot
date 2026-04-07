import asyncio
from datetime import datetime
from loguru import logger

import repository as rep


def is_registration_time(t_day):
    now = datetime.now()

    if now.weekday() != t_day.weekday:
        return False

    return (
        t_day.registration_start <= now.strftime("%H:%M")
        <= t_day.registration_end
    )


def get_active_training(schedules):
    for t_day in schedules:
        if is_registration_time(t_day):
            return t_day
    return None


async def notify(bot, chat_id, text):
    try:
        await bot.send_message(chat_id, text)
    except:
        pass


async def scheduler_loop(conn, bot, stop_event: asyncio.Event):
    t_lists_status = {}
    initialized_chats = set()

    while not stop_event.is_set():
        logger.debug("Scheduler tick")

        t_lists = await rep.get_managed_chats(conn)

        for t_list in t_lists:
            chat_id = t_list.chat_id

            schedules = await rep.get_training_schedule(conn, chat_id)
            active_training = get_active_training(schedules)
            active_training_id = active_training.id if active_training else None
            previous_training_id = t_lists_status.get(chat_id)

            if chat_id not in initialized_chats:
                t_lists_status[chat_id] = active_training_id
                initialized_chats.add(chat_id)
                continue

            if previous_training_id is None and active_training_id is not None:
                logger.info(f"OPEN registration | chat={chat_id}")
                await rep.clear_participants(conn, chat_id)
                await notify(bot, chat_id, "🔥 Запись открыта!")

            elif previous_training_id is not None and active_training_id is None:
                logger.info(f"CLOSE registration | chat={chat_id}")
                participants = await rep.get_participants(conn, chat_id)

                if participants:
                    text = "❌ Запись закрыта!\n\n👥 Участники:\n"

                    for i, p in enumerate(participants, 1):
                        text += f"{i}. {p.username or p.full_name}\n"

                else:
                    text = "❌ Запись закрыта!\n\n👥 Участников нет"

                await notify(bot, chat_id, text)
                await rep.clear_participants(conn, chat_id)

            t_lists_status[chat_id] = active_training_id

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
            break
        except asyncio.TimeoutError:
            pass
