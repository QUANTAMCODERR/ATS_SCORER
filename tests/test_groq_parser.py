import unittest
from unittest.mock import Mock

from backend.core.config import GROQ_MODEL
from backend.services.groq_parser import _call_groq


class GroqModelConfigurationTests(unittest.TestCase):
    def test_uses_configured_supported_model(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content='{}'))
        ]

        result = _call_groq(client, 'system', 'user')

        self.assertEqual(result, '{}')
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs['model'],
            GROQ_MODEL,
        )


if __name__ == '__main__':
    unittest.main()
