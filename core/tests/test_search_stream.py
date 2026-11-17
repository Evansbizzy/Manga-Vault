import json
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from rest_framework.test import APIClient


class SearchStreamEndpointTests(TestCase):
    @override_settings(DEBUG=True)
    def test_stream_emits_source_events_then_a_completion_event(self):
        result = {
            'source_status': {
                'source': 'fixture', 'label': 'Fixture', 'status': 'ok',
                'count': 1, 'duration_ms': 8, 'cached': True,
            },
            'results': [{
                'source': 'fixture', 'title': 'Example', 'cover': '',
                'source_id': 'example-id',
            }],
        }
        client = APIClient()
        with patch('api.views.search_all_progressively', return_value=iter([result])):
            response = client.get('/api/search/stream/?q=Example')
            body = b''.join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'].split(';')[0], 'application/x-ndjson')
        events = [json.loads(line) for line in body.splitlines()]
        self.assertEqual(events[0]['source_status']['duration_ms'], 8)
        self.assertTrue(events[-1]['done'])

