# Очистка старых PDF

Скрипт [../scripts/cleanup_pdfs.sh](../scripts/cleanup_pdfs.sh) удаляет PDF-файлы старше заданного числа дней.

- **Переменные:** `PDF_STORAGE_PATH` (каталог с PDF), `KEEP_PDF_DAYS` (по умолчанию 30).
- **Локально (без Docker):** из корня проекта:  
  `PDF_STORAGE_PATH=./shared/pdf_storage KEEP_PDF_DAYS=30 ./scripts/cleanup_pdfs.sh`

**На сервере с Docker:** PDF хранятся в volume `parser_pdf_storage`, смонтированном в контейнерах как `/data/pdfs`. Варианты:

1. Cron + разовый контейнер (рекомендуется):
   ```bash
   # Каждое воскресенье в 04:00 — удалить PDF старше 30 дней
   0 4 * * 0 docker run --rm -v parser_pdf_storage:/data alpine sh -c 'find /data -maxdepth 1 -type f -name "*.pdf" -mtime +30 -delete'
   ```

2. Либо смонтировать volume в хост (если настроено) и вызывать `cleanup_pdfs.sh` с `PDF_STORAGE_PATH`, указывающим на этот каталог.
