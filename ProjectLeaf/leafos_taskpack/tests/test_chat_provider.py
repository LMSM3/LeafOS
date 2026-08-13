import importlib.util
import json
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("leaf_chat", ROOT / "core" / "ui" / "chat.py")
leaf_chat = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(leaf_chat)


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


class ChatProviderTests(unittest.TestCase):
    def test_llamacpp_chat_stream_uses_openai_endpoint_and_real_sse_content(self):
        response = FakeResponse(
            [
                b'data: {"choices":[{"delta":{"reasoning_content":"hidden","content":"hello "},"finish_reason":null}]}\n',
                b'data: {"choices":[{"delta":{"content":"world"},"finish_reason":null}]}\n',
                b'data: [DONE]\n',
            ]
        )
        private_sizes = []
        with mock.patch.object(leaf_chat.urllib.request, "urlopen", return_value=response) as urlopen:
            chunks = list(leaf_chat._stream_from_llama_server(
                "http://127.0.0.1:8080", "hi", 4096, mock.Mock(),
                private_reasoning_listener=private_sizes.append,
            ))

        self.assertEqual(["hello ", "world"], chunks)
        self.assertEqual([6], private_sizes)
        request = urlopen.call_args.args[0]
        self.assertEqual("http://127.0.0.1:8080/v1/chat/completions", request.full_url)
        payload = json.loads(request.data)
        self.assertEqual([{"role": "user", "content": "hi"}], payload["messages"])
        self.assertTrue(payload["stream"])

    def test_empty_llamacpp_stream_fails_instead_of_generating_fallback_text(self):
        response = FakeResponse([b'data: [DONE]\n'])
        with mock.patch.object(leaf_chat.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "no chat content"):
                list(leaf_chat._stream_from_llama_server("http://127.0.0.1:8080", "hi", 4096, mock.Mock()))


if __name__ == "__main__":
    unittest.main()
