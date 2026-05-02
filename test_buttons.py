# from bale import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton
#
# BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
# bot = Bot(token=BOT_TOKEN)
#
#
# @bot.event
# async def on_message(message: Message):
#     if not message.content:
#         return
#
#     content = message.content.strip().lower()
#
#     if content == "/start":
#         inline_keyboard = InlineKeyboardMarkup()
#
#         inline_keyboard.add(
#             InlineKeyboardButton(text="✅ انجام شد", callback_data="done_1"),
#             row=1
#         )
#         inline_keyboard.add(
#             InlineKeyboardButton(text="🗑️حذف", callback_data="delete_1"),
#             row=1
#         )
#
#         # اضافه کردن دکمه ردیف دوم
#         inline_keyboard.add(
#             InlineKeyboardButton(text="📋 لیست کامل", callback_data="list_all"),
#             row=2
#         )
#
#         await message.reply(
#             "🎯 این یک پیام تستی با دکمه است:\n\nروی دکمه‌ها کلیک کنید.",
#             components=inline_keyboard
#         )
#
#     # هندل کردن پاسخ دکمه‌ها
#     elif message.content and message.content.startswith(('done_1', 'delete_1', 'list_all')):
#         if message.content == "done_1":
#             await message.reply("👍 دکمه 'انجام شد' زده شد!")
#         elif message.content == "delete_1":
#             await message.reply("🗑️ دکمه 'حذف' زده شد!")
#         elif message.content == "list_all":
#             await message.reply("📋 در حال نمایش لیست...")
#
#
# if __name__ == "__main__":
#     print("Testing buttons...")
#     bot.run()