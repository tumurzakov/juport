# Juport - Jupyter Reports System

Система для автоматического запуска Jupyter ноутбуков по расписанию с генерацией отчетов в HTML и Excel форматах.

## Возможности

- 📊 **Автоматическое выполнение ноутбуков** по расписанию (cron)
- 📈 **Генерация отчетов** в HTML и Excel форматах
- 🗂️ **Управление артефактами** - автоматическое сохранение и скачивание файлов
- 🌐 **Веб-интерфейс** для просмотра отчетов и результатов
- 🔧 **REST API** для управления отчетами и расписаниями
- 🐳 **Docker поддержка** с Jupyter Lab sidecar
- 📅 **Планировщик задач** с поддержкой cron выражений
- 🔄 **Переменные окружения** для настройки ноутбуков
- 🎛️ **Colab параметры** - поддержка Google Colab-стиля параметров (`# @param`) с dropdown, slider и другими типами
- ⏰ **Управление расписаниями** - создание, редактирование и мониторинг расписаний
- 📊 **Мониторинг выполнений** - отслеживание статуса и истории запусков

## Архитектура

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Juport API    │    │  Jupyter Lab    │    │   MySQL DB      │
│   (Litestar)    │◄──►│   (Sidecar)     │    │   (Reports)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Web Interface  │    │   Notebooks     │    │   Scheduler     │
│   (Templates)   │    │   Execution     │    │   (Cron Jobs)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Быстрый старт

### 1. Клонирование и настройка

```bash
git clone <repository-url>
cd juport
```

### 2. Настройка окружения

```bash
# Копируем файл конфигурации
cp env.example .env

# Редактируем настройки
nano .env
```

### 3. Запуск с Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Инициализация базы данных
docker-compose exec juport python scripts/init_db.py

# Настройка директорий
docker-compose exec juport python scripts/setup_directories.py
```

### 4. Доступ к сервисам

- **Juport Web Interface**: http://localhost:8000
- **Jupyter Lab**: http://localhost:8888 (token: `jupyter-token`)
- **MySQL**: localhost:3306

## Конфигурация

### Переменные окружения

```bash
# База данных
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/juport

# Jupyter Lab
JUPYTER_NOTEBOOKS_PATH=/app/notebooks
JUPYTER_OUTPUT_PATH=/app/outputs

# Приложение
DEBUG=true
HOST=0.0.0.0
PORT=8000
SECRET_KEY=your-secret-key-here

# Планировщик
SCHEDULER_INTERVAL=60
```

### Структура проекта

```
juport/
├── app/                    # Основное приложение
│   ├── config.py          # Конфигурация
│   ├── database.py        # Настройки БД
│   ├── models.py          # Модели данных
│   ├── schemas.py         # Pydantic схемы
│   ├── scheduler.py       # Планировщик задач
│   ├── main.py           # Точка входа
│   ├── routes/           # API маршруты
│   │   ├── reports.py    # Управление отчетами
│   │   ├── notebooks.py  # Управление ноутбуками
│   │   ├── web.py        # Веб-интерфейс
│   │   └── files.py      # Скачивание файлов
│   └── services/         # Бизнес-логика
│       └── notebook_executor.py
├── templates/            # HTML шаблоны
├── notebooks/           # Jupyter ноутбуки
├── outputs/            # Результаты выполнения
├── examples/           # Примеры ноутбуков
├── scripts/            # Скрипты инициализации
├── alembic/           # Миграции БД
├── docker-compose.yml # Docker конфигурация
└── requirements.txt   # Python зависимости
```

## Использование

### Создание отчета

#### Переменные в ноутбуках

Juport поддерживает два способа определения переменных в ноутбуках:

##### 1. Переменные окружения (os.getenv)

```python
import os

# Простые переменные
api_url = os.getenv("API_URL", "https://api.example.com")
start_date = os.getenv("START_DATE", "2024-01-01")
period_days = int(os.getenv("PERIOD_DAYS", "30"))

# Переменные с описанием в комментариях
company_name = os.getenv("COMPANY_NAME", "Моя компания")  # Название компании для отчета
include_forecast = os.getenv("INCLUDE_FORECAST", "false").lower() == "true"  # Включить прогноз
```

##### 2. Colab параметры (# @param)

```python
# Текстовые поля
text = "value" # @param {type:"string"}
text_with_placeholder = "" # @param {type:"string", placeholder:"enter a value"}

# Числовые поля
number_input = 10.0 # @param {type:"number"}
integer_input = 10 # @param {type:"integer"}

# Boolean поля
boolean_checkbox = True # @param {type:"boolean"}
boolean_dropdown = True # @param ["False", "True"] {type:"raw"}

# Dropdown списки
dropdown = "1st option" # @param ["1st option", "2nd option", "3rd option"]
text_and_dropdown = "value" # @param ["1st option", "2nd option", "3rd option"] {allow-input: true}

# Range slider
number_slider = 0 # @param {type:"slider", min:-1, max:1, step:0.1}
integer_slider = 1 # @param {type:"slider", min:0, max:100, step:1}

# Поля даты
date_input = "2018-03-22" # @param {type:"date"}

# Raw поля (произвольные значения)
raw_input = None # @param {type:"raw"}
raw_dropdown = raw_input # @param [1, "raw_input", "False", "string"] {type:"raw"}
```

#### Через API

```bash
curl -X POST http://localhost:8000/api/reports \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Отчет по продажам",
    "description": "Еженедельный отчет по продажам",
    "notebook_path": "sales.ipynb",
    "is_active": true,
    "artifacts_config": {
      "files": [
        {
          "name": "sales_report_{execution_id}.xlsx",
          "type": "excel",
          "description": "Отчет по продажам"
        }
      ]
    },
    "variables": {
      "period_days": 7,
      "include_forecast": true
    }
  }'
```

#### Через веб-интерфейс

1. Откройте http://localhost:8000
2. Нажмите "Все отчеты" для просмотра доступных notebooks
3. Используйте кнопку "Запустить" для одноразового выполнения
4. Просматривайте результаты и скачивайте файлы

#### Прямое выполнение отчета

```bash
curl -X POST http://localhost:8000/api/reports/execute-direct \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Отчет по продажам",
    "notebook_path": "sales.ipynb",
    "variables": {
      "period_days": 7
    },
    "artifacts_config": {
      "files": [
        {
          "name": "sales_report.xlsx",
          "type": "excel"
        }
      ]
    }
  }'
```

### Написание ноутбука

#### Переменные окружения

Ноутбук получает переменные через переменные окружения:

```python
import os
import json

# Получение переменных
variables_str = os.getenv('JUPORT_VARIABLES', '{}')
variables = json.loads(variables_str)

# Получение конфигурации артефактов
artifacts_config_str = os.getenv('JUPORT_ARTIFACTS_CONFIG', '{}')
artifacts_config = json.loads(artifacts_config_str)

# Директория для сохранения результатов
output_dir = os.getenv('JUPORT_OUTPUT_DIR', './output')
execution_id = os.getenv('JUPORT_EXECUTION_ID', 'unknown')
```

#### Сохранение артефактов

```python
# Сохранение Excel файла
import pandas as pd

df = pd.DataFrame(data)
excel_path = f'{output_dir}/report_{execution_id}.xlsx'
df.to_excel(excel_path, index=False)

# Сохранение изображения
import matplotlib.pyplot as plt
plt.savefig(f'{output_dir}/chart_{execution_id}.png')
```

### Расписание (Cron)

Поддерживаются стандартные cron выражения:

- `0 9 1 * *` - 1-го числа каждого месяца в 9:00
- `0 8 * * 1` - Каждый понедельник в 8:00
- `0 */6 * * *` - Каждые 6 часов
- `0 0 * * 0` - Каждое воскресенье в полночь

## API Документация

### Отчеты

#### Получить список отчетов

```bash
GET /api/reports
```

#### Создать отчет

```bash
POST /api/reports
Content-Type: application/json

{
  "name": "Название отчета",
  "description": "Описание",
  "notebook_path": "path/to/notebook.ipynb",
  "is_active": true,
  "artifacts_config": {...},
  "variables": {...}
}
```

#### Запустить отчет вручную

```bash
POST /api/reports/{report_id}/execute
```

#### Выполнить отчет напрямую (без создания расписания)

```bash
POST /api/reports/execute-direct
Content-Type: application/json

{
  "name": "Название отчета",
  "notebook_path": "path/to/notebook.ipynb",
  "variables": {...},
  "artifacts_config": {...}
}
```

#### Получить выполнения отчета

```bash
GET /api/reports/{report_id}/executions
```

### Ноутбуки

#### Получить список ноутбуков

```bash
GET /api/notebooks
```

### Файлы

#### Скачать артефакт

```bash
GET /api/files/{file_path}
```

### Расписания

#### Получить список расписаний

```bash
GET /api/schedules
```

#### Создать расписание

```bash
POST /api/schedules
Content-Type: application/json

{
  "name": "Ежедневный отчет",
  "description": "Ежедневный отчет по продажам",
  "report_id": 1,
  "cron_expression": "0 9 * * *",
  "timezone": "UTC",
  "is_active": true
}
```

#### Получить расписание

```bash
GET /api/schedules/{schedule_id}
```

#### Обновить расписание

```bash
PUT /api/schedules/{schedule_id}
Content-Type: application/json

{
  "name": "Обновленное расписание",
  "cron_expression": "0 8 * * *",
  "is_active": false
}
```

#### Удалить расписание

```bash
DELETE /api/schedules/{schedule_id}
```

#### Запустить расписание вручную

```bash
POST /api/schedules/{schedule_id}/execute
```

#### Переключить статус расписания

```bash
PUT /api/schedules/{schedule_id}/toggle
```

#### Получить выполнения расписания

```bash
GET /api/schedules/{schedule_id}/executions
```

#### Получить активные расписания

```bash
GET /api/schedules/active
```

#### Проверить cron выражение

```bash
POST /api/schedules/validate-cron
Content-Type: application/json

{
  "cron_expression": "0 9 * * *"
}
```

## Веб-интерфейс

### Главная страница (`/`)

- Список всех отчетов с расписанием
- Статус последних выполнений
- Возможность запуска отчетов вручную
- Ссылка на список всех доступных отчетов
- Ссылка на управление расписаниями

### Список отчетов (`/reports`)

- Все доступные Jupyter notebooks
- Информация о последнем выполнении
- Кнопка "Запустить" для одноразового выполнения
- Статус наличия результатов

### Просмотр результатов (`/view-report/{report_name}`)

- HTML версия последнего отчета
- Список всех прикрепленных файлов
- Возможность скачивания файлов
- Информация о времени выполнения

### Страница отчета (`/report/{report_id}`)

- Детальная информация об отчете
- История выполнений
- Просмотр результатов

### Страница выполнения (`/execution/{execution_id}`)

- HTML версия отчета
- Список артефактов для скачивания
- Логи выполнения

### Управление расписаниями (`/schedules`)

- Список всех расписаний
- Создание новых расписаний
- Редактирование существующих расписаний
- Включение/отключение расписаний
- Ручной запуск расписаний
- Просмотр истории выполнений

### Страница расписания (`/schedule/{schedule_id}`)

- Детальная информация о расписании
- История выполнений расписания
- Статистика выполнений
- Быстрые действия (запуск, остановка, удаление)

## Разработка

### Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка базы данных
python scripts/init_db.py

# Запуск приложения
python -m app.main
```

### Миграции базы данных

```bash
# Создание миграции
alembic revision --autogenerate -m "Description"

# Применение миграций
alembic upgrade head
```

### Тестирование

```bash
# Запуск тестов
pytest

# Запуск с покрытием
pytest --cov=app
```

## Мониторинг и логирование

### Логи

Приложение использует стандартное Python логирование:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Report execution started")
```

### Мониторинг

- Статус выполнения отчетов в веб-интерфейсе
- Логи выполнения в базе данных
- Метрики через API endpoints

## Аутентификация

### LDAP Аутентификация

Система поддерживает аутентификацию через LDAP. Если LDAP не настроен, доступ к системе открыт без пароля.

#### Настройка LDAP

Добавьте следующие переменные в `.env` файл:

```bash
# LDAP сервер
LDAP_SERVER=ldap.example.com
LDAP_PORT=389
LDAP_USE_SSL=false

# Базовая DN
LDAP_BASE_DN=dc=example,dc=com

# Шаблон DN пользователя (один из методов)
LDAP_USER_DN_TEMPLATE=uid={username},ou=users,dc=example,dc=com

# Или поиск пользователя (альтернативный метод)
LDAP_USER_SEARCH_BASE=ou=users,dc=example,dc=com
LDAP_USER_SEARCH_FILTER=(uid={username})

# Учетные данные для поиска (если нужны)
LDAP_BIND_DN=cn=admin,dc=example,dc=com
LDAP_BIND_PASSWORD=admin_password

# Поиск групп пользователя (опционально)
LDAP_GROUP_SEARCH_BASE=ou=groups,dc=example,dc=com
LDAP_GROUP_SEARCH_FILTER=(member={user_dn})
```

#### Методы аутентификации

**Метод 1: Прямая привязка (Direct Bind)**
```bash
LDAP_USER_DN_TEMPLATE=uid={username},ou=users,dc=example,dc=com
```

**Метод 2: Поиск и привязка (Search and Bind)**
```bash
LDAP_USER_SEARCH_BASE=ou=users,dc=example,dc=com
LDAP_USER_SEARCH_FILTER=(uid={username})
LDAP_BIND_DN=cn=admin,dc=example,dc=com
LDAP_BIND_PASSWORD=admin_password
```

#### Без LDAP

Если переменные LDAP не настроены, система работает без аутентификации - любой пользователь может получить доступ.

## Безопасность

### Рекомендации

1. **Секретные ключи**: Используйте сильные секретные ключи
2. **База данных**: Ограничьте доступ к MySQL
3. **Файлы**: Проверяйте пути к файлам на directory traversal
4. **CORS**: Настройте CORS для продакшена
5. **LDAP**: Настройте LDAP аутентификацию для продакшена

### Переменные окружения

```bash
# Продакшен настройки
DEBUG=false
SECRET_KEY=your-very-secure-secret-key
DATABASE_URL=mysql+aiomysql://user:password@db:3306/juport
```

## Troubleshooting

### Частые проблемы

#### Ноутбук не выполняется

1. Проверьте путь к ноутбуку
2. Убедитесь, что ноутбук находится в `JUPYTER_NOTEBOOKS_PATH`
3. Проверьте логи выполнения

#### Ошибки базы данных

1. Проверьте подключение к MySQL
2. Убедитесь, что база данных создана
3. Проверьте права пользователя

#### Файлы не сохраняются

1. Проверьте права на запись в `JUPYTER_OUTPUT_PATH`
2. Убедитесь, что директория существует
3. Проверьте конфигурацию артефактов

### Логи

```bash
# Просмотр логов Docker
docker-compose logs juport

# Просмотр логов планировщика
docker-compose exec juport tail -f /var/log/juport.log
```

## Лицензия

MIT License

## Поддержка

Для вопросов и предложений создавайте issues в репозитории.

## Changelog

### v1.8.0

- **Поддержка Colab параметров**: Добавлено сканирование и поддержка Google Colab-стиля параметров (`# @param`)
- **Расширенные типы полей**: Поддержка dropdown, range slider, placeholder и других типов из Colab
- **Умный парсинг**: Автоматическое извлечение опций для dropdown и конфигураций для slider
- **Улучшенный UX**: Динамическое создание полей ввода на основе Colab аннотаций
- **Обратная совместимость**: Полная поддержка как `os.getenv()` так и Colab `@param` аннотаций
- **Поддерживаемые типы Colab**:
  - `text` - текстовые поля с placeholder
  - `number`/`integer` - числовые поля
  - `boolean` - чекбоксы и dropdown для boolean
  - `date` - поля выбора даты
  - `slider` - range slider с настройками min/max/step
  - `dropdown` - выпадающие списки с опциями
  - `raw` - текстовые поля для произвольных значений
- **Новые возможности**:
  - Автоматическое определение типов полей из Colab аннотаций
  - Поддержка `allow-input` для dropdown с автодополнением
  - Placeholder для текстовых полей
  - Range slider с отображением текущего значения
  - Умное извлечение опций из Colab синтаксиса

### v1.7.1

- **Исправление передачи переменных**: Исправлена передача переменных в ноутбук через `JUPORT_VARIABLES`
- **Автоматическая загрузка переменных**: Ноутбуки теперь автоматически загружают переменные из `JUPORT_VARIABLES` в `os.environ`
- **Отладочная информация**: Добавлено сообщение о количестве загруженных переменных в начале выполнения
- **Полная интеграция**: Переменные из веб-интерфейса корректно передаются и используются в ноутбуках

### v1.7.0

- **Автоматическое сканирование переменных**: Система автоматически сканирует ноутбуки на предмет `os.getenv()` вызовов
- **Динамические поля ввода**: Найденные переменные отображаются как поля ввода в модальном окне запуска отчета
- **Умное определение типов**: Автоматическое определение типов переменных (text, number, boolean, date, email, url)
- **Извлечение описаний**: Система извлекает описания переменных из комментариев в коде
- **Новый API endpoint**: `/api/reports/{report_id}/variables` для получения переменных ноутбука
- **Обновленный notebook_executor**: Добавлен метод `scan_notebook_variables()` для сканирования переменных
- **Улучшенный UX**: Пользователи видят все необходимые переменные перед запуском отчета

### v1.6.0

- **Загрузка файлов при запуске отчета**: Добавлена возможность загрузки файлов в модальном окне подтверждения
- **Копирование файлов во временную папку**: Загруженные файлы автоматически копируются во временную папку выполнения отчета
- **Новый API endpoint**: `/api/reports/{report_id}/execute-with-file` для выполнения отчетов с файлами
- **Обновленный планировщик**: Добавлен метод `create_manual_task_with_file()` для создания задач с файлами
- **Улучшенный notebook_executor**: Добавлен метод `_copy_uploaded_files_to_temp_dir()` для копирования файлов
- **Обновленный worker**: Передача `task_id` в notebook_executor для корректной работы с файлами
- **Безопасность**: Файлы сохраняются с префиксом `task_{task_id}_` для изоляции между задачами

### v1.5.0

- **Модальное окно подтверждения запуска**: Добавлено модальное окно с подтверждением перед запуском отчета
- **Улучшенный UX**: Пользователь видит детали отчета перед запуском (название, путь к ноутбуку, ожидаемое время выполнения)
- **Предупреждения**: Информационные сообщения о времени выполнения и рекомендации не закрывать страницу
- **Двухэтапный процесс**: Сначала подтверждение, затем выполнение с индикатором прогресса
- **Обновленные шаблоны**: Модифицированы `templates/index.html` и `templates/report.html` для поддержки нового функционала
- **JavaScript улучшения**: Добавлены функции `showExecuteConfirmModal()` и `confirmExecute()` для управления модальными окнами
- **Обработка состояния**: Корректное управление состоянием кнопок и модальных окон

### v1.4.0

- **Улучшенная архитектура выполнения ноутбуков**: Полная реорганизация `notebook_executor` для работы с временными папками
- **Изоляция выполнения**: Каждый таск создает временную папку в системной временной директории
- **Безопасность**: Ноутбуки копируются в изолированную среду, исключая влияние на исходные файлы
- **Автоматическая очистка**: Временные папки полностью удаляются после завершения выполнения
- **Новая логика работы**:
  1. Создание временной папки в системной временной директории при старте таска
  2. Копирование ноутбука в временную папку с добавлением подавления предупреждений
  3. Запуск и рендеринг ноутбука в изолированной среде
  4. Сбор всех файлов кроме .ipynb из временной папки
  5. Прикрепление файлов к execution результату
  6. Полная очистка временной папки со всем содержимым
- **Улучшенная производительность**: Устранены конфликты при одновременном выполнении нескольких ноутбуков
- **Надежность**: Гарантированная очистка временных файлов даже при ошибках выполнения

### v1.3.0

- **Новая функциональность**: LDAP аутентификация с возможностью работы без пароля
- **Безопасность**: Добавлена система аутентификации с поддержкой LDAP
- **Гибкость**: Если LDAP не настроен, система работает без аутентификации
- **Новые компоненты**:
  - `app/services/auth.py` - сервис аутентификации с поддержкой LDAP
  - `app/middleware/auth.py` - middleware для проверки аутентификации
  - `app/routes/auth.py` - маршруты для входа и выхода
  - `templates/login.html` - страница входа
- **Конфигурация**: Добавлены переменные окружения для настройки LDAP
- **Методы аутентификации**: Поддержка прямого bind и search-and-bind методов
- **UI**: Добавлена кнопка выхода в навигации для аутентифицированных пользователей
- **Документация**: Обновлена документация с инструкциями по настройке LDAP

### v1.2.0

- **Новая функциональность**: Полноценное управление расписаниями
- **Новые модели данных**: Schedule и ScheduleExecution для разделения отчетов и расписаний
- **Новые API endpoints**: Полный набор API для управления расписаниями
- **Веб-интерфейс расписаний**: Страницы для создания, редактирования и мониторинга расписаний
- **Улучшенный планировщик**: Работа с новой моделью расписаний и отслеживание выполнений
- **Новые маршруты**:
  - `/schedules` - управление расписаниями
  - `/schedule/{schedule_id}` - детальная информация о расписании
  - `/api/schedules/*` - API для управления расписаниями
- **Мониторинг**: Отслеживание статуса выполнений, времени последнего и следующего запуска
- **Валидация**: Проверка cron выражений перед созданием расписаний
- **Миграции**: Добавлены таблицы для управления расписаниями

### v1.1.0

- **Новая функциональность**: Список всех доступных отчетов (notebooks) с возможностью одноразового запуска
- **Улучшенная архитектура**: Отдельные папки для каждого отчета в `outputs/reports/`
- **Автоматическая очистка**: Временные файлы автоматически удаляются после выполнения
- **Новые маршруты**:
  - `/reports` - список всех доступных отчетов
  - `/view-report/{report_name}` - просмотр результатов отчета
  - `/download/{report_name}/{filename}` - скачивание файлов отчета
  - `/api/reports/execute-direct` - прямое выполнение отчета без создания расписания
- **Улучшенный UI**: Кнопки для запуска отчетов, просмотр результатов с прикрепленными файлами
- **Безопасность**: Проверка путей файлов для предотвращения directory traversal атак
- **Исправления**: Исправлена ошибка инициализации контроллеров в Litestar

### v1.0.0

- Базовая функциональность
- Веб-интерфейс
- API для управления отчетами
- Планировщик задач
- Docker поддержка
- Интеграция с Jupyter Lab
