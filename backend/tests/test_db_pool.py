import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from unittest.mock import Mock, patch

import httpx
import db_pool


class DatabasePoolTests(unittest.TestCase):
    def setUp(self):
        self.local_patch = patch.object(db_pool, '_local', local())
        self.local_patch.start()
        self.addCleanup(self.local_patch.stop)

    @patch.object(db_pool, 'create_client')
    @patch.object(db_pool.httpx, 'Client')
    def test_service_client_reused_only_in_its_own_thread(self, transport, create):
        create.side_effect = lambda *args, **kwargs: object()
        barrier = Barrier(2)
        def use():
            first = db_pool.service_client_for('https://test.supabase.co', 'key')
            barrier.wait(timeout=5)
            self.assertIs(first, db_pool.service_client_for('https://test.supabase.co', 'key'))
            return first
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: use(), range(2)))
        self.assertIsNot(first, second)
        self.assertEqual(create.call_count, 2)
        options = create.call_args.kwargs['options']
        self.assertFalse(options.auto_refresh_token)
        self.assertFalse(options.persist_session)

    @patch.object(db_pool, 'create_client')
    @patch.object(db_pool.httpx, 'Client')
    def test_changing_credentials_closes_previous_transport(self, transport, create):
        db_pool.service_client_for('https://test.supabase.co', 'first')
        old = transport.return_value
        db_pool.service_client_for('https://test.supabase.co', 'second')
        old.close.assert_called_once()

    def test_read_retries_a_transient_connection_failure(self):
        read = Mock(side_effect=[httpx.ConnectError('unavailable'), ['saved-row']])
        self.assertEqual(db_pool.read_with_retry(read), ['saved-row'])
        self.assertEqual(read.call_count, 2)

    def test_read_does_not_retry_schema_or_authorization_errors(self):
        read = Mock(side_effect=ValueError('database rejected query'))
        with self.assertRaises(ValueError):
            db_pool.read_with_retry(read)
        read.assert_called_once()

    def test_repeated_network_failure_is_not_hidden(self):
        read = Mock(side_effect=httpx.ReadTimeout('unavailable'))
        with self.assertRaises(httpx.ReadTimeout):
            db_pool.read_with_retry(read)
        self.assertEqual(read.call_count, 2)
