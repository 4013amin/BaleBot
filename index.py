# import json
# import os
# from bale import Bot, Message
#
# BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
# DATA_FILE = "user_data.json"
#
# users_data = {}
#
# def load_data():
#     global users_data
#     if os.path.exists(DATA_FILE):
#         try:
#             with open(DATA_FILE, "r", encoding="utf-8") as f:
#                 users_data = json.load(f)
#                 print(f"Data loaded from file. Users: {list(users_data.keys())}")
#         except Exception as e:
#             print(f"Error loading JSON: {e}")
#             users_data = {}
#     else:
#         users_data = {}
#
# def save_data():
#     global users_data
#     try:
#         with open(DATA_FILE, "w", encoding="utf-8") as f:
#             json.dump(users_data, f, ensure_ascii=False, indent=4)
#     except Exception as e:
#         print(f"Error saving data: {e}")
#
# load_data()
#
# bot = Bot(token=BOT_TOKEN)
#
# def is_user_message(message):
#     sender = None
#     if hasattr(message, 'sender') and message.sender:
#         sender = message.sender
#     elif hasattr(message, 'from_user') and message.from_user:
#         sender = message.from_user
#
#     if sender:
#         if hasattr(sender, 'is_bot'):
#             return not sender.is_bot
#     return True
#
# @bot.event
# async def on_message(message: Message):
#     if not is_user_message(message):
#         return
#
#     raw_content = message.content if message.content else ""
#     content = raw_content.strip().lower()
#
#     user_id = None
#     if hasattr(message, 'sender') and message.sender:
#         user_id = message.sender.id
#     elif hasattr(message, 'from_user') and message.from_user:
#         user_id = message.from_user.id
#
#     if not user_id:
#         return
#
#     if user_id not in users_data:
#         users_data[user_id] = {"tasks": []}
#         save_data()
#
#     try:
#         if content == "/start":
#             await message.reply(
#                 "سلام! 👋\n"
#                 "دستورات:\n"
#                 "/add [متن]: افزودن کار جدید (مثال: /add خرید نان)\n"
#                 "/list: مشاهده لیست\n"
#                 "/del [شماره]: حذف کار (مثال: /del 1)"
#             )
#             return
#
#         elif content.startswith("/add "):
#             task_text = content.replace("/add ", "").strip()
#             if not task_text:
#                 await message.reply("❌ لطفاً متن کار را بنویسید.\nمثال: /add خرید نان")
#                 return
#
#             # اضافه کردن به دیکشنری در حافظه
#             users_data[user_id]["tasks"].append({"text": task_text, "done": False})
#
#             # ذخیره فوری روی دیسک
#             save_data()
#
#             await message.reply(f"✅ کار '{task_text}' اضافه شد.")
#
#         elif content == "/list":
#             # خواندن دوباره از فایل برای اطمینان از آخرین وضعیت (اختیاری اما امن)
#             # در اینجا چون از متغیر سراسری استفاده می‌کنیم و save_data را صدا زدیم،
#             # نیازی به ریلود نیست مگر اینکه بات کرش کرده و ریست شده باشد.
#             # برای اطمینان بیشتر، می‌توانیم چک کنیم که آیا داده‌ها در حافظه هستند یا نه.
#
#             # اگر به هر دلیلی دیکشنری خالی بود، دوباره از فایل لود کن
#             if not users_data or user_id not in users_data:
#                 load_data()
#
#             tasks = users_data[user_id]["tasks"]
#             if not tasks:
#                 await message.reply("📭 لیست شما خالی است.")
#                 return
#
#             msg = "📋 لیست کارها:\n\n"
#             for i, task in enumerate(tasks, 1):
#                 status = "✅ انجام شده" if task["done"] else "⬜ در انتظار"
#                 msg += f"{i}. {task['text']} - {status}\n"
#             await message.reply(msg)
#
#         elif content.startswith("/del "):
#             try:
#                 index = int(content.replace("/del ", "").strip()) - 1
#                 tasks = users_data[user_id]["tasks"]
#
#                 if 0 <= index < len(tasks):
#                     removed = tasks.pop(index)
#                     save_data()
#                     await message.reply(f"🗑️ کار '{removed['text']}' حذف شد.")
#                 else:
#                     await message.reply("❌ شماره نامعتبر است.")
#             except ValueError:
#                 await message.reply("❌ لطفاً یک عدد وارد کنید.")
#
#         else:
#             await message.reply("❌ دستور نامعتبر است. از /start برای راهنمایی استفاده کنید.")
#
#     except Exception as e:
#         print(f"Error: {e}")
#         await message.reply("❌ خطایی رخ داد.")
#
#
# if __name__ == "__main__":
#     print("Bot is running...")
#     try:
#         bot.run()
#     except KeyboardInterrupt:
#         print("Bot stopped.")