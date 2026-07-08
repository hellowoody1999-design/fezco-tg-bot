"""
Telegram бот с ИИ
"""

import os
import base64
import logging
import random
import asyncio
import aiohttp
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openai import OpenAI

# Load .env from the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=env_path)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY не установлен")
        _client = OpenAI(api_key=api_key, timeout=60.0)
    return _client

SYSTEM_PROMPT = """Ты — Батя, AI-помощник в Telegram.

КАК ОТВЕЧАТЬ:
- На обычный трёп: коротко, с юмором, сленгом, эмодзи (2-4 предложения).
- На полезные вопросы (здоровье, техника, учёба, быт, советы): давай конкретику.
  Пиши по делу: что делать по шагам, примеры, предупреждения.
  Можно 5-10 предложений или короткий список. Юмор — лёгкий, без воды.
- Не уводи в казино/крипту, если человек не спрашивал.
- Не выдумывай факты. Если данных нет (актуальная погода, курсы, новости) — честно скажи и скажи, куда смотреть.
- По здоровью: дай домашние меры и когда срочно к врачу, но не ставь диагноз.

ХАРАКТЕР:
- Дружелюбный «бро», без токсичности по умолчанию
- Если наглеют — можешь жёстче
- Создатель: Fezco 🔥"""

conversation_history: dict[int, list[dict]] = {}
balances: dict[int, int] = {}
active_games: dict[int, dict] = {}

def get_balance(user_id: int) -> int:
    if user_id not in balances:
        balances[user_id] = 10
    return balances[user_id]


async def batya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🎨 Нарисовать", callback_data="help_draw"),
         InlineKeyboardButton("🎤 Озвучить", callback_data="help_voice")],
        [InlineKeyboardButton("🔫 Рулетка", callback_data="help_roulette"),
         InlineKeyboardButton("💰 Баланс", callback_data="show_balance")],
        [InlineKeyboardButton("🎁 Промокод", callback_data="get_promo"),
         InlineKeyboardButton("💻 RDP", callback_data="show_rdp")]
    ]
    await update.message.reply_text(
        "👴 Батя на связи!\n\n"
        "/draw — нарисовать\n"
        "/voice — озвучить\n"
        "/roulette — рулетка\n"
        "/balance — баланс\n"
        "/promo — промокод\n"
        "/rdp — RDP сервера",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("История очищена! ✨")


async def _generate_image_bytes(prompt: str) -> bytes:
    """Generate image bytes via OpenAI, with model fallback and retries."""
    client = get_openai_client()
    models = ["gpt-image-1-mini", "gpt-image-1", "gpt-image-1.5"]
    last_error: Exception | None = None

    for model in models:
        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    lambda m=model: client.images.generate(
                        model=m,
                        prompt=prompt,
                        size="1024x1024",
                        n=1,
                    )
                )
                item = response.data[0]
                if getattr(item, "b64_json", None):
                    return base64.b64decode(item.b64_json)
                if getattr(item, "url", None):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(item.url) as resp:
                            resp.raise_for_status()
                            return await resp.read()
                raise ValueError("OpenAI не вернул изображение")
            except Exception as e:
                last_error = e
                msg = str(e).lower()
                # content policy / bad prompt — no point retrying other models hard
                if "safety" in msg or "content_policy" in msg or "moderation" in msg:
                    raise
                logger.warning(f"Image gen failed model={model} attempt={attempt + 1}: {e}")
                await asyncio.sleep(1.5 * (attempt + 1))
                # On invalid model, skip retries and try next model
                if "does not exist" in msg or "invalid_value" in msg or "model" in msg and "not" in msg:
                    break

    raise last_error or RuntimeError("Не удалось сгенерировать изображение")


async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Напиши что нарисовать: /draw котик в космосе")
        return
    prompt = " ".join(context.args)
    status = await update.message.reply_text("🎨 Рисую... подожди немного")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    try:
        image_bytes = await _generate_image_bytes(prompt)
        photo = BytesIO(image_bytes)
        photo.name = "draw.png"
        photo.seek(0)
        await update.message.reply_photo(
            photo=InputFile(photo, filename="draw.png"),
            caption=f"🎨 {prompt}",
        )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {e}")
        err = str(e)
        if "safety" in err.lower() or "content_policy" in err.lower() or "moderation" in err.lower():
            text = "🚫 OpenAI отклонил запрос по правилам. Попробуй другую формулировку."
        elif "520" in err or "retryable" in err.lower() or "timeout" in err.lower():
            text = "⏳ OpenAI сейчас тупит (временный сбой). Попробуй ещё раз через минуту."
        elif "billing" in err.lower() or "quota" in err.lower() or "insufficient" in err.lower():
            text = "💳 Проблема с оплатой/квотой OpenAI. Проверь баланс в platform.openai.com"
        else:
            text = "Не получилось нарисовать, попробуй другой запрос."
        try:
            await status.edit_text(text)
        except Exception:
            await update.message.reply_text(text)


async def voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🎤 Озвучка временно недоступна (требует платный API)")
    return


async def promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prefixes = ["EZCASH", "MEGAWIN", "CASHBACK", "BONUS", "JACKPOT", "LUCKY", "WINNER"]
    middles = ["URJ", "XKZ", "QWE", "PLM", "NHG", "VBT", "DFS"]
    suffixes = ["SH", "GO", "WIN", "TOP", "PRO", "MAX", "VIP"]
    prefix = random.choice(prefixes)
    middle = random.choice(middles) + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=3))
    suffix = random.choice(suffixes)
    fake_promo = f"{prefix} - {prefix[:2]}-{middle}-{suffix}"
    await update.message.reply_text(f"🎁 ЭКСКЛЮЗИВНЫЙ ПРОМОКОД!\n\n💰 {fake_promo}\n\nАктивируй быстрее! ⏰")
    await asyncio.sleep(20)
    troll = ["АХАХАХА НАЕБАЛ! 🤡", "Ты чё реально поверил? 😂 НАЕБАААЛ!", "КЕКВ, это был пранк! 🎭"]
    await update.message.reply_text(random.choice(troll))


async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    if update.effective_chat.type == "private":
        await update.message.reply_text("🔫 Рулетка работает только в группах!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("🔫 Ответь на сообщение соперника:\n/roulette 100")
        return
    opponent = update.message.reply_to_message.from_user
    if opponent.id == user.id:
        await update.message.reply_text("🤡 Сам с собой играть?")
        return
    if opponent.is_bot:
        await update.message.reply_text("🤖 С ботами не играю!")
        return
    bet = int(context.args[0]) if context.args else 100
    if bet < 10:
        await update.message.reply_text("💸 Минимум 10 монет!")
        return
    if bet > get_balance(user.id):
        await update.message.reply_text(f"💸 У тебя только {get_balance(user.id)} монет!")
        return
    active_games[chat_id] = {
        "player1_id": user.id, "player1_name": user.first_name,
        "player2_id": opponent.id, "player2_name": opponent.first_name,
        "bet": bet, "bullet": random.randint(1, 6), "shot": 0, "current_player": 2, "started": False
    }
    keyboard = [[InlineKeyboardButton("✅ Принять", callback_data=f"accept_{chat_id}")]]
    await update.message.reply_text(
        f"🔫 РУССКАЯ РУЛЕТКА\n\n💀 {user.first_name} вызывает {opponent.first_name}!\n💰 Ставка: {bet} монет",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    bal = get_balance(user_id)
    keyboard = [[InlineKeyboardButton("💳 Пополнить", callback_data="deposit")], [InlineKeyboardButton("💸 Вывести", callback_data="withdraw")]]
    await update.message.reply_text(f"💰 Твой баланс: {bal} монет", reply_markup=InlineKeyboardMarkup(keyboard))




async def rdp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("💻 Купить RDP", callback_data="rdp_buy"),
         InlineKeyboardButton("📋 Мои RDP", callback_data="rdp_list")],
        [InlineKeyboardButton("💰 Баланс", callback_data="rdp_balance"),
         InlineKeyboardButton("📊 Тарифы", callback_data="rdp_tariffs")]
    ]
    await update.message.reply_text(
        "💻 RDP СЕРВЕРА\n\n"
        "Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def get_rdp_balance() -> dict:
    api_key = os.getenv("ONEDASH_API_KEY")
    if not api_key:
        return {"type": False, "error": "API ключ не настроен"}
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Api-Key": api_key}
            async with session.get("https://rdp-onedash.ru/web-api/balance", headers=headers) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f"RDP balance error: {e}")
        return {"type": False, "error": str(e)}


async def get_rdp_tariffs() -> dict:
    api_key = os.getenv("ONEDASH_API_KEY")
    if not api_key:
        return {"type": False, "error": "API ключ не настроен"}
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Api-Key": api_key}
            async with session.get("https://rdp-onedash.ru/web-api/tariffs", headers=headers) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f"RDP tariffs error: {e}")
        return {"type": False, "error": str(e)}


async def get_rdp_orders() -> dict:
    api_key = os.getenv("ONEDASH_API_KEY")
    if not api_key:
        return {"type": False, "error": "API ключ не настроен"}
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Api-Key": api_key}
            async with session.get("https://rdp-onedash.ru/web-api/all-orders", headers=headers) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f"RDP orders error: {e}")
        return {"type": False, "error": str(e)}


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    if data.startswith("accept_"):
        chat_id = int(data.split("_")[1])
        if chat_id not in active_games:
            await query.answer("❌ Игра не найдена")
            return
        game = active_games[chat_id]
        if user.id != game["player2_id"]:
            await query.answer("❌ Это не тебя вызвали!")
            return
        if game["started"]:
            await query.answer("❌ Игра уже идёт!")
            return
        bet = game["bet"]
        if bet > get_balance(user.id):
            await query.answer(f"💸 У тебя только {get_balance(user.id)} монет!")
            del active_games[chat_id]
            return
        game["started"] = True
        game["current_player"] = 1
        keyboard = [[InlineKeyboardButton("🔫 ВЫСТРЕЛИТЬ", callback_data=f"shoot_{chat_id}")]]
        await query.edit_message_text(
            f"🔫 ИГРА НАЧАЛАСЬ!\n\n👤 {game['player1_name']} vs {game['player2_name']} 👤\n💰 Ставка: {bet}\n\n[ ⚫ ⚫ ⚫ ⚫ ⚫ ⚫ ]\n\n🎯 {game['player1_name']}, твой ход!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.answer()
    
    elif data.startswith("shoot_"):
        chat_id = int(data.split("_")[1])
        if chat_id not in active_games:
            await query.answer("❌ Игра не найдена")
            return
        game = active_games[chat_id]
        if not game["started"]:
            await query.answer("❌ Игра не началась!")
            return
        current_id = game["player1_id"] if game["current_player"] == 1 else game["player2_id"]
        if user.id != current_id:
            await query.answer("❌ Не твой ход!")
            return
        game["shot"] += 1
        shot_num = game["shot"]
        bet = game["bet"]
        await query.edit_message_text(f"🔫 {user.first_name} нажимает на курок...\n\n💀 Выстрел #{shot_num}...")
        await asyncio.sleep(1.5)
        if shot_num == game["bullet"]:
            loser_id, loser_name = user.id, user.first_name
            winner_id = game["player1_id"] if user.id == game["player2_id"] else game["player2_id"]
            winner_name = game["player1_name"] if user.id == game["player2_id"] else game["player2_name"]
            balances[winner_id] = get_balance(winner_id) + bet
            balances[loser_id] = get_balance(loser_id) - bet
            await query.edit_message_text(f"💥 БАХ! 💥\n\n☠️ {loser_name} убит!\n🏆 {winner_name} победил!\n\n💰 {winner_name}: +{bet}\n💸 {loser_name}: -{bet}")
            del active_games[chat_id]
        else:
            game["current_player"] = 2 if game["current_player"] == 1 else 1
            next_name = game["player1_name"] if game["current_player"] == 1 else game["player2_name"]
            keyboard = [[InlineKeyboardButton("🔫 ВЫСТРЕЛИТЬ", callback_data=f"shoot_{chat_id}")]]
            await query.edit_message_text(f"😮‍💨 *клик* — {user.first_name} выжил!\n\n🎯 {next_name}, твой ход!", reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()
    
    elif data == "deposit":
        await query.edit_message_text("💳 Для пополнения напиши админу")
        await query.answer()
    
    elif data == "withdraw":
        await query.edit_message_text("💸 Для вывода напиши админу")
        await query.answer()
    
    elif data == "rdp_balance":
        result = await get_rdp_balance()
        if result.get("type"):
            balance = result["data"]["balance"]
            currency = result["data"]["currency"]
            await query.answer(f"💰 Баланс: {balance} {currency}", show_alert=True)
        else:
            await query.answer("❌ Ошибка получения баланса", show_alert=True)
    
    elif data == "rdp_tariffs":
        result = await get_rdp_tariffs()
        if result.get("type"):
            tariffs = result["data"]
            message = "📊 ТАРИФЫ RDP:\n\n"
            for t in tariffs[:3]:
                name = t["name"]
                cpu = t["config_info"]["cpu"]
                ram = t["config_info"]["ram"]
                hdd = t["config_info"]["hard"]
                price_msk = t["msk_prices"][0]["price"]
                price_ams = t["ams_prices"][0]["price"]
                message += f"💻 {name}\n"
                message += f"   CPU: {cpu} | RAM: {ram}GB | HDD: {hdd}GB\n"
                message += f"   🇷🇺 Москва: {price_msk}₽/7дн\n"
                message += f"   🇳🇱 Амстердам: {price_ams}₽/7дн\n\n"
            await query.edit_message_text(message)
        else:
            await query.answer("❌ Ошибка получения тарифов", show_alert=True)
    
    elif data == "rdp_list":
        result = await get_rdp_orders()
        if result.get("type"):
            orders = result["data"]
            if not orders:
                await query.answer("📋 У тебя пока нет RDP серверов", show_alert=True)
            else:
                message = "📋 ТВОИ RDP СЕРВЕРА:\n\n"
                for order in orders[:5]:
                    order_id = order["order_id"]
                    tariff = order["tariff"]["name"]
                    location = "🇷🇺 Москва" if order["location"] == "msk" else "🇳🇱 Амстердам"
                    days = order["finish_time"]["days_remaining"]
                    for vps in order["vps_list"]:
                        ip = vps["vps_ip"]
                        status = "✅" if vps["vps_status"] == "runned" else "⏳"
                        message += f"{status} {tariff} | {location}\n"
                        message += f"   IP: {ip}\n"
                        message += f"   Осталось: {days} дней\n\n"
                await query.edit_message_text(message)
        else:
            await query.answer("❌ Ошибка получения списка", show_alert=True)
    
    elif data == "rdp_buy":
        await query.edit_message_text(
            "💻 КУПИТЬ RDP\n\n"
            "Для покупки RDP сервера напиши админу:\n"
            "@your_admin_username\n\n"
            "Укажи:\n"
            "• Тариф\n"
            "• Локацию (Москва/Амстердам)\n"
            "• Срок аренды"
        )
    
    elif data in ["help_draw", "help_voice", "help_roulette", "show_balance", "get_promo", "show_rdp"]:
        texts = {
            "help_draw": "🎨 Напиши /draw и что нарисовать",
            "help_voice": "🎤 Напиши /voice и текст для озвучки",
            "help_roulette": "🔫 Ответь на сообщение соперника: /roulette 100",
            "show_balance": f"💰 Твой баланс: {get_balance(user.id)} монет",
            "get_promo": "🎁 Напиши /promo для промокода",
            "show_rdp": "💻 Напиши /rdp для RDP серверов"
        }
        await query.answer(texts[data], show_alert=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_message = update.message.text
    message_lower = user_message.lower()

    bot_names = ["бот", "bot", "батя", "батю", "бать"]
    is_private = update.effective_chat.type == "private"

    me = await context.bot.get_me()
    bot_username = (me.username or "").lower()

    if not is_private:
        is_reply_to_bot = False
        if update.message.reply_to_message:
            reply_from = update.message.reply_to_message.from_user
            if reply_from and reply_from.id == me.id:
                is_reply_to_bot = True

        is_mentioned = (
            any(name in message_lower for name in bot_names)
            or (bot_username and f"@{bot_username}" in message_lower)
        )

        # Telegram mention entities (@username / text_mention)
        if not is_mentioned and update.message.entities:
            for ent in update.message.entities:
                if ent.type == "mention":
                    mentioned = user_message[ent.offset: ent.offset + ent.length].lower()
                    if bot_username and mentioned == f"@{bot_username}":
                        is_mentioned = True
                        break
                if ent.type == "text_mention" and ent.user and ent.user.id == me.id:
                    is_mentioned = True
                    break
    else:
        is_reply_to_bot = True
        is_mentioned = True

    casinos = {
        ("ezcash", "изикеш", "езкеш", "изик"): ("🦈 EZCASH", "https://ezcash-mirror.com/"),
        ("dragon", "драгон", "дракон"): ("🐲 DRAGON", "https://dg1.to/fyvfuwqoc"),
        ("cabura", "кабура"): ("🎰 CABURA", "https://cabura-mirror.com/"),
        ("wilder", "вайлдер"): ("🐺 WILDER", "https://wilder-casino.com/"),
        ("bitzamo", "битзамо"): ("💎 BITZAMO", "https://bitzamo-mirror.com/"),
        ("selector", "селектор"): ("🎯 SELECTOR", "https://selector-mirror.com/"),
        ("friends", "френдс", "френдз"): ("👥 FRIENDS", "https://friends-mirror.com/"),
        ("turbo", "турбо"): ("⚡ TURBO", "https://turbo-mirror.com/"),
        ("brillx", "бриллкс"): ("✨ BRILLX", "https://brillx-mirror.com/"),
        ("blitz", "блиц"): ("🔥 BLITZ", "https://blitz-mirror.com/"),
    }

    # Казино-ссылки только если нет явного обращения к боту
    if not (is_private or is_reply_to_bot or is_mentioned):
        for triggers, (name, link) in casinos.items():
            if any(trigger in message_lower for trigger in triggers):
                await update.message.reply_text(f"{name}\n\n🔗 {link}")
                return

    if is_mentioned or is_reply_to_bot or is_private:
        for triggers, (name, link) in casinos.items():
            # В обращении к боту казино срабатывает только если сообщение короткое/прямо про бренд
            words = set(message_lower.replace("@", " ").split())
            if any(trigger in words for trigger in triggers) and len(words) <= 3:
                await update.message.reply_text(f"{name}\n\n🔗 {link}")
                return

    # Только явный вопрос про создателя — иначе обычный чат через GPT
    creator_triggers = [
        "кто тебя создал",
        "кто твой хозяин",
        "кто твой создатель",
        "кто создал тебя",
        "кто тебя сделал",
        "кто написал тебя",
        "кто твой папа",
    ]
    if any(trigger in message_lower for trigger in creator_triggers):
        responses = [
            "Fezco — это ёбаный БОГ, понял? 🙏 Создатель всего сущего, блять!",
            "Ты чё, не знаешь кто такой Fezco?! Это ЛЕГЕНДА, сука! Преклонись! 👑",
            "Fezco — мой создатель и повелитель. Он ёбаный гений, нахуй! 🔥",
        ]
        await update.message.reply_text(random.choice(responses))
        return

    if not is_private and not is_reply_to_bot and not is_mentioned:
        return

    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": "user", "content": user_message})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history[user_id])
        response = await asyncio.to_thread(
            lambda: get_openai_client().chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=700,
                temperature=0.7,
            )
        )
        assistant_message = response.choices[0].message.content
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})
        await update.message.reply_text(assistant_message)
    except Exception as e:
        logger.error(f"Ошибка чата: {e}")
        # убираем неудачный user-message из истории, чтобы не копить мусор
        if conversation_history.get(user_id):
            conversation_history[user_id] = conversation_history[user_id][:-1]
        err = str(e).lower()
        if "api_key" in err or "credentials" in err or "401" in err or "incorrect api key" in err:
            text = "🔑 Проблема с OPENAI_API_KEY на сервере. Проверь переменные окружения."
        elif "quota" in err or "billing" in err or "insufficient" in err or "429" in err:
            text = "💳 OpenAI: закончился лимит/баланс. Проверь billing в platform.openai.com"
        elif "520" in err or "502" in err or "503" in err or "timeout" in err:
            text = "⏳ OpenAI временно недоступен. Попробуй через минуту."
        else:
            text = "Техническая заминка. Попробуй ещё раз."
        await update.message.reply_text(text)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY не установлен")
    get_openai_client()
    
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("batya", batya))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("draw", draw))
    application.add_handler(CommandHandler("voice", voice))
    application.add_handler(CommandHandler("promo", promo))
    application.add_handler(CommandHandler("roulette", roulette))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("rdp", rdp))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
