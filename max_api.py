"""Минимальный клиент официального MAX Bot API."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import config


class MaxAPIError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class MaxAPI:
    """HTTP-клиент без привязки к VK или Telegram SDK."""

    def __init__(self, token: str | None = None, api_base: str | None = None):
        self.token = token or config.MAX_BOT_TOKEN
        self.api_base = (api_base or config.MAX_API_BASE_URL).rstrip('/')
        if not self.token:
            raise ValueError('Не задана переменная окружения MAX_BOT_TOKEN')

    def _request(self, path, method='GET', params=None, payload=None, timeout=30):
        url = self.api_base + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        headers = {'Authorization': self.token, 'Accept': 'application/json'}
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                error_body = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                error_body = {}
            code = error_body.get('code') if isinstance(error_body, dict) else None
            message = error_body.get('message') if isinstance(error_body, dict) else None
            message = message or f'MAX API вернул HTTP {exc.code}'
            raise MaxAPIError(str(message), status=exc.code, code=code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise MaxAPIError(f'Не удалось связаться с MAX API: {exc}') from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MaxAPIError('MAX API вернул некорректный JSON') from exc

    def get_updates(self, marker=None, timeout=60):
        params = {'timeout': min(max(int(timeout), 0), 90), 'types': 'message_created,bot_added,bot_started'}
        if marker is not None:
            params['marker'] = marker
        return self._request('/updates', params=params, timeout=95)

    def get_chat(self, chat_id):
        return self._request(f'/chats/{urllib.parse.quote(str(chat_id), safe="")}')

    def get_chat_admins(self, chat_id):
        return self._request(f'/chats/{urllib.parse.quote(str(chat_id), safe="")}/members/admins')

    def get_subscriptions(self):
        return self._request('/subscriptions')

    def set_commands(self):
        commands = [
            {'name': 'menu', 'description': 'Показать меню и варианты голосования'},
            {'name': 'paid', 'description': 'Выбрать питание платно'},
            {'name': 'free', 'description': 'Выбрать бесплатное питание'},
            {'name': 'no_meal', 'description': 'Сообщить, что не обедаете'},
            {'name': 'status', 'description': 'Проверить свой выбор на сегодня'},
            {'name': 'help', 'description': 'Справка по боту'},
            {'name': 'id', 'description': 'Показать MAX ID пользователя и чата'},
            {'name': 'bind_class', 'description': 'Привязать беседу к классу (администратор)'},
            {'name': 'register_teacher', 'description': 'Зарегистрировать учителя для класса'},
            {'name': 'report', 'description': 'Получить дневной отчёт'},
        ]
        return self._request('/me/commands', method='PATCH', payload={'commands': commands})

    def subscribe(self, url, secret):
        return self._request('/subscriptions', method='POST', payload={
            'url': url,
            'update_types': ['message_created', 'bot_added', 'bot_started'],
            'secret': secret,
        })

    def send_message(self, recipient_id, text, recipient_type='chat_id', attachments=None):
        if recipient_type not in {'chat_id', 'user_id'}:
            raise ValueError('recipient_type должен быть chat_id или user_id')
        payload = {'text': str(text)}
        if attachments:
            payload['attachments'] = attachments
        return self._request('/messages', method='POST', params={recipient_type: recipient_id}, payload=payload)

    def send_file(self, user_id, filename, file_bytes, caption=''):
        """Загружает файл и отправляет его в личный диалог пользователя."""
        upload_info = self._request('/uploads', method='POST', params={'type': 'file'})
        upload_url = upload_info.get('url')
        media_token = upload_info.get('token')
        if not upload_url or not media_token:
            raise MaxAPIError('MAX API не вернул URL и token для загрузки файла')

        safe_filename = os.path.basename(filename).replace('"', '_').replace('\r', '_').replace('\n', '_')
        boundary = '----MaxBot' + uuid.uuid4().hex
        body = b''.join((
            f'--{boundary}\r\n'.encode('ascii'),
            f'Content-Disposition: form-data; name="data"; filename="{safe_filename}"\r\n'.encode('utf-8'),
            b'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n',
            file_bytes,
            f'\r\n--{boundary}--\r\n'.encode('ascii'),
        ))
        # URL загрузки выдан MAX; токен бота на сторонний media-host не отправляем.
        upload_request = urllib.request.Request(
            upload_url,
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(upload_request, timeout=90) as response:
                response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise MaxAPIError(f'Не удалось загрузить файл в MAX: {exc}') from exc

        time.sleep(1)
        attachment = [{'type': 'file', 'payload': {'token': media_token}}]
        for attempt in range(3):
            try:
                return self.send_message(user_id, caption, recipient_type='user_id', attachments=attachment)
            except MaxAPIError as exc:
                if exc.code != 'attachment.not.ready' or attempt == 2:
                    raise
                time.sleep(1 + attempt * 2)

