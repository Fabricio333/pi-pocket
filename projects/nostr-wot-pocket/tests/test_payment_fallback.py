import unittest
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from pocket.apps.pay21 import App, invoice_error
from pocket.ui import UI

class PaymentFallbackTests(unittest.TestCase):
    def test_server_errors_are_not_reported_as_wifi_errors(self):
        self.assertEqual(invoice_error(HTTPError('https://example.com',502,'Bad Gateway',{},None)), 'Invoice server HTTP 502')
        self.assertEqual(invoice_error(URLError('DNS failed')), 'Network request failed')
        self.assertEqual(invoice_error(ValueError('Invalid invoice')), 'Invoice request rejected')

    def test_address_qr_works_without_network_and_does_not_become_invoice(self):
        ctx=SimpleNamespace(ui=UI(),invoice=None)
        app=App(ctx)
        app.event('invoice-error','Invoice server HTTP 502')
        self.assertEqual(app.render().size,(240,240))
        with patch('qrcode.QRCode.add_data', autospec=True) as add:
            app.handle({'up'})
            add.assert_called_once_with(unittest.mock.ANY,'lightning:avidflower48@walletofsatoshi.com')
        self.assertEqual(app.page,'address')
        self.assertIsNone(ctx.invoice)
        self.assertIsNone(app.qr)
        self.assertEqual(app.render().size,(240,240))
        self.assertEqual(app.render().getpixel((0,0)),(255,255,255))
        self.assertTrue(app.back())
        self.assertEqual(app.page,'intro')

    def test_retry_remains_available(self):
        app=App(SimpleNamespace(ui=UI(),invoice=None))
        app.event('invoice-error','Invoice server HTTP 502')
        with patch.object(app,'request') as request:
            app.handle({'ok'})
            request.assert_called_once_with()

    def test_invoice_qr_uses_the_entire_display_without_header(self):
        import qrcode
        from PIL import Image
        from unittest.mock import patch
        app=App(SimpleNamespace(ui=UI(),invoice=None))
        invoice='LNBC210N1'+'A'*450
        app.current_address='avidflower48@walletofsatoshi.com'
        with patch.object(app.ctx.ui,'text') as text:
            app.make_qr(invoice)
            text.assert_not_called()
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=1,border=4)
        qr.add_data(invoice.upper());qr.make(fit=True)
        expected=qr.make_image(fill_color='black',back_color='white').convert('RGB').resize((240,240),Image.Resampling.NEAREST)
        self.assertEqual(app.render().tobytes(),expected.tobytes())
