from bale import Bot, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQueryUpdate
import sqlite3
import asyncio

BOT_TOKEN = "1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q"
bot = Bot(token=BOT_TOKEN)

dbName = "test.db"


def showButton():
    keyboard = InlineKeyboardMarkup()
    
    btn1 = InlineKeyboardButton("This is Button Testi", callback_data="btn1")
    btn2 = InlineKeyboardButton("This is button Tow", callback_data="btn2")
    
    keyboard.add(btn1, row=1)
    keyboard.add(btn2, row=2)
    
    return keyboard
    

@bot.event
async def on_message(message: Message):
    if not message.content:
        return

    content = message.content.strip().lower()

    if content == "/start":
        
        await message.reply(
            "🎯 این یک پیام تستی با دکمه است:\n\nروی دکمه‌ها کلیک کنید.",
            components=showButton()
        )
        

@bot.event
async def on_callback_query(query: CallbackQueryUpdate):
    if query and query.data :
        callable_data = query.data
        
        await bot.answer_callback_query(query.id , "دکمه کلیک شد ! ")
        

if __name__ == "__main__":
    print("Testing buttons...")
    bot.run()
