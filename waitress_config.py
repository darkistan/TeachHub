"""
Конфігурація Waitress WSGI сервера для TeachHub
"""
import os

# Базові налаштування
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 5000))

# Налаштування потоків та з'єднань
THREADS = int(os.getenv('WAITRESS_THREADS', 4))
CHANNEL_TIMEOUT = int(os.getenv('WAITRESS_CHANNEL_TIMEOUT', 120))
CLEANUP_INTERVAL = int(os.getenv('WAITRESS_CLEANUP_INTERVAL', 30))

# SSL налаштування (якщо використовується)
SSL_CERT_PATH = os.getenv('SSL_CERT_PATH', None)
SSL_KEY_PATH = os.getenv('SSL_KEY_PATH', None)

# Конфігурація для Waitress
WAITRESS_CONFIG = {
    'host': HOST,
    'port': PORT,
    'threads': THREADS,
    'channel_timeout': CHANNEL_TIMEOUT,
    'cleanup_interval': CLEANUP_INTERVAL,
    'asyncore_use_poll': True,
}

# Додаємо SSL якщо вказано
if SSL_CERT_PATH and SSL_KEY_PATH:
    WAITRESS_CONFIG['url_scheme'] = 'https'
    # Waitress не підтримує SSL напряму, потрібен reverse proxy
    # Але зберігаємо конфігурацію для майбутнього використання

