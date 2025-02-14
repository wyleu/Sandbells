from django.test import TestCase

# Create your tests here.

class SimpleTestCase(TestCase):
    def test_one_plus_one(self):
        print("hllo")
        self.assertEquals(1 + 1 ,2)