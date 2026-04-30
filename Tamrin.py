import os
import json
from bale import Message, Bot

# Bot Data
bot = Bot(token="1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q")

users = {}

FilePath = "user_data.json"


def Load_data():
    global users
    if os.path.exists(FilePath):
        with open(FilePath, "r", encoding='utf-8') as f:
            users = json.load(f)
            print(f"Data loaded from file. Users: {list(users.keys())}")


users_data = Load_data()


def Save_data(data):
    global users
    if os.path.exists(FilePath):
        try:
            with open(FilePath, "w", encoding="utf-8") as f:
                users = json.dump(users, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving data: {e}")


print("Current users data:", users)


@bot.event
async def on_message(pm: Message):
    if pm.content == "/start":
        await pm.reply("سلام خیلی خوش اومدین ")
    else:
        user_id = str(pm.author.id)
        if user_id not in users:
            users[user_id] = {"messages": []}
        users[user_id]["messages"].append(pm.content)

        Save_data()

        await pm.reply("دیتایی که نوشتید به درستی ذخیره شد.")
        print(f"Saved message from user {user_id}. Total users: {len(users)}")


if __name__ == "__main__":
    print("Bot is running...")
    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot stopped.")