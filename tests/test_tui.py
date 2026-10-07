import io
import unittest
from rich.console import Console
from mockdeck.tui import print_startup_banner, log_request

class TestTUI(unittest.TestCase):
    def setUp(self):
        self.string_io = io.StringIO()
        self.console = Console(file=self.string_io, force_terminal=True, color_system="standard")

    def test_print_startup_banner(self):
        resources = {"users": 3, "posts": 5}
        print_startup_banner(
            host="127.0.0.1",
            port=8000,
            resources=resources,
            delay=150,
            chaos=0.1,
            read_only=False,
            console=self.console,
        )
        output = self.string_io.getvalue()
        self.assertIn("mockdeck", output)
        self.assertIn("127.0.0.1:8000", output)
        self.assertIn("users", output)
        self.assertIn("posts", output)
        self.assertIn("150ms", output)
        self.assertIn("10%", output)

    def test_log_request(self):
        log_request("GET", "/users?role=admin", 200, 14.5, "127.0.0.1", console=self.console)
        log_request("POST", "/users", 201, 23.1, "127.0.0.1", console=self.console)
        log_request("GET", "/unknown", 404, 2.0, "127.0.0.1", console=self.console)
        log_request("GET", "/error", 500, 1.2, "127.0.0.1", console=self.console)

        output = self.string_io.getvalue()
        self.assertIn("GET", output)
        self.assertIn("/users?role=admin", output)
        self.assertIn("200", output)
        self.assertIn("POST", output)
        self.assertIn("201", output)
        self.assertIn("404", output)
        self.assertIn("500", output)

if __name__ == "__main__":
    unittest.main()
