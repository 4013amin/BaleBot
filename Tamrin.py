from bale import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton, Update
import sqlite3
import asyncio
import requests
from typing import List, Optional
import re

# توکن بات خود را اینجا قرار دهید
BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
bot = Bot(token=BOT_TOKEN)

# نام فایل دیتابیس
DB_NAME = "bulk_sms.db"

# API Base URL برای Bale
BALE_API_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

# ذخیره موقت انتخاب‌های کاربران
user_phone_selections = {}  # {chat_id: [phone_ids]}
user_temp_data = {}  # {chat_id: {state, recipients, message}}


# ایجاد اتصال به دیتابیس
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_phones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            phone_number TEXT,
            label TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn


conn = init_db()


# توابع مدیریت دیتابیس
def save_phone_to_db(chat_id: int, phone_number: str, label: str = ""):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO saved_phones (chat_id, phone_number, label) VALUES (?, ?, ?)",
        (chat_id, phone_number, label)
    )
    conn.commit()


def get_saved_phones(chat_id: int) -> List[tuple]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, phone_number, label FROM saved_phones WHERE chat_id = ? ORDER BY added_date DESC",
        (chat_id,)
    )
    return cursor.fetchall()


def delete_phone(phone_id: int):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_phones WHERE id = ?", (phone_id,))
    conn.commit()


def get_phone_by_id(phone_id: int) -> Optional[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number FROM saved_phones WHERE id = ?", (phone_id,))
    result = cursor.fetchone()
    return result[0] if result else None


# تابع ارسال پیام با API مستقیم
async def send_message_to_user(chat_id: str, text: str) -> tuple:
    """
    ارسال پیام به کاربر
    Returns: (success: bool, error_message: str)
    """
    try:
        url = f"{BALE_API_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()

        if result.get('ok'):
            return True, ""
        else:
            error_desc = result.get('description', 'Unknown error')
            return False, error_desc
    except Exception as e:
        return False, str(e)


# توابع ساخت کیبورد
def create_main_menu():
    """منوی اصلی"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="👥 مدیریت مخاطبین", callback_data="menu_contacts"), row=1)
    keyboard.add(InlineKeyboardButton(text="📤 ارسال پیام انبوه", callback_data="menu_send"), row=2)
    return keyboard


def create_contacts_menu():
    """منوی مدیریت مخاطبین"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="➕ افزودن شماره جدید", callback_data="add_phone"), row=1)
    keyboard.add(InlineKeyboardButton(text="📋 لیست مخاطبین", callback_data="list_phones"), row=2)
    keyboard.add(InlineKeyboardButton(text="🗑️ حذف مخاطب", callback_data="delete_phones"), row=3)
    keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"), row=4)
    return keyboard


def create_send_menu():
    """منوی ارسال پیام"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="📱 از مخاطبین ذخیره شده", callback_data="send_saved"), row=1)
    keyboard.add(InlineKeyboardButton(text="📁 آپلود فایل", callback_data="send_file"), row=2)
    keyboard.add(InlineKeyboardButton(text="✍️ وارد کردن دستی", callback_data="send_manual"), row=3)
    keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"), row=4)
    return keyboard


def create_back_button(callback_data: str):
    """دکمه بازگشت"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data=callback_data), row=1)
    return keyboard


def create_phone_selection_keyboard(phones: List[tuple], selected_ids: List[int]):
    """کیبورد انتخاب چندگانه مخاطبین"""
    keyboard = InlineKeyboardMarkup()
    row = 1

    for phone in phones[:15]:  # محدودیت 15 مخاطب
        phone_id, phone_number, label = phone
        prefix = "✅ " if phone_id in selected_ids else "⬜ "
        display = f"{prefix}{phone_number}"
        if label:
            display += f" ({label})"

        keyboard.add(
            InlineKeyboardButton(text=display, callback_data=f"sel_{phone_id}"),
            row=row
        )
        row += 1

    # دکمه‌های پایین
    selected_count = len(selected_ids)
    if selected_count > 0:
        keyboard.add(
            InlineKeyboardButton(text=f"📤 ارسال به {selected_count} مخاطب", callback_data="confirm_send"),
            row=row + 1
        )

    keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_send"), row=row + 2)
    return keyboard


# هندلر اصلی پیام‌ها
@bot.event
async def on_message(message: Message):
    """مدیریت پیام‌های دریافتی"""
    if not message.content:
        return

    content = message.content.strip()
    chat_id = message.chat.id

    # بررسی وضعیت کاربر
    user_state = user_temp_data.get(chat_id, {}).get("state")

    # حالت‌های مختلف
    if user_state == "waiting_phone":
        await process_add_phone(message)
        return

    elif user_state == "waiting_file":
        if message.document:
            await process_file_upload(message)
        else:
            await message.reply(
                "❌ لطفاً یک فایل متنی ارسال کنید.",
                components=create_back_button("menu_send")
            )
        return

    elif user_state == "waiting_manual":
        await process_manual_input(message)
        return

    elif user_state == "waiting_message":
        await process_and_send_message(message)
        return

    # دستور /start
    if content == "/start":
        await message.reply(
            "🌟 به ربات مدیریت و ارسال پیام Bale خوش آمدید!\n\n"
            "👥 مخاطبین خود را مدیریت کنید\n"
            "📤 به صورت انبوه پیام ارسال کنید\n\n"
            "از منوی زیر استفاده کنید:",
            components=create_main_menu()
        )


# مدیریت callback ها
@bot.event
async def on_callback(callback: Update):
    """مدیریت کلیک روی دکمه‌ها"""
    try:
        # در کتابخانه bale، callback.data مستقیماً در دسترس است
        if not hasattr(callback, 'data'):
            return

        data = callback.data
        chat_id = callback.message.chat.id

        # ============ منوی اصلی ============
        if data == "menu_main":
            await callback.message.reply(
                "📌 منوی اصلی:",
                components=create_main_menu()
            )

        elif data == "menu_contacts":
            await callback.message.reply(
                "👥 مدیریت مخاطبین:",
                components=create_contacts_menu()
            )

        elif data == "menu_send":
            await callback.message.reply(
                "📤 انتخاب روش ارسال:",
                components=create_send_menu()
            )

        # ============ مدیریت مخاطبین ============
        elif data == "add_phone":
            user_temp_data[chat_id] = {"state": "waiting_phone"}
            await callback.message.reply(
                "📱 لطفاً شماره را وارد کنید:\n\n"
                "فرمت: 09123456789\n"
                "همراه با اسم: 09123456789 علی\n\n"
                "برای لغو روی بازگشت کلیک کنید.",
                components=create_back_button("menu_contacts")
            )

        elif data == "list_phones":
            phones = get_saved_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "📋 لیست مخاطبین خالی است!",
                    components=create_contacts_menu()
                )
            else:
                text = "📋 **مخاطبین شما:**\n\n"
                for phone in phones:
                    _, number, label = phone
                    text += f"📱 {number}"
                    if label:
                        text += f" - {label}"
                    text += "\n"

                await callback.message.reply(text, components=create_contacts_menu())

        elif data == "delete_phones":
            phones = get_saved_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "هیچ مخاطبی برای حذف وجود ندارد!",
                    components=create_contacts_menu()
                )
            else:
                keyboard = InlineKeyboardMarkup()
                for i, phone in enumerate(phones[:10]):
                    phone_id, number, label = phone
                    display = f"🗑️ {number}"
                    if label:
                        display += f" ({label})"
                    keyboard.add(
                        InlineKeyboardButton(text=display, callback_data=f"del_{phone_id}"),
                        row=i + 1
                    )
                keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_contacts"), row=11)

                await callback.message.reply(
                    "برای حذف روی مخاطب کلیک کنید:",
                    components=keyboard
                )

        elif data.startswith("del_"):
            phone_id = int(data.replace("del_", ""))
            phone_number = get_phone_by_id(phone_id)
            delete_phone(phone_id)
            await callback.message.reply(
                f"✅ مخاطب {phone_number} حذف شد.",
                components=create_contacts_menu()
            )

        # ============ ارسال پیام ============
        elif data == "send_saved":
            phones = get_saved_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "❌ هیچ مخاطبی ذخیره نشده!\nابتدا مخاطب اضافه کنید.",
                    components=create_send_menu()
                )
            else:
                user_phone_selections[chat_id] = []
                await callback.message.reply(
                    f"📱 {len(phones)} مخاطب یافت شد.\n"
                    "مخاطبین مورد نظر را انتخاب کنید:",
                    components=create_phone_selection_keyboard(phones, [])
                )

        elif data.startswith("sel_"):
            phone_id = int(data.replace("sel_", ""))

            if chat_id not in user_phone_selections:
                user_phone_selections[chat_id] = []

            selections = user_phone_selections[chat_id]

            if phone_id in selections:
                selections.remove(phone_id)
            else:
                selections.append(phone_id)

            user_phone_selections[chat_id] = selections

            # به‌روزرسانی کیبورد
            phones = get_saved_phones(chat_id)
            await callback.message.edit_text(
                f"📱 {len(phones)} مخاطب | انتخاب شده: {len(selections)}\n"
                "برای انتخاب/حذف روی مخاطبین کلیک کنید:",
                components=create_phone_selection_keyboard(phones, selections)
            )

        elif data == "confirm_send":
            selections = user_phone_selections.get(chat_id, [])
            if not selections:
                await callback.message.reply(
                    "❌ هیچ مخاطبی انتخاب نشده!",
                    components=create_back_button("menu_send")
                )
            else:
                recipients = []
                for phone_id in selections:
                    number = get_phone_by_id(phone_id)
                    if number:
                        recipients.append(number)

                user_temp_data[chat_id] = {
                    "state": "waiting_message",
                    "recipien   ts": recipients
                }

                await callback.message.reply(
                    f"✅ {len(recipients)} مخاطب انتخاب شد.\n\n"
                    "✍️ لطفاً متن پیام خود را بنویسید:",
                    components=create_back_button("menu_send")
                )

        elif data == "send_file":
            user_temp_data[chat_id] = {"state": "waiting_file"}
            await callback.message.reply(
                "📁 لطفاً فایل txt خود را ارسال کنید.\n"
                "هر خط = یک شماره یا @username",
                components=create_back_button("menu_send")
            )

        elif data == "send_manual":
            user_temp_data[chat_id] = {"state": "waiting_manual"}
            await callback.message.reply(
                "✍️ شماره‌ها را وارد کنید (هر خط یک شماره):\n\n"
                "مثال:\n"
                "09123456789\n"
                "@username\n"
                "123456789",
                components=create_back_button("menu_send")
            )

    except Exception as e:
        print(f"❌ Error in callback: {e}")


# توابع پردازش
async def process_add_phone(message: Message):
    """پردازش شماره جدید"""
    chat_id = message.chat.id
    content = message.content.strip()

    # جدا کردن شماره و برچسب
    parts = content.split(maxsplit=1)
    phone = parts[0]
    label = parts[1] if len(parts) > 1 else ""

    # اعتبارسنجی
    phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)

    if not phone_clean.isdigit() or len(phone_clean) < 6:
        await message.reply(
            "❌ شماره نامعتبر! دوباره تلاش کنید.",
            components=create_back_button("menu_contacts")
        )
        return

    # ذخیره
    save_phone_to_db(chat_id, phone_clean, label)

    # پاک کردن state
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]

    msg = f"✅ شماره {phone_clean} ذخیره شد!"
    if label:
        msg += f"\nبرچسب: {label}"

    await message.reply(msg, components=create_contacts_menu())


async def process_file_upload(message: Message):
    """پردازش فایل آپلود شده"""
    chat_id = message.chat.id

    try:
        # دانلود فایل
        file_id = message.document.file_id
        resp = requests.post(f"{BALE_API_URL}/getFile", json={"file_id": file_id}).json()

        if not resp.get('ok'):
            await message.reply("❌ خطا در دریافت فایل", components=create_back_button("menu_send"))
            return

        file_path = resp['result']['file_path']
        content = requests.get(f"https://tapi.bale.ai/file/bot{BOT_TOKEN}/{file_path}").text

        # استخراج شماره‌ها
        recipients = []
        for line in content.split('\n'):
            line = line.strip()
            if line and (line.isdigit() or line.startswith('@')):
                recipients.append(line)

        if not recipients:
            await message.reply("❌ هیچ شماره معتبری یافت نشد!", components=create_back_button("menu_send"))
            return

        user_temp_data[chat_id] = {
            "state": "waiting_message",
            "recipients": recipients
        }

        await message.reply(
            f"✅ {len(recipients)} شماره از فایل استخراج شد.\n\n"
            "✍️ متن پیام را بنویسید:",
            components=create_back_button("menu_send")
        )

    except Exception as e:
        await message.reply(f"❌ خطا: {e}", components=create_back_button("menu_send"))


async def process_manual_input(message: Message):
    """پردازش ورودی دستی"""
    chat_id = message.chat.id

    recipients = []
    for line in message.content.strip().split('\n'):
        line = line.strip()
        if line and (line.isdigit() or line.startswith('@')):
            recipients.append(line)

    if not recipients:
        await message.reply(
            "❌ هیچ شماره معتبری یافت نشد!",
            components=create_back_button("menu_send")
        )
        return

    user_temp_data[chat_id] = {
        "state": "waiting_message",
        "recipients": recipients
    }

    await message.reply(
        f"✅ {len(recipients)} شماره دریافت شد.\n\n"
        "✍️ متن پیام را بنویسید:",
        components=create_back_button("menu_send")
    )


async def process_and_send_message(message: Message):
    """ارسال پیام به گیرندگان"""
    chat_id = message.chat.id
    message_text = message.content.strip()

    user_data = user_temp_data.get(chat_id, {})
    recipients = user_data.get("recipients", [])

    if not recipients:
        await message.reply("❌ خطا: لیست گیرندگان خالی است!", components=create_main_menu())
        return

    # پاک کردن state
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]
    if chat_id in user_phone_selections:
        del user_phone_selections[chat_id]

    # ارسال پیام وضعیت
    status = await message.reply(f"⏳ در حال ارسال به {len(recipients)} نفر...")

    success = 0
    failed = 0
    failed_list = []

    for i, recipient in enumerate(recipients, 1):
        ok, error = await send_message_to_user(recipient, message_text)

        if ok:
            success += 1
        else:
            failed += 1
            failed_list.append((recipient, error))
            print(f"❌ خطا: {recipient} - {error}")

        # به‌روزرسانی هر 5 تا
        if i % 5 == 0:
            try:
                await status.edit_text(
                    f"📤 ارسال: {i}/{len(recipients)}\n"
                    f"✅ موفق: {success}\n"
                    f"❌ ناموفق: {failed}"
                )
            except:
                pass

        await asyncio.sleep(0.5)

    # گزارش نهایی
    report = f"📊 **گزارش ارسال**\n\n"
    report += f"👥 کل: {len(recipients)}\n"
    report += f"✅ موفق: {success}\n"
    report += f"❌ ناموفق: {failed}\n"

    if failed_list and len(failed_list) <= 5:
        report += "\n🚫 ناموفق‌ها:\n"
        for num, err in failed_list:
            if "no such group or user" in err.lower():
                report += f"• {num} - کاربر ربات را استارت نکرده\n"
            else:
                report += f"• {num} - {err[:30]}\n"

    await message.reply(report, components=create_main_menu())


if __name__ == "__main__":
    print("🤖 ربات Bale شروع به کار کرد...")
    bot.run()