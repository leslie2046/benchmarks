from contextlib import redirect_stdout
from io import StringIO
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cli import perf_audio, perf_dify, perf_embedding, perf_reranker
from shared.report_writer import percentile


class CliSafetyTests(unittest.TestCase):
    def test_reranker_default_provider_exists(self):
        with patch("sys.argv", ["perf_reranker"]):
            args = perf_reranker.parse_args()
        self.assertIn(args.provider, perf_reranker.RERANK_PROVIDERS)

    def test_clis_share_the_report_percentile_definition(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        for module in (perf_audio, perf_dify, perf_embedding, perf_reranker):
            self.assertIs(module.percentile, percentile)

    def test_embedding_and_reranker_disable_redirects(self):
        response = SimpleNamespace(status_code=200, text="")
        for module, args, config in (
            (perf_embedding, SimpleNamespace(provider="siliconflow", concurrency=1, requests=1, timeout=1, input_file=None, json_report=None), ("https://example.test/embeddings", "embed", None)),
            (perf_reranker, SimpleNamespace(provider="siliconflow", concurrency=1, requests=1, timeout=1, input_file=None, json_report=None, proxy=None, batch_size=0), ("https://example.test/rerank", "rank", None)),
        ):
            session = MagicMock()
            session.post.return_value = response
            with self.subTest(module=module.__name__), patch.object(module, "resolve_config", return_value=config), patch.object(module, "get_session", return_value=session):
                with redirect_stdout(StringIO()):
                    module.benchmark(args)
            self.assertFalse(session.post.call_args.kwargs["allow_redirects"])

    def test_all_failed_runs_do_not_calculate_latency_statistics(self):
        response = SimpleNamespace(status_code=500, text="failed")
        for module, args, config in (
            (perf_embedding, SimpleNamespace(provider="siliconflow", concurrency=1, requests=1, timeout=1, input_file=None, json_report=None), ("https://example.test/embeddings", "embed", None)),
            (perf_reranker, SimpleNamespace(provider="siliconflow", concurrency=1, requests=1, timeout=1, input_file=None, json_report=None, proxy=None, batch_size=0), ("https://example.test/rerank", "rank", None)),
        ):
            session = MagicMock()
            session.post.return_value = response
            output = StringIO()
            with self.subTest(module=module.__name__), patch.object(module, "resolve_config", return_value=config), patch.object(module, "get_session", return_value=session), redirect_stdout(output):
                module.benchmark(args)
            self.assertIn("Success      : 0/1", output.getvalue())
            self.assertIn("QPS          : 0.00", output.getvalue())
            self.assertNotIn("Average      :", output.getvalue())

    def test_audio_and_dify_disable_redirects(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "sample.wav"
            audio_path.write_bytes(b"audio")
            args = SimpleNamespace(provider="vllm", base_url="https://example.test/audio", model="asr", audio_duration=1, concurrency=1, requests=1, proxy=None, timeout=1, json_report=None)
            session = MagicMock()
            session.post.return_value = SimpleNamespace(status_code=200, text="")
            with patch.object(perf_audio, "get_session", return_value=session), patch.dict("os.environ", {}, clear=True), redirect_stdout(StringIO()):
                perf_audio.benchmark(args, audio_path)
            self.assertFalse(session.post.call_args.kwargs["allow_redirects"])

            session.post.return_value = SimpleNamespace(status_code=500, text="failed")
            output = StringIO()
            with patch.object(perf_audio, "get_session", return_value=session), patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
                perf_audio.benchmark(args, audio_path)
            self.assertIn("Success      : 0/1", output.getvalue())
            self.assertIn("QPS          : 0.00", output.getvalue())
            self.assertNotIn("Average      :", output.getvalue())

        response = MagicMock()
        response.__enter__.return_value = response
        response.raise_for_status.return_value = None
        session = MagicMock()
        session.__enter__.return_value = session
        session.post.return_value = response
        args = SimpleNamespace(api="retrieve", timeout=1, verify_ssl=True)
        with patch.object(perf_dify.requests, "Session", return_value=session):
            result = perf_dify.run_once(args, "https://example.test/retrieve", {}, "query")
        self.assertTrue(result["ok"])
        self.assertFalse(session.post.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
