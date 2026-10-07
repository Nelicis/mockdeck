import unittest

class TestSmoke(unittest.TestCase):
    def test_import_mockdeck(self):
        import mockdeck
        self.assertEqual(mockdeck.__version__, "0.1.0")

if __name__ == "__main__":
    unittest.main()
