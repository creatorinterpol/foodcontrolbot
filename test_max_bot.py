"""Локальные проверки MAX-бота без вызовов MAX API и без реальных данных."""
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

import config
import database
from bot_max import MaxCanteenBot, build_report, create_app, local_now
from max_api import MaxAPI


class FakeAPI:
    def __init__(self):
        self.messages = []
        self.files = []
        self.chat_admins = {}

    def send_message(self, recipient_id, text, recipient_type='chat_id', attachments=None):
        self.messages.append((str(recipient_id), text, recipient_type, attachments))
        return {}

    def send_file(self, user_id, filename, file_bytes, caption=''):
        self.files.append((str(user_id), filename, file_bytes, caption))
        return {}

    def get_chat(self, chat_id):
        return {'chat_id': chat_id, 'title': 'Класс 7А'}

    def get_chat_admins(self, chat_id):
        return {'members': self.chat_admins.get(str(chat_id), [])}


class FakeHTTPResponse:
    def __init__(self, body=b'{}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class MaxBotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = config.DATABASE_PATH
        config.DATABASE_PATH = self.temp.name + '/test.sqlite3'
        database.init_database()
        self.api = FakeAPI()
        self.bot = MaxCanteenBot(self.api, admin_ids=['101'])

    def tearDown(self):
        config.DATABASE_PATH = self.old_db_path
        self.temp.cleanup()

    @staticmethod
    def update(text, user_id='202', group_id='700', first='Иван', last='Иванов'):
        recipient = {'chat_id': group_id} if group_id else {'user_id': user_id}
        update = {
            'update_type': 'message_created',
            'message': {
                'sender': {'user_id': user_id, 'first_name': first, 'last_name': last},
                'recipient': recipient,
                'body': {'text': text},
            },
        }
        if group_id:
            update['chat_id'] = group_id
        return update

    def bind_group(self):
        self.bot.handle_update(self.update('/bind_class 7А', user_id='101'))

    def test_group_binding_requires_configured_admin(self):
        self.bot.handle_update(self.update('/bind_class 7А', user_id='999'))
        self.assertIsNone(database.max_get_group_class('700'))
        self.bot.handle_update(self.update('/bind_class 7А', user_id='101'))
        self.assertEqual(database.max_get_group_class('700'), '7А')

    def test_vote_uses_max_profile_name_and_updates_same_day(self):
        self.bind_group()
        self.bot.handle_update(self.update('/paid'))
        self.bot.handle_update(self.update('/free'))
        today = local_now().date().isoformat()
        votes = database.max_get_class_votes('7А', today)
        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0]['student_name'], 'Иван Иванов')
        self.assertEqual(votes[0]['status'], 'бесплатно')

    def test_unbound_group_does_not_save_votes(self):
        self.bot.handle_update(self.update('/paid'))
        self.assertEqual(database.max_get_class_votes('7А', local_now().date().isoformat()), [])

    def test_group_admin_can_register_teacher_in_direct_chat(self):
        self.bind_group()
        self.api.chat_admins['700'] = [{'user_id': '202'}]
        self.bot.handle_update(self.update('/register_teacher 7А', user_id='202', group_id=None))
        self.assertEqual(database.max_get_teacher('7А'), {'user_id': '202', 'teacher_name': 'Иван Иванов'})

    def test_only_current_teacher_or_global_admin_can_replace_assignment(self):
        database.max_register_teacher('7А', '202', 'Первый учитель')
        accepted = database.max_register_teacher('7А', '303', 'Другой учитель')
        self.assertFalse(accepted)
        accepted = database.max_register_teacher('7А', '303', 'Администратор', allow_replace=True)
        self.assertTrue(accepted)
        self.assertEqual(database.max_get_teacher('7А')['user_id'], '303')

    def test_excel_is_class_specific_and_sorted_by_category_then_name(self):
        votes = [
            {'student_name': 'Яковлев Я', 'status': 'не обедает'},
            {'student_name': 'Петров П', 'status': 'платно'},
            {'student_name': 'Алексеев А', 'status': 'платно'},
            {'student_name': 'Иванов И', 'status': 'бесплатно'},
        ]
        content, counts = build_report('7А', '2026-10-22', votes)
        from openpyxl import load_workbook
        sheet = load_workbook(BytesIO(content), read_only=True).active
        rows = list(sheet.values)
        self.assertEqual(counts, {'платно': 2, 'бесплатно': 1, 'не обедает': 1})
        self.assertEqual(rows[0], ('Питание класса 7А', '2026-10-22'))
        self.assertEqual(rows[7:], [
            ('Алексеев А', 'Платно'),
            ('Петров П', 'Платно'),
            ('Иванов И', 'Бесплатно'),
            ('Яковлев Я', 'Не обедает'),
        ])

    def test_old_votes_are_removed_but_today_is_kept(self):
        database.max_save_vote('7А', '202', 'Иван Иванов', 'платно', '2026-10-21')
        database.max_save_vote('7А', '303', 'Пётр Петров', 'бесплатно', '2026-10-22')
        database.max_clear_old_votes('2026-10-22')
        self.assertEqual(database.max_get_class_votes('7А', '2026-10-21'), [])
        self.assertEqual(len(database.max_get_class_votes('7А', '2026-10-22')), 1)

    def test_webhook_checks_max_secret_header(self):
        old_secret = config.MAX_WEBHOOK_SECRET
        config.MAX_WEBHOOK_SECRET = 'test-secret_123'
        try:
            client = create_app(self.bot).test_client()
            denied = client.post('/webhook', json={'update_type': 'bot_started'})
            accepted = client.post(
                '/webhook',
                json={'update_type': 'bot_started', 'user': {'user_id': 202}},
                headers={'X-Max-Bot-Api-Secret': 'test-secret_123'},
            )
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(accepted.status_code, 200)
        finally:
            config.MAX_WEBHOOK_SECRET = old_secret

    def test_api_uses_documented_host_authorization_and_upload_flow(self):
        api = MaxAPI(token='test-token', api_base='https://api.example.test')
        responses = [
            FakeHTTPResponse(b'{"url":"https://upload.example.test/file","token":"file-token"}'),
            FakeHTTPResponse(),
            FakeHTTPResponse(b'{}'),
        ]
        with patch('max_api.urllib.request.urlopen', side_effect=responses) as urlopen, patch('max_api.time.sleep'):
            api.send_file('202', 'report.xlsx', b'xlsx-bytes', caption='Daily report')

        upload_metadata_request = urlopen.call_args_list[0].args[0]
        self.assertEqual(upload_metadata_request.full_url, 'https://api.example.test/uploads?type=file')
        self.assertEqual(upload_metadata_request.get_header('Authorization'), 'test-token')
        media_upload_request = urlopen.call_args_list[1].args[0]
        self.assertIsNone(media_upload_request.get_header('Authorization'))
        self.assertIn(b'name="data"; filename="report.xlsx"', media_upload_request.data)
        send_request = urlopen.call_args_list[2].args[0]
        self.assertIn('user_id=202', send_request.full_url)
        message = __import__('json').loads(send_request.data.decode('utf-8'))
        self.assertEqual(message['attachments'][0]['payload']['token'], 'file-token')
        self.assertEqual(message['text'], 'Daily report')


if __name__ == '__main__':
    unittest.main()
