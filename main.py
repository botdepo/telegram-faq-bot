"""Бот-визитка с ответами на частые вопросы.

Клиент видит приветствие и кнопки с частыми вопросами («Цены», «Адрес»,
«Доставка»…) — ответ приходит сразу. Если нужного нет, клиент просто
пишет — сообщение приходит владельцу, тот отвечает обычным «Ответить»
в Telegram, и бот пересылает ответ клиенту.

Настраивать ничего не нужно: кто первым напишет боту /start — тот
владелец. Вопросы, ответы и приветствие владелец задаёт командами
прямо в чате.

Токен бот получает из переменной окружения BOT_TOKEN — на botdepo её
подставляет панель, локально задайте сами (см. README).
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

dp = Dispatcher()


async def is_owner(event: Message | CallbackQuery) -> bool:
    # async, а не F.func: синхронные фильтры aiogram гоняет в другом потоке, а SQLite так не умеет
    return event.from_user.id == storage.owner_id()


DEFAULT_WELCOME = "Здравствуйте! Выберите вопрос ниже или просто напишите — ответим здесь же."


def faq_menu() -> InlineKeyboardMarkup | None:
    rows = [[InlineKeyboardButton(text=q, callback_data=f"faq:{fid}")] for fid, q, _ in storage.list_faq()]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if storage.claim_owner(message.from_user.id):
        await message.answer(
            "Вы владелец этого бота. Сообщения клиентов будут приходить сюда — "
            "отвечайте на них через «Ответить».\n\n"
            "Настройка:\n"
            "/welcome Текст — приветствие для клиентов\n"
            "/add Вопрос | Ответ — добавить кнопку с ответом, например:\n"
            "/add Цены | Стрижка — 1500 ₽, окрашивание — от 3000 ₽\n"
            "/list — список вопросов с кнопками удаления\n\n"
            "Так бот сейчас выглядит для клиентов:"
        )
    await message.answer(storage.get("welcome", DEFAULT_WELCOME), reply_markup=faq_menu())


@dp.message(Command("welcome"), is_owner)
async def set_welcome(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Например: /welcome Здравствуйте! Это кофейня «Зерно». Чем помочь?")
        return
    storage.put("welcome", command.args)
    await message.answer("Приветствие обновил. /start — посмотреть, как видят клиенты.")


@dp.message(Command("add"), is_owner)
async def add(message: Message, command: CommandObject) -> None:
    question, sep, answer = (command.args or "").partition("|")
    question, answer = question.strip(), answer.strip()
    if not sep or not question or not answer:
        await message.answer("Формат: /add Вопрос | Ответ\nНапример: /add Адрес | Москва, ул. Ленина, 1. Ежедневно 10–21.")
        return
    if len(question) > 60:
        await message.answer("Вопрос длинноват для кнопки — уложитесь в 60 символов.")
        return
    storage.add_faq(question, answer)
    await message.answer(f"Добавил «{question}». /start — посмотреть, как видят клиенты.")


@dp.message(Command("list"), is_owner)
async def list_(message: Message) -> None:
    items = storage.list_faq()
    if not items:
        await message.answer("Вопросов пока нет. Добавьте: /add Вопрос | Ответ")
        return
    rows = [[InlineKeyboardButton(text=f"🗑 {q}", callback_data=f"del:{fid}")] for fid, q, _ in items]
    await message.answer("Нажмите, чтобы удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.regexp(r"^del:\d+$"), is_owner)
async def delete(callback: CallbackQuery) -> None:
    storage.delete_faq(int(callback.data.split(":")[1]))
    rows = [[InlineKeyboardButton(text=f"🗑 {q}", callback_data=f"del:{fid}")] for fid, q, _ in storage.list_faq()]
    await callback.message.edit_text(
        "Нажмите, чтобы удалить:" if rows else "Все вопросы удалены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
    )
    await callback.answer("Удалено")


@dp.callback_query(F.data.regexp(r"^faq:\d+$"))
async def show_answer(callback: CallbackQuery) -> None:
    item = storage.get_faq(int(callback.data.split(":")[1]))
    if item is None:
        await callback.answer("Этого вопроса уже нет", show_alert=True)
        return
    await callback.message.answer(f"{item[1]}\n\n{item[2]}", reply_markup=faq_menu())
    await callback.answer()


@dp.message(is_owner, F.reply_to_message)
async def reply_to_client(message: Message, bot: Bot) -> None:
    client = storage.client_of(message.reply_to_message.message_id)
    if client is None:
        await message.answer("Не нашёл, чьё это сообщение. Отвечайте именно на сообщение клиента.")
        return
    try:
        await bot.copy_message(client, message.chat.id, message.message_id)
    except TelegramAPIError:
        await message.answer("Не получилось доставить: клиент, похоже, заблокировал бота.")
        return
    await message.answer("Отправил.")


@dp.message(is_owner)
async def owner_hint(message: Message) -> None:
    await message.answer("Чтобы ответить клиенту, нажмите на его сообщение → «Ответить». Команды — в /start.")


@dp.message(F.chat.type == "private")
async def from_client(message: Message, bot: Bot) -> None:
    owner = storage.owner_id()
    if owner is None:
        await message.answer("Бот ещё не настроен. Владелец должен первым написать /start.")
        return
    if message.text and message.text.startswith("/"):
        await message.answer("Выберите вопрос или просто напишите сообщение.", reply_markup=faq_menu())
        return
    # forward показывает владельцу, кто пишет; ответ находим по id пересланного сообщения
    forwarded = await bot.forward_message(owner, message.chat.id, message.message_id)
    storage.remember_thread(forwarded.message_id, message.from_user.id)
    await message.answer("Передал. Ответим здесь, как только сможем.")


async def main() -> None:
    bot = Bot(token=os.environ["BOT_TOKEN"])
    me = await bot.get_me()
    logging.info("бот запущен: @%s", me.username)
    if storage.owner_id() is None:
        logging.info("владельца пока нет: напишите боту /start первым — станете владельцем")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
