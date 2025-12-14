"""
Скрипт запуску Flask веб-інтерфейсу для TeachHub
"""
import os
from web_admin.app import app

if __name__ == '__main__':
    # Перевіряємо режим роботи з змінних середовища
    flask_env = os.getenv('FLASK_ENV', 'development')
    # Для development за замовчуванням debug=True, для production - False
    if flask_env == 'production':
        flask_debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    else:
        flask_debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 5000))
    
    # Якщо production режим - використовуємо Waitress
    if flask_env == 'production':
        from waitress import serve
        
        print("=" * 60)
        print("🌐 Запуск веб-інтерфейсу TeachHub Admin (Production)")
        print("=" * 60)
        print(f"\n📍 Адреса: http://{host}:{port}")
        print("💡 Натисніть Ctrl+C для зупинки\n")
        
        # Конфігурація Waitress для production
        serve(
            app,
            host=host,
            port=port,
            threads=4,
            channel_timeout=120,
            cleanup_interval=30,
            asyncore_use_poll=True
        )
    else:
        # Development режим - стандартний Flask сервер
        print("=" * 60)
        print("🌐 Запуск веб-інтерфейсу TeachHub Admin (Development)")
        print("=" * 60)
        print(f"\n📍 Адреса: http://{host}:{port}")
        print("💡 Натисніть Ctrl+C для зупинки\n")
        
        app.run(host=host, port=port, debug=flask_debug)



