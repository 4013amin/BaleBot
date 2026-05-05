from bale import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton, Update
import sqlite3
import asyncio
import requests
from typing import List, Optional, Dict, Tuple
import re
import logging
from datetime import datetime
import json

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

# توکن بات
BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
bot = Bot(token=BOT_TOKEN)

# نام فایل دیتابیس
DB_NAME = "bulk_sms.db"

# API Base URL
BALE_API_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

# ذخیره موقت انتخاب‌های کاربران
user_phone_selections = {}
user_temp_data = {}
user_chat_mapping = {}  # ذخیره موقت mapping شماره به chat_id


class Database:
    def __init__(self, db_name: str):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_phones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                phone_number TEXT,
                label TEXT,
                user_chat_id TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_chat_ids (
                phone_number TEXT PRIMARY KEY,
                chat_id TEXT,
                username TEXT,
                first_name TEXT,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS send_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                recipients_count INTEGER,
                success_count INTEGER,
                failed_count INTEGER,
                send_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def save_phone(self, chat_id: int, phone_number: str, label: str = ""):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO saved_phones (chat_id, phone_number, label) VALUES (?, ?, ?)",
            (chat_id, phone_number, label)
        )
        self.conn.commit()
    
    def save_multiple_phones(self, chat_id: int, phones_list: List[Tuple[str, str]]):
        cursor = self.conn.cursor()
        cursor.executemany(
            "INSERT INTO saved_phones (chat_id, phone_number, label) VALUES (?, ?, ?)",
            [(chat_id, phone, label) for phone, label in phones_list]
        )
        self.conn.commit()
    
    def get_phones(self, chat_id: int) -> List[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, phone_number, label FROM saved_phones WHERE chat_id = ? ORDER BY added_date DESC",
            (chat_id,)
        )
        return cursor.fetchall()
    
    def get_phone_by_id(self, phone_id: int) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT phone_number FROM saved_phones WHERE id = ?", (phone_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def save_user_chat_id(self, phone_number: str, user_chat_id: str, username: str = "", first_name: str = ""):
        """ذخیره chat_id یک کاربر"""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO user_chat_ids (phone_number, chat_id, username, first_name, last_activity)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (phone_number, user_chat_id, username, first_name)
        )
        self.conn.commit()
        logger.info(f"✅ ذخیره chat_id برای {phone_number}: {user_chat_id}")
    
    def get_user_chat_id(self, phone_number: str) -> Optional[str]:
        """دریافت chat_id یک کاربر"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT chat_id FROM user_chat_ids WHERE phone_number = ?", (phone_number,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def delete_phone(self, phone_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM saved_phones WHERE id = ?", (phone_id,))
        self.conn.commit()
    
    def delete_all_phones(self, chat_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM saved_phones WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
    
    def save_send_history(self, chat_id: int, recipients_count: int, success_count: int, failed_count: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO send_history (chat_id, recipients_count, success_count, failed_count) VALUES (?, ?, ?, ?)",
            (chat_id, recipients_count, success_count, failed_count)
        )
        self.conn.commit()
    
    def get_stats(self, chat_id: int) -> Dict:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM saved_phones WHERE chat_id = ?", (chat_id,))
        total_contacts = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*), SUM(recipients_count), SUM(success_count), SUM(failed_count)
            FROM send_history WHERE chat_id = ?
        """, (chat_id,))
        stats = cursor.fetchone()
        
        return {
            "total_contacts": total_contacts,
            "total_sends": stats[0] or 0,
            "total_recipients": stats[1] or 0,
            "total_success": stats[2] or 0,
            "total_failed": stats[3] or 0
        }


db = Database(DB_NAME)


class MessageSender:
    @staticmethod
    async def send_media_to_user(chat_id: str, message_type: str, file_id: str = None, caption: str = "") -> Tuple[bool, str]:
        """ارسال پیام با استفاده از chat_id عددی"""
        logger.info(f"📤 ارسال {message_type} به chat_id: {chat_id}")
        
        try:
            url = None
            payload = {"chat_id": chat_id}  # مستقیم از chat_id عددی استفاده کن
            
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
            
            logger.info(f"📥 پاسخ: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            if result.get('ok'):
                logger.info(f"✅ پیام با موفقیت ارسال شد")
                return True, ""
            else:
                error_desc = result.get('description', 'Unknown error')
                logger.error(f"❌ خطا در ارسال: {error_desc}")
                return False, error_desc
                
        except Exception as e:
            logger.error(f"❌ خطای اتصال: {str(e)}")
            return False, str(e)
    
    @staticmethod
    async def get_chat_id_for_phone(phone_number: str, owner_chat_id: int) -> Tuple[bool, str]:
        """
        دریافت chat_id برای یک شماره تلفن
        اول دیتابیس محلی رو چک می‌کنه، بعد از کاربر می‌خواد با اون شماره استارت کنه
        """
        # چک کردن دیتابیس محلی
        stored_chat_id = db.get_user_chat_id(phone_number)
        if stored_chat_id:
            logger.info(f"✅ chat_id برای {phone_number} در دیتابیس پیدا شد: {stored_chat_id}")
            return True, stored_chat_id
        
        # اگه پیدا نشد، به کاربر بگو که طرف مقابل باید ربات رو استارت کنه
        return False, "chat_id پیدا نشد"


class KeyboardBuilder:
    @staticmethod
    def main_menu():
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="👥 مدیریت مخاطبین", callback_data="menu_contacts"), row=1)
        keyboard.add(InlineKeyboardButton(text="📤 ارسال پیام انبوه", callback_data="menu_send"), row=2)
        keyboard.add(InlineKeyboardButton(text="📊 آمار و گزارشات", callback_data="menu_stats"), row=3)
        keyboard.add(InlineKeyboardButton(text="❓ راهنما", callback_data="menu_help"), row=4)
        return keyboard
    
    @staticmethod
    def contacts_menu():
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="➕ افزودن شماره جدید", callback_data="add_phone"), row=1)
        keyboard.add(InlineKeyboardButton(text="📋 لیست مخاطبین", callback_data="list_phones"), row=2)
        keyboard.add(InlineKeyboardButton(text="📁 آپلود فایل مخاطبین", callback_data="upload_contacts"), row=3)
        keyboard.add(InlineKeyboardButton(text="🗑️ حذف مخاطب", callback_data="delete_phones"), row=4)
        keyboard.add(InlineKeyboardButton(text="🗑️ حذف همه مخاطبین", callback_data="delete_all"), row=5)
        keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"), row=6)
        return keyboard
    
    @staticmethod
    def send_menu():
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="📱 از مخاطبین ذخیره شده", callback_data="send_saved"), row=1)
        keyboard.add(InlineKeyboardButton(text="📁 آپلود فایل شماره", callback_data="send_file"), row=2)
        keyboard.add(InlineKeyboardButton(text="✍️ وارد کردن دستی شماره", callback_data="send_manual"), row=3)
        keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"), row=4)
        return keyboard
    
    @staticmethod
    def back_button(callback_data: str = "menu_main"):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data=callback_data), row=1)
        return keyboard
    
    @staticmethod
    def phone_selection_keyboard(phones: List[Tuple], selected_ids: List[int]):
        keyboard = InlineKeyboardMarkup()
        row = 1
        
        keyboard.add(InlineKeyboardButton(text="✅ انتخاب همه", callback_data="select_all"), row=row)
        row += 1
        keyboard.add(InlineKeyboardButton(text="📌 ۱۰ تای اول", callback_data="select_first_10"), row=row)
        row += 1
        keyboard.add(InlineKeyboardButton(text="📌 ۱۰ تای آخر", callback_data="select_last_10"), row=row)
        row += 1
        keyboard.add(InlineKeyboardButton(text="❌ حذف انتخاب", callback_data="clear_all"), row=row)
        row += 1
        
        keyboard.add(InlineKeyboardButton(text="➖➖➖➖➖➖➖➖", callback_data="noop"), row=row)
        row += 1
        
        for phone in phones[:20]:
            phone_id, phone_number, label = phone
            prefix = "✅ " if phone_id in selected_ids else "⬜ "
            display = f"{prefix}{phone_number}"
            if label:
                display += f" ({label[:10]})"
            
            keyboard.add(
                InlineKeyboardButton(text=display, callback_data=f"sel_{phone_id}"),
                row=row
            )
            row += 1
        
        selected_count = len(selected_ids)
        if selected_count > 0:
            keyboard.add(
                InlineKeyboardButton(text=f"📤 ارسال به {selected_count} مخاطب", callback_data="confirm_send"),
                row=row
            )
            row += 1
        
        keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_send"), row=row)
        return keyboard
    
    @staticmethod
    def confirm_send_keyboard():
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="📤 تایید و ارسال", callback_data="confirm_send_final"), row=1)
        keyboard.add(InlineKeyboardButton(text="🔙 انصراف", callback_data="menu_send"), row=2)
        return keyboard


class ContactManager:
    @staticmethod
    def extract_phone_numbers(text: str) -> List[Tuple[str, str]]:
        phones = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(maxsplit=1)
            phone_raw = parts[0].strip()
            label = parts[1].strip() if len(parts) > 1 else ""
            
            phone = re.sub(r'[^\d]', '', phone_raw)
            
            if len(phone) >= 10:
                if len(phone) == 10:
                    phone = '0' + phone
                elif len(phone) > 11:
                    phone = phone[:11]
                
                if phone.startswith('09') and len(phone) == 11:
                    phones.append((phone, label))
        
        return phones


# ذخیره خودکار chat_id کاربران وقتی پیام می‌دن
@bot.event
async def on_message(message: Message):
    chat_id = message.chat.id
    user_state = user_temp_data.get(chat_id, {}).get("state")
    
    logger.info(f"📨 پیام از کاربر {chat_id} | وضعیت: {user_state}")
    
    # ذخیره خودکار chat_id کاربر
    if hasattr(message, 'from_id') and message.from_id:
        # اگر کاربر شماره تلفن داشته باشه (از طریق contact)
        if hasattr(message, 'contact') and message.contact:
            phone = message.contact.phone_number
            db.save_user_chat_id(
                phone,
                str(chat_id),
                getattr(message.contact, 'first_name', ''),
                getattr(message.contact, 'first_name', '')
            )
            logger.info(f"💾 ذخیره خودکار: {phone} -> chat_id: {chat_id}")
    
    if user_state == "waiting_phone":
        await handle_add_phone(message)
    elif user_state == "waiting_contacts_file":
        await handle_contacts_file(message)
    elif user_state == "waiting_manual":
        await handle_manual_input(message)
    elif user_state == "waiting_file":
        await handle_file_for_send(message)
    elif user_state == "waiting_media":
        await handle_media_input(message)
    elif user_state == "waiting_chat_id":
        await handle_chat_id_input(message)
    elif hasattr(message, 'content') and message.content == "/start":
        await handle_start(message)
    elif hasattr(message, 'content') and message.content == "/help":
        await handle_help(message)
    elif hasattr(message, 'content') and message.content == "/register":
        await handle_register(message)
    elif hasattr(message, 'content') and message.content.startswith("/chatid"):
        await handle_show_chatid(message)
    else:
        await handle_unknown(message)


async def handle_start(message: Message):
    """نمایش پیام خوش‌آمدگویی"""
    chat_id = message.chat.id
    
    welcome_text = (
        "🌟 **به ربات ارسال پیام انبوه Bale خوش آمدید!**\n\n"
        f"🆔 **Chat ID شما:** `{chat_id}`\n\n"
        "🚀 **قابلیت‌های ربات:**\n"
        "• مدیریت مخاطبین (ذخیره، حذف، ویرایش)\n"
        "• ارسال پیام انبوه به صورت گروهی\n"
        "• پشتیبانی از متن، عکس، ویدیو و فایل\n"
        "• آپلود لیست مخاطبین از فایل\n"
        "• آمار و گزارشات ارسال\n\n"
        "⚠️ **نکته مهم:**\n"
        "برای ارسال پیام به یک شماره، آن شخص باید:\n"
        "1. ربات را استارت کرده باشد\n"
        "2. دستور /register را زده باشد\n"
        "3. یا chat_id خود را با شما به اشتراک بگذارد\n\n"
        "📱 از منوی زیر استفاده کنید:"
    )
    await message.reply(welcome_text, components=KeyboardBuilder.main_menu())


async def handle_register(message: Message):
    """ثبت‌نام کاربر با دستور /register"""
    chat_id = message.chat.id
    username = getattr(message.from_id, 'username', 'Unknown')
    first_name = getattr(message.from_id, 'first_name', 'Unknown')
    
    # اینجا می‌تونیم شماره رو از کاربر بپرسیم
    await message.reply(
        f"✅ **اطلاعات شما ثبت شد!**\n\n"
        f"🆔 Chat ID: `{chat_id}`\n"
        f"👤 نام: {first_name}\n"
        f"📝 Username: @{username}\n\n"
        "📱 حالا شماره تلفن خود را وارد کنید\n"
        "(فقط شماره 11 رقمی مثل 09123456789):",
        components=KeyboardBuilder.back_button()
    )
    
    user_temp_data[chat_id] = {"state": "waiting_chat_id"}


async def handle_chat_id_input(message: Message):
    """ذخیره chat_id کاربر با شماره تلفن"""
    chat_id = message.chat.id
    content = message.content.strip() if hasattr(message, 'content') else ""
    
    phone = re.sub(r'[^\d]', '', content)
    
    if phone.startswith('09') and len(phone) == 11:
        db.save_user_chat_id(phone, str(chat_id))
        
        if chat_id in user_temp_data:
            del user_temp_data[chat_id]
        
        await message.reply(
            f"✅ **ثبت نام کامل شد!**\n\n"
            f"📱 شماره: {phone}\n"
            f"🆔 Chat ID: {chat_id}\n\n"
            "حالا دیگران می‌توانند به شما پیام ارسال کنند.",
            components=KeyboardBuilder.main_menu()
        )
    else:
        await message.reply(
            "❌ شماره نامعتبر! لطفاً یک شماره 11 رقمی وارد کنید.\n"
            "مثال: 09123456789",
            components=KeyboardBuilder.back_button()
        )


async def handle_show_chatid(message: Message):
    """نمایش chat_id به کاربر"""
    chat_id = message.chat.id
    await message.reply(
        f"🆔 **Chat ID شما:** `{chat_id}`\n\n"
        "این شناسه را برای دوستانتان بفرستید تا بتوانند به شما پیام دهند.\n"
        "یا از دستور /register استفاده کنید."
    )


async def handle_help(message: Message):
    help_text = (
        "❓ **راهنمای ربات**\n\n"
        "1️⃣ **برای دریافت پیام:**\n"
        "• دستور /register را بزنید\n"
        "• شماره تلفن خود را وارد کنید\n\n"
        "2️⃣ **برای ارسال پیام:**\n"
        "• مخاطبین را اضافه کنید\n"
        "• مخاطبین را انتخاب کنید\n"
        "• پیام خود را بفرستید\n\n"
        "3️⃣ **دستورات:**\n"
        "/start - شروع\n"
        "/register - ثبت نام برای دریافت پیام\n"
        "/chatid - نمایش chat_id\n"
        "/help - راهنما"
    )
    await message.reply(help_text, components=KeyboardBuilder.back_button())


async def handle_unknown(message: Message):
    await message.reply(
        "❓ متوجه نشدم! لطفاً از منو استفاده کنید یا /help را بزنید.",
        components=KeyboardBuilder.main_menu()
    )


async def handle_add_phone(message: Message):
    chat_id = message.chat.id
    content = message.content.strip() if hasattr(message, 'content') else ""
    
    phones = ContactManager.extract_phone_numbers(content)
    
    if phones:
        db.save_multiple_phones(chat_id, phones)
        
        # چک کردن کدوم شماره‌ها chat_id دارند
        registered = []
        not_registered = []
        
        for phone, _ in phones:
            if db.get_user_chat_id(phone):
                registered.append(phone)
            else:
                not_registered.append(phone)
        
        response = f"✅ {len(phones)} شماره ذخیره شد:\n"
        for phone, label in phones[:5]:
            status = "✅" if phone in registered else "⚠️"
            response += f"{status} {phone}"
            if label:
                response += f" - {label}"
            response += "\n"
        
        if not_registered:
            response += f"\n⚠️ {len(not_registered)} شماره هنوز ربات را استارت نکرده‌اند!\n"
            response += "از آنها بخواهید /register را بزنند."
    else:
        response = "❌ شماره معتبری یافت نشد!\nفرمت صحیح: 09123456789"
    
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]
    
    await message.reply(response, components=KeyboardBuilder.contacts_menu())


async def handle_contacts_file(message: Message):
    chat_id = message.chat.id
    
    if not hasattr(message, 'document'):
        await message.reply(
            "❌ لطفاً یک فایل ارسال کنید.",
            components=KeyboardBuilder.back_button("menu_contacts")
        )
        return
    
    status_msg = await message.reply("⏳ در حال پردازش فایل...")
    
    try:
        file_id = message.document.file_id
        response = requests.post(f"{BALE_API_URL}/getFile", json={"file_id": file_id}, timeout=30)
        result = response.json()
        
        if result.get('ok'):
            file_path = result['result']['file_path']
            file_url = f"https://tapi.bale.ai/file/bot{BOT_TOKEN}/{file_path}"
            content_response = requests.get(file_url, timeout=30)
            content = content_response.content.decode('utf-8', errors='ignore')
            
            phones = ContactManager.extract_phone_numbers(content)
            
            if phones:
                db.save_multiple_phones(chat_id, phones)
                
                registered = sum(1 for phone, _ in phones if db.get_user_chat_id(phone))
                
                text = f"✅ {len(phones)} مخاطب ذخیره شد!\n"
                text += f"✅ {registered} نفر ثبت‌نام کرده‌اند\n"
                text += f"⚠️ {len(phones) - registered} نفر ثبت‌نام نکرده‌اند"
                
                await status_msg.edit_text(text, components=KeyboardBuilder.contacts_menu())
            else:
                await status_msg.edit_text(
                    "❌ شماره معتبری یافت نشد!",
                    components=KeyboardBuilder.back_button("menu_contacts")
                )
        else:
            await status_msg.edit_text(
                "❌ خطا در دریافت فایل",
                components=KeyboardBuilder.back_button("menu_contacts")
            )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ خطا: {str(e)[:100]}",
            components=KeyboardBuilder.back_button("menu_contacts")
        )
    
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]


async def handle_manual_input(message: Message):
    chat_id = message.chat.id
    content = message.content.strip() if hasattr(message, 'content') else ""
    
    phones = ContactManager.extract_phone_numbers(content)
    
    if phones:
        phone_numbers = [phone for phone, _ in phones]
        user_temp_data[chat_id] = {
            "state": "waiting_media",
            "recipients": phone_numbers
        }
        
        await message.reply(
            f"✅ {len(phone_numbers)} شماره دریافت شد.\n\n"
            "📤 حالا پیام خود را ارسال کنید\n"
            "(متن، عکس، ویدیو یا فایل)",
            components=KeyboardBuilder.back_button("menu_send")
        )
    else:
        await message.reply(
            "❌ شماره معتبری یافت نشد!",
            components=KeyboardBuilder.back_button("menu_send")
        )


async def handle_file_for_send(message: Message):
    chat_id = message.chat.id
    
    if not hasattr(message, 'document'):
        await message.reply(
            "❌ لطفاً یک فایل ارسال کنید.",
            components=KeyboardBuilder.back_button("menu_send")
        )
        return
    
    status_msg = await message.reply("⏳ در حال پردازش فایل...")
    
    try:
        file_id = message.document.file_id
        response = requests.post(f"{BALE_API_URL}/getFile", json={"file_id": file_id}, timeout=30)
        result = response.json()
        
        if result.get('ok'):
            file_path = result['result']['file_path']
            file_url = f"https://tapi.bale.ai/file/bot{BOT_TOKEN}/{file_path}"
            content_response = requests.get(file_url, timeout=30)
            content = content_response.content.decode('utf-8', errors='ignore')
            
            phones = ContactManager.extract_phone_numbers(content)
            
            if phones:
                phone_numbers = [phone for phone, _ in phones]
                user_temp_data[chat_id] = {
                    "state": "waiting_media",
                    "recipients": phone_numbers
                }
                
                await status_msg.edit_text(
                    f"✅ {len(phone_numbers)} شماره استخراج شد.\n\n"
                    "📤 حالا پیام خود را ارسال کنید",
                    components=KeyboardBuilder.back_button("menu_send")
                )
            else:
                await status_msg.edit_text(
                    "❌ شماره معتبری یافت نشد!",
                    components=KeyboardBuilder.back_button("menu_send")
                )
        else:
            await status_msg.edit_text(
                "❌ خطا در دریافت فایل",
                components=KeyboardBuilder.back_button("menu_send")
            )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ خطا: {str(e)[:100]}",
            components=KeyboardBuilder.back_button("menu_send")
        )


async def handle_media_input(message: Message):
    chat_id = message.chat.id
    
    media_data = {}
    
    if hasattr(message, 'document') and message.document:
        media_data = {
            "type": "document",
            "file_id": message.document.file_id,
            "file_name": message.document.file_name or "فایل"
        }
    elif hasattr(message, 'photo') and message.photo:
        photo = message.photo[-1] if isinstance(message.photo, list) else message.photo
        media_data = {
            "type": "photo",
            "file_id": photo.file_id if hasattr(photo, 'file_id') else message.photo.file_id
        }
        if hasattr(message, 'content') and message.content:
            media_data["caption"] = message.content
    elif hasattr(message, 'video') and message.video:
        media_data = {
            "type": "video",
            "file_id": message.video.file_id
        }
        if hasattr(message, 'content') and message.content:
            media_data["caption"] = message.content
    elif hasattr(message, 'content') and message.content.strip():
        media_data = {
            "type": "text",
            "caption": message.content.strip()
        }
    
    if media_data:
        user_temp_data[chat_id]["media"] = media_data
        user_temp_data[chat_id]["state"] = "waiting_confirm"
        
        preview = f"📤 **پیش‌نمایش پیام**\n\n"
        preview += f"📌 نوع: {media_data.get('type', 'متن')}\n"
        preview += f"👥 گیرندگان: {len(user_temp_data[chat_id].get('recipients', []))} نفر\n"
        
        if media_data.get('caption'):
            preview += f"\n📝 متن پیام:\n{media_data['caption'][:200]}"
        
        preview += "\n\nبرای ارسال تایید کنید:"
        
        await message.reply(preview, components=KeyboardBuilder.confirm_send_keyboard())
    else:
        await message.reply(
            "❌ محتوای معتبری یافت نشد!",
            components=KeyboardBuilder.back_button("menu_send")
        )


# هندلر callback‌ها
@bot.event
async def on_callback(callback: Update):
    try:
        if not hasattr(callback, 'data'):
            return
        
        data = callback.data
        chat_id = callback.message.chat.id
        message_id = callback.message.message_id
        
        logger.info(f"🔘 کلیک: {data} | کاربر: {chat_id}")
        
        if data == "menu_main":
            await callback.message.reply("📌 منوی اصلی:", components=KeyboardBuilder.main_menu())
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "menu_contacts":
            await callback.message.reply("👥 مدیریت مخاطبین:", components=KeyboardBuilder.contacts_menu())
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "menu_send":
            await callback.message.reply("📤 انتخاب روش ارسال:", components=KeyboardBuilder.send_menu())
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "menu_stats":
            stats = db.get_stats(chat_id)
            text = (
                "📊 **آمار و گزارشات**\n\n"
                f"👥 کل مخاطبین: {stats['total_contacts']}\n"
                f"📤 تعداد ارسال‌ها: {stats['total_sends']}\n"
                f"📨 کل گیرندگان: {stats['total_recipients']}\n"
                f"✅ موفق: {stats['total_success']}\n"
                f"❌ ناموفق: {stats['total_failed']}"
            )
            await callback.message.reply(text, components=KeyboardBuilder.back_button())
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "menu_help":
            help_text = (
                "❓ **راهنما**\n\n"
                "/start - شروع\n"
                "/register - ثبت نام\n"
                "/chatid - نمایش chat_id\n\n"
                "⚠️ گیرندگان باید /register زده باشند"
            )
            await callback.message.reply(help_text, components=KeyboardBuilder.back_button())
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "add_phone":
            user_temp_data[chat_id] = {"state": "waiting_phone"}
            await callback.message.reply(
                "📱 شماره را وارد کنید:\n"
                "مثال: 09123456789\n"
                "با نام: 09123456789 علی محمدی\n\n"
                "⚠️ دوستانتان باید /register زده باشند",
                components=KeyboardBuilder.back_button("menu_contacts")
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "list_phones":
            phones = db.get_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "📋 لیست مخاطبین خالی است!",
                    components=KeyboardBuilder.contacts_menu()
                )
            else:
                text = f"📋 **مخاطبین شما ({len(phones)} عدد):**\n\n"
                for i, (_, number, label) in enumerate(phones[:50], 1):
                    status = "✅" if db.get_user_chat_id(number) else "⚠️"
                    text += f"{i}. {status} {number}"
                    if label:
                        text += f" - {label}"
                    text += "\n"
                
                text += "\n✅ = ثبت‌نام کرده | ⚠️ = ثبت‌نام نکرده"
                
                if len(phones) > 50:
                    text += f"\n... و {len(phones) - 50} مخاطب دیگر"
                
                await callback.message.reply(text, components=KeyboardBuilder.contacts_menu())
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "upload_contacts":
            user_temp_data[chat_id] = {"state": "waiting_contacts_file"}
            await callback.message.reply(
                "📁 فایل مخاطبین را ارسال کنید.\n\n"
                "فرمت پشتیبانی شده:\n"
                "• CSV (شماره,نام)\n"
                "• TXT (هر خط یک شماره)",
                components=KeyboardBuilder.back_button("menu_contacts")
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "delete_phones":
            phones = db.get_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "هیچ مخاطبی برای حذف وجود ندارد!",
                    components=KeyboardBuilder.contacts_menu()
                )
            else:
                keyboard = InlineKeyboardMarkup()
                for i, (phone_id, number, label) in enumerate(phones[:15]):
                    display = f"🗑️ {number}"
                    if label:
                        display += f" ({label[:15]})"
                    keyboard.add(
                        InlineKeyboardButton(text=display, callback_data=f"del_{phone_id}"),
                        row=i + 1
                    )
                keyboard.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_contacts"), row=16)
                
                await callback.message.reply(
                    f"برای حذف روی مخاطب کلیک کنید: ({len(phones)} مخاطب)",
                    components=keyboard
                )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "delete_all":
            count = len(db.get_phones(chat_id))
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="✅ بله، حذف همه", callback_data="confirm_delete_all"), row=1)
            keyboard.add(InlineKeyboardButton(text="❌ انصراف", callback_data="menu_contacts"), row=2)
            
            await callback.message.reply(
                f"⚠️ آیا از حذف {count} مخاطب مطمئن هستید؟\nاین عمل غیرقابل بازگشت است.",
                components=keyboard
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "confirm_delete_all":
            count = len(db.get_phones(chat_id))
            db.delete_all_phones(chat_id)
            await callback.message.reply(
                f"✅ {count} مخاطب حذف شدند.",
                components=KeyboardBuilder.contacts_menu()
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data.startswith("del_"):
            phone_id = int(data.replace("del_", ""))
            phone_number = db.get_phone_by_id(phone_id)
            db.delete_phone(phone_id)
            await callback.message.reply(
                f"✅ شماره {phone_number} حذف شد.",
                components=KeyboardBuilder.contacts_menu()
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "send_saved":
            phones = db.get_phones(chat_id)
            if not phones:
                await callback.message.reply(
                    "❌ هیچ مخاطبی ذخیره نشده!",
                    components=KeyboardBuilder.send_menu()
                )
            else:
                user_phone_selections[chat_id] = []
                sent_msg = await callback.message.reply(
                    f"📱 {len(phones)} مخاطب یافت شد.\n"
                    "مخاطبین مورد نظر را انتخاب کنید:\n"
                    "✅ = ثبت‌نام کرده | ⚠️ = ثبت‌نام نکرده",
                    components=KeyboardBuilder.phone_selection_keyboard(phones, [])
                )
                user_temp_data[chat_id] = {"state": "selecting", "selection_msg_id": sent_msg.message_id}
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "select_all":
            phones = db.get_phones(chat_id)
            user_phone_selections[chat_id] = [p[0] for p in phones]
            await update_selection_message(chat_id, phones, user_phone_selections[chat_id])
        
        elif data == "select_first_10":
            phones = db.get_phones(chat_id)
            user_phone_selections[chat_id] = [p[0] for p in phones[:10]]
            await update_selection_message(chat_id, phones, user_phone_selections[chat_id])
        
        elif data == "select_last_10":
            phones = db.get_phones(chat_id)
            user_phone_selections[chat_id] = [p[0] for p in phones[-10:]]
            await update_selection_message(chat_id, phones, user_phone_selections[chat_id])
        
        elif data == "clear_all":
            user_phone_selections[chat_id] = []
            phones = db.get_phones(chat_id)
            await update_selection_message(chat_id, phones, [])
        
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
            phones = db.get_phones(chat_id)
            await update_selection_message(chat_id, phones, selections)
        
        elif data == "confirm_send":
            selections = user_phone_selections.get(chat_id, [])
            
            if not selections:
                await callback.message.reply(
                    "❌ هیچ مخاطبی انتخاب نشده!",
                    components=KeyboardBuilder.back_button("menu_send")
                )
                return
            
            recipients = []
            not_registered = []
            
            for phone_id in selections:
                number = db.get_phone_by_id(phone_id)
                if number:
                    chat_id_found = db.get_user_chat_id(number)
                    if chat_id_found:
                        recipients.append(chat_id_found)  # ذخیره chat_id به جای شماره
                    else:
                        not_registered.append(number)
            
            if not_registered:
                warning = (
                    f"⚠️ {len(not_registered)} نفر ربات را استارت نکرده‌اند:\n"
                    + "\n".join(not_registered[:5])
                    + "\n\nاز آنها بخواهید /register را بزنند."
                )
                await callback.message.reply(warning)
            
            if not recipients:
                await callback.message.reply(
                    "❌ هیچ‌یک از مخاطبین انتخاب شده ربات را استارت نکرده‌اند!",
                    components=KeyboardBuilder.back_button("menu_send")
                )
                return
            
            user_temp_data[chat_id] = {
                "state": "waiting_media",
                "recipients": recipients,
                "selection_msg_id": user_temp_data.get(chat_id, {}).get("selection_msg_id")
            }
            
            await callback.message.reply(
                f"✅ {len(recipients)} مخاطب آماده ارسال.\n\n"
                "📤 حالا پیام خود را ارسال کنید.\n"
                "(متن، عکس، ویدیو یا فایل)",
                components=KeyboardBuilder.back_button("menu_send")
            )
        
        elif data == "confirm_send_final":
            await execute_send(callback)
        
        elif data == "send_file":
            user_temp_data[chat_id] = {"state": "waiting_file"}
            await callback.message.reply(
                "📁 فایل شماره‌ها را ارسال کنید.",
                components=KeyboardBuilder.back_button("menu_send")
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "send_manual":
            user_temp_data[chat_id] = {"state": "waiting_manual"}
            await callback.message.reply(
                "✍️ شماره‌ها را وارد کنید:\n"
                "(هر خط یک شماره)",
                components=KeyboardBuilder.back_button("menu_send")
            )
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
        
        elif data == "noop":
            pass
        
    except Exception as e:
        logger.error(f"❌ خطا در callback: {str(e)}", exc_info=True)


async def update_selection_message(chat_id: int, phones: List[Tuple], selections: List[int]):
    """به‌روزرسانی پیام انتخاب مخاطبین"""
    try:
        msg_data = user_temp_data.get(chat_id, {})
        msg_id = msg_data.get("selection_msg_id")
        
        if msg_id:
            url = f"{BALE_API_URL}/editMessageText"
            payload = {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": f"📱 {len(phones)} مخاطب | انتخاب شده: {len(selections)}\n"
                        "برای انتخاب/حذف روی مخاطبین کلیک کنید:\n"
                        "✅ = ثبت‌نام کرده | ⚠️ = ثبت‌نام نکرده",
                "reply_markup": KeyboardBuilder.phone_selection_keyboard(phones, selections).to_json()
            }
            
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی پیام: {e}")


async def execute_send(callback: Update):
    """اجرای ارسال پیام با استفاده از chat_id"""
    chat_id = callback.message.chat.id
    user_data = user_temp_data.get(chat_id, {})
    recipients = user_data.get("recipients", [])  # حالا اینها chat_id هستند
    media = user_data.get("media", {})
    
    if not recipients or not media:
        await callback.message.reply(
            "❌ اطلاعات ناقص است!",
            components=KeyboardBuilder.main_menu()
        )
        return
    
    logger.info(f"🚀 شروع ارسال به {len(recipients)} نفر (با chat_id)")
    logger.info(f"📝 محتوا: {json.dumps(media, indent=2, ensure_ascii=False)}")
    logger.info(f"👥 Chat ID ها: {recipients}")
    
    status_msg = await callback.message.reply(f"⏳ در حال ارسال به {len(recipients)} نفر...")
    
    success = 0
    failed = 0
    failed_details = []
    
    for i, recipient_chat_id in enumerate(recipients, 1):
        logger.info(f"📤 ارسال {i}/{len(recipients)} به chat_id: {recipient_chat_id}")
        
        ok, error = await MessageSender.send_media_to_user(
            recipient_chat_id,  # ارسال با chat_id عددی
            media.get("type", "text"),
            media.get("file_id"),
            media.get("caption", "")
        )
        
        if ok:
            success += 1
            logger.info(f"✅ ارسال موفق به {recipient_chat_id}")
        else:
            failed += 1
            failed_details.append(f"🆔 {recipient_chat_id}: {error}")
            logger.error(f"❌ خطا برای {recipient_chat_id}: {error}")
        
        # به‌روزرسانی وضعیت
        if i % 5 == 0 or i == len(recipients):
            try:
                progress_text = (
                    f"📤 پیشرفت: {i}/{len(recipients)}\n"
                    f"✅ موفق: {success}\n"
                    f"❌ ناموفق: {failed}"
                )
                
                url = f"{BALE_API_URL}/editMessageText"
                payload = {
                    "chat_id": chat_id,
                    "message_id": status_msg.message_id,
                    "text": progress_text
                }
                requests.post(url, json=payload, timeout=10)
            except Exception as e:
                logger.error(f"خطا در به‌روزرسانی وضعیت: {e}")
        
        await asyncio.sleep(0.5)
    
    # ذخیره در تاریخچه
    db.save_send_history(chat_id, len(recipients), success, failed)
    
    # پاک کردن داده‌های موقت
    if chat_id in user_temp_data:
        del user_temp_data[chat_id]
    if chat_id in user_phone_selections:
        del user_phone_selections[chat_id]
    
    # گزارش نهایی
    report = (
        f"📊 **گزارش ارسال**\n\n"
        f"👥 کل: {len(recipients)}\n"
        f"✅ موفق: {success}\n"
        f"❌ ناموفق: {failed}\n"
    )
    
    if failed_details:
        report += f"\n❌ **جزئیات خطاها:**\n"
        report += "\n".join(failed_details[:5])
    
    try:
        await bot.delete_message(chat_id, status_msg.message_id)
    except:
        pass
    
    await callback.message.reply(report, components=KeyboardBuilder.main_menu())


if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ربات ارسال پیام انبوه Bale")
    print("=" * 50)
    print("📝 دستورات:")
    print("  /start - شروع و مشاهده chat_id")
    print("  /register - ثبت نام (برای دریافت پیام)")
    print("  /chatid - نمایش chat_id")
    print("=" * 50)
    
    logger.info("🚀 ربات شروع به کار کرد")
    bot.run()