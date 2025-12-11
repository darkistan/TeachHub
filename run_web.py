"""
Скрипт запуску Flask веб-інтерфейсу для TeachHub
"""
from web_admin.app import app

if __name__ == '__main__':
    print("=" * 60)
    print("🌐 Запуск веб-інтерфейсу TeachHub Admin")
    print("=" * 60)
    print("\n📍 Адреса: http://127.0.0.1:5000")
    print("💡 Натисніть Ctrl+C для зупинки\n")
    
    app.run(host='127.0.0.1', port=5000, debug=True)



