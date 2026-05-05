ResumePro AI 🎯
VK-бот на базе GigaChat, который адаптирует резюме под конкретную вакансию с hh.ru, генерирует сопроводительное письмо и возвращает оба документа пользователю в виде PDF-файлов прямо в VK.

Проект Школы 21.

Что умеет бот
Принимает резюме в формате PDF или DOCX
Парсит вакансию с hh.ru по ссылке
Адаптирует резюме под требования вакансии с помощью GigaChat
Генерирует сопроводительное письмо
Возвращает документы как PDF-вложения прямо в VK
Показывает Match Score (насколько резюме соответствует вакансии)
Параллельно генерирует резюме и письмо в режиме /оба
Команды
Команда	Действие
/старт	Приветствие и инструкция
/помощь	Справка по командам
/пример	Показать пример работы
/анализ	Детальный анализ соответствия вакансии
/письмо	Только сопроводительное письмо
/оба	Резюме + письмо одновременно
/статус	Текущее состояние сессии
/скачать	Повторно получить последние PDF-файлы
/сброс	Начать заново (очистить сессию)
Стек
Компонент	Технология
Язык	Python 3.11
Веб-фреймворк	Flask 3.x
VK API	vk-api 11.x
ИИ	GigaChat (Сбер) через LangChain
Парсинг вакансий	BeautifulSoup4 + requests
Чтение резюме	pypdf + python-docx
Генерация PDF	fpdf2 + DejaVuSans (кириллица)
Деплой	Railway (nixpacks)
Структура проекта
rezume-pro-bot/
├── main.py                  # Основная логика бота (Flask + VK Callback API)
├── Procfile                 # Точка входа для Railway
├── railway.toml             # Конфигурация деплоя Railway
├── requirements.txt         # Python-зависимости
│
├── config/
│   └── settings.py          # Загрузка переменных окружения
│
├── services/
│   └── resume_generator.py  # Генерация резюме и письма через GigaChat
│
├── prompts/
│   └── anti_hallucination.py  # Промпты с защитой от галлюцинаций
│
├── utils/
│   ├── pdf_generator.py     # Создание PDF с кириллицей (fpdf2)
│   ├── utils.py             # Парсинг hh.ru, извлечение текста из файлов
│   └── validation.py        # Валидация резюме, поиск навыков, ATS-скор
│
├── fonts/
│   └── DejaVuSans.ttf       # Шрифт с поддержкой кириллицы (обязателен!)
│
├── diagnostics/             # Утилиты для локальной отладки
└── tests/                   # Тесты на галлюцинации ИИ

Локальный запуск
1. Клонировать репозиторий
git clone https://github.com/RadaVega/rezume-pro-bot.git
cd rezume-pro-bot

2. Установить зависимости
pip install -r requirements.txt

3. Создать файл .env
VK_TOKEN=your_vk_group_token
VK_GROUP_ID=your_group_id
VK_CONFIRMATION_TOKEN=your_confirmation_token
GIGACHAT_API_KEY=your_gigachat_api_key

Токен GigaChat получить на developers.sber.ru

4. Запустить бота
python main.py

Бот поднимает Flask-сервер на порту 5000 и ждёт Callback-запросов от VK.

Деплой на Railway
1. Создать проект
Зайди на railway.app → New Project → Deploy from GitHub repo → выбери RadaVega/rezume-pro-bot.

Railway автоматически определит Procfile и соберёт проект через nixpacks.

2. Добавить переменные окружения
В разделе Variables добавь:

Переменная	Где взять
VK_TOKEN	VK → Управление группой → Работа с API
VK_GROUP_ID	ID твоей группы VK
VK_CONFIRMATION_TOKEN	VK → Настройки API → Callback API
GIGACHAT_API_KEY	developers.sber.ru
3. Получить публичный URL
Settings → Networking → Generate Domain → скопируй URL вида:

https://rezume-pro-bot-production.up.railway.app

4. Подключить к VK
В настройках группы VK → Управление → Настройки API → Callback API:

Версия API: 5.199
URL: https://your-railway-url.up.railway.app/webhook
Нажать Подтвердить — бот ответит автоматически ✅
Во вкладке Типы событий включить: Входящие сообщения.

Переменные окружения
Переменная	Обязательна	Описание
VK_TOKEN	✅	Токен доступа группы VK
VK_GROUP_ID	✅	ID группы VK (число)
VK_CONFIRMATION_TOKEN	✅	Строка подтверждения Callback API
GIGACHAT_API_KEY	✅	API-ключ GigaChat
PORT	—	Порт Flask (по умолчанию 5000)
Как работает сессия
Бот хранит состояние каждого пользователя в памяти (словарь). Сессия живёт 2 часа с момента последнего действия, после чего очищается автоматически.

Пользователь отправляет PDF/DOCX
    ↓
Бот извлекает текст резюме → сохраняет в сессию
    ↓
Пользователь отправляет ссылку hh.ru (или /оба)
    ↓
Бот парсит вакансию
    ↓
GigaChat адаптирует резюме + генерирует письмо (параллельно)
    ↓
PDF-файлы загружаются в VK Docs API
    ↓
Пользователь получает 2 вложения в чате

Шрифт (важно!)
Файл fonts/DejaVuSans.ttf обязателен для генерации PDF с кириллицей. Он уже включён в репозиторий.

Если нужно скачать вручную:

mkdir -p fonts
curl -L "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2" \
  | tar -xj --strip-components=2 -C fonts "dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf"

Лицензия
MIT