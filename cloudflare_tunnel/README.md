# Cloudflare Tunnel - Автоматична налаштування

Ця директорія містить скрипти для автоматичної налаштування Cloudflare Tunnel на Windows Server.

## Що таке Cloudflare Tunnel?

Cloudflare Tunnel - це безпечний спосіб опублікувати ваш веб-інтерфейс в інтернет без необхідності:
- Відкривати порти в брандмауері
- Налаштовувати Port Forwarding на роутері
- Встановлювати SSL сертифікати на сервері

**Переваги:**
- ✅ Автоматичний SSL (HTTPS)
- ✅ Захист від DDoS
- ✅ Не потрібно відкривати порти
- ✅ Працює за NAT/файрволом
- ✅ Безкоштовно

## Передумови

1. **Cloudflare акаунт** з зареєстрованим доменом
2. **Адміністративні права** на Windows Server
3. **Домен** налаштований в Cloudflare (DNS записи)

## Швидкий старт

### Крок 1: Підготовка в Cloudflare Dashboard

1. Увійдіть в [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Виберіть ваш домен
3. Перейдіть в **Zero Trust** → **Networks** → **Tunnels**
4. Натисніть **Create a tunnel**
5. Виберіть **Cloudflared** (не Docker)
6. Скопіюйте **Tunnel Token** (потрібен для встановлення)

### Крок 2: Встановлення на сервері

1. Відкрийте PowerShell або CMD **як адміністратор**
2. Перейдіть в директорію проекту:
   ```batch
   cd D:\schedule_bot\cloudflare_tunnel
   ```
3. Запустіть скрипт встановлення:
   ```batch
   install_tunnel.bat
   ```
4. Введіть **Tunnel Token** з Cloudflare Dashboard
5. Введіть **домен** (наприклад: `teachhub.example.com`)
6. Введіть **локальний порт** (за замовчуванням: `5000`)

### Крок 3: Налаштування маршруту в Cloudflare

Після встановлення тунелю:

1. В Cloudflare Dashboard → **Zero Trust** → **Networks** → **Tunnels**
2. Виберіть ваш тунель
3. Натисніть **Configure** → **Public Hostname**
4. Додайте новий маршрут:
   - **Subdomain:** `teachhub` (або залиште порожнім для кореневого домену)
   - **Domain:** ваш домен
   - **Service:** `http://localhost:5000` (або ваш порт)
5. Натисніть **Save**

### Крок 4: Запуск тунелю

```batch
start_tunnel.bat
```

Або встановіть як службу Windows (автозапуск):

```batch
install_tunnel_service.bat
```

## Управління тунелем

### Запуск тунелю
```batch
start_tunnel.bat
```

### Зупинка тунелю
```batch
stop_tunnel.bat
```

### Перезапуск тунелю
```batch
restart_tunnel.bat
```

### Перегляд статусу
```batch
status_tunnel.bat
```

### Видалення тунелю
```batch
uninstall_tunnel.bat
```

## Структура файлів

- `install_tunnel.bat` - Основний скрипт встановлення
- `start_tunnel.bat` - Запуск тунелю
- `stop_tunnel.bat` - Зупинка тунелю
- `restart_tunnel.bat` - Перезапуск тунелю
- `status_tunnel.bat` - Перегляд статусу
- `uninstall_tunnel.bat` - Видалення тунелю
- `install_tunnel_service.bat` - Встановлення як служби Windows
- `uninstall_tunnel_service.bat` - Видалення служби
- `config.yaml` - Конфігураційний файл (створюється автоматично)

## Налаштування як служби Windows

Для автоматичного запуску тунелю при старті системи:

```batch
install_tunnel_service.bat
```

Служба буде називатися `CloudflareTunnel` та запускатиметься автоматично.

## Перевірка роботи

1. Перевірте статус тунелю:
   ```batch
   status_tunnel.bat
   ```

2. Відкрийте браузер та перейдіть на ваш домен:
   ```
   https://teachhub.example.com
   ```

3. Перевірте логи:
   ```
   cloudflare_tunnel\logs\cloudflared.log
   ```

## Усунення проблем

### Тунель не запускається

1. Перевірте, чи встановлений `cloudflared.exe`:
   ```batch
   dir cloudflared\cloudflared.exe
   ```

2. Перевірте конфігурацію:
   ```batch
   type config.yaml
   ```

3. Перевірте логи:
   ```batch
   type logs\cloudflared.log
   ```

### Помилка "Tunnel token is invalid"

1. Перевірте, чи правильно скопійовано токен з Cloudflare Dashboard
2. Перевстановіть тунель:
   ```batch
   uninstall_tunnel.bat
   install_tunnel.bat
   ```

### Домен не працює

1. Перевірте налаштування Public Hostname в Cloudflare Dashboard
2. Перевірте, чи працює локальний сервер:
   ```batch
   curl http://localhost:5000/health
   ```

## Додаткова інформація

- [Офіційна документація Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflare Zero Trust](https://www.cloudflare.com/products/zero-trust/)

