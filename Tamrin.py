import os
import json
from bale import Message , Bot

#Bot Data
token = Bot(token="1046992923:wz1DSSvbJizZp8EPgNWjSCVHoxtMMztsK9Q")


users = {}

FilePath = "user_data.json"

def _load_data_():
    global users
    if os.path.exists(FilePath):
        with open(FilePath ,"r" ,  encoding= 'utf-8') as f:
          users = json.load(f)
          print(f"Data loaded from file. Users: {list(users.keys())}")
          
          
_load_data_()

def __saveData__():
    global users
    if os.path.exists(FilePath):
        try:
            with open(FilePath , "w" , encoding="utf-8") as f :
                users = json.dump(FilePath , ensure_ascii=False )
        except Exception as e:
            print(f"Error saving data: {e}")



print("Current users data:", users)