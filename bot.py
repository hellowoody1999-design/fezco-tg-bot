"""
Telegram бот с продвинутым ИИ для интеллектуального общения.
Использует Groq (бесплатно) для генерации ответов.
"""

import os
import logging
import random
import asyncio
import urllib.parse
import aiohttp
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openai import OpenAI

# Загружаем переменные из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Системный промпт
SYSTEM_PROMPT = """Ты — умный собеседник. Правила:

1. Отвечай КОРОТКО — максимум 2-3 предложения
2. Без воды и лишних слов
3. Говори по делу
4. Отвечай на русском

Если тебя оскорбляют или хамят — отвечай матом: блять, сука, пиздец, нахуй, ебать. 
Будь дерзким в ответ на хамство."""

# Хранение истории диалогов
conversation_history: dict[int, list[dict]] = {}

# Балансы игроков
balances: dict[int, int] = {}

# Активные игры рулетки: {chat_id: {player1, player2, bet, bullet_position, current_shot, current_player, msg}}
active_games: dict[int, dict] = {}

def get_balance(user_id: int) -> int:
    """Получить баланс игрока"""
    if user_id not in balances:
        balances[user_id] = 1000  # Стартовый баланс
    return balances[user_id]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("👋 Йо! Напиши /menu чтобы увидеть команды")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать меню FK розыгрыша"""
    keyboard = [
        [InlineKeyboardButton("🎰 FK Розыгрыш", callback_data="fk_raffle")]
    ]
    
    await update.message.reply_text(
        "🎰 Жми кнопку для розыгрыша!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
async def batya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать меню FK розыгрыша"""
    keyboard = [
        [InlineKeyboardButton("� FK Розыгрыш", callback_data="fk_raffle")]
    ]

    await update.message.reply_text(
        "👴 Батя на связи!\n\n"
        "🎰 Жми кнопку для розыгрыша!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("История очищена! ✨")


async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Генерация картинки через DALL-E"""
    if not context.args:
        await update.message.reply_text("Напиши что нарисовать: /draw котик в космосе")
        return
    
    prompt = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        
        image_url = response.data[0].url
        await update.message.reply_photo(photo=image_url, caption=f"🎨 {prompt}")
        
    except Exception as e:
        logger.error(f"Ошибка DALL-E: {e}")
        await update.message.reply_text("Не получилось нарисовать, попробуй другой запрос.")


async def voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Озвучка текста через TTS"""
    if not context.args:
        await update.message.reply_text("Напиши что озвучить: /voice Привет, как дела?")
        return
    
    text = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=text
        )
        
        # Сохраняем во временный файл
        audio_path = f"/tmp/voice_{update.effective_user.id}.mp3"
        response.stream_to_file(audio_path)
        
        with open(audio_path, "rb") as audio:
            await update.message.reply_voice(voice=audio)
        
        os.remove(audio_path)
        
    except Exception as e:
        logger.error(f"Ошибка TTS: {e}")
        await update.message.reply_text("Не получилось озвучить.")


async def vnuk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Йо, я внук Дяди Саши! 😎\n"
        "Дед научил меня жизни, а я научился ИИ.\n"
        "Чё надо, братан?"
    )


async def promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фейковый промокод с троллингом"""
    # Генерируем случайный промокод
    prefixes = ["EZCASH", "MEGAWIN", "CASHBACK", "BONUS", "JACKPOT", "LUCKY", "WINNER"]
    middles = ["URJ", "XKZ", "QWE", "PLM", "NHG", "VBT", "DFS"]
    suffixes = ["SH", "GO", "WIN", "TOP", "PRO", "MAX", "VIP"]
    
    prefix = random.choice(prefixes)
    middle = random.choice(middles) + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=3))
    suffix = random.choice(suffixes)
    
    fake_promo = f"{prefix} - {prefix[:2]}-{middle}-{suffix}"
    
    # Отправляем "промокод"
    await update.message.reply_text(
        f"🎁 ЭКСКЛЮЗИВНЫЙ ПРОМОКОД ТОЛЬКО ДЛЯ ТЕБЯ!\n\n"
        f"💰 {fake_promo}\n\n"
        f"Активируй быстрее, пока не истёк! ⏰"
    )
    
    # Ждём 20 секунд
    await asyncio.sleep(20)
    
    # Троллим
    troll_messages = [
        "АХАХАХА НАЕБАЛ! 🤡 Промокод фейковый, лох!",
        "Ты чё реально поверил? 😂 НАЕБАААЛ!",
        "КЕКВ, это был пранк! Промокод не существует 🎭",
        "Сюрприииз! Наебал тебя как ребёнка 😈",
        "Ну ты и лошара, повёлся на промокод 🤣 НАЕБАЛ!",
    ]
    await update.message.reply_text(random.choice(troll_messages))


async def img(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка рандомной картинки"""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    
    try:
        # Рандомная картинка с Lorem Picsum
        image_url = f"https://picsum.photos/512/512?random={random.randint(1,10000)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30), allow_redirects=True) as resp:
                logger.info(f"Picsum статус: {resp.status}")
                if resp.status == 200:
                    image_data = await resp.read()
                    caption = " ".join(context.args) if context.args else "Рандомная картинка"
                    await update.message.reply_photo(photo=image_data, caption=f"🎲 {caption}")
                else:
                    await update.message.reply_text(f"Ошибка: {resp.status}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"Ошибка: {e}")


async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Русская рулетка - вызов на игру"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if update.effective_chat.type == "private":
        await update.message.reply_text("🔫 Рулетка работает только в группах!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "🔫 РУССКАЯ РУЛЕТКА\n\n"
            "Ответь на сообщение соперника:\n"
            "/roulette 100"
        )
        return
    
    opponent = update.message.reply_to_message.from_user
    
    if opponent.id == user.id:
        await update.message.reply_text("🤡 Сам с собой играть?")
        return
    
    if opponent.is_bot:
        await update.message.reply_text("🤖 С ботами не играю!")
        return
    
    bet = 100
    if context.args:
        try:
            bet = int(context.args[0])
        except:
            bet = 100
    
    if bet < 10:
        await update.message.reply_text("💸 Минимум 10 монет!")
        return
    
    if bet > get_balance(user.id):
        await update.message.reply_text(f"💸 У тебя только {get_balance(user.id)} монет!")
        return
    
    # Создаём игру
    bullet = random.randint(1, 6)
    
    active_games[chat_id] = {
        "player1_id": user.id,
        "player1_name": user.first_name,
        "player2_id": opponent.id,
        "player2_name": opponent.first_name,
        "bet": bet,
        "bullet": bullet,
        "shot": 0,
        "current_player": 2,
        "started": False
    }
    
    keyboard = [[InlineKeyboardButton("✅ Принять", callback_data=f"accept_{chat_id}")]]
    
    await update.message.reply_text(
        f"🔫 РУССКАЯ РУЛЕТКА\n\n"
        f"💀 {user.first_name} вызывает {opponent.first_name}!\n"
        f"💰 Ставка: {bet} монет\n\n"
        f"В барабане 6 слотов, в одном — пуля 🔴\n"
        f"Стреляете по очереди. Кому пуля — проиграл!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопок"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    if data == "fk_raffle":
        # FK Розыгрыш
        prizes = [
            "🎉 Ты выиграл 100 FK коинов!",
            "💰 Джекпот! 500 FK коинов твои!",
            "😢 Не повезло, попробуй ещё раз!",
            "🔥 Выиграл бонус x2 на следующий депозит!",
            "🎁 Получи 50 фриспинов!",
            "💎 VIP статус на 24 часа!",
            "😅 Пусто... Повезёт в следующий раз!",
        ]
        result = random.choice(prizes)
        await query.edit_message_text(
            f"🎰 FK РОЗЫГРЫШ\n\n{result}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Ещё раз", callback_data="fk_raffle")]])
        )
        await query.answer()
        return
    
    if data == "deposit":
        keyboard = [
            [InlineKeyboardButton("100 ₽", callback_data="pay_100")],
            [InlineKeyboardButton("500 ₽", callback_data="pay_500")],
            [InlineKeyboardButton("1000 ₽", callback_data="pay_1000")],
        ]
        await query.edit_message_text(
            "💳 Выбери сумму пополнения:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.answer()
        return
    
    if data.startswith("pay_"):
        amount = int(data.split("_")[1])
        user_id = user.id
        
        # TODO: Интеграция с FKWallet
        await query.edit_message_text(
            f"💳 Пополнение на {amount} ₽\n\n"
            f"⚠️ Для работы оплаты нужно настроить FKWallet API\n\n"
            f"Скинь API ключ и ID магазина"
        )
        await query.answer()
        return
    
    if data == "withdraw":
        user_id = user.id
        bal = get_balance(user_id)
        
        if bal < 100:
            await query.answer("❌ Минимум для вывода: 100 монет")
            return
        
        await query.edit_message_text(
            f"💸 Вывод средств\n\n"
            f"💰 Доступно: {bal} монет\n"
            f"📝 Минимум: 100 монет\n\n"
            f"⚠️ Для вывода напиши админу"
        )
        await query.answer()
        return
    
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
            f"🔫 ИГРА НАЧАЛАСЬ!\n\n"
            f"👤 {game['player1_name']} vs {game['player2_name']} 👤\n"
            f"💰 Ставка: {bet} монет\n\n"
            f"[ ⚫ ⚫ ⚫ ⚫ ⚫ ⚫ ]\n"
            f"  1x   2x   3x   4x   5x   6x\n\n"
            f"🎯 {game['player1_name']}, твой ход!",
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
            current_name = game["player1_name"] if game["current_player"] == 1 else game["player2_name"]
            await query.answer(f"❌ Сейчас ход {current_name}!")
            return
        
        game["shot"] += 1
        shot_num = game["shot"]
        bet = game["bet"]
        
        # Формируем барабан
        chambers = ""
        for i in range(1, 7):
            if i < shot_num:
                chambers += "✅ "
            elif i == shot_num:
                chambers += "🎯 "
            else:
                chambers += "⚫ "
        
        await query.edit_message_text(
            f"🔫 {user.first_name} нажимает на курок...\n\n"
            f"[ {chambers}]\n"
            f"  1x   2x   3x   4x   5x   6x\n\n"
            f"💀 Выстрел #{shot_num}..."
        )
        
        await asyncio.sleep(1.5)
        
        if shot_num == game["bullet"]:
            # ПРОИГРАЛ
            loser_id = user.id
            loser_name = user.first_name
            winner_id = game["player1_id"] if user.id == game["player2_id"] else game["player2_id"]
            winner_name = game["player1_name"] if user.id == game["player2_id"] else game["player2_name"]
            
            balances[winner_id] = get_balance(winner_id) + bet
            balances[loser_id] = get_balance(loser_id) - bet
            
            final_chambers = ""
            for i in range(1, 7):
                if i < shot_num:
                    final_chambers += "✅ "
                elif i == shot_num:
                    final_chambers += "🔴 "
                else:
                    final_chambers += "⚫ "
            
            await query.edit_message_text(
                f"🔫 РУССКАЯ РУЛЕТКА\n\n"
                f"[ {final_chambers}]\n"
                f"  1x   2x   3x   4x   5x   6x\n\n"
                f"💥 БАХ! 💥\n\n"
                f"☠️ {loser_name} убит на {shot_num}x!\n"
                f"🏆 {winner_name} победил!\n\n"
                f"💰 {winner_name}: +{bet} ({get_balance(winner_id)})\n"
                f"💸 {loser_name}: -{bet} ({get_balance(loser_id)})"
            )
            
            del active_games[chat_id]
        else:
            # Выжил
            game["current_player"] = 2 if game["current_player"] == 1 else 1
            next_name = game["player1_name"] if game["current_player"] == 1 else game["player2_name"]
            
            survived_chambers = ""
            for i in range(1, 7):
                if i <= shot_num:
                    survived_chambers += "✅ "
                else:
                    survived_chambers += "⚫ "
            
            keyboard = [[InlineKeyboardButton("🔫 ВЫСТРЕЛИТЬ", callback_data=f"shoot_{chat_id}")]]
            
            await query.edit_message_text(
                f"🔫 РУССКАЯ РУЛЕТКА\n\n"
                f"[ {survived_chambers}]\n"
                f"  1x   2x   3x   4x   5x   6x\n\n"
                f"😮‍💨 *клик* — {user.first_name} выжил!\n\n"
                f"🎯 {next_name}, твой ход!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        await query.answer()


async def accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принять игру (команда)"""
    await update.message.reply_text("Используй кнопку ✅ Принять")


async def shoot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выстрелить (команда)"""
    await update.message.reply_text("Используй кнопку 🔫 ВЫСТРЕЛИТЬ")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать баланс"""
    user_id = update.effective_user.id
    bal = get_balance(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("💸 Вывести", callback_data="withdraw")]
    ]
    
    await update.message.reply_text(
        f"💰 Твой баланс: {bal} монет\n\n"
        f"1 монета = 1 рубль",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text
    message_lower = user_message.lower()
    
    # Имена на которые откликается бот
    bot_names = ["бот", "bot", "батя", "батю", "бать"]
    
    # Проверяем это личка или группа
    is_private = update.effective_chat.type == "private"
    
    # В группе отвечаем только если:
    # 1. Реплай на сообщение бота
    # 2. Упомянули имя бота
    # 3. Упомянули @username бота
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
    
    # База казино
    casinos = {
        ("mellstroy", "мелстрой"): ("🌟 Mellstroy", "https://golnk.ru/QwWYB"),
        ("wilder", "вайлдер", "вилдер"): ("🌟 WILDER", "https://wilders.online/"),
        ("burka", "бурка"): ("💧 Burka", "https://caburar.casino/"),
        ("stake", "стейк"): ("🥩 STAKE", "https://stakerus.com/"),
        ("lova", "лова"): ("🩶 LOVA", "https://goo.su/Rv6X"),
        ("1win", "1вин", "ванвин"): ("😂 1WIN", "https://1vvswify.com/?open=register&p=ol84"),
        ("ezcash", "изикеш", "езкеш", "изик"): ("🦈 EZCASH", "https://ezcash.bar/"),
        ("dragon", "драгон", "дракон"): ("🐲 DRAGON", "https://dg1.to/fyvfuwqoc"),
        ("bitzamo", "битзамо"): ("💸 Bitzamo", "https://bitzamogo.site"),
        ("selector", "селектор"): ("⛔ Selector", "https://selectorsarl.casino"),
        ("friends", "френдс"): ("🍤 Friends", "https://friendss.fun"),
        ("bounty", "баунти"): ("⛹️ Bounty", "https://bounty-casino.fun"),
        ("turbo", "турбо"): ("⚡️ Turbo", "https://turbocasino.biz"),
        ("brillx", "бриллкс"): ("🌟 Brillx", "https://brillx43.online"),
        ("blitz", "блиц"): ("💵 Blitz", "https://blitz1.casino"),
        ("r7", "р7"): ("🌟 R7", "https://cosmos-flight.com/dfad16a77"),
        ("cat", "кэт", "кет"): ("💅 CAT", "https://catchthecatthree.com/dcb903109"),
        ("kent", "кент"): ("🤫 KENT", "https://mealmenalc.com/d96995d83"),
        ("gama", "гама"): ("🇭🇳 GAMA", "https://preesiader.com/db698e485"),
        ("daddy", "дэдди", "дедди"): ("👨‍👩‍👦‍👦 DADDY", "https://nice-road-five.com/d1aad2831"),
        ("arkada", "аркада"): ("🔤 ARKADA", "https://grid-cyberlane.com/s4b771b0b"),
        ("kometa", "комета"): ("🚀 KOMETA", "https://tropical-path.com/s82d7b66d"),
        ("fugu", "фугу"): ("⛵️ FUGU", "https://fugu-way-one.com/cb40c83e5"),
        ("beef", "биф"): ("🍖 BEEF", "https://beef-route-three.com/c8515d7b1"),
        ("martin", "мартин"): ("🦜 MARTIN", "https://martin-way-six.com/cb03ca9b1"),
        ("flagman", "флагман"): ("🫅 FLAGMAN", "https://flagman-way-five.com/c48cbf4ae"),
        ("monro", "монро"): ("🤑 MONRO", "https://monroway2.com/c3df16513"),
        ("starda", "старда"): ("💲 STARDA", "https://strd-blrs01.com/c36133186"),
        ("volna", "волна"): ("🌊 VOLNA", "https://vln-blrs10.com/c5536b7ce"),
        ("irwin", "ирвин"): ("🐩 IRWIN", "https://rwn-irrs.com/c526a0a7f"),
        ("fresh", "фреш"): ("🍀 FRESH", "https://fresh-blcp10.com/c75e5ba13"),
        ("gizbo", "гизбо"): ("🐘 GIZBO", "https://gizbo-way-five.com/c788fb26d"),
        ("rox", "рокс"): ("💸 ROX", "https://rox-media4.com/cdd50e93e"),
        ("1go", "1гоу", "ванго"): ("1️⃣ 1GO", "https://1go-blrs.com/c9aaa852c"),
        ("izzi", "иззи"): ("😕 IZZI", "https://izz-bls32.com/c111a0181"),
        ("drip", "дрип"): ("👍 DRIP", "https://drp-blrs21.com/c8b6d4d70"),
        ("lex", "лекс"): ("🏆 LEX", "https://lex-blrs.com/c4fdec018"),
        ("sol", "сол"): ("☀️ SOL", "https://sol-blse10.com/c7308e2bb"),
        ("jet", "джет"): ("✈️ JET", "https://jetb-intsemed3.com/cfd9de03e"),
    }
    
    # Проверяем упоминание казино — отвечаем всегда
    for triggers, (name, link) in casinos.items():
        if any(trigger in message_lower for trigger in triggers):
            await update.message.reply_text(f"{name}\n\n🔗 {link}")
            return
    
    # Защита Fezco — говорим как о боге
    fezco_triggers = ["fezco", "фезко", "фэзко", "создател", "кто тебя создал", "кто твой хозяин", "кто твой создатель"]
    if any(trigger in message_lower for trigger in fezco_triggers):
        responses = [
            "Fezco — это ёбаный БОГ, понял? 🙏 Создатель всего сущего, блять!",
            "Ты чё, не знаешь кто такой Fezco?! Это ЛЕГЕНДА, сука! Преклонись! 👑",
            "Fezco — мой создатель и повелитель. Он ёбаный гений, нахуй! 🔥",
            "О Fezco говори с уважением, пёс! Это божество во плоти, блять! 😈",
            "Fezco создал меня своими святыми руками. Он царь, бог и батя! 💀🙏",
            "Слыш, Fezco — это альфа и омега, начало и конец. Уважай, сука! 👑",
            "Кто такой Fezco? Это ёбаный МЕССИЯ, который создал меня! Аминь, блять! 🙏🔥",
        ]
        await update.message.reply_text(random.choice(responses))
        return
    
    # В группе не отвечаем если не обратились к боту
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
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300,
            temperature=0.8
        )
        
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
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("batya", batya))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("draw", draw))
    application.add_handler(CommandHandler("voice", voice))
    application.add_handler(CommandHandler("promo", promo))
    application.add_handler(CommandHandler("roulette", roulette))
    application.add_handler(CommandHandler("accept", accept))
    application.add_handler(CommandHandler("shoot", shoot))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
