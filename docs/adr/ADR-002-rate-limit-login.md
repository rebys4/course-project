# ADR-002: Rate limiting для /auth/login (5/мин по IP)

## Context
NFR-05 требует защиту от перебора логина: после 5 попыток в минуту — HTTP 429. В STRIDE (P04) зафиксировано DoS/Bruteforce на /auth/login.

## Decision
- Добавляем эндпоинт `/auth/login` и in-memory лимитер: 5 попыток / 60 секунд на IP (берём X-Forwarded-For либо remote addr).
- При превышении лимита возвращаем 429 "Too Many Requests". Ответы не раскрывают, что именно неверно (минимизация утечек).

## Consequences
- Снижается риск перебора и ресурсного истощения.
- Для прода потребуется Redis/Ingress-лимитер — заведено в backlog.

## Links
- NFR-05, NFR-01; P04/STRIDE (D, S)
- Issue #14 (AuthN/AuthZ + RL)
