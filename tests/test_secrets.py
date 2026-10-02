import tempfile
import unittest
from pathlib import Path

from backend.secrets import SecretBox


class SecretBoxTests(unittest.TestCase):
    def test_encrypts_and_decrypts_without_storing_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            box = SecretBox.from_data_dir(Path(directory))
            encrypted = box.encrypt("top-secret")
            self.assertNotIn("top-secret", encrypted)
            self.assertEqual(box.decrypt(encrypted), "top-secret")

    def test_generated_key_is_stable_for_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            encrypted = SecretBox.from_data_dir(path).encrypt("stable")
            self.assertEqual(SecretBox.from_data_dir(path).decrypt(encrypted), "stable")


if __name__ == "__main__":
    unittest.main()
