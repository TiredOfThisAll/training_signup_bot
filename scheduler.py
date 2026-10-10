
import asyncio
from datetime import datetime

from loguru import logger

import repository as rep


def is_registration_time(t_day, now):
    if now.weekday() != t_day.weekday:
        return False

    current = now.strftime("%H:%M")

    # Конец интервала не включается.
    return t_day.registration_start <= current < t_day.registration_end


def get_active_training(schedules, now):
    for t_day in schedules:
        if is_registration_time(t_day, now):
            return t_day

    return None


async def notify(bot, chat_id, text) -> bool:
    try:
        await asyncio.wait_for(
            bot.send_message(chat_id, text),
            timeout=30,
        )
        return True

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            f"Failed to send notification | chat={chat_id}"
        )
        return False


def build_close_message(participants):
    if not participants:
        return "❌ Запись закрыта!\n\n👥 Участников нет"

    text = "❌ Запись закрыта!\n\n👥 Участники:\n"

    for i, participant in enumerate(participants, 1):
        text += (
            f"{i}. "
            f"{participant.username or participant.full_name}\n"
        )

    return text


async def close_registration(conn, bot, chat_id) -> bool:
    logger.info(f"CLOSE registration | chat={chat_id}")

    logger.info(f"CLOSE step=read_participants | chat={chat_id}")
    participants = await rep.get_participants(conn, chat_id)

    logger.info(
        f"CLOSE step=participants_loaded | chat={chat_id} "
        f"count={len(participants)}"
    )

    text = build_close_message(participants)

    logger.info(f"CLOSE step=send_message | chat={chat_id}")
    sent = await notify(bot, chat_id, text)

    if not sent:
        logger.error(
            f"CLOSE failed; keeping state and participants | "
            f"chat={chat_id}"
        )
        return False

    logger.info(f"CLOSE step=clear_participants | chat={chat_id}")
    await rep.clear_participants(conn, chat_id)

    logger.info(f"CLOSE complete | chat={chat_id}")
    return True


async def process_chat(conn, bot, chat_id):
    now = datetime.now()

    schedules = await rep.get_training_schedule(conn, chat_id)
    active_training = get_active_training(schedules, now)

    active_training_id = (
        active_training.id if active_training else None
    )

    state_exists, previous_training_id = (
        await rep.get_scheduler_state(conn, chat_id)
    )

    # Первое подключение после добавления persistent state.
    if not state_exists:
        logger.warning(
            f"Scheduler state bootstrap | chat={chat_id} "
            f"active={active_training_id}"
        )

        # Если регистрация уже закрыта, а участники остались,
        # восстанавливаем незавершённое закрытие.
        if active_training_id is None:
            participants = await rep.get_participants(conn, chat_id)

            if participants:
                closed = await close_registration(
                    conn, bot, chat_id
                )

                if not closed:
                    return

        await rep.set_scheduler_state(
            conn, chat_id, active_training_id
        )

        logger.info(
            f"Scheduler state initialized | chat={chat_id} "
            f"active={active_training_id}"
        )
        return

    # Состояние не изменилось — никаких действий не требуется.
    if previous_training_id == active_training_id:
        return

    # Предыдущее состояние было открыто.
    # Значит, сначала нужно корректно закрыть регистрацию.
    if previous_training_id is not None:
        closed = await close_registration(conn, bot, chat_id)

        if not closed:
            # Состояние останется прежним.
            # На следующем тике будет повторная попытка.
            return

        await rep.set_scheduler_state(conn, chat_id, None)

    # Текущее состояние открыто.
    if active_training_id is not None:
        logger.info(f"OPEN registration | chat={chat_id}")

        sent = await notify(
            bot,
            chat_id,
            "🔥 Запись открыта!",
        )

        if not sent:
            logger.error(
                f"OPEN failed; will retry | chat={chat_id}"
            )
            return

        await rep.set_scheduler_state(
            conn, chat_id, active_training_id
        )

        logger.info(
            f"OPEN complete | chat={chat_id} "
            f"training={active_training_id}"
        )


async def scheduler_loop(conn, bot, stop_event: asyncio.Event):
    while not stop_event.is_set():
        logger.info(
            f"Scheduler tick | "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        try:
            managed_chats = await rep.get_managed_chats(conn)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Failed to get managed chats; will retry"
            )

        else:
            for chat in managed_chats:
                try:
                    await process_chat(
                        conn,
                        bot,
                        chat.chat_id,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        f"Scheduler failed for chat={chat.chat_id}; "
                        f"will retry next tick"
                    )

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=60,
            )
            break

        except asyncio.TimeoutError:
            pass
