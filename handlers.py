import asyncio
import json
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, FSInputFile, Message

from keyboards import (
    after_test_keyboard,
    answer_keyboard,
    phone_request_keyboard,
    remove_keyboard,
    start_test_keyboard,
)
from states import TestStates

logger = logging.getLogger(__name__)
router = Router()

BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = BASE_DIR / "data" / "questions.json"
START_IMAGE = BASE_DIR / "images" / "start.png"
END_IMAGE = BASE_DIR / "images" / "end.png"

WELCOME_TEXT = (
    "👋 Вітаємо в Talkaholics English School!\n\n"
    "Цей експрес-тест допоможе визначити ваш рівень англійської мови "
    "від A1 до C1.\n\n"
    "📋 15 питань з варіантами відповідей A, B, C.\n"
    "⏱ Займе лише кілька хвилин.\n\n"
    "Натисніть «Старт», щоб розпочати!"
)

PROMO_TEXT = (
    "🎓 Talkaholics English School\n\n"
    "Хочете покращити свою англійську швидко та ефективно?\n\n"
    "✅ Індивідуальний підхід\n"
    "✅ Досвідчені викладачі\n"
    "✅ Безкоштовна консультація для нових учнів\n\n"
    "▶️Запишіться на безкоштовну консультацію — ми допоможемо "
    "скласти персональний план навчання!"
)

LEVEL_DESCRIPTIONS = {
    "A1": "Початковий рівень (Beginner). Ви лише починаєте вивчати англійську.",
    "A2": "Базовий рівень (Elementary). Ви розумієте прості фрази та висловлювання.",
    "B1": "Середній рівень (Intermediate). Ви можете спілкуватися в побутових ситуаціях.",
    "B2": "Вище середнього (Upper-Intermediate). Ви впевнено володієте мовою.",
    "C1": "Просунутий рівень (Advanced). Ви вільно володієте англійською мовою.",
}


def load_questions() -> list[dict]:
    try:
        with QUESTIONS_PATH.open(encoding="utf-8") as file:
            questions = json.load(file)
        if len(questions) != 15:
            raise ValueError(f"Expected 15 questions, got {len(questions)}")
        return questions
    except Exception:
        logger.exception("Failed to load questions from %s", QUESTIONS_PATH)
        raise


QUESTIONS = load_questions()


async def send_with_typing(
        bot: Bot,
        chat_id: int,
        text: str,
        *,
        reply_markup=None,
        delay: float = 1.0,
        parse_mode: str | None = None,
) -> Message:
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    await asyncio.sleep(delay)
    kwargs = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": reply_markup,
    }
    if parse_mode is not None:
        kwargs["parse_mode"] = parse_mode
    return await bot.send_message(**kwargs)


def calculate_level(score: int, total: int) -> str:
    ratio = score / total
    if ratio <= 0.2:
        return "A1"
    if ratio <= 0.4:
        return "A2"
    if ratio <= 0.6:
        return "B1"
    if ratio <= 0.8:
        return "B2"
    return "C1"


def format_question(question: dict, chosen: str | None = None) -> str:
    options = question["options"]
    question_text = question["text"]

    if chosen is not None:
        answer = options[chosen]
        question_text = question_text.replace("___", f"[{answer} 😉 ]", 1)
    else:
        question_text = question_text.replace("___", "[___]")

    return (
        f"Питання {question['id']} з {len(QUESTIONS)}\n\n"
        f"{question_text}\n\n"
        f"A) {options['A']}\n"
        f"B) {options['B']}\n"
        f"C) {options['C']}"
    )


async def show_selected_answer(
        callback: CallbackQuery,
        question: dict,
        chosen: str,
) -> None:
    if not callback.message:
        return

    await callback.message.edit_text(
        text=format_question(question, chosen=chosen),
        reply_markup=None,
    )


async def send_question(bot: Bot, chat_id: int, question_index: int) -> None:
    question = QUESTIONS[question_index]
    await send_with_typing(
        bot,
        chat_id,
        format_question(question),
        reply_markup=answer_keyboard(question["id"]),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    user = message.from_user
    logger.info("User %s started the bot", user.id if user else "unknown")

    try:
        if not START_IMAGE.exists():
            raise FileNotFoundError(f"Start image not found: {START_IMAGE}")

        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await asyncio.sleep(1.0)
        await message.answer_photo(
            photo=FSInputFile(START_IMAGE),
            caption=WELCOME_TEXT,
            reply_markup=start_test_keyboard(),
        )
    except Exception:
        logger.exception("Error sending welcome message to user %s", user.id)
        await message.answer(
            "Вітаємо! На жаль, сталася помилка. Спробуйте ще раз пізніше.",
        )


@router.callback_query(F.data == "start_test")
async def start_test(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()

    try:
        await state.clear()
        await state.set_state(TestStates.answering)
        # Ініціалізуємо список для збору відповідей та лічильник балів
        await state.update_data(
            current_index=0,
            score=0,
            report_lines=[],
        )

        if callback.message:
            await send_question(bot, callback.message.chat.id, 0)
    except Exception:
        logger.exception(
            "Error starting test for user %s",
            callback.from_user.id,
        )
        await send_with_typing(
            bot,
            callback.message.chat.id if callback.message else callback.from_user.id,
            "На жаль, сталася помилка під час запуску тесту. "
            "Спробуйте ще раз командою /start.",
        )


@router.callback_query(F.data.startswith("answer:"))
async def process_answer(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        admin_id: int,
) -> None:
    await callback.answer()

    current_state = await state.get_state()
    if current_state != TestStates.answering.state:
        return

    try:
        _, question_id_str, chosen = callback.data.split(":")
        question_id = int(question_id_str)

        data = await state.get_data()
        current_index = data.get("current_index", 0)
        score = data.get("score", 0)
        report_lines = data.get("report_lines", [])

        question = QUESTIONS[current_index]
        if question["id"] != question_id:
            logger.warning(
                "Question mismatch for user %s: expected %s, got %s",
                callback.from_user.id,
                question["id"],
                question_id,
            )
            return

        options = question["options"]
        correct = question["correct"]
        chosen_text = options.get(chosen, chosen)
        correct_text = options.get(correct, correct)

        # Перевіряємо відповідь та формуємо рядок для звіту
        if chosen == correct:
            score += 1
            report_lines.append(
                f"🔹 Питання {question['id']}: {question['text']}\n"
                f"   Відповідь: {chosen}) {chosen_text} (✅)"
            )
        else:
            report_lines.append(
                f"🔹 Питання {question['id']}: {question['text']}\n"
                f"   Відповідь: {chosen}) {chosen_text} (❌ Правильно: {correct}) {correct_text})"
            )

        if callback.message:
            await show_selected_answer(callback, question, chosen)
            await asyncio.sleep(0.6)

        next_index = current_index + 1
        chat_id = callback.message.chat.id if callback.message else callback.from_user.id

        if next_index >= len(QUESTIONS):
            await state.clear()
            level = calculate_level(score, len(QUESTIONS))

            # Формуємо інформацію про користувача для адміна
            user = callback.from_user
            user_link = f"@{user.username}" if user.username else user.full_name

            # Збираємо весь звіт в одне повідомлення
            admin_report = (
                    f"📋 **Новий результат тесту з англійської!**\n"
                    f"👤 Користувач: {user_link} (ID: `{user.id}`)\n"
                    f"🏆 Балів: {score}/{len(QUESTIONS)}\n"
                    f"📊 Рівень: **{level}**\n\n"
                    f"**Деталі тесту та помилки:**\n\n" +
                    "\n\n".join(report_lines)
            )

            # Надсилаємо єдине повідомлення адміністратору
            await bot.send_message(
                chat_id=admin_id,
                text=admin_report,
                parse_mode=ParseMode.HTML,
            )

            result_text = (
                f"🎯 Результат тесту\n\n"
                f"Правильних відповідей: {score} з {len(QUESTIONS)}\n"
                f"Ваш рівень: <b>{level}</b>\n\n"
                f"{LEVEL_DESCRIPTIONS[level]}"
            )

            await send_with_typing(
                bot,
                chat_id,
                result_text,
                delay=1.2,
                parse_mode=ParseMode.HTML,
                reply_markup=after_test_keyboard(),
            )

            if not END_IMAGE.exists():
                raise FileNotFoundError(f"End image not found: {END_IMAGE}")

            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(1.0)
            await bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(END_IMAGE),
                caption=PROMO_TEXT,
            )

            logger.info(
                "User %s completed test: score=%s, level=%s",
                user.id,
                score,
                level,
            )
            return

        # Зберігаємо оновлений індекс, бал та накопичений звіт у стейт
        await state.update_data(
            current_index=next_index,
            score=score,
            report_lines=report_lines,
        )
        await send_question(bot, chat_id, next_index)

    except Exception:
        logger.exception(
            "Error processing answer for user %s",
            callback.from_user.id,
        )
        chat_id = callback.message.chat.id if callback.message else callback.from_user.id
        await send_with_typing(
            bot,
            chat_id,
            "На жаль, сталася помилка. Почніть тест заново командою /start.",
        )
        await state.clear()


@router.callback_query(F.data == "request_consultation")
async def request_consultation(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
) -> None:
    await callback.answer()

    try:
        await state.set_state(TestStates.waiting_for_phone)
        chat_id = callback.message.chat.id if callback.message else callback.from_user.id

        await send_with_typing(
            bot,
            chat_id,
            "📞 Будь ласка, надішліть ваш номер телефону, "
            "натиснувши кнопку «Надіслати номер» нижче.\n\n"
            "Ми зв'яжемося з вами для запису на безкоштовну консультацію!",
            reply_markup=phone_request_keyboard(),
        )
        logger.info("User %s requested consultation", callback.from_user.id)
    except Exception:
        logger.exception(
            "Error requesting consultation from user %s",
            callback.from_user.id,
        )


@router.message(TestStates.waiting_for_phone, F.contact)
async def process_contact(
        message: Message,
        state: FSMContext,
        bot: Bot,
        admin_id: int,
) -> None:
    contact = message.contact
    user = message.from_user

    try:
        if contact.user_id and contact.user_id != user.id:
            await send_with_typing(
                bot,
                message.chat.id,
                "Будь ласка, надішліть саме свій номер телефону.",
            )
            return

        full_name = contact.first_name or "—"
        if contact.last_name:
            full_name = f"{full_name} {contact.last_name}"

        admin_text = (
            "📩 Нова заявка на безкоштовну консультацію!\n\n"
            f"👤 Ім'я: {full_name}\n"
            f"📱 Телефон: {contact.phone_number}\n"
            f"🆔 Telegram ID: {user.id}"
        )
        if user.username:
            admin_text += f"\n🔗 Username: @{user.username}"

        await bot.send_message(chat_id=admin_id, text=admin_text)

        await state.clear()
        await send_with_typing(
            bot,
            message.chat.id,
            "✅ Дякуємо! Ваш номер отримано.\n\n"
            "Наш менеджер зв'яжеться з вами найближчим часом "
            "для запису на безкоштовну консультацію. До зустрічі! 🎉",
            reply_markup=remove_keyboard(),
        )

        logger.info(
            "Contact from user %s sent to admin %s: %s",
            user.id,
            admin_id,
            contact.phone_number,
        )
    except Exception:
        logger.exception("Error processing contact from user %s", user.id)
        await send_with_typing(
            bot,
            message.chat.id,
            "На жаль, не вдалося надіслати заявку. Спробуйте ще раз пізніше.",
            reply_markup=remove_keyboard(),
        )
        await state.clear()


@router.message(TestStates.waiting_for_phone)
async def process_invalid_phone_input(message: Message, bot: Bot) -> None:
    await send_with_typing(
        bot,
        message.chat.id,
        "Будь ласка, використайте кнопку «Надіслати номер» "
        "для надсилання контакту.",
        reply_markup=phone_request_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, bot: Bot) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await send_with_typing(bot, message.chat.id, "Немає активних дій для скасування.")
        return

    await state.clear()
    await send_with_typing(
        bot,
        message.chat.id,
        "Дію скасовано. Щоб почати знову, натисніть /start.",
        reply_markup=remove_keyboard(),
    )