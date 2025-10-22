# ADR-003: Безопасные CSV-загрузки: лимит размера, magic bytes, quarantine (UUID)

## Context
Есть путь /topics/import. Нужны безопасные загрузки (из P03: лимиты размера/времени, проверка формата, безопасное имя, quarantine).

## Decision
- Принимаем CSV через multipart.
- Ограничение размера: 1 MiB (env CSV_MAX_BYTES).
- Простая проверка «похоже на CSV»: UTF-8/ASCII + наличие разделителей в первых KБ.
- Сохраняем файл в quarantine директорию (env QUARANTINE_DIR, default ./quarantine) под UUID+.csv.
- Возвращаем 202 Accepted с метаданными (stored_filename, size).

## Consequences
- Снижается риск RCE/zip-bomb/Path traversal до ETL-этапа.
- В следующих итерациях — антивирус/валидатор CSV.

## Links
- NFR-06 (аудит операций), NFR-01 (лимиты); P04/STRIDE (Tampering/Info Disclosure)
