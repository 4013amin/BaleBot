import json
import os
from bale.bot import Bot, Message

# توکن بات خود را اینجا قرار دهید
BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
DATA_FILE = "user_data.json"

# دیکشنری اصلی برای ذخیره داده‌ها
# ساختار: { user_id: { "tasks": { task_id: {"text": "...", "done": False} } } }
# از این ساختار استفاده می‌کنیم تا مدیریت آسان‌تر باشد
users_data = {}

def load_data():
    """بارگذاری داده‌ها از فایل JSON"""
    global users_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                users_data = json.load(f)
            print(f"Data loaded. Users: {list(users_data.keys())}")
        except Exception as e:
            print(f"Error loading JSON: {e}")
            users_data = {}
    else:
        users_data = {}

def save_data():
    """ذخیره داده‌ها در فایل JSON"""
    global users_data
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving data: {e}")

# بارگذاری اولیه داده‌ها
load_data()

bot = Bot(token=BOT_TOKEN)

def is_user_message(message):
    """بررسی اینکه آیا پیام از طرف یک کاربر واقعی (نه ربات) ارسال شده است"""
    sender = None
    if hasattr(message, 'sender') and message.sender:
        sender = message.sender
    elif hasattr(message, 'from_user') and message.from_user:
        sender = message.from_user
    
    if sender:
        if hasattr(sender, 'is_bot'):
            return not sender.is_bot
        return True
    return False

@bot.event
async def on_message(message: Message):
    if not is_user_message(message):
        return

    # دریافت شناسه کاربر
    user_id = None
    if hasattr(message, 'sender') and message.sender:
        user_id = message.sender.id
    elif hasattr(message, 'from_user') and message.from_user:
        user_id = message.from_user.id

    if not user_id:
        return

    # اطمینان از وجود رکورد برای کاربر
    if user_id not in users_data:
        users_data[user_id] = {"tasks": {}}
    
    # دریافت متن پیام
    raw_content = message.content if message.content else ""
    content = raw_content.strip().lower()

    # اگر پیام دکمه (callback) باشد، پردازش متفاوتی نیاز دارد
    # اما در Bale معمولاً دکمه‌ها به صورت جداگانه هندل می‌شوند یا در content می‌آیند
    # در اینجا فرض می‌کنیم کاربر دکمه را زده و پیام جدیدی ارسال می‌شود یا از callback_query استفاده می‌کنیم.
    # برای سادگی در این نسخه، از دکمه‌های Inline استفاده می‌کنیم که وقتی زده شوند، یک پیام callback ایجاد می‌کنند.
    
    # نکته مهم: در Bale، دکمه‌های Inline وقتی کلیک شوند، معمولاً به صورت یک پیام خاص یا callback پردازش می‌شوند.
    # برای سادگی، ما از دکمه‌هایی استفاده می‌کنیم که وقتی کلیک شوند، متن خاصی را به بات می‌فرستند یا از on_callback_query استفاده می‌کنیم.
    # اما Bale.py گاهی دکمه‌ها را به صورت متن معمولی پردازش نمی‌کند.
    # بیایید از رویکرد استاندارد استفاده کنیم: دکمه‌ها را ارسال می‌کنیم و برای کلیک روی آن‌ها، تابع جداگانه داریم.
    
    # اگر پیام دکمه نیست (یعنی متن معمولی است):
    if not hasattr(message, 'callback_query'):
        
        if content == "/start":
            await message.reply(
                "سلام! 👋\n"
                "به ربات لیست کارها خوش آمدید.\n\n"
                "دستورات:\n"
                "/add [متن کار]: افزودن کار جدید\n"
                "/list: مشاهده و مدیریت لیست\n"
                "/del [id]: حذف کار با شناسه\n"
                "/clear: پاک کردن همه کارها\n"
                "\n💡 نکته: در لیست کارها می‌توانید دکمه‌های 'انجام شد' و 'حذف' را بزنید."
            )
            return

        elif content.startswith("/add "):
            task_text = content.replace("/add ", "").strip()
            if not task_text:
                await message.reply("❌ لطفاً متن کار را بنویسید.\nمثال: /add خرید نان")
                return

            # تولید ID یکتا برای کار (زمان فعلی)
            import time
            task_id = str(int(time.time()))
            
            users_data[user_id]["tasks"][task_id] = {"text": task_text, "done": False}
            save_data()
            
            # بازگرداندن پیام موفقیت
            await message.reply(f"✅ کار '{task_text}' با شناسه {task_id} اضافه شد.")
            return

        elif content == "/list":
            tasks = users_data[user_id]["tasks"]
            if not tasks:
                await message.reply("📭 لیست شما خالی است.")
                return

            msg = "📋 لیست کارهای شما:\n\n"
            buttons = []
            
            for task_id, task in tasks.items():
                status = "✅ انجام شده" if task["done"] else "⬜ انجام نشده"
                msg += f"ID: {task_id}\n"
                msg += f"متن: {task['text']}\n"
                msg += f"وضعیت: {status}\n\n"
                
                # اضافه کردن دکمه‌های Inline برای هر کار
                # Bale از InlineButton استفاده می‌کند
                # دکمه انجام/انجام نشدن
                action_text = "انجام شد" if not task["done"] else "لغو انجام"
                buttons.append([
                    {
                        "text": action_text,
                        "callback_data": f"toggle_{task_id}"
                    },
                    {
                        "text": "حذف",
                        "callback_data": f"delete_{task_id}"
                    }
                ])

            # ارسال پیام همراه با دکمه‌ها
            # توجه: در Bale.py برای ارسال دکمه، از پارامتر reply_markup یا inline_keyboard استفاده می‌شود
            # اما Bale.py گاهی پیچیده است. بیایید از روش ساده‌تر استفاده کنیم:
            # ارسال متن و سپس دکمه‌ها
            
            # نکته: Bale.py استاندارد Inline Button را کمی متفاوت هندل می‌کند.
            # برای اطمینان، از روش زیر استفاده می‌کنیم:
            
            # اگر Bale.py شما از inline_keyboard پشتیبانی می‌کند:
            try:
                from bale.bot import InlineKeyboardMarkup, InlineKeyboardButton
                
                keyboard = []
                for task_id, task in tasks.items():
                    action_text = "انجام شد" if not task["done"] else "لغو انجام"
                    row = [
                        InlineKeyboardButton(text=action_text, callback_data=f"toggle_{task_id}"),
                        InlineKeyboardButton(text="حذف", callback_data=f"delete_{task_id}")
                    ]
                    keyboard.append(row)
                
                markup = InlineKeyboardMarkup(keyboard)
                await message.reply(msg, reply_markup=markup)
            except Exception as e:
                print(f"Error creating buttons: {e}")
                await message.reply(msg)
            
            return

        elif content.startswith("/del "):
            try:
                task_id = content.replace("/del ", "").strip()
                if task_id in users_data[user_id]["tasks"]:
                    removed = users_data[user_id]["tasks"].pop(task_id)
                    save_data()
                    await message.reply(f"🗑️ کار '{removed['text']}' حذف شد.")
                else:
                    await message.reply("❌ شناسه کار پیدا نشد.")
            except Exception as e:
                await message.reply("❌ خطایی رخ داد.")
            return

        elif content == "/clear":
            users_data[user_id]["tasks"] = {}
            save_data()
            await message.reply("🧹 همه کارها پاک شدند.")
            return

        else:
            await message.reply("❌ دستور نامعتبر است. از /start برای راهنمایی استفاده کنید.")

    else:
        # این بخش برای زمانی است که کاربر روی دکمه کلیک می‌کند (Callback Query)
        # در Bale.py، وقتی کاربر دکمه را می‌زند، پیامی با ویژگی callback_query ارسال می‌شود
        callback_data = message.callback_query
        if not callback_data:
            return
            
        # داده‌های دکمه
        data = callback_data
        # در Bale.py، callback_data معمولاً به صورت رشته است
        # ما باید تشخیص دهیم کدام دکمه زده شده
        
        # نکته: در Bale.py، وقتی دکمه کلیک می‌شود، message.callback_query مقدار True یا رشته داده را برمی‌گرداند
        # اما ساختار دقیق بسته به نسخه کتابخانه متفاوت است.
        # بیایید فرض کنیم message.content شامل داده‌ای است که ما در callback_data فرستادیم
        # یا بهتر، از رویه استاندارد Bale استفاده کنیم.
        
        # در Bale.py، وقتی دکمه کلیک می‌شود، message.content برابر با callback_data است
        # پس ما می‌توانیم message.content را چک کنیم اگر callback_query وجود دارد
        
        if message.content.startswith("toggle_"):
            task_id = message.content.replace("toggle_", "")
            if task_id in users_data[user_id]["tasks"]:
                users_data[user_id]["tasks"][task_id]["done"] = not users_data[user_id]["tasks"][task_id]["done"]
                save_data()
                await message.reply(f"✅ وضعیت کار به‌روز شد.")
            else:
                await message.reply("❌ خطا در به‌روزرسانی.")
                
        elif message.content.startswith("delete_"):
            task_id = message.content.replace("delete_", "")
            if task_id in users_data[user_id]["tasks"]:
                removed = users_data[user_id]["tasks"].pop(task_id)
                save_data()
                await message.reply(f"🗑️ کار '{removed['text']}' حذف شد.")
            else:
                await message.reply("❌ خطا در حذف.")
                

if __name__ == "__main__":
    print("Bot is running...")
    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot stopped.")