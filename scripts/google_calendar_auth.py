#!/usr/bin/env python3
"""
Скрипт для получения refresh token для Google Calendar API.

Использование:
    python scripts/google_calendar_auth.py
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.integrations.calendar_client import GoogleCalendarClient
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import webbrowser
import threading
import os

# Конфигурация
REDIRECT_URI = "http://localhost:8080"
PORT = 8080

# Храним полученный код
received_code = None
received_state = None
server_should_stop = False


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Обработчик для OAuth callback."""
    
    def do_GET(self):
        global received_code, received_state, server_should_stop
        
        # Парсим URL
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        # Получаем код авторизации
        if 'code' in query_params:
            received_code = query_params['code'][0]
            if 'state' in query_params:
                received_state = query_params['state'][0]
            
            # Отправляем ответ
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = """
            <html>
            <head>
                <title>Авторизация успешна</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        max-width: 600px;
                        margin: 100px auto;
                        text-align: center;
                    }
                    .success {
                        color: #4CAF50;
                        font-size: 24px;
                        margin-bottom: 20px;
                    }
                </style>
            </head>
            <body>
                <div class="success">✅ Авторизация успешна!</div>
                <p>Можете закрыть это окно и вернуться в терминал.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
            # Останавливаем сервер
            server_should_stop = True
        
        elif 'error' in query_params:
            error = query_params['error'][0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""
            <html>
            <head>
                <title>Ошибка авторизации</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        max-width: 600px;
                        margin: 100px auto;
                        text-align: center;
                    }}
                    .error {{
                        color: #f44336;
                        font-size: 24px;
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="error">❌ Ошибка авторизации</div>
                <p>Ошибка: {error}</p>
                <p>Попробуйте снова запустить скрипт.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            server_should_stop = True
    
    def log_message(self, format, *args):
        # Отключаем логи сервера
        pass


def run_oauth_flow():
    """Запускает OAuth flow для получения refresh token."""
    
    # Проверяем наличие credentials.json
    credentials_file = project_root / "credentials.json"
    if not credentials_file.exists():
        print("❌ Ошибка: Файл credentials.json не найден!")
        print("\nШаги для получения credentials.json:")
        print("1. Перейдите в Google Cloud Console: https://console.cloud.google.com/")
        print("2. Создайте новый проект или выберите существующий")
        print("3. Включите Google Calendar API")
        print("4. Создайте OAuth 2.0 credentials (тип: Desktop app)")
        print("5. Скачайте credentials.json в корень проекта")
        print("\nПодробная инструкция: README.md")
        return None
    
    print("✅ Файл credentials.json найден")
    print("\n" + "="*60)
    print("🔐 Авторизация Google Calendar API")
    print("="*60)
    
    # Инициализируем клиента
    try:
        client = GoogleCalendarClient(credentials_file=str(credentials_file))
    except Exception as e:
        print(f"❌ Ошибка инициализации клиента: {e}")
        return None
    
    # Получаем URL для авторизации
    auth_url = client.get_auth_url(
        redirect_uri=REDIRECT_URI,
        state="calendar_auth"
    )
    
    print("\n📋 Шаги:")
    print("1. Сейчас откроется браузер с страницей авторизации Google")
    print("2. Выберите аккаунт и разрешите доступ к календарю")
    print("3. После авторизации вы будете перенаправлены обратно")
    print("4. Refresh token будет сохранен автоматически")
    
    input("\nНажмите Enter для продолжения...")
    
    # Запускаем локальный сервер для приема callback
    global received_code, server_should_stop
    received_code = None
    server_should_stop = False
    
    server = HTTPServer(('localhost', PORT), OAuthCallbackHandler)
    
    def run_server():
        while not server_should_stop:
            server.handle_request()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print(f"\n🌐 Локальный сервер запущен на {REDIRECT_URI}")
    print("🔗 Открываю браузер...")
    
    # Открываем браузер
    webbrowser.open(auth_url)
    
    # Ждем получения кода
    print("\n⏳ Ожидание авторизации...")
    server_thread.join(timeout=300)  # 5 минут
    
    if received_code is None:
        print("\n❌ Не удалось получить код авторизации")
        print("Попробуйте снова или проверьте настройки OAuth в Google Cloud Console")
        return None
    
    print("\n✅ Код авторизации получен")
    print("🔄 Обмен кода на токены...")
    
    # Обмениваем код на токены
    try:
        tokens = client.exchange_code_for_tokens(
            code=received_code,
            redirect_uri=REDIRECT_URI
        )
        
        refresh_token = tokens['refresh_token']
        
        print("\n" + "="*60)
        print("✅ Успешно получен refresh token!")
        print("="*60)
        print(f"\nRefresh Token:\n{refresh_token}")
        print("\n" + "="*60)
        
        # Сохраняем в .env
        env_file = project_root / ".env"
        
        if env_file.exists():
            # Читаем существующий .env
            with open(env_file, 'r') as f:
                lines = f.readlines()
            
            # Обновляем или добавляем GOOGLE_CALENDAR_REFRESH_TOKEN
            token_found = False
            for i, line in enumerate(lines):
                if line.startswith('GOOGLE_CALENDAR_REFRESH_TOKEN='):
                    lines[i] = f'GOOGLE_CALENDAR_REFRESH_TOKEN={refresh_token}\n'
                    token_found = True
                    break
            
            if not token_found:
                # Добавляем в конец файла
                if lines and not lines[-1].endswith('\n'):
                    lines.append('\n')
                lines.append(f'GOOGLE_CALENDAR_REFRESH_TOKEN={refresh_token}\n')
            
            # Записываем обновленный .env
            with open(env_file, 'w') as f:
                f.writelines(lines)
            
            print(f"\n💾 Токен сохранен в {env_file}")
        else:
            # Создаем новый .env
            with open(env_file, 'w') as f:
                f.write(f'GOOGLE_CALENDAR_REFRESH_TOKEN={refresh_token}\n')
            
            print(f"\n💾 Создан новый файл {env_file} с токеном")
        
        print("\n✅ Настройка завершена!")
        print("\n📝 Что дальше:")
        print("1. Токен уже сохранен в .env файле")
        print("2. Можете использовать интеграцию с Google Calendar")
        print("3. Пример использования см. в docs/calendar_quick_start.md")
        
        return refresh_token
        
    except Exception as e:
        print(f"\n❌ Ошибка при обмене кода на токены: {e}")
        return None


if __name__ == "__main__":
    print("\n🚀 Запуск процесса авторизации Google Calendar...\n")
    
    refresh_token = run_oauth_flow()
    
    if refresh_token:
        print("\n✨ Готово!")
    else:
        print("\n❌ Авторизация не завершена")
        sys.exit(1)
