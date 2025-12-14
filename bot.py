from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from datetime import datetime, timedelta
from collections import deque

TOKEN = "8321160351:AAEb_eWW8jTlGiWbzLsuGmqSTUH6KA1O_f4"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==== FSM States ====
class ProfileStates(StatesGroup):
    rules = State()
    name = State()
    age = State()
    gender = State()
    country = State()
    finished = State()
    change_field = State()

# ==== بيانات المستخدمين ====
user_profiles = {}  # user_id: profile_data
search_queue = deque()   # قائمة انتظار البحث
active_chats = {}  # user_id: partner_id
chat_start_time = {}  # user_id: datetime بدء الدردشة

# ==== الكلمات المسيئة ====
bad_words = ["سيء", "badword", "إهانة"]  # يمكن إضافة المزيد

# ==== لوحة القواعد ====
rules_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ أوافق")],
        [KeyboardButton(text="❌ أرفض")]
    ],
    resize_keyboard=True
)

# ==== لوحة البحث ====
search_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔍 بحث عن مستخدم")],
              [KeyboardButton(text="👤 عرض الملف الشخصي")],
              [KeyboardButton(text="✏️ تغيير بياناتي")]],
    resize_keyboard=True
)

# ==== لوحة اختيار الجنس ====
gender_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="ذكر")], [KeyboardButton(text="أنثى")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# ==== لوحة اختيار الدولة (مثال: سوريا) ====
country_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="سوريا")], [KeyboardButton(text="دولة أخرى")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# ==== عند /start ====
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "مرحبًا! 📌\n"
        "للبدء، يرجى قراءة الشروط:\n\n"
        "1️⃣ لديك 150 نقطة عند التسجيل.\n"
        "2️⃣ يجب الالتزام بالقواعد وعدم الإساءة.\n"
        "3️⃣ كل محاولة لتغيير أي بيانات في الملف الشخصي تتطلب خصم 25 نقطة والمراجعة.\n"
        "4️⃣ عند كل إساءة يتم خصم 10 نقاط، وحظر المستخدم:\n"
        "   - أول مرة: 3 أيام\n"
        "   - الثانية: 5 أيام\n"
        "   - الثالثة: حظر دائم\n\n"
        "هل توافق على هذه الشروط؟",
        reply_markup=rules_keyboard
    )
    await state.set_state(ProfileStates.rules)

# ==== موافقة القواعد ====
@dp.message(ProfileStates.rules)
async def rules_agreement(message: types.Message, state: FSMContext):
    if message.text == "✅ أوافق":
        await message.answer("جيد! لنبدأ بإنشاء ملفك الشخصي.\n📛 ارسل اسمك:")
        await state.set_state(ProfileStates.name)
    else:
        await message.answer("❌ يجب الموافقة على القواعد للمتابعة.")

# ==== إدخال الاسم ====
@dp.message(ProfileStates.name)
async def set_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("🎂 ارسل عمرك:")
    await state.set_state(ProfileStates.age)

# ==== إدخال العمر ====
@dp.message(ProfileStates.age)
async def set_age(message: types.Message, state: FSMContext):
    await state.update_data(age=message.text)
    await message.answer("⚧ اختر جنسك:", reply_markup=gender_keyboard)
    await state.set_state(ProfileStates.gender)

# ==== إدخال الجنس ====
@dp.message(ProfileStates.gender)
async def set_gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await message.answer("🌍 اختر دولتك:", reply_markup=country_keyboard)
    await state.set_state(ProfileStates.country)

# ==== إدخال الدولة وإنهاء الملف الشخصي ====
@dp.message(ProfileStates.country)
async def set_country(message: types.Message, state: FSMContext):
    data = await state.get_data()
    profile = {
        "name": data.get("name"),
        "age": data.get("age"),
        "gender": data.get("gender"),
        "country": message.text,
        "points": 150,
        "warnings": 0,
        "banned_until": None
    }
    user_profiles[message.from_user.id] = profile
    await message.answer(
        f"✅ تم إنشاء ملفك الشخصي:\n\n"
        f"📛 الاسم: {profile['name']}\n"
        f"🎂 العمر: {profile['age']}\n"
        f"⚧ الجنس: {profile['gender']}\n"
        f"🌍 الدولة: {profile['country']}\n"
        f"💰 النقاط: {profile['points']}",
        reply_markup=search_keyboard
    )
    await state.set_state(ProfileStates.finished)

# ==== عرض الملف الشخصي ====
@dp.message(ProfileStates.finished, F.text == "👤 عرض الملف الشخصي")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    profile = user_profiles.get(user_id)
    if profile:
        await message.answer(
            f"📛 الاسم: {profile['name']}\n"
            f"🎂 العمر: {profile['age']}\n"
            f"⚧ الجنس: {profile['gender']}\n"
            f"🌍 الدولة: {profile['country']}\n"
            f"💰 النقاط: {profile['points']}"
        )
    else:
        await message.answer("❌ لم يتم إنشاء الملف الشخصي بعد.")

# ==== البحث عن مستخدم وإنشاء غرفة ====
@dp.message(ProfileStates.finished, F.text == "🔍 بحث عن مستخدم")
async def start_search(message: types.Message):
    user_id = message.from_user.id
    profile = user_profiles.get(user_id)
    
    if profile is None:
        await message.answer("❌ لم يتم إنشاء الملف الشخصي بعد.")
        return

    # التحقق من الحظر
    if profile["banned_until"]:
        if datetime.now() < profile["banned_until"]:
            await message.answer("🚫 أنت محظور مؤقتًا.")
            return
        else:
            profile["banned_until"] = None

    if user_id in search_queue or user_id in active_chats:
        await message.answer("⏳ أنت بالفعل في قائمة البحث أو في محادثة، يرجى الانتظار.")
        return

    if search_queue:
        partner_id = search_queue.popleft()
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        chat_start_time[user_id] = datetime.now()
        chat_start_time[partner_id] = datetime.now()
        
        # إرسال معلومات الملف الشخصي للطرفين
        partner_profile = user_profiles[partner_id]
        await message.answer(
            f"✅ تم العثور على شريك! يمكنك بدء المحادثة.\n"
            f"📛 اسم الشريك: {partner_profile['name']}\n"
            f"🎂 عمره: {partner_profile['age']}\n"
            f"⚧ جنسه: {partner_profile['gender']}\n"
            f"🌍 دولته: {partner_profile['country']}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚪 إنهاء المحادثة", callback_data="end_chat")],
                    [InlineKeyboardButton(text="⚠️ إبلاغ", callback_data="report_chat")]
                ]
            )
        )
        my_profile = profile
        await bot.send_message(partner_id,
            f"✅ تم العثور على شريك! يمكنك بدء المحادثة.\n"
            f"📛 اسم الشريك: {my_profile['name']}\n"
            f"🎂 عمره: {my_profile['age']}\n"
            f"⚧ جنسه: {my_profile['gender']}\n"
            f"🌍 دولته: {my_profile['country']}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚪 إنهاء المحادثة", callback_data="end_chat")],
                    [InlineKeyboardButton(text="⚠️ إبلاغ", callback_data="report_chat")]
                ]
            )
        )
    else:
        search_queue.append(user_id)
        await message.answer("⏳ تم وضعك في قائمة البحث، يرجى الانتظار حتى يتم العثور على شريك.")

# ==== تمرير الرسائل بين المستخدمين مع مراقبة الكلمات المسيئة ====
@dp.message(ProfileStates.finished)
async def relay_messages(message: types.Message):
    user_id = message.from_user.id

    # إذا المستخدم في غرفة دردشة
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await bot.send_message(partner_id, f"💬 شريكك: {message.text}")
        return
    
    # التحقق من الكلمات المسيئة خارج المحادثة
    profile = user_profiles.get(user_id)
    if profile is None:
        return

    for word in bad_words:
        if word in message.text.lower():
            profile["points"] -= 10
            profile["warnings"] += 1
            
            if profile["warnings"] == 1:
                profile["banned_until"] = datetime.now() + timedelta(days=3)
                await message.answer("🚫 أول إساءة! تم حظرك لمدة 3 أيام.")
            elif profile["warnings"] == 2:
                profile["banned_until"] = datetime.now() + timedelta(days=5)
                await message.answer("🚫 ثانية إساءة! تم حظرك لمدة 5 أيام.")
            elif profile["warnings"] >= 3:
                profile["banned_until"] = datetime.max
                await message.answer("🚫 ثالث إساءة! تم حظرك نهائيًا.")
            break

# ==== إنهاء المحادثة أو الإبلاغ ====
@dp.callback_query(F.data.in_(["end_chat", "report_chat"]))
async def chat_controls(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    partner_id = active_chats.get(user_id)
    start_time = chat_start_time.get(user_id)
    
    if callback_query.data == "end_chat":
        if datetime.now() - start_time < timedelta(minutes=1):
            await callback_query.message.answer("⏳ لا يمكنك إنهاء المحادثة قبل مرور دقيقة واحدة.")
            return

    if partner_id:
        if callback_query.data == "end_chat":
            await bot.send_message(partner_id, "🚪 تم إنهاء المحادثة من الطرف الآخر.")
        elif callback_query.data == "report_chat":
            await bot.send_message(partner_id, "⚠️ تم الإبلاغ عنك من قبل شريكك.")
        
        # إنهاء الدردشة
        del active_chats[user_id]
        del active_chats[partner_id]
        del chat_start_time[user_id]
        del chat_start_time[partner_id]
    
    await callback_query.message.answer("✅ تم معالجة العملية.", reply_markup=search_keyboard)

# ==== تغيير بيانات الملف الشخصي ====
@dp.message(ProfileStates.finished, F.text == "✏️ تغيير بياناتي")
async def change_profile(message: types.Message):
    user_id = message.from_user.id
    profile = user_profiles.get(user_id)
    if profile["points"] < 25:
        await message.answer("❌ لا تمتلك نقاط كافية لطلب تغيير البيانات.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📛 الاسم", callback_data="change_name")],
        [InlineKeyboardButton(text="🎂 العمر", callback_data="change_age")],
        [InlineKeyboardButton(text="⚧ الجنس", callback_data="change_gender")],
        [InlineKeyboardButton(text="🌍 الدولة", callback_data="change_country")]
    ])
    await message.answer("اختر البيانات التي تريد تغييرها (سيتم خصم 25 نقطة لكل تغيير):", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("change_"))
async def field_selected(callback_query: types.CallbackQuery, state: FSMContext):
    field = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    profile = user_profiles.get(user_id)
    
    if profile["points"] < 25:
        await callback_query.message.answer("❌ لا تمتلك نقاط كافية لطلب تغيير البيانات.")
        return

    profile["points"] -= 25
    await state.update_data(change_field=field)
    await callback_query.message.answer(f"📌 ارسل القيمة الجديدة لـ {field}:")
    await state.set_state(ProfileStates.change_field)

@dp.message(ProfileStates.change_field)
async def save_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("change_field")
    user_id = message.from_user.id
    profile = user_profiles.get(user_id)

    profile[field] = message.text
    await message.answer(f"✅ تم تحديث {field} بنجاح!\n💰 نقاطك المتبقية: {profile['points']}")
    await state.set_state(ProfileStates.finished)

# ==== تشغيل البوت ====
if __name__ == "__main__":
    async def main():
        await dp.start_polling(bot)

    asyncio.run(main())