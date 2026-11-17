import unittest
from pocket import led_protocol as led

class LedProtocolTests(unittest.TestCase):
    def test_verified_whole_strip_packets(self):
        self.assertEqual(led.color().hex(),'bc0406000003e8000055')
        self.assertEqual(led.brightness(100).hex(),'bc050600640000000055')
        self.assertEqual(led.power(True).hex(),'bc01010155')
        self.assertEqual(led.power(False).hex(),'bc01010055')

    def test_direction_is_not_power_and_effects_are_explicit(self):
        self.assertEqual(led.effect('red-running').hex(),'bc0602005455')
        self.assertEqual(led.effect('red-tailing').hex(),'bc0602004d55')
        self.assertEqual(led.direction(False).hex(),'bc07010055')
        self.assertNotEqual(led.direction(False),led.power(False))
        with self.assertRaises(KeyError):led.effect('guess-an-opcode')

    def test_count_is_bounded_configuration_not_a_pixel_selector(self):
        self.assertEqual(led.count_probe(8).hex(),'bc0302000855')
        self.assertEqual(led.count_probe(300).hex(),'bc0302012c55')
        for number in [1,0,301]:
            with self.assertRaises(ValueError):led.count_probe(number)

if __name__=='__main__':unittest.main()
