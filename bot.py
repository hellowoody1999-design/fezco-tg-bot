"""
Telegram бот с ИИ
"""

import os
import logging
import random
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openai import OpenAI

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Ты — умный собеседник. Правила:
1. Отвечай КОРОТКО — максимум 2-3 предложения
2. Без воды и лишних слов
3. Говори по делу
4. Отвечай на русском

Если тебя оскорбляют или хамят — отвечай матом: блять, сука, пиздец, нахуй, ебать. 
Будь дерзким в ответ на хамство."""

conversation_history: dict[int, list[dict]] = {}
balances: dict[int, int] = {}
active_games: dict[int, dict] = {}
crypto_rates: dict[str, dict] = {}
last_update_time: str = "Не обновлялось"

def get_balance(user_id: int) -> int:
    if user_id not in balances:
        balances[user_id] = 10
    return balances[user_id]


async def fetch_crypto_rates() -> None:
    """Получает актуальные курсы обмена из CryptoBot"""
    global crypto_rates, last_update_time
    
    crypto_token = os.getenv("CRYPTO_BOT_TOKEN")
    if not crypto_token:
        logger.warning("CRYPTO_BOT_TOKEN не установлен, используем Binance P2P")
        await fetch_binance_p2p()
        return

    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Crypto-Pay-API-Token": crypto_token}
            
            async with session.get("https://pay.crypt.bot/api/getExchangeRates", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if not data.get("ok"):
                        logger.error(f"CryptoBot API error: {data}")
                        await fetch_binance_p2p()
                        return
                    
                    rates = {}
                    for rate_info in data.get("result", []):
                        source = rate_info.get("source", "")
                        target = rate_info.get("target", "")
                        rate = float(rate_info.get("rate", 0))
                        is_valid = rate_info.get("is_valid", False)

                        if source and target and rate > 0 and is_valid:
                            pair_name = f"{source}/{target}"
                            rates[pair_name] = {
                                "price": rate,
                                "rate": rate,
                                "is_valid": is_valid,
                                "source": "CryptoBot"
                            }

                    crypto_rates = rates
                    last_update_time = datetime.now().strftime("%H:%M:%S")
                    logger.info(f"CryptoBot курсы обновлены: {len(rates)} пар")
                else:
                    logger.error(f"HTTP {resp.status} при получении курсов CryptoBot")
                    await fetch_binance_p2p()
    except Exception as e:
        logger.error(f"Ошибка получения курсов CryptoBot: {e}")
        await fetch_binance_p2p()


async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает актуальные курсы обмена"""
    if not crypto_rates:
        await update.message.reply_text("⏳ Загружаю курсы обмена...")
        await fetch_crypto_rates()
        if not crypto_rates:
            await update.message.reply_text("❌ Не удалось загрузить курсы, попробуй позже")
            return

    # Проверяем источник данных
    first_item = next(iter(crypto_rates.values()))
    source = first_item.get("source", "Unknown")

    if source == "CryptoBot":
        # Показываем курсы CryptoBot
        sorted_pairs = sorted(crypto_rates.items(), key=lambda x: x[1]["rate"], reverse=True)

        message = f"💱 КУРСЫ ОБМЕНА CRYPTOBOT\n🕐 Обновлено: {last_update_time}\n\n"
        message += "📈 ЛУЧШИЕ КУРСЫ:\n\n"

        for i, (pair, data) in enumerate(sorted_pairs[:15], 1):
            rate = data["rate"]
            message += f"{i}. {pair}: {rate:,.4f}\n"

    else:
        # Показываем Binance P2P
        sorted_pairs = sorted(crypto_rates.items(), key=lambda x: x[1]["price"], reverse=True)

        message = f"💱 P2P ОБМЕН USDT → RUB\n🕐 Обновлено: {last_update_time}\n\n"
        message += "📈 ЛУЧШИЕ КУРСЫ (ПРОДАЖА):\n\n"

        for i, (key, data) in enumerate(sorted_pairs[:10], 1):
            price = data["price"]
            min_amt = data.get("min", 0)
            max_amt = data.get("max", 0)
            available = data.get("available", 0)
            nickname = data.get("nickname", "Unknown")
            orders = data.get("orders", 0)
            completion = data.get("completion", 0)

            message += f"{i}. 💰 {price:.2f} ₽\n"
            message += f"   👤 {nickname}\n"
            message += f"   📊 {orders} сделок | {completion*100:.0f}% успех\n"
            message += f"   💵 {min_amt:.0f} - {max_amt:.0f} USDT\n"
            message += f"   ✅ Доступно: {available:.0f} USDT\n\n"

    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_crypto")]]
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))


async def fetch_binance_p2p() -> None:
    """Fallback: получает P2P объявления с Binance"""
    global crypto_rates, last_update_time

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "asset": "USDT",
                "fiat": "RUB",
                "merchantCheck": False,
                "page": 1,
                "payTypes": [],
                "publisherType": None,
                "rows": 20,
                "tradeType": "SELL"
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }

            async with session.post(
                "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
                json=payload,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates = {}

                    if data.get("data"):
                        ads = data["data"]
                        sorted_ads = sorted(ads, key=lambda x: float(x["adv"]["price"]), reverse=True)

                        for i, ad in enumerate(sorted_ads[:10], 1):
                            adv = ad["adv"]
                            advertiser = ad["advertiser"]

                            price = float(adv["price"])
                            min_amount = float(adv["minSingleTransAmount"])
                            max_amount = float(adv["dynamicMaxSingleTransAmount"])
                            available = float(adv["surplusAmount"])

                            rates[f"P2P_{i}"] = {
                                "price": price,
                                "min": min_amount,
                                "max": max_amount,
                                "available": available,
                                "nickname": advertiser.get("nickName", "Unknown"),
                                "orders": advertiser.get("monthOrderCount", 0),
                                "completion": advertiser.get("monthFinishRate", 0),
                                "rate": price,
                                "source": "Binance P2P"
                            }

                        crypto_rates = rates
                        last_update_time = datetime.now().strftime("%H:%M:%S")
                        logger.info(f"Binance P2P объявления обновлены: {len(rates)} продавцов")
                else:
                    logger.error(f"HTTP {resp.status} при получении Binance P2P")
    except Exception as e:
        logger.error(f"Ошибка получения Binance P2P: {e}")




async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает актуальные P2P объявления для обмена"""
    if not crypto_rates:
        await update.message.reply_text("⏳ Загружаю P2P объявления...")
        await fetch_crypto_rates()
        if not crypto_rates:
            await update.message.reply_text("❌ Не удалось загрузить объявления, попробуй позже")
            return
    
    # Сортируем по цене (от высокой к низкой)
    sorted_pairs = sorted(crypto_rates.items(), key=lambda x: x[1]["price"], reverse=True)
    
    message = f"💱 P2P ОБМЕН USDT → RUB\n🕐 Обновлено: {last_update_time}\n\n"
    message += "📈 ЛУЧШИЕ КУРСЫ (ПРОДАЖА):\n\n"
    
    # Показываем топ-10 объявлений
    for i, (key, data) in enumerate(sorted_pairs[:10], 1):
        price = data["price"]
        min_amt = data["min"]
        max_amt = data["max"]
        available = data["available"]
        nickname = data["nickname"]
        orders = data["orders"]
        completion = data["completion"]
        
        message += f"{i}. 💰 {price:.2f} ₽\n"
        message += f"   👤 {nickname}\n"
        message += f"   📊 {orders} сделок | {completion*100:.0f}% успех\n"
        message += f"   � {min_amt:.0f} - {max_amt:.0f} USDT\n"
        message += f"   ✅ Доступно: {available:.0f} USDT\n\n"
    
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_crypto")]]
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))


async def batya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🎨 Нарисовать", callback_data="help_draw"),
         InlineKeyboardButton("🎤 Озвучить", callback_data="help_voice")],
        [InlineKeyboardButton("🔫 Рулетка", callback_data="help_roulette"),
         InlineKeyboardButton("💰 Баланс", callback_data="show_balance")],
        [InlineKeyboardButton("💱 Курсы P2P", callback_data="show_crypto"),
         InlineKeyboardButton("🎁 Промокод", callback_data="get_promo")]
    ]
    await update.message.reply_text(
        "👴 Батя на связи!\n\n"
        "/draw — нарисовать\n"
        "/voice — озвучить\n"
        "/roulette — рулетка\n"
        "/balance — баланс\n"
        "/crypto — P2P обмен\n"
        "/promo — промокод",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("История очищена! ✨")


async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Напиши что нарисовать: /draw котик в космосе")
        return
    prompt = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    try:
        response = client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1024", quality="standard", n=1)
        await update.message.reply_photo(photo=response.data[0].url, caption=f"🎨 {prompt}")
    except Exception as e:
        logger.error(f"Ошибка DALL-E: {e}")
        await update.message.reply_text("Не получилось нарисовать, попробуй другой запрос.")


async def voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Напиши что озвучить: /voice Привет, как дела?")
        return
    text = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    try:
        response = client.audio.speech.create(model="tts-1", voice="onyx", input=text)
        audio_path = f"/tmp/voice_{update.effective_user.id}.mp3"
        response.stream_to_file(audio_path)
        with open(audio_path, "rb") as audio:
            await update.message.reply_voice(voice=audio)
        os.remove(audio_path)
    except Exception as e:
        logger.error(f"Ошибка TTS: {e}")
        await update.message.reply_text("Не получилось озвучить.")


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
    
    elif data == "refresh_crypto":
        await query.answer("🔄 Обновляю P2P объявления...")
        await fetch_crypto_rates()
        if not crypto_rates:
            await query.edit_message_text("❌ Не удалось обновить объявления")
            return
        
        # Сортируем по цене (от высокой к низкой)
        sorted_pairs = sorted(crypto_rates.items(), key=lambda x: x[1]["price"], reverse=True)
        
        message = f"💱 P2P ОБМЕН USDT → RUB\n🕐 Обновлено: {last_update_time}\n\n"
        message += "📈 ЛУЧШИЕ КУРСЫ (ПРОДАЖА):\n\n"
        
        for i, (key, pair_data) in enumerate(sorted_pairs[:10], 1):
            price = pair_data["price"]
            min_amt = pair_data["min"]
            max_amt = pair_data["max"]
            available = pair_data["available"]
            nickname = pair_data["nickname"]
            orders = pair_data["orders"]
            completion = pair_data["completion"]
            
            message += f"{i}. 💰 {price:.2f} ₽\n"
            message += f"   👤 {nickname}\n"
            message += f"   📊 {orders} сделок | {completion*100:.0f}% успех\n"
            message += f"   � {min_amt:.0f} - {max_amt:.0f} USDT\n"
            message += f"   ✅ Доступно: {available:.0f} USDT\n\n"
        
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_crypto")]]
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data in ["help_draw", "help_voice", "help_roulette", "show_balance", "show_crypto", "get_promo"]:
        texts = {
            "help_draw": "🎨 Напиши /draw и что нарисовать",
            "help_voice": "🎤 Напиши /voice и текст для озвучки",
            "help_roulette": "🔫 Ответь на сообщение соперника: /roulette 100",
            "show_balance": f"💰 Твой баланс: {get_balance(user.id)} монет",
            "show_crypto": "💱 Напиши /crypto для P2P обмена",
            "get_promo": "🎁 Напиши /promo для промокода"
        }
        await query.answer(texts[data], show_alert=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text
    message_lower = user_message.lower()
    
    bot_names = ["бот", "bot", "батя", "батю", "бать"]
    is_private = update.effective_chat.type == "private"
    
    if not is_private:
        is_reply_to_bot = False
        if update.message.reply_to_message:
            reply_from = update.message.reply_to_message.from_user
            if reply_from and reply_from.id == context.bot.id:
                is_reply_to_bot = True
        bot_username = (await context.bot.get_me()).username.lower()
        is_mentioned = any(name in message_lower for name in bot_names) or f"@{bot_username}" in message_lower
    else:
        is_reply_to_bot = True
        is_mentioned = True
    
    casinos = {
        ("mellstroy", "мелстрой"): ("🌟 Mellstroy", "https://golnk.ru/QwWYB"),
        ("stake", "стейк"): ("🥩 STAKE", "https://stakerus.com/"),
        ("1win", "1вин", "ванвин"): ("😂 1WIN", "https://1vvswify.com/?open=register&p=ol84"),
        ("ezcash", "изикеш", "езкеш", "изик"): ("🦈 EZCASH", "https://ezcash.bar/"),
        ("dragon", "драгон", "дракон"): ("🐲 DRAGON", "https://dg1.to/fyvfuwqoc"),
        ("kent", "кент"): ("🤫 KENT", "https://mealmenalc.com/d96995d83"),
        ("cat", "кэт", "кет"): ("💅 CAT", "https://catchthecatthree.com/dcb903109"),
    }
    
    for triggers, (name, link) in casinos.items():
        if any(trigger in message_lower for trigger in triggers):
            await update.message.reply_text(f"{name}\n\n🔗 {link}")
            return
    
    fezco_triggers = ["fezco", "фезко", "фэзко", "создател", "кто тебя создал", "кто твой хозяин"]
    if any(trigger in message_lower for trigger in fezco_triggers):
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
        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=300, temperature=0.8)
        assistant_message = response.choices[0].message.content
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})
        await update.message.reply_text(assistant_message)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("Техническая заминка. Попробуй ещё раз.")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY не установлен")
    
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("batya", batya))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("draw", draw))
    application.add_handler(CommandHandler("voice", voice))
    application.add_handler(CommandHandler("promo", promo))
    application.add_handler(CommandHandler("roulette", roulette))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("crypto", crypto))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
