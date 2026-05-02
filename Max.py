# import json
# import os
# from bale import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton
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
#     global users_data
#     try:
#         with open(DATA_FILE, "w", encoding='utf-8') as f:
#             json.dump(users_data, f, ensure_ascii=False, indent=4)
#     except Exception as e:
#         print(f"An error occurred while saving data: {e}")
#
#
# load_data()
#
#
# def get_user_state(user_id):
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
# @bot.event
# async def on_message(message: Message):
#     if message.content == "/start":
#         keyboard = InlineKeyboardMarkup()
#         keyboard.add(
#             InlineKeyboardButton(text="این متن نمایش برای تست کردن دکمه ها است ", callback_data="done_1"),
#             row=1
#         )
#         keyboard.add(
#             InlineKeyboardButton(text="این متن نمایش برای تست کردن دکمه دومی ها است ", callback_data="done_2"),
#             row=2
#         )
#         await message.reply(
#             "🎯 این یک پیام تستی با دکمه است:\n\nروی دکمه‌ها کلیک کنید.",
#             components=keyboard
#         )
#         if message.content == "done_1":
#             await message.reply("👍 دکمه 'انجام شد' زده شد!")
#
#
# if __name__ == "__main__":
#     print("Bot is running...")
#     bot.run()
