```gherkin
Feature: Performance and Security of Study Planner API

  Scenario: NFR-01 — Проверка времени ответа API
    Given сервис Study Planner запущен в production
    When клиент выполняет 1000 запросов GET /topics в секунду
    Then 95 процентиль времени ответа не превышает 200 миллисекунд

  Scenario: NFR-03 — Проверка параметров Argon2id
    Given новый пользователь регистрируется
    When пароль хэшируется
    Then алгоритм должен использовать Argon2id с памятью ≥ 64 MB и итерациями ≥ 3

  Scenario: NFR-04 — Проверка истечения JWT
    Given пользователь авторизован и получает токен
    When проходит 1 час
    Then токен становится недействительным при обращении к защищённому эндпоинту

  Scenario: NFR-05 — Проверка защиты от перебора пароля
    Given пользователь 5 раз вводит неправильный пароль
    When он делает 6-ю попытку
    Then сервер отвечает HTTP 429 "Too Many Requests"

  Scenario: NFR-08 — Проверка HTTPS-соединения
    Given клиент подключается к API
    When используется HTTP
    Then сервер перенаправляет на HTTPS и добавляет заголовок HSTS
```
