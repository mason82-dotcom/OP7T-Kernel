import importlib.util
import tempfile
import unittest
from pathlib import Path

script = Path(__file__).resolve().parents[1] / "scripts" / "verify-config.py"
spec = importlib.util.spec_from_file_location("verify_config", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigTests(unittest.TestCase):
    def test_missing_symbol_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, frag = Path(tmp) / "config", Path(tmp) / "fragment"
            config.write_text("CONFIG_FOO=y\n")
            frag.write_text("CONFIG_FOO=y\nCONFIG_BAR=y\n")
            self.assertIn("CONFIG_BAR", module.verify(config, [frag], False)[0])

    def test_disabled_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, frag = Path(tmp) / "config", Path(tmp) / "fragment"
            config.write_text("CONFIG_FOO=y\n# CONFIG_BAR is not set\n")
            frag.write_text("CONFIG_FOO=y\n# CONFIG_BAR is not set\n")
            self.assertEqual([], module.verify(config, [frag], False))

    def test_board_signature_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config"
            config.write_text("CONFIG_USB_GADGET=y\nCONFIG_USB_CONFIGFS=y\nCONFIG_USB_CONFIGFS_F_HID=y\nCONFIG_QCA_CLD_WLAN=m\n# CONFIG_MODULE_SIG_FORCE is not set\n")
            self.assertTrue(any("CONFIG_MODULE_SIG_FORCE" in e for e in module.verify(config, [], True)))


if __name__ == "__main__":
    unittest.main()
