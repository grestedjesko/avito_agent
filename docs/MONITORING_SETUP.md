# Настройка мониторинга с Langfuse

## Быстрый старт

### 1. Запуск Langfuse

```bash
# Запустить Langfuse и PostgreSQL
docker-compose up -d

# Проверить статус
docker-compose ps
```

### 2. Создание проекта

1. Откройте http://localhost:3000
2. Создайте аккаунт и войдите
3. Создайте новый проект
4. Перейдите в **Settings → API Keys**
5. Скопируйте **Public Key** и **Secret Key**

### 3. Конфигурация

Создайте файл `.env` из `.env.example`:

```bash
cp .env.example .env
```

Заполните ключи Langfuse:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-ваш-ключ
LANGFUSE_SECRET_KEY=sk-lf-ваш-секретный-ключ
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_ENABLED=true
```

### 4. Запуск агента

```bash
python src/main.py --mode console
```

## Что отслеживается

- **Трейсы**: все LLM вызовы (classify_intent, generate_response, validation)
- **Метрики**: latency, token usage, стоимость запросов
- **Scores**: качество ответов, уверенность классификации
- **Логи**: структурированные логи с контекстом сессии
- **Узлы**: выполнение каждого узла графа агента

## Dashboard

После выполнения запросов откройте Langfuse UI:

- **Traces**: детальный просмотр каждого запроса
- **Sessions**: группировка по сессиям пользователей
- **Metrics**: графики токенов, латентности, стоимости
- **Scores**: оценки качества ответов

## Отключение мониторинга

```env
LANGFUSE_ENABLED=false
```

## Просмотр метрик в коде

```python
from src.observability.metrics import get_metrics_collector

metrics = get_metrics_collector()
summary = metrics.finish_conversation(session_id)
print(summary)
```

## Troubleshooting

**Langfuse не подключается**:
```bash
# Проверить логи
docker-compose logs langfuse-server

# Перезапустить
docker-compose restart
```

**Трейсы не появляются**: проверьте правильность ключей в `.env`

**Высокая нагрузка**: уменьшите `flush_at` в `langfuse_config.py`


