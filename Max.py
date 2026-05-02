# import json
# import os
# from bale.bot import Bot, Message
#
# # توکن ربات خود را اینجا قرار دهید
# BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
# DATA_FILE = "user_data.json"
#
# # ایجاد آبجکت ربات
# bot = Bot(token=BOT_TOKEN)
# users_data = {}
#
#
# def load_data():
#     """داده‌های کاربران را از فایل JSON بارگذاری می‌کند."""
#     global users_data
#     if os.path.exists(DATA_FILE):
#         try:
#             with open(DATA_FILE, "r", encoding='utf-8') as f:
#                 data = json.load(f)
#                 users_data = data
#                 print(f"Data loaded successfully. Number of users: {len(users_data)}")
#         except json.JSONDecodeError:
#             print(f"Error decoding JSON from {DATA_FILE}. Starting with empty data.")
#             users_data = {}
#         except Exception as e:
#             print(f"An error occurred while loading data: {e}. Starting with empty data.")
#             users_data = {}
#     else:
#         print(f"Data file '{DATA_FILE}' not found. Starting with empty data.")
#         users_data = {}
#
#
# def save_data():
#     """داده‌های کاربران را در فایل JSON ذخیره می‌کند."""
#     global users_data
#     try:
#         with open(DATA_FILE, "w", encoding='utf-8') as f:
#             json.dump(users_data, f, ensure_ascii=False, indent=4)
#     except Exception as e:
#         print(f"An error occurred while saving data: {e}")
#
#
# # بارگذاری داده‌ها در ابتدای اجرای برنامه
# load_data()
#
#
# def get_user_state(user_id):
#     """اطلاعات وضعیت کاربر را برمی‌گرداند و اگر وجود نداشت، ایجاد می‌کند."""
#     if user_id not in users_data:
#         users_data[user_id] = {
#             "tasks": [],
#             "state": "idle",
#             "current_command": None
#         }
#         save_data()
#     return users_data[user_id]
#
#
# def create_inline_keyboard(buttons_data):
#     """
#     یک InlineKeyboardMarkup از لیست دکمه‌ها می‌سازد.
#     buttons_data: لیستی از لیست‌های دکمه. هر دکمه یک دیکشنری با کلید 'text' و 'callback_data' است.
#     """
#     inline_keyboard = []
#     for row in buttons_data:
#         keyboard_row = []
#         for btn in row:
#             # ساختار استاندارد InlineKeyboardButton
#             btn_obj = {
#                 'text': btn['text'],
#                 'callback_data': btn['callback_data']
#             }
#             keyboard_row.append(btn_obj)
#         inline_keyboard.append(keyboard_row)
#
#     return {
#         'inline_keyboard': inline_keyboard
#     }
#
#
# @bot.event
# async def on_message(message: Message):
#     """
#     این تابع زمانی که پیامی از کاربر دریافت می‌شود، فراخوانی می‌شود.
#     """
#     user_id = None
#     # دریافت user_id از from_user
#     if message.from_user:
#         if hasattr(message.from_user, 'id'):
#             user_id = message.from_user.id
#         else:
#             pass
#     if not user_id and message.sender_chat:
#         if hasattr(message.sender_chat, 'id'):
#             user_id = message.sender_chat.id
#     if not user_id:
#         return
#
#     # دریافت یا ایجاد وضعیت کاربر
#     user_info = get_user_state(user_id)
#     raw_content = message.content if message.content else ""
#     content = raw_content.strip().lower()
#
#     # تابع کمکی برای ارسال پیام
#     async def send_msg(text, reply_markup=None):
#         try:
#             # استفاده از bot.api.sendMessage به جای bot.sendMessage
#             await bot.api.sendMessage(
#                 chat_id=user_id,
#                 text=text,
#                 parse_mode='HTML',
#                 reply_markup=reply_markup
#             )
#         except Exception as e:
#             print(f"Error sending message: {e}")
#
#     # --- پردازش وضعیت‌های چندمرحله‌ای ---
#     if user_info["state"] == "waiting_for_task_text":
#         if raw_content:
#             task_id = len(user_info["tasks"]) + 1
#             user_info["tasks"].append({
#                 "id": task_id,
#                 "text": raw_content,
#                 "done": False
#             })
#             await send_msg(f"✅ کار '{raw_content}' با شناسه {task_id} اضافه شد.")
#             user_info["state"] = "idle"
#             user_info["current_command"] = None
#             save_data()
#         else:
#             await send_msg("❌ متن کار نمی‌تواند خالی باشد. لطفاً متن کار را ارسال کنید.")
#         return
#
#     if user_info["state"] == "waiting_for_task_id":
#         try:
#             task_id = int(raw_content)
#             tasks = user_info["tasks"]
#             found_task = None
#             for task in tasks:
#                 if task['id'] == task_id:
#                     found_task = task
#                     break
#             if not found_task:
#                 await send_msg(f"❌ کاری با شناسه {task_id} یافت نشد. لیست را با /list ببینید.")
#                 return
#             if user_info["current_command"] == "done":
#                 found_task['done'] = True
#                 await send_msg(f"✅ کار '{found_task['text']}' به عنوان انجام شده علامت زده شد.")
#             elif user_info["current_command"] == "delete":
#                 tasks.remove(found_task)
#                 # بازسازی IDها
#                 for i, t in enumerate(tasks):
#                     t['id'] = i + 1
#                 await send_msg(f"🗑 کار '{found_task['text']}' حذف شد.")
#             user_info["state"] = "idle"
#             user_info["current_command"] = None
#             save_data()
#         except ValueError:
#             await send_msg("❌ لطفاً یک عدد معتبر (شناسه کار) ارسال کنید.")
#         return
#
#     # --- پردازش دستور /start ---
#     if content == "/start":
#         welcome_message = (
#             "👋 درود بر شما!\n\n"
#             "به بازوی TODOList خوش آمدید.\n"
#             "من اینجا هستم تا به شما در مدیریت کارهایتان کمک کنم.\n\n"
#             "📜 **راهنمای استفاده:**\n"
#             "• `/add [متن کار]` : برای اضافه کردن یک کار جدید به لیست.\n"
#             "  _مثال:_ `/add خرید نان`\n\n"
#             "• `/list` : برای نمایش تمام کارهایی که باید انجام دهید.\n\n"
#             "• `/done [شماره کار]` : برای علامت زدن یک کار به عنوان انجام شده.\n"
#             "  _مثال:_ `/done 3`\n\n"
#             "• `/delete [شماره کار]` : برای حذف کامل یک کار از لیست.\n"
#             "  _مثال:_ `/delete 5`\n\n"
#             "• `/help` : نمایش مجدد این راهنما."
#         )
#
#         # تعریف دکمه‌ها به صورت دیکشنری
#         keyboard_buttons = [
#             [
#                 {'text': '➕ اضافه کردن کار', 'callback_data': 'add_task_prompt'},
#                 {'text': '📋 نمایش لیست', 'callback_data': 'list_tasks'}
#             ],
#             [
#                 {'text': '✅ انجام شد', 'callback_data': 'mark_done_prompt'},
#                 {'text': '🗑 حذف کار', 'callback_data': 'delete_task_prompt'}
#             ]
#         ]
#
#         # تبدیل به ساختار استاندارد API
#         reply_markup = create_inline_keyboard(keyboard_buttons)
#
#
#
#     # --- پردازش دستورات متنی ---
#     elif content.startswith("/add "):
#         task_text = raw_content.strip()[5:]
#         if task_text:
#             task_id = len(user_info["tasks"]) + 1
#             user_info["tasks"].append({
#                 "id": task_id,
#                 "text": task_text,
#                 "done": False
#             })
#             await send_msg(f"✅ کار '{task_text}' با شناسه {task_id} اضافه شد.")
#             save_data()
#         else:
#             await send_msg("لطفاً متن کار را بعد از دستور /add وارد کنید.\n*مثال:* `/add خرید شیر`")
#     elif content == "/list":
#         await send_task_list(user_id)
#     elif content == "/help":
#         await send_msg("برای دیدن راهنما، دستور /start را بفرستید.")
#     else:
#         if user_info["state"] == "idle":
#             await send_msg("من فقط دستورات خاصی را متوجه می‌شوم. برای راهنما /help را بفرستید.")
#
#
# async def send_task_list(user_id):
#     user_info = get_user_state(user_id)
#     if not user_info["tasks"]:
#         await bot.api.sendMessage(
#             chat_id=user_id,
#             text="📭 لیست کارهای شما خالی است. با دستور `/add` یا دکمه‌های زیر یک کار جدید اضافه کنید.",
#             parse_mode='HTML'
#         )
#         return
#     message_text = "📋 **لیست کارهای شما:**\n\n"
#     for task in user_info["tasks"]:
#         status = "✅" if task['done'] else "⬜"
#         message_text += f"{task['id']}. {status} {task['text']}\n"
#     await bot.api.sendMessage(
#         chat_id=user_id,
#         text=message_text,
#         parse_mode='HTML'
#     )
#
#
# @bot.event
# async def on_callback_query(callback_query):
#     """
#     مدیریت کلیک روی دکمه‌های Inline
#     """
#     try:
#         query = callback_query
#         callback_data = query.data
#         query_id = query.id
#         # پاسخ دادن به دکمه برای خارج کردن آن از حالت انتظار
#         await bot.answer_callback_query(callback_query_id=query_id)
#
#         # دریافت اطلاعات کاربر از callback_query
#         user = query.from_user
#         user_id = user.id if hasattr(user, 'id') else None
#         if not user_id:
#             return
#
#         user_info = get_user_state(user_id)
#
#         if callback_data == 'add_task_prompt':
#             user_info["state"] = "waiting_for_task_text"
#             user_info["current_command"] = "add"
#             save_data()
#             await bot.api.sendMessage(
#                 chat_id=user_id,
#                 text="📝 لطفاً متن کار جدید خود را ارسال کنید.",
#                 parse_mode='HTML'
#             )
#         elif callback_data == 'list_tasks':
#             await send_task_list(user_id)
#         elif callback_data == 'mark_done_prompt':
#             await bot.api.sendMessage(
#                 chat_id=user_id,
#                 text="🔢 لطفاً شماره کاری که انجام شده را ارسال کنید.\n(برای مثال: 1 یا 2)",
#                 parse_mode='HTML'
#             )
#             user_info["state"] = "waiting_for_task_id"
#             user_info["current_command"] = "done"
#             save_data()
#         elif callback_data == 'delete_task_prompt':
#             await bot.api.sendMessage(
#                 chat_id=user_id,
#                 text="🔢 لطفاً شماره کاری که می‌خواهید حذف کنید را ارسال کنید.",
#                 parse_mode='HTML'
#             )
#             user_info["state"] = "waiting_for_task_id"
#             user_info["current_command"] = "delete"
#             save_data()
#     except Exception as e:
#         print(f"Error in callback: {e}")
#
#
# if __name__ == "__main__":
#     print("Bot is running...")
#     bot.run()