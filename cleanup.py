import os
import shutil

def cleanup_old_data():
    """Удалить старые файлы БД и начать с чистого листа"""
    
    # Удаляем старую БД если есть
    if os.path.exists("bot_database.db"):
        os.remove("bot_database.db")
        print("✅ Удалена старая БД bot_database.db")
    
    # Удаляем папку с БД групп для полного сброса
    if os.path.exists("databases"):
        response = input("Удалить все данные групп? (y/n): ")
        if response.lower() == 'y':
            shutil.rmtree("databases")
            print("✅ Удалены все данные групп")
        else:
            print("⏭️ Данные групп сохранены")
    
    print("✨ Готово к запуску!")

if __name__ == "__main__":
    cleanup_old_data()