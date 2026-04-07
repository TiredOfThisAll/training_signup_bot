from loguru import logger
import sys
import os


def setup_logger():
    os.makedirs("logs", exist_ok=True)
    logger.remove()  # убираем дефолтный логгер

    # --- Консоль ---
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | "
               "<level>{level}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>"
    )

    # --- Файл ---
    logger.add(
        "logs/bot.log",
        level="DEBUG",
        rotation="10 MB",       # новый файл при 10MB
        retention="7 days",     # хранить 7 дней
        compression="zip",      # архивировать старые
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )

    return logger
