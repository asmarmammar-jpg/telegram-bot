from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage # يمكن استخدام تخزين دائم هنا أيضاً، لكن سنبقي FSM في الذاكرة لسرعة الأداء
import asyncio
from datetime import datetime, timedelta
from collections import deque
import os
import aiosqlite # <--- تمت إضافة الاستيراد

# ====================================================================
# === إعدادات التوكن وقاعدة البيانات ===

# قراءة التوكن من متغيرات البيئة - ضروري للتشغيل على Render
TOKEN = os.environ.get("TELEGRAM_TOKEN") 
if not TOKEN:
    print("خطأ: لم يتم العثور على توكن البوت. يرجى تعيين متغير TELEGRAM_TOKEN.")
    exit()

DB_NAME = "dating_bot.db" # اسم ملف قاعدة البيانات
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ====================================================================
# === دوال المساعدة للتعامل مع قاعدة البيانات ===

async def init_db():
    """إنشاء جدول المستخدمين إذا لم يكن موجوداً"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                age TEXT,
                gender TEXT,
                country TEXT,
                points INTEGER,
                warnings INTEGER,
                banned_until TEXT -- نحفظها كنص بصيغة ISO أو كلمة 'permanent'
            )
        """)
        await db.commit()

async def get_user_profile(user_id: int):
    """جلب بيانات المستخدم وتحويل حقل الحظر إلى كائن datetime"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if row:
            profile = dict(row)
            # معالجة حقل الحظر
            banned_until_str = profile.get('banned_until')
            if banned_until_str:
                if banned_until_str == 'permanent':
                    profile['banned_until'] = datetime.max
                elif banned_until_str != 'None':
                    try:
                        profile['banned_until'] = datetime.fromisoformat(banned_until_str)
                    except ValueError:
                        profile['banned_until'] = None
                else:
                    profile['banned_until'] = None
            else:
                profile['banned_until'] = None

            return profile
        return None

async def update_user_profile(user_id: int, **kwargs):
    """تحديث حقول محددة في ملف المستخدم"""
    if not kwargs:
        return

    # تحويل datetime إلى نص قبل الحفظ
    if 'banned_until' in kwargs:
        if kwargs['banned_until'] is None:
            kwargs['banned_until'] = 'None'
        elif kwargs['banned_until'] == datetime.max:
            kwargs['banned_until'] = 'permanent'
        else:
            kwargs['banned_until'] = kwargs['banned_until'].isoformat()
    
    set_clauses = ", ".join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values())
    values.append(user_id)
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE users SET {set_clauses} WHERE user_id = ?", tuple(values))
        await db.commit()

# ====================================================================

# ==== FSM States ====
class ProfileStates(StatesGroup):
    rules = State()
    name = State()
    age = State()
    gender = State()
    country = State()
    finished = State()
    change_field = State()

# ==== بيانات المستخدمين (نحتفظ بالباقي في الذاكرة لأنها بيانات مؤقتة) ====
# user_profiles = {}  # <--- تم حذفها والاعتماد على قاعدة البيانات
search_queue = deque()   # قائمة انتظار البحث
active_chats = {}  # user_id: partner_id
chat_start_time = {}  # user_id: datetime بدء الدردشة

# ==== الكلمات المسيئة ====
bad_words = ["سيء", "badword", "إهانة"]  # يمكن إضافة المزيد

# ==== لوحات المفاتيح ====
rules_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ أوافق")],
        [KeyboardButton(text="❌ أرفض")]
    ],
    resize_keyboard=True
)

search_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔍 بحث عن مستخدم")],
              [KeyboardButton(text="👤 عرض الملف الشخصي")],
              [KeyboardButton(text="✏️ تغيير بياناتي")]],
    resize_keyboard=True
)

gender_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="ذكر")], [KeyboardButton(text="أنثى")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

country_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="سوريا")], [KeyboardButton(text="دولة أخرى")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# ====================================================================
# === الدوال المعدلة للاعتماد على قاعدة البيانات ===

# ==== عند /start (مُعدل لمنع التسجيل المكرر) ====
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # التحقق من قاعدة البيانات
    profile = await get_user_profile(user_id)
    if profile:
        await message.answer("أهلاً بعودتك! 😃\nلقد تم إنشاء ملفك الشخصي بالفعل، يمكنك الآن البدء في البحث أو عرض ملفك.", reply_markup=search_keyboard)
        await state.set_state(ProfileStates.finished)
        return

    # إذا لم يكن مسجلاً، نكمل عملية التسجيل
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

# ==== باقي خطوات التسجيل (بدون تغيير في المنطق) ====
@dp.message(ProfileStates.rules)
async def rules_agreement(message: types.Message, state: FSMContext):
    if message.text == "✅ أوافق":
        await message.answer("جيد! لنبدأ بإنشاء ملفك الشخصي.\n📛 ارسل اسمك:")
        await state.set_state(ProfileStates.name)
    else:
        await message.answer("❌ يجب الموافقة على القواعد للمتابعة.")

@dp.message(ProfileStates.name)
async def set_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("🎂 ارسل عمرك:")
    await state.set_state(ProfileStates.age)

@dp.message(ProfileStates.age)
async def set_age(message: types.Message, state: FSMContext):
    # التحقق من أن العمر رقم صحيح
    if not message.text.isdigit():
        await message.answer("❌ يرجى إرسال العمر كرقم صحيح.")
        return
        
    await state.update_data(age=message.text)
    await message.answer("⚧ اختر جنسك:", reply_markup=gender_keyboard)
    await state.set_state(ProfileStates.gender)

@dp.message(ProfileStates.gender)
async def set_gender(message: types.Message, state: FSMContext):
    if message.text not in ["ذكر", "أنثى"]:
        await message.answer("❌ يرجى اختيار 'ذكر' أو 'أنثى' من لوحة المفاتيح.")
        return
    await state.update_data(gender=message.text)
    await message.answer("🌍 اختر دولتك:", reply_markup=country_keyboard)
    await state.set_state(ProfileStates.country)

# ==== إدخال الدولة وإنهاء الملف الشخصي (مُعدل للحفظ في قاعدة البيانات) ====
@dp.message(ProfileStates.country)
async def set_country(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    
    profile = {
        "user_id": user_id,
        "name": data.get("name"),
        "age": data.get("age"),
        "gender": data.get("gender"),
        "country": message.text,
        "points": 150,
        "warnings": 0,
        "banned_until": None
    }

    # الحفظ في قاعدة البيانات
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, name, age, gender, country, points, warnings, banned_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile["user_id"], 
            profile["name"], 
            profile["age"], 
            profile["gender"], 
            profile["country"], 
            profile["points"], 
            profile["warnings"], 
            'None' # حفظ حالة الحظر كنص
        ))
        await db.commit()
    
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

# ==== عرض الملف الشخصي (مُعدل للقراءة من قاعدة البيانات) ====
@dp.message(ProfileStates.finished, F.text == "👤 عرض الملف الشخصي")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    profile = await get_user_profile(user_id) # <--- قراءة من DB
    
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

# ==== البحث عن مستخدم وإنشاء غرفة (مُعدل للتحقق من الحظر من قاعدة البيانات) ====
@dp.message(ProfileStates.finished, F.text == "🔍 بحث عن مستخدم")
async def start_search(message: types.Message):
    user_id = message.from_user.id
    profile = await get_user_profile(user_id) # <--- قراءة من DB
    
    if profile is None:
        await message.answer("❌ لم يتم إنشاء الملف الشخصي بعد.")
        return

    # التحقق من الحظر
    if profile["banned_until"]:
        if datetime.now() < profile["banned_until"]:
            await message.answer("🚫 أنت محظور مؤقتًا.")
            return
        else:
            # رفع الحظر
            await update_user_profile(user_id, banned_until=None) 
            profile["banned_until"] = None

    if user_id in search_queue or user_id in active_chats:
        await message.answer("⏳ أنت بالفعل في قائمة البحث أو في محادثة، يرجى الانتظار.")
        return

    if search_queue:
        partner_id = search_queue.popleft()
        partner_profile = await get_user_profile(partner_id) # <--- قراءة من DB
        
        # التأكد من أن الشريك لم يُحظر أثناء الانتظار
        if not partner_profile or (partner_profile.get("banned_until") and datetime.now() < partner_profile["banned_until"]):
            await message.answer("❌ تعذر العثور على شريك متاح، يرجى المحاولة مرة أخرى.")
            search_queue.append(user_id) # إعادة المستخدم الحالي إلى قائمة الانتظار
            return

        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        chat_start_time[user_id] = datetime.now()
        chat_start_time[partner_id] = datetime.now()
        
        # إرسال معلومات الملف الشخصي للطرفين
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

# ==== تمرير الرسائل بين المستخدمين مع مراقبة الكلمات المسيئة (مُعدل لتحديث قاعدة البيانات) ====
@dp.message(ProfileStates.finished)
async def relay_messages(message: types.Message):
    user_id = message.from_user.id

    # إذا المستخدم في غرفة دردشة
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await bot.send_message(partner_id, f"💬 شريكك: {message.text}")
        return
    
    # التحقق من الكلمات المسيئة خارج المحادثة
    profile = await get_user_profile(user_id) # <--- قراءة من DB
    if profile is None:
        return

    for word in bad_words:
        if word in message.text.lower():
            # تحديث محلي للمتغيرات
            new_points = profile["points"] - 10
            new_warnings = profile["warnings"] + 1
            new_banned_until = None
            
            ban_message = "🚫 تم خصم 10 نقاط بسبب استخدام كلمات مسيئة."

            if new_warnings == 1:
                new_banned_until = datetime.now() + timedelta(days=3)
                ban_message = "🚫 أول إساءة! تم حظرك لمدة 3 أيام."
            elif new_warnings == 2:
                new_banned_until = datetime.now() + timedelta(days=5)
                ban_message = "🚫 ثانية إساءة! تم حظرك لمدة 5 أيام."
            elif new_warnings >= 3:
                new_banned_until = datetime.max
                ban_message = "🚫 ثالث إساءة! تم حظرك نهائيًا."
            
            # الحفظ في قاعدة البيانات
            await update_user_profile(
                user_id,
                points=new_points,
                warnings=new_warnings,
                banned_until=new_banned_until
            )

            await message.answer(ban_message)
            break

# ==== إنهاء المحادثة أو الإبلاغ (بدون تغيير، لا تعتمد على user_profiles) ====
@dp.callback_query(F.data.in_(["end_chat", "report_chat"]))
async def chat_controls(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    partner_id = active_chats.get(user_id)
    start_time = chat_start_time.get(user_id)
    
    if start_time and callback_query.data == "end_chat":
        if datetime.now() - start_time < timedelta(minutes=1):
            await callback_query.message.answer("⏳ لا يمكنك إنهاء المحادثة قبل مرور دقيقة واحدة.")
            return

    if partner_id:
        if callback_query.data == "end_chat":
            await bot.send_message(partner_id, "🚪 تم إنهاء المحادثة من الطرف الآخر.")
        elif callback_query.data == "report_chat":
            await bot.send_message(partner_id, "⚠️ تم الإبلاغ عنك من قبل شريكك.")
            # هنا يجب إضافة منطق حفظ الإبلاغ في قاعدة البيانات للمراجعة لاحقاً

        # إنهاء الدردشة
        if user_id in active_chats:
            del active_chats[user_id]
        if partner_id in active_chats:
            del active_chats[partner_id]
        if user_id in chat_start_time:
            del chat_start_time[user_id]
        if partner_id in chat_start_time:
            del chat_start_time[partner_id]
    
    await callback_query.message.answer("✅ تم معالجة العملية.", reply_markup=search_keyboard)

# ==== تغيير بيانات الملف الشخصي (مُعدل للقراءة من قاعدة البيانات) ====
@dp.message(ProfileStates.finished, F.text == "✏️ تغيير بياناتي")
async def change_profile(message: types.Message):
    user_id = message.from_user.id
    profile = await get_user_profile(user_id) # <--- قراءة من DB
    
    if profile and profile["points"] < 25:
        await message.answer("❌ لا تمتلك نقاط كافية لطلب تغيير البيانات.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📛 الاسم", callback_data="change_name")],
        [InlineKeyboardButton(text="🎂 العمر", callback_data="change_age")],
        [InlineKeyboardButton(text="⚧ الجنس", callback_data="change_gender")],
        [InlineKeyboardButton(text="🌍 الدولة", callback_data="change_country")]
    ])
    await message.answer("اختر البيانات التي تريد تغييرها (سيتم خصم 25 نقطة لكل تغيير):", reply_markup=keyboard)

# ==== معالجة اختيار حقل التغيير (مُعدل لتحديث قاعدة البيانات) ====
@dp.callback_query(F.data.startswith("change_"))
async def field_selected(callback_query: types.CallbackQuery, state: FSMContext):
    field = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    profile = await get_user_profile(user_id) # <--- قراءة من DB
    
    if profile and profile["points"] < 25:
        await callback_query.message.answer("❌ لا تمتلك نقاط كافية لطلب تغيير البيانات.")
        return

    # خصم النقاط مباشرة من قاعدة البيانات
    new_points = profile["points"] - 25
    await update_user_profile(user_id, points=new_points) # <--- حفظ في DB

    await state.update_data(change_field=field)
    await callback_query.message.answer(f"📌 ارسل القيمة الجديدة لـ {field} (نقاطك المتبقية: {new_points}):")
    await state.set_state(ProfileStates.change_field)

# ==== حفظ القيمة الجديدة (مُعدل لتحديث قاعدة البيانات) ====
@dp.message(ProfileStates.change_field)
async def save_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("change_field")
    user_id = message.from_user.id
    
    # تحديث الحقل مباشرة في قاعدة البيانات
    await update_user_profile(user_id, **{field: message.text}) # <--- حفظ في DB

    # قراءة النقاط الجديدة لعرضها
    profile = await get_user_profile(user_id)
    
    await message.answer(f"✅ تم تحديث {field} بنجاح!\n💰 نقاطك المتبقية: {profile['points']}")
    await state.set_state(ProfileStates.finished)

# ==== تشغيل البوت (مُعدل لتهيئة قاعدة البيانات) ====
if __name__ == "__main__":
    async def main():
        await init_db() # <--- تهيئة قاعدة البيانات قبل بدء البوت
        await dp.start_polling(bot)

    asyncio.run(main())

