Проект для хакатона Kita AI — ассистент для трека «AI-Code Review Assistant».

Для этого проекта мы взяли реальный банковский кейс из https://github.com/confluentinc/confluent-kafka-go/pull/1493, где MR был смержен.
Для этого мы сделали `git clone` репозитория, затем загрузили его в `gitlab`, создали новую ветку с коммитами из MR → создали новый MR и в итоге использовали наше решение, чтобы доказать его работоспособность.

Пример того, как наши агенты предоставили `Review` и `Suggestions` для MR:
<img width="937" height="801" alt="image" src="https://github.com/user-attachments/assets/9e4245e3-36fa-426f-8d53-1d1df776831e" />

И наконец, после того как джуниор исправил код на основе обратной связи от Kita AI, мы показываем, как наш бот меняет метку с `changes_requested` на `ready-for-merge`:
<img width="907" height="650" alt="image" src="https://github.com/user-attachments/assets/bacaef06-4609-47b9-9633-d76e047ad14e" />

Чтобы убедиться, что наша модель предоставляет качественные ревью и корректные предложения по коду, мы провели оценку модели с помощью нашего `Evaluation Pipeline`.

## Evaluation Pipeline

1. Сначала мы создали различные сценарии для оценки. Их можно посмотреть в папке: `evaluation_pipeline/benchmarks`
2. Затем пайплайн оценки на основе этих сценариев:
   - Автоматическая генерация тестовых сценариев (11, от простых к сложным) и юнит-тестов
   - Автоматическое создание MR
   - Использование блока обработки для анализа и предоставления предложений по коду
   - Автоматическое применение исправлений и мерж MR
   - Выполнение юнит-тестов до и после применения исправлений
   - Сравнение результатов и отправка отчёта на страницу MR

<img width="1048" height="588" alt="image" src="https://github.com/user-attachments/assets/3a460d08-7b6c-4f4a-bb18-5452c620f897" />


## Инструкция по установке

1. Склонируйте этот репозиторий
2. Установите зависимости:
```bash
pip install -r requirements.txt
```
3. Настройте переменные окружения:
```bash
cp .env.example .env
```

## Пайплайн нашего решения

<img width="504" height="568" alt="image" src="https://github.com/user-attachments/assets/32c4dab7-5c0c-42bf-b7f1-c6daba53b0f0" />

Как работает пайплайн:

1. Создаётся новый MR.
2. Наш **Senior Agent** получает `user_comments + diffs` → и предоставляет ревью с одной из 3 меток.
3. Наш **Suggestions Agent** получает `feedback_from_senior_agent + diffs` → и создаёт предложения по улучшению участков кода.
4. В конце всё отправляется через `GitLab API` в репозиторий.

### Инструкция по запуску:

Сначала необходимо подключить бота к репозиторию GitLab, а также убедиться, что переменные окружения указаны в файле .env.

1. Запустите вебхук-сервер для новых MR: `python real_world_case/1_webhook_for_new_mr.py`
2. Запустите вебхук-сервер для новых коммитов: `python real_world_case/2_webhook_for_new_commits.py`
3. Протестируйте создание нового MR: `python real_world_case/1_1_generation_of_new_MR.py`
4. Протестируйте создание нового коммита: `python real_world_case/commit_simulator_from_junior.py`

После этого вы сможете увидеть изменения в MR и коммитах в репозитории GitLab с меткой от бота Kita `ready-for-merge`.
<img width="907" height="650" alt="image" src="https://github.com/user-attachments/assets/bacaef06-4609-47b9-9633-d76e047ad14e" />
