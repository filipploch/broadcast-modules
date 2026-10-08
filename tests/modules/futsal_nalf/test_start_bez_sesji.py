"""Start panelu bez otwartej sesji (zadne mecz nie jest wybrany): zapytanie o dane poczatkowe nie moze konczyc sie wyjatkiem."""
import unittest
import harness

APP, TMP = harness.boot("futsal_nalf")


class StartBezSesji(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)

    def test_request_initial_data_bez_meczu_nie_rzuca_wyjatku(self):
        from core.extensions import socketio
        client = socketio.test_client(APP)
        try:
            client.emit('request_initial_data')         # wyjatek w handlerze przerwalby test
        finally:
            client.disconnect()


if __name__ == "__main__":
    unittest.main()
