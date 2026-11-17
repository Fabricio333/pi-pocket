import unittest
from unittest.mock import patch
from PIL import ImageColor
from pocket.brand import ACCENT, CARD, DOMAIN, logo
from pocket.ui import UI

class BrandingTests(unittest.TestCase):
    def test_brand_header_and_logo_fit_device_screen(self):
        ui=UI()
        self.assertEqual(logo(25).size,(25,25))
        self.assertEqual(logo().mode,'RGBA')
        with patch.object(ui,'text',wraps=ui.text) as draw:
            frame,_=ui.base('Doorbell','Ready to ring')
        self.assertEqual(frame.size,(240,240))
        labels=[call.args[2] for call in draw.call_args_list]
        self.assertIn(DOMAIN,labels)
        self.assertNotIn('NOSTR WOT',labels)

    def test_startup_progress_stays_within_display_and_reaches_ready(self):
        ui=UI()
        empty=ui.startup(-1)
        full=ui.startup(2,'Ready')
        self.assertEqual(empty.size,(240,240))
        self.assertEqual(full.getpixel((120,214)),ImageColor.getrgb(ACCENT))
        self.assertEqual(empty.getpixel((120,214)),ImageColor.getrgb(CARD))
        self.assertNotEqual(empty.tobytes(),full.tobytes())
