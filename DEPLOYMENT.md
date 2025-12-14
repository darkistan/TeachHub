# Інструкції з розгортання TeachHub на Windows Server

## Передумови

- Windows Server (будь-яка версія)
- Python 3.8+ встановлений
- Доступ до інтернету для встановлення залежностей
- Домен (опціонально, для SSL)
- Адміністративні права на сервері

## Крок 1: Підготовка середовища

### 1.1 Клонування репозиторію

```batch
git clone https://github.com/darkistan/TeachHub.git
cd TeachHub
```

### 1.2 Встановлення залежностей

```batch
setup.bat
```

Це створить віртуальне середовище та встановить всі необхідні пакети.

### 1.3 Налаштування конфігурації

Скопіюйте `config.env.example` в `config.env` та заповніть необхідні значення:

```batch
copy config.env.example config.env
```

**Генерація FLASK_SECRET_KEY:**

```batch
generate_secret_key.bat
```

Скопіюйте згенерований ключ та додайте його в `config.env`, потім відкрийте файл для редагування:

```batch
notepad config.env
```

**Обов'язкові змінні:**
- `TELEGRAM_BOT_TOKEN` - токен Telegram бота
- `FLASK_SECRET_KEY` - секретний ключ (згенеруйте через `generate_secret_key.bat` або `openssl rand -hex 32`)

**Для production:**
```env
FLASK_ENV=production
FLASK_DEBUG=False
HOST=0.0.0.0
PORT=5000
```

## Крок 2: Налаштування Windows Firewall

### 2.1 Відкриття портів через PowerShell (як адміністратор)

```powershell
# Дозволити HTTP (порт 80)
New-NetFirewallRule -DisplayName "TeachHub HTTP" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow

# Дозволити HTTPS (порт 443)
New-NetFirewallRule -DisplayName "TeachHub HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow

# Закрити порт 5000 для публічного доступу (якщо не використовується)
New-NetFirewallRule -DisplayName "Block Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Block
```

### 2.2 Альтернатива через GUI

1. Відкрийте "Брандмауэр Захисту Windows"
2. Натисніть "Додаткові параметри"
3. Виберіть "Правила для вхідних з'єднань" → "Створити правило"
4. Тип: Порт → TCP → Конкретні локальні порти: `80,443`
5. Дія: Дозволити з'єднання
6. Профіль: Всі
7. Ім'я: "TeachHub Web Access"

### 2.3 Обмеження доступу до RDP/SSH (рекомендовано)

Якщо використовуєте RDP, обмежте доступ тільки з ваших IP:

```powershell
# Дозволити RDP тільки з конкретного IP (замініть YOUR_IP)
New-NetFirewallRule -DisplayName "RDP from Office" -Direction Inbound -LocalPort 3389 -Protocol TCP -Action Allow -RemoteAddress YOUR_IP
```

## Крок 3: Налаштування SSL сертифікату

### Варіант 1: Win-ACME (рекомендовано для Windows)

1. Завантажте Win-ACME з https://www.win-acme.com/
2. Запустіть `wacs.exe`
3. Виберіть опцію для створення нового сертифікату
4. Виберіть ваш домен
5. Виберіть "Manual input" для введення шляхів до файлів
6. Вкажіть шляхи до сертифікату та ключа в `config.env`:
   ```env
   SSL_CERT_PATH=C:\path\to\cert.pem
   SSL_KEY_PATH=C:\path\to\key.pem
   ```

### Варіант 2: Cloudflare (найпростіше)

1. Зареєструйте домен в Cloudflare
2. Додайте ваш сервер як A-запис (IP адреса)
3. Увімкніть "Proxy" (помаранчева хмара)
4. Увімкніть "SSL/TLS" → "Full" або "Full (strict)"
5. Cloudflare автоматично надасть SSL сертифікат

**Переваги Cloudflare:**
- Автоматичний SSL
- Захист від DDoS
- Кешування статичних файлів
- Додатковий захист від брутфорсу

### Варіант 3: Cloudflare Tunnel (РЕКОМЕНДОВАНО - найбезпечніше)

**Cloudflare Tunnel** - це найбезпечніший спосіб опублікувати веб-інтерфейс без необхідності:
- Відкривати порти в брандмауері
- Налаштовувати Port Forwarding на роутері
- Встановлювати SSL сертифікати на сервері

**Переваги Cloudflare Tunnel:**
- ✅ Автоматичний SSL (HTTPS)
- ✅ Не потрібно відкривати порти
- ✅ Працює за NAT/файрволом
- ✅ Захист від DDoS
- ✅ Безкоштовно
- ✅ Найбезпечніший варіант

**Швидке встановлення:**

1. Перейдіть в директорію зі скриптами:
   ```batch
   cd cloudflare_tunnel
   ```

2. Запустіть встановлення (як адміністратор):
   ```batch
   install_tunnel.bat
   ```

3. Введіть дані:
   - Tunnel Token (з Cloudflare Dashboard → Zero Trust → Tunnels)
   - Домен (наприклад: `teachhub.example.com`)
   - Локальний порт (за замовчуванням: `5000`)

4. Налаштуйте Public Hostname в Cloudflare Dashboard:
   - Zero Trust → Networks → Tunnels → ваш тунель → Configure → Public Hostname
   - Subdomain: `teachhub` (або порожній для кореневого домену)
   - Service: `http://localhost:5000`

5. Запустіть тунель:
   ```batch
   start_tunnel.bat
   ```

   Або встановіть як службу Windows (автозапуск):
   ```batch
   install_tunnel_service.bat
   ```

**Детальні інструкції:** Дивіться `cloudflare_tunnel/README.md`

**Управління тунелем:**
- Запуск: `start_tunnel.bat`
- Зупинка: `stop_tunnel.bat`
- Перезапуск: `restart_tunnel.bat`
- Статус: `status_tunnel.bat`
- Видалення: `uninstall_tunnel.bat`

### Порівняння варіантів публікації

| Варіант | Складність | Безпека | Потрібні порти | SSL | Рекомендація |
|---------|------------|---------|----------------|-----|--------------|
| **Cloudflare Tunnel** | ⭐ Легко | ⭐⭐⭐⭐⭐ | ❌ Не потрібні | ✅ Автоматично | ✅ **Найкраще** |
| Cloudflare + Port Forwarding | ⭐⭐ Середньо | ⭐⭐⭐⭐ | ✅ 80, 443 | ✅ Автоматично | ✅ Добре |
| Прямий доступ (без Cloudflare) | ⭐⭐⭐ Складно | ⭐⭐ | ✅ 443 | ⚠️ Потрібен сертифікат | ⚠️ Не рекомендовано |

**Рекомендація:** Використовуйте **Cloudflare Tunnel** - це найбезпечніший та найпростіший варіант.

## Крок 4: Запуск у production режимі

### 4.1 Встановлення змінних середовища

```batch
set FLASK_ENV=production
set FLASK_DEBUG=False
set HOST=0.0.0.0
set PORT=5000
```

### 4.2 Запуск через Waitress

```batch
start_web.bat
```

Або безпосередньо:

```batch
venv\Scripts\python.exe run_web.py
```

### 4.3 Запуск як служба Windows (опціонально)

Створіть файл `teachhub_service.bat`:

```batch
@echo off
cd /d C:\path\to\TeachHub
set FLASK_ENV=production
set FLASK_DEBUG=False
set HOST=0.0.0.0
set PORT=5000
venv\Scripts\python.exe run_web.py
```

Використайте NSSM (Non-Sucking Service Manager) для створення служби:

1. Завантажте NSSM: https://nssm.cc/download
2. Розпакуйте та запустіть `nssm.exe install TeachHub`
3. Вкажіть шлях до `teachhub_service.bat` в "Path"
4. Встановіть "Startup type" як "Automatic"
5. Запустіть службу

## Крок 5: Моніторинг та логування

### 5.1 Health Check

Перевірте доступність через:

```batch
curl http://your-domain.com/health
```

Очікувана відповідь:
```json
{
  "status": "healthy",
  "timestamp": "2025-12-13T18:00:00",
  "environment": "production"
}
```

### 5.2 Перегляд логів

Логи зберігаються в:
- `logs.txt` - файл логів
- База даних - таблиця `logs`

### 5.3 Налаштування моніторингу

Використайте Windows Task Scheduler для регулярної перевірки:

1. Відкрийте "Планувальник завдань"
2. Створіть нове завдання
3. Тригер: щогодини
4. Дія: запуск програми
5. Програма: `powershell.exe`
6. Аргументи: `-Command "Invoke-WebRequest -Uri http://localhost:5000/health"`

## Крок 6: Резервне копіювання

### 6.1 Автоматичний backup

Створіть завдання в Task Scheduler для запуску `backup.bat` щодня:

```batch
backup.bat
```

Backup файли зберігаються в директорії `backups/`:
- `schedule_bot_backup_YYYYMMDD_HHMMSS.db` - база даних
- `config_backup_YYYYMMDD_HHMMSS.env` - конфігурація

### 6.2 Очищення старих backup

Скрипт автоматично видаляє backup старіше 30 днів.

### 6.3 Відновлення з backup

```batch
copy backups\schedule_bot_backup_YYYYMMDD_HHMMSS.db schedule_bot.db
copy backups\config_backup_YYYYMMDD_HHMMSS.env config.env
```

## Крок 7: Захист від брутфорсу

### 7.1 Rate Limiting

Rate limiting вже налаштований:
- `/login`: 5 спроб на хвилину
- `/api/*`: 30 запитів на хвилину

### 7.2 Cloudflare захист

Якщо використовуєте Cloudflare:
1. Увімкніть "Under Attack Mode" при підозрілих активностях
2. Налаштуйте "Rate Limiting Rules"
3. Увімкніть "Bot Fight Mode"

### 7.3 Windows Event Log моніторинг

Створіть PowerShell скрипт для моніторингу невдалих спроб входу:

```powershell
# monitor_failed_logins.ps1
$logs = Get-Content logs.txt | Select-String "Невдала спроба входу"
if ($logs.Count -gt 10) {
    # Відправити сповіщення адміністратору
    Write-Host "Попередження: багато невдалих спроб входу!"
}
```

## Крок 8: Оновлення

### 8.1 Оновлення коду

```batch
git pull origin main
venv\Scripts\pip.exe install -r requirements.txt
```

### 8.2 Перезапуск служби

Якщо використовується служба Windows:
```batch
net stop TeachHub
net start TeachHub
```

Або просто перезапустіть `start_web.bat`.

## Крок 9: Перевірка безпеки

### 9.1 Чек-лист безпеки

- [ ] `FLASK_SECRET_KEY` змінено з dev значення
- [ ] `FLASK_ENV=production`
- [ ] `FLASK_DEBUG=False`
- [ ] Windows Firewall налаштований (або використовується Cloudflare Tunnel)
- [ ] SSL сертифікат встановлено (або використовується Cloudflare Tunnel)
- [ ] Cloudflare Tunnel налаштовано (рекомендовано)
- [ ] Rate limiting працює
- [ ] Backup налаштовано
- [ ] Моніторинг налаштовано
- [ ] Пароль адміністратора змінено

### 9.2 Тестування

1. Перевірте доступ через HTTP та HTTPS
2. Перевірте rate limiting (спробуйте 6+ входів за хвилину)
3. Перевірте health check endpoint
4. Перевірте security headers через https://securityheaders.com/

## Усунення проблем

### Проблема: Порт зайнятий

```batch
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### Проблема: База даних заблокована

Перевірте логи на помилки "БД заблокована". Це нормально при високому навантаженні, але якщо часто - збільште `WAITRESS_THREADS`.

### Проблема: SSL не працює

- Перевірте що сертифікат не прострочений
- Перевірте що порт 443 відкритий в firewall (якщо не використовуєте Cloudflare Tunnel)
- Якщо використовуєте Cloudflare - перевірте налаштування SSL
- Якщо використовуєте Cloudflare Tunnel - перевірте статус тунелю: `cloudflare_tunnel\status_tunnel.bat`

## Додаткові ресурси

- [Waitress документація](https://docs.pylonsproject.org/projects/waitress/)
- [Flask-Limiter документація](https://flask-limiter.readthedocs.io/)
- [Win-ACME документація](https://www.win-acme.com/)
- [Cloudflare документація](https://developers.cloudflare.com/)
- [Cloudflare Tunnel документація](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflare Tunnel скрипти](cloudflare_tunnel/README.md) - детальні інструкції з встановлення

