// Service Worker для TeachHub PWA
const CACHE_NAME = 'teachhub-v1';
const SW_VERSION = '1.0.0';

// Подія install - виконується при встановленні service worker
self.addEventListener('install', function(event) {
    console.log('[Service Worker] Installing service worker version', SW_VERSION);
    // Вмикаємо service worker одразу після встановлення
    self.skipWaiting();
});

// Подія activate - виконується при активації service worker
self.addEventListener('activate', function(event) {
    console.log('[Service Worker] Activating service worker version', SW_VERSION);
    // Отримуємо контроль над всіма сторінками одразу
    event.waitUntil(clients.claim());
});

// Обробка повідомлень від клієнта
self.addEventListener('message', function(event) {
    console.log('[Service Worker] Received message:', event.data);
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

