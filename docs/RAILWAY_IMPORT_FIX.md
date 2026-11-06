# MAQSAT — исправление ModuleNotFoundError: No module named 'app'

В старой сборке Railway выполнение `alembic upgrade head` прерывалось при `from app.db import DATABASE_URL` в `migrations/env.py`. Путь `/srv` не был включён в путь импорта Python для CLI Alembic.

## Исправлено
- `Dockerfile`: `PYTHONPATH=/srv` в `ENV`.
- `Dockerfile`: `python -m alembic upgrade head` вместо `alembic upgrade head`.
- `backend/app/__init__.py`: пакет `app` оформлен явно.
- `README.md`: подсказка по повторному деплою.

## Применение в Railway
1. Замени старый код на исправленный, либо внеси изменения в Dockerfile вручную.
2. Выполни `git add .`, `git commit -m "Fix Alembic module imports on Railway"`, `git push`.
3. В Railway проверь **Root Directory** (`/` если в корне репозитория находится Dockerfile и папки frontend/backend) и способ сборки (Dockerfile). Если задан свой Start Command, удали его либо убедись, что он совместим с исправлениями.
4. Выполни Redeploy, чтобы Railway пересобрал образ из обновлённого коммита.
5. Убедись, что у сервиса заданы `DATABASE_URL` (ссылка на Railway PostgreSQL), `APP_SECRET`, `APP_ORIGIN` и `APP_ENV=production`.
6. После запуска проверь `https://<домен>/healthz`.

Эта ошибка может скрывать следующую проблему (например, неправильный DATABASE_URL). Если она появится после исправления, смотри новый traceback, не меняй значения переменных наугад.

## Локальная проверка
```bash
cd backend
python -m alembic upgrade head
python -m pytest -q
```

Локально миграции проверены на SQLite; реальный деплой Railway и PostgreSQL не выполнялись.
