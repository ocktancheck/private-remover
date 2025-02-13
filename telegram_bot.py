import asyncio
import os
import logging
import time
import sys
from telethon import TelegramClient, events, types, errors
from telethon.tl.functions.messages import DeleteHistoryRequest
from telethon.tl.types import PeerUser, PeerChat, PeerChannel

# Logging setup
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("telegram_bot.log", mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ANSI escape codes for colors (console output)
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'


# Configuration (replace with your data!)
API_ID = 25523669
API_HASH = '1fcedc4aa538f304fbf0cb16febb15be'

SESSION_NAME1 = 'sender_account'
SESSION_NAME2 = 'receiver_account'

BLACKLIST_FILE = 'blacklist.txt'

TELEGRAM_USER_ID = 777000


# Create Telegram clients
sender_client = TelegramClient(SESSION_NAME1, API_ID, API_HASH)
receiver_client = TelegramClient(SESSION_NAME2, API_ID, API_HASH)


def load_list_from_file(filename):
    """Loads a list of IDs from a file (generic function)."""
    logger.info(f"Загрузка списка из файла '{filename}'...")
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            id_list = [int(line.strip()) for line in f]
            logger.info(f"Загружено {len(id_list)} ID из '{filename}'.")
            return id_list
    except FileNotFoundError:
        logger.warning(f"Файл '{filename}' не найден. Список будет пуст.")
        return []
    except ValueError:
        logger.error(f"Ошибка в '{filename}': ID должны быть числами.")
        return []
    except Exception as e:
        logger.exception(f"Ошибка при загрузке списка из '{filename}': {e}")
        return []

def load_blacklist():
    """Loads the blacklist from the file."""
    return load_list_from_file(BLACKLIST_FILE)


async def delete_chats(client, include_bots=False, max_retries=3, retry_delay=5):
    """Deletes personal chats and bot chats, with retries."""
    blacklist = load_blacklist()
    logger.info(f"Удаление чатов на {client.session.filename}...")
    if include_bots:
        logger.info("Включено удаление чатов с ботами.")
    else:
        logger.info("Удаление чатов с ботами выключено.")

    try:
        dialogs = await client.get_dialogs()
        logger.info(f"Получено {len(dialogs)} диалогов.")
    except Exception as e:
        logger.exception(f"Ошибка получения диалогов: {e}")
        return

    deleted_count = 0
    error_count = 0

    for dialog in dialogs:

        # --- Personal Chat and Bot Handling ---
        if not dialog.is_user:
            logger.debug(f"Пропуск {dialog.name} (не личный чат).")
            continue

        if dialog.entity.id == TELEGRAM_USER_ID:
            logger.info(f"{Colors.BLUE}Пропуск Telegram (ID: {dialog.entity.id}).{Colors.RESET}")
            continue

        if dialog.entity.id in blacklist:
            logger.info(f"{Colors.BLUE}Пропуск {dialog.entity.first_name} ({dialog.entity.id}).{Colors.RESET}")
            continue

        if not include_bots and dialog.entity.bot:
            logger.info(f"{Colors.BLUE}Пропуск бота {dialog.entity.first_name} ({dialog.entity.id}).{Colors.RESET}")
            continue


        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"{Colors.YELLOW}Удаление {dialog.entity.first_name} ({dialog.entity.id})... ({retries + 1}/{max_retries}){Colors.RESET}")

                if isinstance(dialog.entity, types.User):
                    peer = PeerUser(dialog.entity.id)
                elif isinstance(dialog.entity, types.Chat):
                    peer = PeerChat(dialog.entity.id)
                elif isinstance(dialog.entity, types.Channel):
                    peer = PeerChannel(dialog.entity.id)
                else:
                    logger.warning(f"Неизвестный тип: {type(dialog.entity)}")
                    break

                await client(DeleteHistoryRequest(peer=peer, max_id=0, just_clear=False, revoke=False))
                await asyncio.sleep(0.5)

                logger.info(f"{Colors.GREEN}Удален {dialog.entity.first_name}.{Colors.RESET}")
                deleted_count += 1
                break


            except errors.FloodWaitError as e:
                logger.warning(f"Слишком много запросов! Ждем {e.seconds} сек...")
                await asyncio.sleep(e.seconds)
            except errors.PeerIdInvalidError:
                logger.warning(f"Неверный ID: {dialog.entity.id}. Пропуск.")
                error_count += 1
                break
            except errors.ChatAdminRequiredError:
                logger.error(f"Нет прав для удаления {dialog.entity.first_name}. Пропуск.")
                error_count += 1
                break
            except errors.UserBlockedError:
                logger.warning(f"Пользователь {dialog.entity.first_name} заблокирован. Невозможно удалить чат.")
                error_count += 1
                break
            except Exception as e:
                logger.exception(f"Ошибка при удалении {dialog.entity.first_name}: {e}")
                error_count += 1
                retries += 1  # Retry on unexpected error
        else:
            if retries == max_retries:
                logger.error(f"{Colors.RED}Не удален {dialog.entity.first_name} ({max_retries} попыток).{Colors.RESET}")
                error_count += 1

    logger.info(f"Удаление завершено. Удалено: {deleted_count}, Ошибок: {error_count}")



@sender_client.on(events.NewMessage(pattern=r'\.delete'))
async def delete_handler(event):
    """Handles the .delete command."""
    await delete_chats(receiver_client)
    await event.respond("Личные чаты удалены на втором аккаунте!")

@sender_client.on(events.NewMessage(pattern=r'\.deletebot'))
async def deletebots_handler(event):
    """Handles the .deletebots command."""
    await delete_chats(receiver_client, include_bots=True)
    await event.respond("Личные чаты и чаты с ботами удалены на втором аккаунте!")


async def run_client():
    """Runs the Telegram client and handles restarts."""
    while True:
        try:
            logger.info("Запуск Telegram-бота...")

            logger.info("Подключение аккаунта для отправки команд...")
            await sender_client.start()
            logger.info(f"{Colors.GREEN}Аккаунт-отправитель подключен!{Colors.RESET}")

            logger.info("Подключение аккаунта для удаления чатов...")
            await receiver_client.start()
            logger.info(f"{Colors.GREEN}Аккаунт-получатель подключен!{Colors.RESET}")

            logger.info("Бот запущен и готов к работе.")
            await sender_client.run_until_disconnected()
            await receiver_client.run_until_disconnected()

        except KeyboardInterrupt:
            logger.info("Остановка по Ctrl+C. Выход...")
            break
        except errors.PhoneNumberInvalidError:
            logger.critical("Неверный номер телефона! Проверьте настройки.")
            break
        except errors.AuthKeyUnregisteredError:
            logger.critical("Сессия недействительна! Переавторизуйтесь.")
            break
        except Exception as e:
            logger.exception(f"Непредвиденная ошибка: {e}. Перезапуск...")
            await asyncio.sleep(5)
        finally:
            if sender_client.is_connected():
                await sender_client.disconnect()
            if receiver_client.is_connected():
                await receiver_client.disconnect()
            logger.info("Клиенты отключены.")
            if sys.exc_info()[0] is KeyboardInterrupt:
                break



if __name__ == '__main__':
    asyncio.run(run_client())
