from bale import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton, Update
import sqlite3
import asyncio
import requests
from typing import List, Optional
import re
import csv
import io
import logging
from datetime import datetime

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# توکن بات خود را اینجا قرار دهید
BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
bot = Bot(token=BOT_TOKEN)

# نام فایل دیتابیس
DB_NAME = "bulk_sms.db"

# API Base URL برای Bale
BALE_API_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

# ذخیره موقت انتخاب‌های کاربران
user_phone_selections = {}  # {chat_id: [phone_ids]}
user_temp_data = {}  # {chat_id: {state, recipients, message, message_type, file_id}}


# ایجاد اتصال به دیتابیس
def init_db():
    logger.info("🔄 در حال اتصال به دیتابیس...")
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
    logger.info("✅ دیتابیس با موفقیت راه‌اندازی شد")
    return conn


conn = init_db()


# توابع مدیریت دیتابیس
def save_phone_to_db(chat_id: int, phone_number: str, label: str = ""):
    logger.info(f"📝 ذخیره شماره {phone_number} برای کاربر {chat_id}")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO saved_phones (chat_id, phone_number, label) VALUES (?, ?, ?)",
        (chat_id, phone_number, label)
    )
    conn.commit()
    logger.info(f"✅ شماره {phone_number} ذخیره شد")


def save_multiple_phones(chat_id: int, phones_list: List[tuple]):
    """ذخیره چند شماره به صورت همزمان"""
    logger.info(f"📝 ذخیره {len(phones_list)} شماره برای کاربر {chat_id}")
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO saved_phones (chat_id, phone_number, label) VALUES (?, ?, ?)",
        [(chat_id, phone, label) for phone, label in phones_list]
    )
    conn.commit()
    logger.info(f"✅ {len(phones_list)} شماره با موفقیت ذخیره شد")


def get_saved_phones(chat_id: int) -> List[tuple]:
    logger.info(f"🔍 دریافت لیست مخاطبین کاربر {chat_id}")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, phone_number, label FROM saved_phones WHERE chat_id = ? ORDER BY added_date DESC",
        (chat_id,)
    )
    result = cursor.fetchall()
    logger.info(f"📋 {len(result)} مخاطب برای کاربر {chat_id} یافت شد")
    return result


def delete_phone(phone_id: int):
    logger.info(f"🗑️ حذف مخاطب با ID {phone_id}")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_phones WHERE id = ?", (phone_id,))
    conn.commit()
    logger.info(f"✅ مخاطب با ID {phone_id} حذف شد")


def delete_all_phones(chat_id: int):
    """حذف همه مخاطبین یک کاربر"""
    logger.info(f"🗑️ حذف همه مخاطبین کاربر {chat_id}")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_phones WHERE chat_id = ?", (chat_id,))
    conn.commit()
    logger.info(f"✅ همه مخاطبین کاربر {chat_id} حذف شدند")


def get_phone_by_id(phone_id: int) -> Optional[str]:
    logger.info(f"🔍 دریافت شماره با ID {phone_id}")
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number FROM saved_phones WHERE id = ?", (phone_id,))
    result = cursor.fetchone()
    if result:
        logger.info(f"✅ شماره {result[0]} یافت شد")
    else:
        logger.warning(f"❌ شماره با ID {phone_id} یافت نشد")
    return result[0] if result else None


# تابع ارسال پیام با API مستقیم (پشتیبانی از عکس و ویدیو)
async def send_media_to_user(chat_id: str, message_type: str, file_id: str = None, caption: str = ""):
    """ارسال عکس، ویدیو یا متن به کاربر"""
    logger.info(f"📤 ارسال {message_type} به {chat_id}")
    try:
        url = None
        payload = {"chat_id": chat_id}
        
        if message_type == "text":
            url = f"{BALE_API_URL}/sendMessage"
            payload["text"] = caption
        elif message_type == "photo":
            url = f"{BALE_API_URL}/sendPhoto"
            payload["photo"] = file_id
            if caption:
                payload["caption"] = caption
        elif message_type == "video":
            url = f"{BALE_API_URL}/sendVideo"
            payload["video"] = file_id
            if caption:
                payload["caption"] = caption
        elif message_type == "document":
            url = f"{BALE_API_URL}/sendDocument"
            payload["document"] = file_id
            if caption:
                payload["caption"] = caption
        
        if not url:
            return False, "نوع پیام نامعتبر"
        
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()

        if result.get('ok'):
            logger.info(f"✅ {message_type} با موفقیت به {chat_id} ارسال شد")
            return True, ""
        else:
            error_desc = result.get('description', 'Unknown error')
            logger.error(f"❌ خطا در ارسال به {chat_id}: {error_desc}")
            return False, error_desc
    except Exception as e:
        logger.error(f"❌ خطای connection در ارسال به {chat_id}: {str(e)}")
        return False, str(e)


async def send_message_to_user(chat_id: str, text: str) -> tuple:
    """ارسال پیام متنی به کاربر (برای سازگاری با کد قبلی)"""
    return await send_media_to_user(chat_id, "text", None, text)


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
    keyboard.add(InlineKeyboardButton(text="📁 آپلود فایل مخاطبین", callback_data="upload_contacts"), row=3)
    keyboard.add(InlineKeyboardButton(text="🗑️ حذف مخاطب", callback_data="delete_phones"), row=4)
    keyboard.add(InlineKeyboardButton(text="🗑️ حذف همه مخاطبین", callback_data="delete_all"), row=5)
    keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"), row=6)
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
    """کیبورد انتخاب چندگانه مخاطبین با دکمه‌های اضافی"""
    keyboard = InlineKeyboardMarkup()
    row = 1
    
    total_phones = len(phones)
    all_ids = [p[0] for p in phones]
    
    # دکمه‌های انتخاب سریع
    keyboard.add(InlineKeyboardButton(text="✅ انتخاب همه", callback_data="select_all"), row=row)
    row += 1
    keyboard.add(InlineKeyboardButton(text="📌 5 تای اول", callback_data="select_first_5"), row=row)
    row += 1
    keyboard.add(InlineKeyboardButton(text="📌 5 تای آخر", callback_data="select_last_5"), row=row)
    row += 1
    keyboard.add(InlineKeyboardButton(text="❌ پاک کردن همه", callback_data="clear_all"), row=row)
    row += 1
    
    # خط جداکننده (با یک دکمه خالی)
    keyboard.add(InlineKeyboardButton(text="━━━━━━━━━━━━━━", callback_data="noop"), row=row)
    row += 1

    # نمایش مخاطبین
    for phone in phones[:15]:  # محدودیت 15 مخاطب
        phone_id, phone_number, label = phone
        prefix = "✅ " if phone_id in selected_ids else "⬜ "
        display = f"{prefix}{phone_number}"
        if label:
            display += f" ({label[:15]})"  # محدودیت طول برچسب

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
        row += 1

    keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_send"), row=row + 1)
    return keyboard


# تابع کمکی برای ویرایش پیام
async def edit_message_text(chat_id: int, message_id: int, text: str, components=None):
    """ویرایش پیام در Bale"""
    try:
        url = f"{BALE_API_URL}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if components:
            payload["reply_markup"] = components.to_json()
        
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return True
        else:
            logger.error(f"خطا در ویرایش پیام: {result}")
            return False
    except Exception as e:
        logger.error(f"خطا در ویرایش پیام: {e}")
        return False


async def edit_message_caption(chat_id: int, message_id: int, caption: str, components=None):
    """ویرایش کپشن عکس/ویدیو در Bale"""
    try:
        url = f"{BALE_API_URL}/editMessageCaption"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
        }
        if components:
            payload["reply_markup"] = components.to_json()
        
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return True
        else:
            logger.error(f"خطا در ویرایش کپشن: {result}")
            return False
    except Exception as e:
        logger.error(f"خطا در ویرایش کپشن: {e}")
        return False


# هندلر اصلی پیام‌ها
@bot.event
async def on_message(message: Message):
    """مدیریت پیام‌های دریافتی"""
    
    chat_id = message.chat.id
    
    # بررسی وضعیت کاربر
    user_state = user_temp_data.get(chat_id, {}).get("state")
    logger.info(f"وضعیت فعلی کاربر {chat_id}: {user_state}")
    
    # ========== پردازش فایل برای ارسال ==========
    if user_state == "waiting_media":
        logger.info("🔄 در حالت waiting_media")
        
        # ذخیره اطلاعات رسانه
        media_data = {}
        
        if hasattr(message, 'document') and message.document:
            media_data = {
                "type": "document",
                "file_id": message.document.file_id,
                "file_name": message.document.file_name
            }
            logger.info(f"📁 فایل دریافت شد: {message.document.file_name}")
        elif hasattr(message, 'photo') and message.photo:
            # بزرگترین سایز عکس را بگیر
            photo = message.photo[-1] if isinstance(message.photo, list) else message.photo
            media_data = {
                "type": "photo",
                "file_id": photo.file_id if hasattr(photo, 'file_id') else message.photo.file_id
            }
            logger.info(f"🖼️ عکس دریافت شد")
        elif hasattr(message, 'video') and message.video:
            media_data = {
                "type": "video",
                "file_id": message.video.file_id,
                "file_name": getattr(message.video, 'file_name', 'video.mp4')
            }
            logger.info(f"🎥 ویدیو دریافت شد")
        elif message.content and message.content.strip():
            # متن ساده
            media_data = {
                "type": "text",
                "caption": message.content.strip()
            }
            logger.info(f"📝 متن دریافت شد")
        
        if media_data:
            user_temp_data[chat_id]["media"] = media_data
            user_temp_data[chat_id]["state"] = "waiting_confirm_send"
            
            await message.reply(
                f"✅ رسانه دریافت شد!\n"
                f"نوع: {media_data.get('type', 'text')}\n\n"
                "برای تایید و ارسال به مخاطبین، روی دکمه زیر کلیک کنید:",
                components=create_confirm_send_keyboard()
            )
        else:
            await message.reply(
                "❌ لطفاً یک متن، عکس، ویدیو یا فایل ارسال کنید.",
                components=create_back_button("menu_send")
            )
        return
    
    # ========== پردازش فایل مخاطبین ==========
    if user_state == "waiting_contacts_file":
        logger.info("🔄 در حالت waiting_contacts_file")
        
        if hasattr(message, 'document') and message.document:
            logger.info(f"📁 فایل مخاطب دریافت شد: {message.document.file_name}")
            await process_contacts_file_upload(message)
            return
        elif message.content and message.content.strip():
            logger.info("کاربر متن فرستاده، بررسی به عنوان لیست شماره...")
            await process_text_as_contacts(message)
            return
        else:
            await message.reply(
                "❌ لطفاً یک فایل CSV یا TXT ارسال کنید.\n\n"
                "یا می‌توانید شماره‌ها را مستقیم وارد کنید (هر خط یک شماره):",
                components=create_back_button("menu_contacts")
            )
        return
    
    # ========== پردازش فایل برای ارسال لیست ==========
    if user_state == "waiting_file":
        logger.info("🔄 در حالت waiting_file")
        if hasattr(message, 'document') and message.document:
            logger.info(f"📁 فایل دریافت شد: {message.document.file_name}")
            await process_file_upload(message)
            return
        else:
            await message.reply(
                "❌ لطفاً یک فایل متنی ارسال کنید.",
                components=create_back_button("menu_send")
            )
        return
    
    # ========== پردازش متن ==========
    if not message.content:
        logger.warning("پیام بدون محتوا")
        return
    
    content = message.content.strip()
    
    # حالت‌های مختلف متنی
    if user_state == "waiting_phone":
        logger.info("🔄 در حالت waiting_phone")
        await process_add_phone(message)
        return

    elif user_state == "waiting_manual":
        logger.info("🔄 در حالت waiting_manual")
        await process_manual_input(message)
        return

    # دستور /start
    if content == "/start":
        logger.info(f"کاربر {chat_id} ربات را استارت کرد")
        await message.reply(
            "🌟 به ربات مدیریت و ارسال پیام Bale خوش آمدید!\n\n"
            "👥 مخاطبین خود را مدیریت کنید\n"
            "📤 به صورت انبوه پیام ارسال کنید\n\n"
            "از منوی زیر استفاده کنید:",
            components=create_main_menu()
        )
        return


def create_confirm_send_keyboard():
    """کیبورد تایید ارسال"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="📤 تایید و ارسال به همه", callback_data="confirm_send_final"), row=1)
    keyboard.add(InlineKeyboardButton(text="🔙 انصراف و بازگشت", callback_data="menu_send"), row=2)
    return keyboard


# مدیریت callback ها
@bot.event
async def on_callback(callback: Update):
    """مدیریت کلیک روی دکمه‌ها"""
    try:
        if not hasattr(callback, 'data'):
            logger.warning("Callback بدون data")
            return

        data = callback.data
        chat_id = callback.message.chat.id
        message_id = callback.message.message_id
        logger.info(f"🔘 کلیک روی دکمه {data} از کاربر {chat_id}")

        # ============ منوی اصلی ============
        if data == "menu_main":
            await callback.message.reply(
                "📌 منوی اصلی:",
                components=create_main_menu()
            )
            await bot.delete_message(chat_id, message_id)

        elif data == "menu_contacts":
            await callback.message.reply(
                "👥 مدیریت مخاطبین:",
                components=create_contacts_menu()
            )
            await bot.delete_message(chat_id, message_id)

        elif data == "menu_send":
            await callback.message.reply(
                "📤 انتخاب روش ارسال:",
                components=create_send_menu()
            )
            await bot.delete_message(chat_id, message_id)

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
            await bot.delete_message(chat_id, message_id)

        elif data == "upload_contacts":
            user_temp_data[chat_id] = {"state": "waiting_contacts_file"}
            await callback.message.reply(
                "📁 لطفاً فایل مخاطبین خود را ارسال کنید.\n\n"
                "فرمت‌های پشتیبانی شده:\n"
                "• فایل CSV (شماره,نام)\n"
                "• فایل TXT (هر خط یک شماره)\n\n"
                "یا می‌توانید شماره‌ها را مستقیم در چت وارد کنید.",
                components=create_back_button("menu_contacts")
            )
            await bot.delete_message(chat_id, message_id)

        elif data == "list_phones":
            phones = get_saved_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "📋 لیست مخاطبین خالی است!",
                    components=create_contacts_menu()
                )
            else:
                text = "📋 **مخاطبین شما:**\n\n"
                for i, phone in enumerate(phones, 1):
                    _, number, label = phone
                    text += f"{i}. 📱 {number}"
                    if label:
                        text += f" - {label}"
                    text += "\n"
                    
                    if len(text) > 3800:
                        text += f"\n... و {len(phones) - i} مخاطب دیگر"
                        break

                await callback.message.reply(text, components=create_contacts_menu())
            await bot.delete_message(chat_id, message_id)

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
            await bot.delete_message(chat_id, message_id)

        elif data == "delete_all":
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="✅ بله، حذف همه", callback_data="confirm_delete_all"), row=1)
            keyboard.add(InlineKeyboardButton(text="❌ انصراف", callback_data="menu_contacts"), row=2)
            
            phones_count = len(get_saved_phones(chat_id))
            await callback.message.reply(
                f"⚠️ آیا از حذف {phones_count} مخاطب مطمئن هستید؟\nاین عمل غیرقابل بازگشت است.",
                components=keyboard
            )
            await bot.delete_message(chat_id, message_id)

        elif data == "confirm_delete_all":
            delete_all_phones(chat_id)
            await callback.message.reply(
                "✅ همه مخاطبین با موفقیت حذف شدند.",
                components=create_contacts_menu()
            )
            await bot.delete_message(chat_id, message_id)

        elif data.startswith("del_"):
            phone_id = int(data.replace("del_", ""))
            phone_number = get_phone_by_id(phone_id)
            delete_phone(phone_id)
            await callback.message.reply(
                f"✅ مخاطب {phone_number} حذف شد.",
                components=create_contacts_menu()
            )
            await bot.delete_message(chat_id, message_id)

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
                sent_msg = await callback.message.reply(
                    f"📱 {len(phones)} مخاطب یافت شد.\n"
                    "مخاطبین مورد نظر را انتخاب کنید:",
                    components=create_phone_selection_keyboard(phones, [])
                )
                # ذخیره message_id برای ویرایش بعدی
                user_temp_data[chat_id] = {"selection_msg_id": sent_msg.message_id}
            await bot.delete_message(chat_id, message_id)

        elif data == "select_all":
            phones = get_saved_phones(chat_id)
            all_ids = [p[0] for p in phones]
            user_phone_selections[chat_id] = all_ids
            await update_selection_message(chat_id, phones, all_ids)

        elif data == "select_first_5":
            phones = get_saved_phones(chat_id)
            first_5_ids = [p[0] for p in phones[:5]]
            user_phone_selections[chat_id] = first_5_ids
            await update_selection_message(chat_id, phones, first_5_ids)

        elif data == "select_last_5":
            phones = get_saved_phones(chat_id)
            last_5_ids = [p[0] for p in phones[-5:]]
            user_phone_selections[chat_id] = last_5_ids
            await update_selection_message(chat_id, phones, last_5_ids)

        elif data == "clear_all":
            user_phone_selections[chat_id] = []
            phones = get_saved_phones(chat_id)
            await update_selection_message(chat_id, phones, [])

        elif data == "noop":
            # دکمه بی‌اثر برای خط جداکننده
            pass

        elif data.startswith("sel_"):
            phone_id = int(data.replace("sel_", ""))

            if chat_id not in user_phone_selections:
                user_phone_selections[chat_id] = []

            selections = user_phone_selections[chat_id]

            if phone_id in selections:
                selections.remove(phone_id)
                logger.info(f"حذف مخاطب {phone_id} از انتخاب")
            else:
                selections.append(phone_id)
                logger.info(f"اضافه کردن مخاطب {phone_id} به انتخاب")

            user_phone_selections[chat_id] = selections

            # به‌روزرسانی پیام
            phones = get_saved_phones(chat_id)
            await update_selection_message(chat_id, phones, selections)

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
                    "state": "waiting_media",
                    "recipients": recipients,
                    "selection_msg_id": user_temp_data.get(chat_id, {}).get("selection_msg_id")
                }

                await callback.message.reply(
                    f"✅ {len(recipients)} مخاطب انتخاب شد.\n\n"
                    "📤 حالا پیام خود را ارسال کنید.\n"
                    "می‌توانید: متن، عکس، ویدیو یا فایل بفرستید.",
                    components=create_back_button("menu_send")
                )

        elif data == "confirm_send_final":
            user_data = user_temp_data.get(chat_id, {})
            recipients = user_data.get("recipients", [])
            media = user_data.get("media", {})
            
            if not recipients:
                await callback.message.reply("❌ لیست گیرندگان خالی است!", components=create_main_menu())
                return
            
            await callback.message.reply(f"⏳ در حال ارسال به {len(recipients)} نفر...")
            
            success = 0
            failed = 0
            failed_list = []
            
            for i, recipient in enumerate(recipients, 1):
                if media.get("type") == "text":
                    ok, error = await send_message_to_user(recipient, media.get("caption", ""))
                else:
                    ok, error = await send_media_to_user(
                        recipient, 
                        media.get("type"), 
                        media.get("file_id"), 
                        media.get("caption", "")
                    )
                
                if ok:
                    success += 1
                else:
                    failed += 1
                    failed_list.append((recipient, error))
                
                if i % 5 == 0:
                    try:
                        await callback.message.edit_text(
                            f"📤 ارسال: {i}/{len(recipients)}\n✅ موفق: {success}\n❌ ناموفق: {failed}"
                        )
                    except:
                        pass
                
                await asyncio.sleep(0.5)
            
            # پاک کردن دیتا
            if chat_id in user_temp_data:
                del user_temp_data[chat_id]
            if chat_id in user_phone_selections:
                del user_phone_selections[chat_id]
            
            report = f"📊 **گزارش ارسال**\n\n👥 کل: {len(recipients)}\n✅ موفق: {success}\n❌ ناموفق: {failed}"
            await callback.message.reply(report, components=create_main_menu())

        elif data == "send_file":
            user_temp_data[chat_id] = {"state": "waiting_file"}
            await callback.message.reply(
                "📁 لطفاً فایل txt خود را ارسال کنید.\n"
                "هر خط = یک شماره یا @username",
                components=create_back_button("menu_send")
            )
            await bot.delete_message(chat_id, message_id)

        elif data == "send_manual":
            user_temp_data[chat_id] = {"state": "waiting_manual"}
            await callback.message.reply(
                "✍️ شماره‌ها را وارد کنید (هر خط یک شماره):\n\n"
                "مثال:\n"
                "09123456789\n"
                "@username",
                components=create_back_button("menu_send")
            )
            await bot.delete_message(chat_id, message_id)

    except Exception as e:
        logger.error(f"❌ خطا در callback: {str(e)}", exc_info=True)


async def update_selection_message(chat_id: int, phones: List[tuple], selections: List[int]):
    """به‌روزرسانی پیام انتخاب مخاطبین"""
    msg_data = user_temp_data.get(chat_id, {})
    msg_id = msg_data.get("selection_msg_id")
    
    if msg_id:
        await edit_message_text(
            chat_id, 
            msg_id,
            f"📱 {len(phones)} مخاطب | انتخاب شده: {len(selections)}\n"
            "برای انتخاب/حذف روی مخاطبین کلیک کنید:",
            components=create_phone_selection_keyboard(phones, selections)
        )


# ============ توابع پردازش ============

async def process_contacts_file_upload(message: Message):
    """پردازش فایل آپلود شده حاوی لیست مخاطبین"""
    chat_id = message.chat.id
    logger.info(f"🔄 شروع پردازش فایل مخاطبین برای کاربر {chat_id}")

    status_msg = await message.reply("⏳ در حال بررسی فایل...")
    message_id = status_msg.message_id

    try:
        if not hasattr(message, 'document') or not message.document:
            await edit_message_text(chat_id, message_id, 
                "❌ هیچ فایلی یافت نشد!", 
                components=create_back_button("menu_contacts"))
            return
        
        await edit_message_text(chat_id, message_id, "📥 در حال دانلود فایل...")
        file_id = message.document.file_id
        
        resp = requests.post(f"{BALE_API_URL}/getFile", json={"file_id": file_id}, timeout=30)
        
        if resp.status_code != 200:
            await edit_message_text(chat_id, message_id,
                "❌ خطا در دریافت فایل", 
                components=create_back_button("menu_contacts"))
            return
        
        result = resp.json()
        if not result.get('ok'):
            await edit_message_text(chat_id, message_id,
                "❌ خطا در دریافت فایل", 
                components=create_back_button("menu_contacts"))
            return

        file_path = result['result']['file_path']
        file_url = f"https://tapi.bale.ai/file/bot{BOT_TOKEN}/{file_path}"
        
        await edit_message_text(chat_id, message_id, "🔍 در حال خواندن فایل...")
        
        response = requests.get(file_url, timeout=30)
        content = response.content.decode('utf-8', errors='ignore')

        phones_list = []
        
        await edit_message_text(chat_id, message_id, "📊 در حال استخراج شماره‌ها...")
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            line = line.replace('،', ',')
            
            if ',' in line:
                parts = line.split(',', 1)
            else:
                parts = line.split(maxsplit=1)
            
            phone_raw = parts[0].strip()
            phone = re.sub(r'[^\d]', '', phone_raw)
            
            if len(phone) >= 10:
                if len(phone) == 10:
                    phone = '0' + phone
                elif len(phone) > 11:
                    phone = phone[:11]
                
                if phone.startswith('09') and len(phone) == 11:
                    label = parts[1].strip() if len(parts) > 1 else ""
                    phones_list.append((phone, label))
        
        if not phones_list:
            await edit_message_text(chat_id, message_id,
                "❌ هیچ شماره معتبری در فایل یافت نشد!",
                components=create_back_button("menu_contacts"))
            return

        await edit_message_text(chat_id, message_id, f"💾 در حال ذخیره {len(phones_list)} شماره...")
        save_multiple_phones(chat_id, phones_list)

        if chat_id in user_temp_data:
            del user_temp_data[chat_id]

        await edit_message_text(chat_id, message_id,
            f"✅ **{len(phones_list)} مخاطب** با موفقیت ذخیره شدند!",
            components=create_contacts_menu())

    except Exception as e:
        logger.error(f"خطا در پردازش فایل: {str(e)}", exc_info=True)
        await edit_message_text(chat_id, message_id,
            f"❌ خطا: {str(e)[:100]}",
            components=create_back_button("menu_contacts"))


async def process_text_as_contacts(message: Message):
    """پردازش متن مستقیم کاربر به عنوان لیست مخاطبین"""
    chat_id = message.chat.id
    content = message.content.strip()
    logger.info(f"پردازش متن مستقیم از کاربر {chat_id}")
    
    status_msg = await message.reply("⏳ در حال پردازش متن...")
    message_id = status_msg.message_id
    
    phones_list = []
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        parts = line.split(maxsplit=1)
        phone_raw = parts[0]
        phone = re.sub(r'[^\d]', '', phone_raw)
        
        if len(phone) >= 10:
            if len(phone) == 10:
                phone = '0' + phone
            elif len(phone) > 11:
                phone = phone[:11]
            
            if phone.startswith('09') and len(phone) == 11:
                label = parts[1] if len(parts) > 1 else ""
                phones_list.append((phone, label))
    
    if not phones_list:
        await edit_message_text(chat_id, message_id,
            "❌ هیچ شماره معتبری در متن یافت نشد!",
            components=create_back_button("menu_contacts"))
        return
    
    await edit_message_text(chat_id, message_id, f"💾 در حال ذخیره {len(phones_list)} شماره...")
    save_multiple_phones(chat_id, phones_list)
    
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]
    
    await edit_message_text(chat_id, message_id,
        f"✅ **{len(phones_list)} مخاطب** با موفقیت ذخیره شدند!",
        components=create_contacts_menu())


async def process_add_phone(message: Message):
    """پردازش شماره جدید"""
    chat_id = message.chat.id
    content = message.content.strip()

    parts = content.split(maxsplit=1)
    phone_raw = parts[0]
    label = parts[1] if len(parts) > 1 else ""

    phone_clean = re.sub(r'[^\d]', '', phone_raw)

    if not phone_clean.isdigit() or len(phone_clean) < 6:
        await message.reply(
            "❌ شماره نامعتبر! دوباره تلاش کنید.",
            components=create_back_button("menu_contacts")
        )
        return

    save_phone_to_db(chat_id, phone_clean, label)

    if chat_id in user_temp_data:
        del user_temp_data[chat_id]

    msg = f"✅ شماره {phone_clean} ذخیره شد!"
    if label:
        msg += f"\nبرچسب: {label}"

    await message.reply(msg, components=create_contacts_menu())


async def process_file_upload(message: Message):
    """پردازش فایل آپلود شده برای ارسال لیست شماره"""
    chat_id = message.chat.id
    logger.info(f"پردازش فایل ارسالی برای کاربر {chat_id}")

    status_msg = await message.reply("⏳ در حال بررسی فایل...")

    try:
        file_id = message.document.file_id
        resp = requests.post(f"{BALE_API_URL}/getFile", json={"file_id": file_id}, timeout=30).json()

        if not resp.get('ok'):
            await status_msg.edit_text("❌ خطا در دریافت فایل", components=create_back_button("menu_send"))
            return

        file_path = resp['result']['file_path']
        content = requests.get(f"https://tapi.bale.ai/file/bot{BOT_TOKEN}/{file_path}", timeout=30).text

        recipients = []
        for line in content.split('\n'):
            line = line.strip()
            if line and (line.isdigit() or line.startswith('@')):
                recipients.append(line)

        if not recipients:
            await status_msg.edit_text("❌ هیچ شماره معتبری یافت نشد!", components=create_back_button("menu_send"))
            return

        user_temp_data[chat_id] = {
            "state": "waiting_media",
            "recipients": recipients
        }

        await status_msg.edit_text(
            f"✅ {len(recipients)} شماره از فایل استخراج شد.\n\n"
            "📤 حالا پیام خود را ارسال کنید (متن، عکس، ویدیو یا فایل):",
            components=create_back_button("menu_send")
        )

    except Exception as e:
        logger.error(f"خطا در پردازش فایل: {e}")
        await status_msg.edit_text(f"❌ خطا: {e}", components=create_back_button("menu_send"))


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
        "state": "waiting_media",
        "recipients": recipients
    }

    await message.reply(
        f"✅ {len(recipients)} شماره دریافت شد.\n\n"
        "📤 حالا پیام خود را ارسال کنید (متن، عکس، ویدیو یا فایل):",
        components=create_back_button("menu_send")
    )


if __name__ == "__main__":
    print("🤖 ربات Bale شروع به کار کرد...")
    print("📝 لاگ‌ها در فایل bot_debug.log ذخیره می‌شوند")
    print("✨ قابلیت‌ها: ارسال متن، عکس، ویدیو و فایل به صورت انبوه")
    logger.info("="*50)
    logger.info("ربات راه‌اندازی شد")
    logger.info("="*50)
    bot.run()