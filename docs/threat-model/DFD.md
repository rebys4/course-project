# Data Flow Diagram (DFD) — Study Planner

## Область и допущения
- Клиент: браузер/мобильный клиент пользователя.
- API: FastAPI (Gateway) с эндпоинтами `/auth/*`, `/topics/*`.
- Auth Service: модуль/сервис аутентификации, выдающий JWT.
- Topics Service: обработка CRUD для тем (пока in-memory, позже Postgres).
- Topics Store: логическое хранилище тем (in-memory → Postgres).
- Monitoring/Logging: сбор метрик/логов (Prometheus/Trace).
- CI/CD & Secrets: пайплайн деплоя и хранилище секретов.

## Границы доверия
- **TB1**: Untrusted (Интернет, клиент пользователя).
- **TB2**: DMZ / API Gateway (публичная точка входа).
- **TB3**: App Network (внутренние сервисы и хранилища).
- **TB4**: CI/CD Boundary (инфраструктура сборки/развёртывания).

## Схема DFD

![Диаграмма DFD](./Диаграмма%20DFD.png)


## Легенда потоков
- **F1**: Запросы клиента к API по HTTPS (NFR-08).
- **F2**: Передача учётных данных на /auth/login.
- **F3**: Выдача/проверка JWT (TTL ≤ 1h, NFR-04).
- **F4**: Защищённые вызовы CRUD /topics с JWT; owner-only (код).
- **F4a**: Доступ к хранилищу тем (in-memory → Postgres).
- **F5/F5a**: Метрики (p95, uptime), логи с trace_id (NFR-01, NFR-02, NFR-06).
- **F6**/F6a: Деплой из CI/CD; секреты из secrets store, ротация ≤ 90д (NFR-07).

## Связь с NFR

- Шифрование каналов: NFR-08 (HTTPS + HSTS).
- Производительность и доступность: NFR-01, NFR-02.
- Пароли/аутентификация: NFR-03, NFR-04.
- Лимитирование входа: NFR-05.
- Логи с trace_id: NFR-06.
- Секреты и ротация: NFR-07.
