"""E2c: pasek w panelu przy braku pluginu i stan nakladki po starcie OBS (wspolna tresc: tests/modules/pasek_pluginow.py)."""
import unittest
import harness
import pasek_pluginow

APP, TMP = harness.boot("garbarnia")


class PasekPluginow(pasek_pluginow.make(APP)):
    pass


if __name__ == "__main__":
    unittest.main()
